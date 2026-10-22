"""Operational immutable PBP intake; descriptive events, never a forecast.

Capture is separate from decision-time derivation so a caller freezes its cutoff
AFTER source receipt. No research artifact is promoted or source fetched on read.
"""
from dataclasses import dataclass
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
from io import StringIO
from pathlib import Path
import re
from uuid import UUID

import pandas as pd

from ..services.source_capture import verify_snapshot_artifact
from .factual_designation import clock
from .market_snapshots import canonical_team
from .opportunity_events import build_event_evidence, validate_event_evidence

VERSION = 'operational_opportunity_source_v1'
DATASET = 'play_by_play'
LICENSE = 'nflverse public play-by-play via installed nflreadpy; retain source attribution and revision limits'


@dataclass(frozen=True)
class SourceLimits:
    max_rows: int = 200_000
    max_bytes: int = 256 * 1024 * 1024


def _limits(limits):
    value = limits or SourceLimits()
    if type(value.max_rows) is not int or type(value.max_bytes) is not int or min(value.max_rows,value.max_bytes) < 1:
        raise ValueError('Source bounds must be positive integers')
    return value


def capture_opportunity_source(service, *, season, week, slate, slate_lock_at,
                               nfl_module=None, limits=None):
    """Fetch one provider season and register its entire immutable source table.

    Service is the existing SourceCaptureService (caller owns its transaction).
    No period/team/player/user filter precedes raw capture. This call does not
    create count forecasts, resolve aliases or mutate existing snapshots.
    """
    limits = _limits(limits)
    if type(season) is not int or type(week) is not int or not 2000 <= season <= 2100 or not 1 <= week <= 18:
        raise ValueError('Explicit regular-season forecast scope required')
    lock = clock(slate_lock_at)
    if not slate or lock is None:
        raise ValueError('Source capture requires slate and lock')
    if nfl_module is None:
        import nflreadpy as nfl_module
    frame = nfl_module.load_pbp(seasons=[season])
    if not isinstance(frame,pd.DataFrame):
        if not hasattr(frame,'write_csv') or not hasattr(frame,'columns'):
            raise ValueError('PBP loader returned no supported tabular source')
        if not 1 <= len(frame) <= limits.max_rows:
            raise ValueError('PBP source empty or exceeds row bound')
        text=frame.write_csv()
        if not isinstance(text,str) or len(text.encode('utf-8'))>limits.max_bytes:
            raise ValueError('PBP source exceeds byte bound')
        # Polars' native CSV path avoids adding a pyarrow conversion dependency.
        frame=pd.read_csv(StringIO(text),low_memory=False,dtype={k:'string' for k in frame.columns if k.endswith('_id')})
    if not 1 <= len(frame) <= limits.max_rows:
        raise ValueError('PBP source empty or exceeds row bound')
    payload = frame.to_csv(index=False,lineterminator='\n').encode('utf-8')
    if len(payload) > limits.max_bytes:
        raise ValueError('PBP source exceeds byte bound')
    capture = service.capture_dataframe(frame,artifact_name=f'nflreadpy_pbp_{season}.csv',
        source_system='nflreadpy',dataset=DATASET,season=season,week=week,slate=slate,
        source_license=LICENSE,source_uri=f'nflreadpy://pbp/{season}',slate_lock_at=lock,
        observation_basis='capture_clock',metadata=dict(contract_id=VERSION,
            loader='load_pbp',nflreadpy_version=str(getattr(nfl_module,'__version__','unknown')),
            provider_rows=len(frame),provider_scope='full_returned_provider_season_before_eligibility_filter',
            provider_csv_sha256=hashlib.sha256(payload).hexdigest(),publication_clock_available=False,
            original_historical_pregame_availability='unverified_revised_provider_capture',
            provider_remote_freshness='unverified; installed loader may return cache-backed data'))
    verify_snapshot_artifact(capture.snapshot)
    if capture.snapshot.content_sha256 != hashlib.sha256(payload).hexdigest():
        raise ValueError('Captured PBP bytes differ from provider serialization')
    if capture.pre_lock is not True:
        raise ValueError('PBP capture is not verified pre-lock')
    return capture


