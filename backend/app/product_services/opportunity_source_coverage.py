"""Observed full-source identity coverage and unassigned opportunity accounting."""
from collections import defaultdict
from copy import deepcopy
from uuid import UUID
import math
from .evaluation_record import digest
from .market_snapshots import canonical_team
from .player_opportunity_components import VERSION as SOURCE_VERSION

VERSION='opportunity_source_coverage_v1'
CHANNELS={'pass_attempts':'official_pass_attempts','rush_attempts':'official_rush_attempts','targets':'targets'}


def count(value):
    if type(value) not in (int,float) or not math.isfinite(value) or value<0 or value!=int(value):raise ValueError('Known nonnegative integer source count required')
    return int(value)


def build_opportunity_source_coverage(source,*,before_period):
    if type(before_period) is not int or not 200001<=before_period or not 1<=before_period%100<=18:raise ValueError('Explicit REG source boundary required')
    if source.get('version')!=SOURCE_VERSION or source.get('before_period')!=before_period or source.get('pregame_serving_eligible') is not False:
        raise ValueError('Matched descriptive full-source component required')
    budgets={};actors=defaultdict(list);canonical_natives={};seen=set()
    def scope(row):
        gid=row['game_id'];team=canonical_team(row['team']);parts=gid.split('_')
        if len(parts)!=4 or not parts[0].isdigit() or not parts[1].isdigit() or not 1<=int(parts[1])<=18 or int(parts[0])*100+int(parts[1])>=before_period or team not in {canonical_team(p) for p in parts[2:]}:raise ValueError('Prior native source game/team required')
        return gid,team
    for row in source['team_denominators']:
        key=scope(row)
        if key in budgets:raise ValueError('Duplicate full-team budget')
        official=row['official']
        if official is None or scope(official)!=key:raise ValueError('Matched official full-team budget required')
        budgets[key]=official
    for row in source['actor_game_rows']:
        key=scope(row);native=row['source_player_id'];pid=row['player_master_id']
        if key not in budgets or not native or (*key,native) in seen:raise ValueError('Unique native actor/fullteam scope required')
        seen.add((*key,native))
        if pid is not None:
            if str(UUID(pid))!=pid:raise ValueError('Canonical UUID spelling required')
            old=canonical_natives.setdefault((key[0],pid),(key[1],native))
            if old!=(key[1],native):raise ValueError('Canonical native/team collision')
        actors[key].append(row)
    rows=[]
    for key,team in sorted(budgets.items()):
        metrics={}
        for ch,name in CHANNELS.items():
            lower=count(team['counted_lower_bound'][ch]);unknown=count(team['unknown_eligibility_events'][ch]);total=team['counts'][ch]
            if total!=(None if unknown else lower):raise ValueError('Official exact/unknown budget partition differs')
            attributed=canonical_mass=0;native_actors=[];canonical_actors=[];potential=[]
            for actor in actors[key]:
                m=actor['metrics'].get(name)
                if m is None:continue
                n=count(m['observed_outcome_sum']) if m['observed_outcome_sum'] is not None else 0
                eligible=count(m['eligible_events']);known=count(m['known_outcome_events']);missing=count(m['unknown_outcome_events']);unknown_actor=count(m['unknown_eligibility_events'])
                if known+missing!=eligible or n!=known:raise ValueError('Unit opportunity count/known event partition differs')
                if unknown_actor:potential.append(actor['source_player_id'])
                attributed+=n
                if n:
                    native_actors.append(actor['source_player_id'])
                    if actor['player_master_id'] is not None:canonical_mass+=n;canonical_actors.append(actor['player_master_id'])
            if attributed>lower:raise ValueError('Actor source count exceeds conserved team budget')
            residual=lower-attributed;full_actor_count=len(native_actors) if not(residual or unknown) else None
            metrics[ch]=dict(
                X08_M01=dict(known_native_actors=len(native_actors),known_canonical_actors=len(canonical_actors),exact_full_source_native_actor_count=full_actor_count,
                    canonical_actor_fraction_among_known_native=len(canonical_actors)/len(native_actors) if native_actors else None,
                    exact_canonical_actor_fraction=len(canonical_actors)/full_actor_count if full_actor_count else None,
                    exact_native_attributed_opportunity_fraction=attributed/total if total else None,
                    exact_canonical_attached_opportunity_fraction=canonical_mass/total if total else None,
                    known_native_actor_ids=sorted(native_actors),known_canonical_actor_ids=sorted(canonical_actors),potential_native_actors_with_unknown_eligibility=sorted(potential)),
                X08_M02=dict(known_team_opportunity_lower_bound=lower,exact_team_opportunities=total,known_native_attributed_opportunities=attributed,
                    known_canonical_attached_opportunities=canonical_mass,known_unattributed_opportunity_lower_bound=residual,
                    exact_unattributed_opportunities=residual if not unknown else None,
                    known_unattached_canonical_opportunity_lower_bound=lower-canonical_mass,
                    unknown_eligibility_events=unknown,unknown_extra_opportunity_quantity=None if unknown else 0,
                    residual_is_allocated=False))
        rows.append(dict(game_id=key[0],team=key[1],metrics=metrics))
    facts=dict(version=VERSION,before_period=before_period,catalog_ids=['X08-M01','X08-M02'],game_rows=rows,
        definitions=dict(X08_M01='Observed per-channel full-source native actor and canonical attachment coverage; complete actor denominator only when no attribution/eligibility gap',
                         X08_M02='Observed team count lower bound minus known native actor counts; unknown eligibility quantity remains unknown, never donated'))
    return facts|dict(semantic_sha256=digest(facts),provenance=deepcopy(source['provenance']),source_component_semantic_sha256=source['semantic_measurements_sha256'],
        identity_review_requests=deepcopy(source['identity_review_requests']),pregame_serving_eligible=False,evidence_use='postlock_descriptive_not_pregame_or_serving',forecast=None,model_consumed=False,optimizer_consumed=False,
        limitations=['Coverage is within observed native source logs, not independently certified complete-game/NFL actor census',
            'Known-native canonical fraction is separate from full-source actor coverage; unknown native actors mask full actor denominator',
            'Unknown eligibility events do not establish the number or ownership of additional physical opportunities',
            'Unmapped native actors retain their known counts; residuals are diagnostics and never automatic replacement allocation or positive features'])


