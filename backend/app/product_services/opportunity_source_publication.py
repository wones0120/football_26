"""Server-owned, append-only publication of verified prior-game measurements.

Only managed artifact identities enter the API. Facts come from immutable source
bytes, never request JSON; publication does not alter a forecast or raw snapshot.
"""
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from ..models import SourceSnapshot
from ..services.source_capture import SnapshotIntegrityError
from .evaluation_record import append_record, digest
from .factual_designation import clock
from .market_snapshots import canonical_team
from .opportunity_source_capture import SCALAR_DIRECTORY, _scalar_ref, load_scalar_artifact

KIND = 'opportunity_source_publication'
CONTRACT = 'prepared_opportunity_source_v1'
CONTEXT_DIRECTORY = Path('artifacts/opportunity_context')


class SourcePublicationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_snapshot_id: UUID
    scalar_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    defense_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    environment_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    idempotency_key: str = Field(min_length=1, max_length=200)


def _managed_json(root, sha, *, max_bytes):
    if not re.fullmatch(r'[0-9a-f]{64}', str(sha)):
        raise ValueError('Invalid managed opportunity artifact identity')
    root = Path(root).resolve(); path = root / (sha + '.json')
    if path.resolve().parent != root or path.stat().st_size > max_bytes:
        raise ValueError('Managed opportunity artifact path or size invalid')
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != sha:
        raise ValueError('Managed opportunity artifact byte hash mismatch')
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError('Managed opportunity artifact must contain an object')
    return value, payload, path


def _context(sha, *, kind, snapshot, scalar, cutoff, directory):
    if sha is None:
        return None
    value, payload, path = _managed_json(directory, sha, max_bytes=2*1024*1024)
    if value.get('version') != kind + '_context_evidence_v1' or value.get('forecast') is not None:
        raise ValueError('Opportunity context is not its declared descriptive producer')
    material = {k:v for k,v in value.items() if k not in {'provenance','selected_semantic_measurements_sha256'}}
    if digest(material) != value.get('selected_semantic_measurements_sha256'):
        raise ValueError('Opportunity context semantic hash mismatch')
    provenance = value['provenance']; original = provenance['original']
    parent = provenance.get('parent_artifact_ref') or original['artifact_publication']['parent_artifact_ref']
    if parent != scalar['parent_artifact_ref']:
        raise ValueError('Opportunity context belongs to another verified event parent')
    source = original['source']
    if (str(source.get('snapshot_id')) != str(snapshot.snapshot_id)
            or source.get('content_sha256') != snapshot.content_sha256
            or original['event_receipt_sha256'] != parent['event_receipt_sha256']
            or value.get('before_period') != scalar['view']['before_period']
            or set(value.get('teams',[])) != set(scalar['teams'] or [])):
        raise ValueError('Opportunity context source/period/team scope mismatch')
    publication = provenance['artifact_publication']
    if not (clock(parent['decision_cutoff_at']) <= clock(publication['decision_cutoff_at'])
            <= clock(publication['published_at']) <= clock(cutoff)):
        raise ValueError('Opportunity context unavailable at decision cutoff')
    module = __import__(f'backend.app.product_services.{kind}_context_evidence', fromlist=['VERSION'])
    if original.get('producer_code_sha256') != hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest():
        raise ValueError('Opportunity context producer code bytes differ; explicit republish required')
    # Verify the small full-source context and exact team slice. This is not a
    # re-run of the147MB event derivation and never changes its source universe.
    full_ref=provenance['full_context_ref']
    full, raw, full_path=_managed_json(directory,full_ref['sha256'],max_bytes=2*1024*1024)
    if str(full_path)!=full_ref['path'] or len(raw)!=full_ref['bytes']:
        raise ValueError('Full-source context reference differs')
    team_key='defense_team' if kind=='defense' else 'team'
    selected=set(value['teams'])
    for field in ('game_rows','team_windows'):
        expected=[r for r in full[field] if r[team_key] in selected]
        if value[field]!=expected:
            raise ValueError('Selected opportunity context differs from full-source measurements')
    return dict(facts=material, semantic_measurements_sha256=digest(material),
        provenance=dict(artifact_sha256=sha, path=str(path), byte_count=len(payload), **deepcopy(provenance)))