def derive_opportunity_event_evidence(snapshot, *, canonical_ids, before_period,
                                      cutoff, official_components=(), limits=None):
    """Verify stored source, derive prior-only events; never fetch on this path.

    Canonical map keys are native GSIS IDs, never display names. Missing aliases
    remain in event review requests. Caller persists those requests through its
    existing review queue before claiming identity completion.
    """
    limits = _limits(limits); decision = clock(cutoff)
    if type(before_period) is not int or not 1 <= before_period % 100 <= 18:
        raise ValueError('Forecast period must be season*100+regular week')
    if snapshot.source_system != 'nflreadpy' or snapshot.dataset != DATASET:
        raise ValueError('Not an operational PBP source snapshot')
    if snapshot.season != before_period//100 or snapshot.week != before_period%100:
        raise ValueError('Snapshot forecast scope differs from decision scope')
    metadata=snapshot.metadata_json or {}
    if (snapshot.media_type != 'text/csv' or snapshot.source_uri != f'nflreadpy://pbp/{snapshot.season}'
            or metadata.get('contract_id') != VERSION or metadata.get('loader') != 'load_pbp'):
        raise ValueError('PBP source format/provider contract missing')
    path=Path(snapshot.artifact_path)
    if snapshot.byte_count > limits.max_bytes or path.stat().st_size > limits.max_bytes:
        raise ValueError('Stored PBP source exceeds byte bound')
    verify_snapshot_artifact(snapshot)
    observed=clock(snapshot.observed_at);captured=clock(snapshot.captured_at)
    if observed > captured or captured > decision:
        raise ValueError('PBP source unavailable at decision cutoff')
    if not snapshot.slate_lock_at or decision >= clock(snapshot.slate_lock_at):
        raise ValueError('Operational PBP decision must precede slate lock')
    ids={}
    for native,pid in canonical_ids.items():
        if not re.fullmatch(r'00-\d{7}',str(native)) or str(UUID(str(pid))) != pid:
            raise ValueError('Identity map requires native GSIS IDs and canonical UUID spelling')
        ids[str(native)]=pid
    header=pd.read_csv(path,nrows=0)
    native_columns={k:'string' for k in header.columns if k.endswith('_id')}
    frame=pd.read_csv(path,low_memory=False,nrows=limits.max_rows+1,dtype=native_columns)
    if len(frame)>limits.max_rows:
        raise ValueError('Stored PBP source exceeds row bound')
    required={'game_id','play_id','season','week','season_type','posteam'}
    if not required <= set(frame):
        raise ValueError('PBP source lacks required native event scope')
    seasons=pd.to_numeric(frame.season,errors='coerce');weeks=pd.to_numeric(frame.week,errors='coerce')
    if seasons.isna().any() or weeks.isna().any() or not seasons.eq(snapshot.season).all() or not weeks.between(0,22).all() or not weeks.eq(weeks.astype(int)).all():
        raise ValueError('PBP source has malformed or conflicting period scope')
    if (frame.season_type.eq('REG') & ~weeks.between(1,18)).any():
        raise ValueError('Regular-season PBP has invalid week')
    prior=seasons*100+weeks < before_period
    regular=frame.season_type.eq('REG') & weeks.le(18)
    eligible=frame.loc[prior & regular].copy()
    # Explicit provider control records are not offensive opportunities, whether
    # or not a possession team happens to be attached. END GAME does not prove
    # that every preceding source play was captured.
    administrative=pd.Series(False,index=eligible.index)
    if {'play_type','pass_attempt','rush_attempt','sack'} <= set(eligible):
        marker=(eligible['desc'].isin(['GAME','END GAME']) if 'desc' in eligible else pd.Series(False,index=eligible.index))
        if 'quarter_end' in eligible:
            marker=marker | eligible.quarter_end.eq(1)
        indicators=['pass_attempt','rush_attempt','sack','qb_dropback','qb_scramble','qb_spike','qb_kneel','two_point_attempt']
        quiet=eligible[[key for key in indicators if key in eligible]]
        administrative=eligible.play_type.isna() & marker & (quiet.isna() | quiet.eq(0)).all(axis=1)
    missing=eligible.posteam.isna()
    nonoff=eligible.play_type.isin(['kickoff','extra_point','field_goal','punt','no_play']) if 'play_type' in eligible else pd.Series(False,index=eligible.index)
    if (missing & ~(nonoff | administrative)).any():
        raise ValueError('Offensive PBP event lacks team scope')
    def records(part):
        return part.astype(object).where(pd.notna(part),None).to_dict('records')
    unscoped_nonoffense=records(eligible.loc[missing])
    scoped_controls=records(eligible.loc[administrative & ~missing])
    rows=records(eligible.loc[~missing & ~administrative])
    # nflverse play IDs are integral identifiers; 1 and 1.0 denote the same
    # native event. Keep the original lexical representation alongside them.
    seen_native=set();team_transforms={}
    for row in rows+unscoped_nonoffense+scoped_controls:
        game=re.fullmatch(r'(\d{4})_(\d{2})_([A-Z]{2,3})_([A-Z]{2,3})',str(row.get('game_id') or ''))
        if not game or int(game[1])!=int(row['season']) or int(game[2])!=int(row['week']):
            raise ValueError('PBP native game identity conflicts with event season/week')
        pair={canonical_team(game[3]),canonical_team(game[4])}
        if len(pair)!=2:
            raise ValueError('Native game requires distinct NFL teams')
        original_teams={key:row.get(key) for key in ('posteam','defteam')}
        for key,native_team in original_teams.items():
            if native_team is not None:
                resolved=canonical_team(str(native_team))
                if resolved not in pair:
                    raise ValueError('PBP team contradicts native game team pair')
                row[key]=resolved;team_transforms[str(native_team)]=resolved
        if row.get('posteam') is not None and row.get('posteam')==row.get('defteam'):
            raise ValueError('PBP offense and defense team conflict')
        row['source_native_team_fields']=original_teams
        try:
            play=Decimal(str(row['play_id']))
            if not play.is_finite() or play!=play.to_integral_value():
                raise ValueError('PBP play ID is not an integral native key')
        except InvalidOperation as exc:
            raise ValueError('Invalid native PBP play ID') from exc
        row['source_play_id_lexical']=row['play_id']
        row['play_id']=str(int(play))
        native=(row['game_id'],row['play_id'])
        if native in seen_native:
            raise ValueError('Duplicate native play event in immutable source')
        seen_native.add(native)
    components=deepcopy(list(official_components))
    for item in components:
        if not item.get('source_id') or not item.get('imported_at') or clock(item['imported_at'])>decision:
            raise ValueError('Official reconciliation component lacks available source receipt')
        game=re.fullmatch(r'(\d{4})_(\d{2})_([A-Z]{2,3})_([A-Z]{2,3})',str(item.get('game_id') or ''))
        if (not game or int(game[1])!=snapshot.season or not 1<=int(game[2])<=18
                or int(game[1])*100+int(game[2])>=before_period
                or item.get('season_type')!='REG'):
            raise ValueError('Official reconciliation native game is not prior regular-season scope')
        for key,expected in (('season',int(game[1])),('week',int(game[2]))):
            if item.get(key) is not None and float(item[key])!=expected:
                raise ValueError('Official reconciliation supplied period conflicts with native game')
        item['source_native_team']=item.get('team')
        item['team']=canonical_team(str(item.get('team') or ''))
        if item['team'] not in {canonical_team(game[3]),canonical_team(game[4])}:
            raise ValueError('Official reconciliation team conflicts with native game')
    source=dict(snapshot_id=str(snapshot.snapshot_id),content_sha256=snapshot.content_sha256,
        captured_at=captured.isoformat(),received_at=captured.isoformat(),
        received_at_basis='persisted_snapshot_capture_clock; no separate provider receipt column',
        observed_at=observed.isoformat(),effective_at=clock(snapshot.effective_at).isoformat() if snapshot.effective_at else None,
        source_uri=snapshot.source_uri,artifact_path=str(path),manifest_path=str(snapshot.manifest_path),
        verification='snapshot_artifact_sha256_verified',publication_clock_available=False,
        scope_exclusions=dict(unscoped_nonoffense=len(unscoped_nonoffense),scoped_administrative_controls=len(scoped_controls)),
        team_transform=dict(function='market_snapshots.canonical_team (Database.dst.normalize_team aliases)',
            native_to_canonical=dict(sorted(team_transforms.items())),original_fields='each event raw_flags.source_native_team_fields; immutable CSV unchanged'),
        remote_freshness='unverified; installed loader may return cache-backed data',
        game_completion='unverified',full_game_coverage='unverified; row eligibility is not whole-game source coverage',
        historical_availability='revised_capture; original historical pregame availability unverified')
    receipt=build_event_evidence(rows,canonical_ids=ids,source_receipt=source,cutoff=cutoff,official_components=components)
    receipt=validate_event_evidence(receipt,before_period=before_period,cutoff=cutoff)
    return dict(version=VERSION,status='identity_review_pending' if receipt['identity_review_requests'] else 'verified_partial_descriptive_events',
        game_completion='unverified; no independent schedule/final or full-game reconciliation proof supplied',
        full_game_coverage='unverified; observed play rows cannot establish a complete official game',
        unscoped_nonoffensive_rows=unscoped_nonoffense,scoped_administrative_rows=scoped_controls,
        snapshot_id=str(snapshot.snapshot_id),before_period=before_period,decision_cutoff_at=decision.isoformat(),
        source_rows=len(frame),selected_prior_regular_rows=int((prior & regular).sum()),derived_scoped_event_rows=len(rows),
        excluded_rows=dict(not_prior_period=int((~prior).sum()),not_regular_season=int((~regular).sum()),
            union_excluded=int((~(prior & regular)).sum())),
        event_evidence=receipt,identity_review_requests=receipt['identity_review_requests'],
        forecast=None,effect='Descriptive source/event evidence only; no FP or count-forecast adjustment',
        limitation='Current-season source derivation only. Capture/receipt precedes current decision; it does not prove original historical information availability')