def load_reviewed_player_component(ref,snapshot,*,cutoff):
    from pathlib import Path
    from datetime import datetime,UTC
    import json,hashlib
    from .factual_designation import clock
    from backend.app.services.source_capture import verify_snapshot_artifact
    verify_snapshot_artifact(snapshot)
    if snapshot.source_system!='nflreadpy' or snapshot.dataset!='play_by_play' or snapshot.media_type!='text/csv':raise ValueError('Authenticated native PBP snapshot required')
    decision=clock(cutoff)
    if decision is None or decision>datetime.now(UTC):raise ValueError('Actual nonfuture reader cutoff required')
    root=Path('artifacts/player_opportunity_components').resolve();p=Path(ref['path']).resolve()
    if p.parent!=root or p.name!=ref['sha256']+'.json' or p.stat().st_size!=ref['bytes'] or not 0<p.stat().st_size<=8*1024*1024:raise ValueError('Managed player component reference required')
    raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Player component byte checksum differs')
    value=json.loads(raw)
    if value.get('version')!=SOURCE_VERSION or value.get('before_period')!=ref.get('before_period',value.get('before_period')):raise ValueError('Declared component version/scope differs')
    source=value['provenance']['source'];retro=value['provenance']['retrospective_read'];parent=retro['parent_artifact_ref']
    if str(snapshot.snapshot_id)!=source['snapshot_id'] or snapshot.content_sha256!=source['content_sha256'] or parent['source_snapshot_id']!=source['snapshot_id'] or parent['source_sha256']!=source['content_sha256'] or parent['event_receipt_sha256']!=value['provenance']['event_receipt_sha256']:raise ValueError('Native source/parent/component pairing differs')
    clocks=[clock(retro.get(k)) for k in ('original_evidence_boundary_at','source_lock_at','actual_read_at','actual_derived_at')]
    if any(c is None for c in clocks) or not clocks[0]<clocks[1]<=clocks[2]<=clocks[3]<=decision:raise ValueError('Original/actual component clocks differ')
    if clock(snapshot.captured_at) is None or clock(snapshot.captured_at)>clocks[0] or clock(snapshot.slate_lock_at)!=clocks[1]:raise ValueError('Frozen source original availability/lock pairing differs')
    parent_path=Path(parent['path']).resolve()
    if parent_path.parent!=Path('artifacts/opportunity_events').resolve() or parent_path.name!=parent['artifact_sha256']+'.json.gz' or parent_path.stat().st_size!=parent['compressed_bytes']:raise ValueError('Managed immutable event parent required')
    with parent_path.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=parent['artifact_sha256']:raise ValueError('Compressed parent bytes differ')
    if value.get('evidence_use')!='postlock_descriptive_not_pregame_or_serving' or value.get('pregame_serving_eligible') is not False:raise ValueError('Explicit retrospective nonserving component required')
    return value


def require_feature_use(value,*,purpose):
    if value.get('version')!=VERSION or purpose!='offline_descriptive' or value.get('pregame_serving_eligible') is not False:raise ValueError('Source coverage diagnostics cannot serve models/forecasts/optimizer')
    return value