def verified_material(session, request, *, cutoff, scalar_directory=None, context_directory=None,
                      parent_directory=None):
    """No fetch or fit; verify actual indexed source and managed derived bytes."""
    snapshot=session.get(SourceSnapshot,str(request.source_snapshot_id))
    if snapshot is None:
        raise ValueError('Indexed opportunity source snapshot unavailable')
    scalar, payload, path=_managed_json(scalar_directory or SCALAR_DIRECTORY, request.scalar_sha256, max_bytes=4*1024*1024)
    ref=_scalar_ref(scalar,payload,path)
    period=snapshot.season*100+snapshot.week
    view=load_scalar_artifact(ref,snapshot,before_period=period,cutoff=cutoff,
        directory=scalar_directory,parent_directory=parent_directory)
    contexts={kind:_context(getattr(request,kind+'_sha256'),kind=kind,snapshot=snapshot,
        scalar=scalar,cutoff=cutoff,directory=context_directory or CONTEXT_DIRECTORY) for kind in ('defense','environment')}
    facts=dict(contract_id=CONTRACT,before_period=period,teams=scalar['teams'],attachment_actor_ids=scalar['actor_ids'],
        opportunity={k:deepcopy(v) for k,v in view.items() if k!='provenance'},
        contexts={k:v['facts'] for k,v in contexts.items() if v is not None},
        definition='Observed prior REG game measurements; not expected counts, healthy status, full-game completion proof or calibrated game probabilities')
    return dict(contract_id=CONTRACT,status='available_descriptive',before_period=period,
        teams=scalar['teams'],actor_ids=scalar['actor_ids'],facts=facts,
        semantic_measurements_sha256=digest(facts),
        provenance=dict(source_snapshot_id=str(snapshot.snapshot_id),source_sha256=snapshot.content_sha256,
            source_captured_at=clock(snapshot.captured_at).isoformat(),scalar_ref=ref,
            source=deepcopy(view['provenance']),contexts={k:v['provenance'] for k,v in contexts.items() if v is not None}),
        forecast=None,numeric_forecast_consumption='unconsumed_until_versioned_forecast_producer_accepts_this_feature_contract')


def publish(session, request, *, now=None, **directories):
    now=clock(now or datetime.now(UTC))
    material=verified_material(session,request,cutoff=now,**directories)
    keys={k:v for k,v in request.model_dump(mode='json').items() if k!='idempotency_key'}
    rows=session.execute(text("SELECT record_id,record_json FROM target.evaluation_record WHERE kind=:kind AND record_json->'payload'->>'idempotency_key'=:key"),
        dict(kind=KIND,key=request.idempotency_key)).mappings().all()
    if rows:
        row=rows[0]; envelope=row['record_json']
        if row['record_id']!='evaluation-'+digest(envelope):
            raise ValueError('Opportunity source publication record hash mismatch')
        old=envelope['payload']
        if old['material']['semantic_measurements_sha256']!=material['semantic_measurements_sha256']:
            raise ValueError('Opportunity source publication idempotency key has different content')
        return dict(record_id=row['record_id'],**old,reused=True)
    value=dict(contract_id=CONTRACT,idempotency_key=request.idempotency_key,request=keys,
        published_at=now.isoformat(),material=material)
    record_id=append_record(session,KIND,value,source=dict(operation='publish_verified_opportunity_source',source_snapshot_id=str(request.source_snapshot_id)))
    return dict(record_id=record_id,**value,reused=False)