ARTIFACT_CONTRACT = 'opportunity_event_artifact_v1'
SCALAR_CONTRACT = 'opportunity_scalar_view_v1'
ARTIFACT_DIRECTORY = Path(__file__).resolve().parents[3]/'artifacts/opportunity_events'
SCALAR_DEFINITIONS = {
    'counts': 'Observed official-stat pass attempts/rush attempts/targets; linked views, never additive offense budgets',
    'zones': 'Preplay yardline outside20/six_to_twenty/inside5/unknown partitions counted lower bounds',
    'goal_to_go': 'Overlapping goal-to-go lower-bound counts; missing flags remain unknown',
    'coverage': 'Event eligibility coverage, not independent proof of a complete official game',
    'residual': 'Full-team counted lower bound minus attached actors; unallocated, never transferred',
}


@dataclass(frozen=True)
class ArtifactLimits:
    max_compressed_bytes: int = 128*1024*1024
    max_expanded_bytes: int = 512*1024*1024


def _artifact_limits(limits):
    value=limits or ArtifactLimits()
    if any(type(v) is not int or v<1 for v in (value.max_compressed_bytes,value.max_expanded_bytes)):
        raise ValueError('Artifact bounds must be positive integers')
    return value


def _json_bytes(value):
    import json
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')


def _hash(value):
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _verify_artifact_input(receipt,snapshot,*,before_period,cutoff):
    verify_snapshot_artifact(snapshot)
    if receipt.get('version')!=VERSION or receipt.get('before_period')!=before_period:
        raise ValueError('Derived artifact scope/contract mismatch')
    metadata=snapshot.metadata_json or {}
    if (snapshot.source_system!='nflreadpy' or snapshot.dataset!=DATASET or snapshot.media_type!='text/csv'
            or metadata.get('contract_id')!=VERSION or metadata.get('loader')!='load_pbp'
            or snapshot.source_uri!=f'nflreadpy://pbp/{snapshot.season}'):
        raise ValueError('Derived artifact raw source/provider contract mismatch')
    if snapshot.season*100+snapshot.week!=before_period:
        raise ValueError('Raw snapshot and derived forecast period differ')
    inner=validate_event_evidence(receipt['event_evidence'],before_period=before_period,cutoff=cutoff)
    source=inner['source']
    if (str(snapshot.snapshot_id)!=source.get('snapshot_id')
            or snapshot.content_sha256!=source.get('content_sha256')
            or snapshot.source_uri!=source.get('source_uri')
            or clock(snapshot.captured_at)!=clock(source.get('captured_at'))
            or clock(snapshot.observed_at)!=clock(source.get('observed_at'))
            or clock(snapshot.effective_at)!=clock(source.get('effective_at'))
            or clock(snapshot.captured_at)!=clock(source.get('received_at'))):
        raise ValueError('Derived receipt differs from actual raw source snapshot')
    if (clock(receipt['decision_cutoff_at'])!=clock(inner['decision_cutoff_at'])
            or receipt.get('source_rows')!=snapshot.row_count
            or receipt.get('derived_scoped_event_rows')!=len(inner['events'])
            or receipt.get('selected_prior_regular_rows')!=len(inner['events'])+len(receipt.get('unscoped_nonoffensive_rows',[]))+len(receipt.get('scoped_administrative_rows',[]))):
        raise ValueError('Derived artifact count/clock scope differs')
    if not snapshot.slate_lock_at or clock(cutoff)>=clock(snapshot.slate_lock_at):
        raise ValueError('Derived artifact intake must precede lock')
    return inner


def semantic_event_view(receipt,*,teams=None,actor_ids=None):
    """Thin measured facts; attachment filters never alter team denominators.

    The semantic hash covers the selected teams' entire source population before
    actor attachment filtering, including genuine prior-row revisions. Whole
    source/current-period bytes and envelope clocks remain provenance only.
    """
    inner=validate_event_evidence(receipt['event_evidence'],before_period=receipt['before_period'],cutoff=receipt['decision_cutoff_at'])
    chosen=None if teams is None else {canonical_team(str(t)) for t in teams}
    attached=None
    if actor_ids is not None:
        attached=set()
        for pid in actor_ids:
            if str(UUID(str(pid)))!=pid:
                raise ValueError('Actor attachment requires canonical UUID spelling')
            attached.add(pid)
    def relevant(row):
        if chosen is None:
            return True
        flags=row.get('raw_flags',row)
        if flags.get('posteam') in chosen or flags.get('defteam') in chosen or row.get('team') in chosen:
            return True
        game=re.fullmatch(r'\d{4}_\d{2}_([A-Z]{2,3})_([A-Z]{2,3})',str(row.get('game_id') or ''))
        return bool(game and {canonical_team(game[1]),canonical_team(game[2])} & chosen)
    def semantic_row(row):
        # The canonical integral play ID is substantive; lexical 1 versus1.0 is
        # original serialization lineage, already retained in the full artifact.
        if isinstance(row,dict):
            return {k:semantic_row(v) for k,v in row.items() if k!='source_play_id_lexical'}
        if isinstance(row,list):
            return [semantic_row(v) for v in row]
        return row
    team_rows=sorted([deepcopy(r) for r in inner['teams'] if chosen is None or r['team'] in chosen],key=lambda r:(r['game_id'],r['team'],_hash(r)))
    all_players=sorted([deepcopy(r) for r in inner['players'] if chosen is None or r['team'] in chosen],key=lambda r:(r['game_id'],r['team'],str(r['source_player_id']),str(r['player_master_id']),_hash(r)))
    events=sorted([semantic_row(r) for r in inner['events'] if relevant(r)],key=lambda r:(r['game_id'],int(r['play_id']),_hash(r)))
    controls=sorted([semantic_row(r) for group in ('unscoped_nonoffensive_rows','scoped_administrative_rows') for r in receipt.get(group,[]) if relevant(r)],key=lambda r:(r['game_id'],int(r['play_id']),_hash(r)))
    requests=sorted([deepcopy(r) for r in inner['identity_review_requests'] if relevant(r)],key=_hash)
    reconciliation=[{k:deepcopy(v) for k,v in r.items() if k not in {'official_imported_at','official_source_id'}} for r in inner['official_reconciliation'] if relevant(r)]
    reconciliation.sort(key=_hash)
    coverage={status:sum(e['status']==status for e in events) for status in ('counted','partial','unknown','excluded','not_applicable')}
    quality=dict(game_completion=receipt['game_completion'],full_game_coverage=receipt['full_game_coverage'],
        remote_freshness=inner['source']['remote_freshness'],historical_availability=inner['source']['historical_availability'],
        reconciliation_trust='Caller-supplied independent component receipt; not verified complete-game proof',
        identity_review_requests=requests,coverage=coverage)
    semantics=dict(contract_id=SCALAR_CONTRACT,event_contract_id=inner['version'],definitions=SCALAR_DEFINITIONS,
        before_period=receipt['before_period'],teams=sorted(chosen) if chosen is not None else None,
        source_uri=inner['source']['source_uri'],team_rows=team_rows,player_rows=all_players,quality=quality,
        prior_event_semantics_sha256=_hash(dict(events=events,controls=controls)),reconciliation=reconciliation)
    players=[r for r in all_players if attached is None or r['player_master_id'] in attached]
    residuals=[]
    for team in team_rows:
        matches=[p for p in players if (p['game_id'],p['team'])==(team['game_id'],team['team'])]
        values={channel:team['counted_lower_bound'][channel]-sum(p['counted_lower_bound'][channel] for p in matches)
                for channel in ('pass_attempts','rush_attempts','targets')}
        if any(v<0 for v in values.values()):
            raise ValueError('Actor attachment exceeds full-source team budget')
        residuals.append(dict(game_id=team['game_id'],team=team['team'],unallocated_counted_lower_bound=values,
            scope='Other/unmapped actors; not a forecast, not redistributed; missing team eligibility remains unknown'))
    return dict(contract_id=SCALAR_CONTRACT,semantic_measurements_sha256=_hash(semantics),
        semantic_hash_scope='Selected teams full-source population BEFORE actor attachment filtering; original prior-row semantics included',
        before_period=receipt['before_period'],definitions=deepcopy(SCALAR_DEFINITIONS),team_rows=team_rows,actor_rows=players,
        actor_attachment_residuals=residuals,unobserved_requested_actor_ids=sorted((attached or set())-{p['player_master_id'] for p in players}),
        quality=quality,forecast=None,effect='Descriptive measured evidence; no FP/count-forecast bonus',
        provenance=dict(source=deepcopy(inner['source']),event_receipt_sha256=inner['sha256'],
            decision_cutoff_at=receipt['decision_cutoff_at'],official_reconciliation=deepcopy(inner['official_reconciliation'])))