def prepared_context(session, *, season, week, teams, actor_ids, cutoff, **directories):
    """Discover only indexed publications, never files by mtime/client reference."""
    period=season*100+week; desired={canonical_team(t) for t in teams}; actors={str(UUID(str(p))) for p in actor_ids}
    rows=session.execute(text("SELECT record_id,record_json FROM target.evaluation_record WHERE kind=:kind ORDER BY recorded_at DESC,record_id DESC LIMIT 100"),dict(kind=KIND)).mappings().all()
    stale=False
    for row in rows:
        envelope=row['record_json']; value=envelope.get('payload',{}); stored=value.get('material',{})
        if clock(value.get('published_at')) is None or clock(value['published_at'])>clock(cutoff):continue
        if not desired.issubset(set(stored.get('teams') or [])):continue
        if stored.get('before_period')!=period:
            stale=True;continue
        if row['record_id']!='evaluation-'+digest(envelope):
            return dict(contract_id=CONTRACT,status='integrity_failed',reason='publication_record_hash_mismatch',forecast=None)
        try:
            material=verified_material(session,SourcePublicationRequest(**value['request'],idempotency_key=value['idempotency_key']),cutoff=cutoff,**directories)
            if material!=stored:raise ValueError('Frozen source publication material changed')
        except (ValueError,OSError,KeyError,SnapshotIntegrityError) as exc:
            return dict(contract_id=CONTRACT,status='integrity_failed',reason=str(exc),forecast=None)
        missing=sorted(actors-set(material.get('actor_ids') or [])) if material.get('actor_ids') is not None else []
        material.update(publication_record_id=row['record_id'],published_at=value['published_at'],
            missing_canonical_attachment_ids=missing,requested_teams=sorted(desired),
            attachment_status='refresh_required_for_missing_actors' if missing else 'full_requested_canonical_universe',
            missing_actor_meaning='No observed source row is not zero opportunity; K/DST offensive measures are inapplicable, and absent offensive actors retain unknown history.')
        return material
    return dict(contract_id=CONTRACT,status='stale_period' if stale else 'unavailable',before_period=period,
        requested_teams=sorted(desired),reason='No verified indexed publication for this prior-period/team scope',forecast=None)


def semantic_game_context(context, *, teams, actor_ids):
    """Numeric game dependencies once, separate from retrieval/reference clocks."""
    context=context or {}; chosen={canonical_team(t) for t in teams}; actors=set(actor_ids)
    if context.get('status')!='available_descriptive':
        return {k:deepcopy(context.get(k)) for k in ('contract_id','status','before_period','reason')}
    facts=context['facts'];op=facts['opportunity']
    measured={k:deepcopy(op.get(k)) for k in ('contract_id','before_period','definitions','forecast','effect')}
    for field in ('team_rows','actor_rows','actor_attachment_residuals'):
        measured[field]=[deepcopy(r) for r in op.get(field,[]) if r['team'] in chosen]
    measured['unobserved_requested_actor_ids']=sorted(set(op.get('unobserved_requested_actor_ids',[]))&actors)
    measured['quality']={k:deepcopy(v) for k,v in op.get('quality',{}).items() if k not in {'coverage','identity_review_requests'}}
    contexts={}
    for kind,block in facts.get('contexts',{}).items():
        key='defense_team' if kind=='defense' else 'team'
        out={k:deepcopy(block[k]) for k in ('version','before_period','definitions','units','source_quality','last_n_observed_games','full_game_coverage') if k in block}
        out.update(teams=sorted(chosen),**{field:[deepcopy(r) for r in block[field] if r[key] in chosen] for field in ('game_rows','team_windows')})
        contexts[kind]=out
    return dict(contract_id=CONTRACT,status='available_descriptive',before_period=context['before_period'],teams=sorted(chosen),
        opportunity=measured,contexts=contexts,attachment_actor_ids=sorted(set(facts.get('attachment_actor_ids') or [])&actors),
        missing_canonical_attachment_ids=sorted(set(context.get('missing_canonical_attachment_ids') or [])&actors),forecast=None)