def _artifact_ref(envelope,compressed,logical,path):
    receipt=envelope['receipt'];inner=receipt['event_evidence'];source=inner['source']
    return dict(contract_id=ARTIFACT_CONTRACT,path=str(path),artifact_sha256=hashlib.sha256(compressed).hexdigest(),
        logical_sha256=hashlib.sha256(logical).hexdigest(),compressed_bytes=len(compressed),expanded_bytes=len(logical),
        source_snapshot_id=source['snapshot_id'],source_sha256=source['content_sha256'],
        event_receipt_sha256=inner['sha256'],before_period=receipt['before_period'],
        decision_cutoff_at=receipt['decision_cutoff_at'],source_captured_at=source['captured_at'],
        definition_ids=dict(source=VERSION,events=inner['version'],scalar=SCALAR_CONTRACT),
        semantic_measurements_sha256=semantic_event_view(receipt)['semantic_measurements_sha256'])


def freeze_event_artifact(receipt,snapshot,*,directory=None,limits=None):
    """Persist one immutable derived artifact; never embed raw flags in a handoff."""
    import gzip
    from ..services.source_capture import _write_new_bytes
    limits=_artifact_limits(limits)
    _verify_artifact_input(receipt,snapshot,before_period=receipt['before_period'],cutoff=receipt['decision_cutoff_at'])
    envelope=dict(contract_id=ARTIFACT_CONTRACT,receipt=receipt)
    logical=_json_bytes(envelope)
    if len(logical)>limits.max_expanded_bytes:
        raise ValueError('Derived artifact exceeds expanded byte bound')
    compressed=gzip.compress(logical,compresslevel=6,mtime=0)
    if len(compressed)>limits.max_compressed_bytes:
        raise ValueError('Derived artifact exceeds compressed byte bound')
    root=Path(directory or ARTIFACT_DIRECTORY).resolve()
    path=root/(hashlib.sha256(compressed).hexdigest()+'.json.gz')
    if path.exists() and path.resolve().parent!=root:
        raise ValueError('Derived artifact path escapes managed root')
    _write_new_bytes(path,compressed)
    return _artifact_ref(envelope,compressed,logical,path)


def load_event_artifact(ref,snapshot,*,before_period,cutoff,directory=None,limits=None):
    """Bounded byte/content checks plus actual indexed raw snapshot verification."""
    import gzip
    import json
    from io import BytesIO
    limits=_artifact_limits(limits);root=Path(directory or ARTIFACT_DIRECTORY).resolve()
    sha=ref.get('artifact_sha256','')
    if not re.fullmatch('[0-9a-f]{64}',str(sha)):
        raise ValueError('Invalid derived artifact identity')
    path=root/(sha+'.json.gz')
    if path.resolve().parent!=root or str(path)!=ref.get('path'):
        raise ValueError('Derived artifact path must be SHA-addressed inside managed root')
    if path.stat().st_size>limits.max_compressed_bytes:
        raise ValueError('Derived artifact exceeds compressed byte bound')
    compressed=path.read_bytes()
    if hashlib.sha256(compressed).hexdigest()!=sha:
        raise ValueError('Derived artifact compressed byte hash mismatch')
    try:
        with gzip.GzipFile(fileobj=BytesIO(compressed)) as stream:
            logical=stream.read(limits.max_expanded_bytes+1)
    except (OSError,EOFError) as exc:
        raise ValueError('Derived artifact encoding invalid') from exc
    if len(logical)>limits.max_expanded_bytes:
        raise ValueError('Derived artifact exceeds expanded byte bound')
    try:
        envelope=json.loads(logical)
    except (ValueError,UnicodeError) as exc:
        raise ValueError('Derived artifact encoding invalid') from exc
    if not isinstance(envelope,dict) or envelope.get('contract_id')!=ARTIFACT_CONTRACT:
        raise ValueError('Unknown derived artifact contract')
    receipt=envelope['receipt']
    _verify_artifact_input(receipt,snapshot,before_period=before_period,cutoff=cutoff)
    if ref!=_artifact_ref(envelope,compressed,logical,path):
        raise ValueError('Derived artifact reference differs from frozen contents')
    return receipt


SCALAR_ARTIFACT_CONTRACT = 'opportunity_scalar_artifact_v1'
SCALAR_DIRECTORY = ARTIFACT_DIRECTORY/'scalar'


def _scalar_ref(envelope,payload,path):
    view=envelope['view'];parent=envelope['parent_artifact_ref']
    return dict(contract_id=SCALAR_ARTIFACT_CONTRACT,path=str(path),sha256=hashlib.sha256(payload).hexdigest(),
        byte_count=len(payload),before_period=view['before_period'],teams=envelope['teams'],actor_ids=envelope['actor_ids'],
        source_snapshot_id=parent['source_snapshot_id'],source_sha256=parent['source_sha256'],
        parent_artifact_sha256=parent['artifact_sha256'],parent_global_semantic_measurements_sha256=parent['semantic_measurements_sha256'],
        selected_semantic_measurements_sha256=view['semantic_measurements_sha256'],
        view_material_sha256=_hash(view),published_at=envelope['publisher']['published_at'])


def freeze_scalar_artifact(parent_ref,snapshot,*,before_period,cutoff,teams=None,actor_ids=None,
                           directory=None,parent_directory=None,max_view_bytes=4*1024*1024,producer_clock=None):
    """Verify full parent ONCE, publish computed scalar facts; no caller payload."""
    from datetime import datetime,timezone
    from ..services.source_capture import _write_new_bytes
    if type(max_view_bytes) is not int or max_view_bytes<1:
        raise ValueError('Scalar artifact byte bound must be positive')
    receipt=load_event_artifact(parent_ref,snapshot,before_period=before_period,cutoff=cutoff,directory=parent_directory)
    team_scope=None if teams is None else sorted({canonical_team(str(t)) for t in teams})
    actors=None if actor_ids is None else sorted(set(actor_ids))
    view=semantic_event_view(receipt,teams=team_scope,actor_ids=actors)
    published=clock((producer_clock or (lambda:datetime.now(timezone.utc)))())
    if published<clock(parent_ref['decision_cutoff_at']):
        raise ValueError('Scalar publication cannot precede original parent derivation')
    envelope=dict(contract_id=SCALAR_ARTIFACT_CONTRACT,parent_artifact_ref=deepcopy(parent_ref),view=view,
        teams=team_scope,actor_ids=actors,publisher=dict(contract_id=SCALAR_ARTIFACT_CONTRACT,
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),published_at=published.isoformat(),
            validation='Full parent and indexed raw snapshot verified before computing scalar view'))
    payload=_json_bytes(envelope)
    if len(payload)>max_view_bytes:
        raise ValueError('Scalar artifact exceeds byte bound')
    root=Path(directory or SCALAR_DIRECTORY).resolve();path=root/(hashlib.sha256(payload).hexdigest()+'.json')
    if path.exists() and path.resolve().parent!=root:
        raise ValueError('Scalar artifact path escapes managed root')
    _write_new_bytes(path,payload)
    return _scalar_ref(envelope,payload,path)


def load_scalar_artifact(ref,snapshot,*,before_period,cutoff,directory=None,parent_directory=None,
                         max_view_bytes=4*1024*1024,parent_limits=None):
    """Bounded serving read: scalar JSON, parent compressed hash, actual raw hash.

    Full parent semantics were verified by the scalar publisher. This path does
    not decompress the large event artifact or fetch a source.
    """
    import json
    if type(max_view_bytes) is not int or max_view_bytes<1:
        raise ValueError('Scalar artifact byte bound must be positive')
    root=Path(directory or SCALAR_DIRECTORY).resolve();sha=ref.get('sha256','')
    if not re.fullmatch('[0-9a-f]{64}',str(sha)):
        raise ValueError('Invalid scalar artifact identity')
    path=root/(sha+'.json')
    if path.resolve().parent!=root or ref.get('path')!=str(path):
        raise ValueError('Scalar artifact must be inside managed root')
    if path.stat().st_size>max_view_bytes:
        raise ValueError('Scalar artifact exceeds byte bound')
    payload=path.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=sha:
        raise ValueError('Scalar artifact byte hash mismatch')
    envelope=json.loads(payload)
    if not isinstance(envelope,dict) or envelope.get('contract_id')!=SCALAR_ARTIFACT_CONTRACT:
        raise ValueError('Unknown scalar artifact contract')
    if ref!=_scalar_ref(envelope,payload,path):
        raise ValueError('Scalar artifact reference differs from contents')
    view=envelope['view'];parent=envelope['parent_artifact_ref'];source=view['provenance']['source']
    if (view.get('contract_id')!=SCALAR_CONTRACT or parent.get('contract_id')!=ARTIFACT_CONTRACT
            or envelope.get('publisher',{}).get('contract_id')!=SCALAR_ARTIFACT_CONTRACT
            or not re.fullmatch('[0-9a-f]{64}',str(envelope['publisher'].get('code_sha256','')))):
        raise ValueError('Scalar producer/view/parent contract mismatch')
    if envelope['teams'] is not None and any(r['team'] not in envelope['teams'] for r in view['team_rows']+view['actor_rows']):
        raise ValueError('Scalar team attachment scope differs')
    if envelope['actor_ids'] is not None and any(r['player_master_id'] not in envelope['actor_ids'] for r in view['actor_rows']):
        raise ValueError('Scalar actor attachment scope differs')
    verify_snapshot_artifact(snapshot)
    metadata=snapshot.metadata_json or {};decision=clock(cutoff)
    if (snapshot.source_system!='nflreadpy' or snapshot.dataset!=DATASET or snapshot.media_type!='text/csv'
            or metadata.get('contract_id')!=VERSION or metadata.get('loader')!='load_pbp'
            or snapshot.source_uri!=f'nflreadpy://pbp/{snapshot.season}'
            or snapshot.season*100+snapshot.week!=before_period or view['before_period']!=before_period
            or parent['before_period']!=before_period):
        raise ValueError('Scalar/raw source provider or period mismatch')
    if (source['snapshot_id']!=str(snapshot.snapshot_id) or source['content_sha256']!=snapshot.content_sha256
            or parent['source_snapshot_id']!=str(snapshot.snapshot_id) or parent['source_sha256']!=snapshot.content_sha256
            or source['source_uri']!=snapshot.source_uri
            or clock(source['captured_at'])!=clock(snapshot.captured_at)
            or clock(parent['source_captured_at'])!=clock(snapshot.captured_at)
            or clock(source['observed_at'])!=clock(snapshot.observed_at)
            or clock(source.get('effective_at'))!=clock(snapshot.effective_at)
            or clock(source['received_at'])!=clock(snapshot.captured_at)
            or view['provenance']['event_receipt_sha256']!=parent['event_receipt_sha256']
            or clock(view['provenance']['decision_cutoff_at'])!=clock(parent['decision_cutoff_at'])):
        raise ValueError('Scalar facts differ from actual frozen parent/raw source')
    if (clock(snapshot.captured_at)>decision or clock(parent['decision_cutoff_at'])>decision
            or clock(envelope['publisher']['published_at'])>decision
            or clock(envelope['publisher']['published_at'])<clock(parent['decision_cutoff_at'])
            or not snapshot.slate_lock_at or decision>=clock(snapshot.slate_lock_at)):
        raise ValueError('Scalar artifact publication/source unavailable at pre-lock cutoff')
    # The immutable scalar file binds the exact verified parent reference. Hash
    # unchanged compressed bytes instead of inflating147MB on each Prepare.
    limits=_artifact_limits(parent_limits);parent_root=Path(parent_directory or ARTIFACT_DIRECTORY).resolve()
    parent_sha=parent['artifact_sha256']
    if not re.fullmatch('[0-9a-f]{64}',str(parent_sha)):
        raise ValueError('Invalid scalar parent identity')
    parent_path=parent_root/(parent_sha+'.json.gz')
    if parent_path.resolve().parent!=parent_root or str(parent_path)!=parent['path']:
        raise ValueError('Scalar parent must be inside managed root')
    if parent_path.stat().st_size>limits.max_compressed_bytes or parent_path.stat().st_size!=parent['compressed_bytes']:
        raise ValueError('Scalar parent compressed byte bound/size mismatch')
    digest=hashlib.sha256()
    with parent_path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    if digest.hexdigest()!=parent_sha:
        raise ValueError('Scalar parent compressed byte hash mismatch')
    return view
