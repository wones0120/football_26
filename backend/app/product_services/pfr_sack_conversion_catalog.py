"""PFR passer-source sack/pressure conversion; no rounded-rate denominator inference."""
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from uuid import UUID
import hashlib
import json
import math
from .evaluation_record import digest
from .factual_designation import clock
from .market_snapshots import canonical_team
from .pfr_source_components import asset_scope,validate_pfr_frame,BASE
from .schedule_context_features import load_schedule_context

VERSION='pfr_sack_conversion_catalog_v1'


def _count(value):
    if value is None or isinstance(value,bool):return None
    try:value=float(value)
    except (TypeError,ValueError):return None
    return int(value) if math.isfinite(value) and value>=0 and value.is_integer() else None


def _scope(row,before_period):
    season,week=_count(row.get('season')),_count(row.get('week'));gid=row.get('game_id');parts=str(gid).split('_')
    if (season is None or week is None or not 1<=week<=18 or row.get('game_type')!='REG'
            or season*100+week>=before_period or len(parts)!=4 or parts[:2]!=[str(season),f'{week:02d}']):raise ValueError('Prior native REG game/period required')
    offense=canonical_team(row.get('team'));pair={canonical_team(x) for x in parts[2:]}
    if len(pair)!=2 or offense not in pair:raise ValueError('Native PFR passer team conflicts with game')
    defense=next(t for t in pair if t!=offense)
    if row.get('opponent') and canonical_team(row['opponent'])!=defense:raise ValueError('Native opponent conflicts with game')
    return gid,season,week,offense,defense


def build_pfr_sack_conversion(records,canonical_rows,source_proof,schedule,*,before_period):
    if type(before_period)is not int or before_period<200001 or not 1<=before_period%100<=18:raise ValueError('Prior REG target required')
    proof={r['snapshot_id']:r for r in source_proof}
    if len(proof)!=len(source_proof) or len({r['season'] for r in source_proof})!=len(source_proof) or not proof:raise ValueError('Unique verified passer-source receipts required')
    seasons={r['season'] for r in source_proof};canonical={};canonical_games={}
    for row in canonical_rows:
        if 'G13-M03' not in row['metrics']:continue
        key=(row['game_id'],canonical_team(row['team']),row['pfr_player_id'])
        if key in canonical:raise ValueError('Duplicate canonical native passer receipt')
        pid=row['player_master_id']
        if pid is not None:
            if str(UUID(pid))!=pid:raise ValueError('Canonical UUID spelling required')
            k=(key[0],pid)
            if k in canonical_games and canonical_games[k]!=key:raise ValueError('Conflicting canonical native passer attachment')
            canonical_games[k]=key
        canonical[key]=row
    expected={}
    for game in schedule['game_rows']:
        if game['game_type']!='REG' or game['season'] not in seasons or game['season']*100+game['week']>=before_period:continue
        gid=game['game_id'];home=canonical_team(game['home_team']);away=canonical_team(game['away_team'])
        for defense,offense in ((home,away),(away,home)):
            key=(gid,defense)
            if key in expected:raise ValueError('Ambiguous native expected defense game')
            expected[key]=dict(game_id=gid,season=game['season'],week=game['week'],defense_team=defense,offense_team=offense)
    groups=defaultdict(list);seen=set()
    for raw in records:
        gid,season,week,offense,defense=_scope(raw,before_period);native=raw.get('pfr_player_id');sid=raw.get('_source_snapshot_id')
        if not isinstance(native,str) or not native or sid not in proof or proof[sid]['season']!=season:
            raise ValueError('Preserved native passer/source scope required')
        key=(gid,offense,native)
        if key in seen:raise ValueError('Duplicate native passer/game source')
        seen.add(key);attachment=canonical.get(key)
        if attachment is None:raise ValueError('Missing reviewed native passer identity receipt; do not guess or drop')
        if not any(r['snapshot_id']==sid and r['stat_type']=='pass' for r in attachment['source_refs']):
            raise ValueError('Canonical passer receipt belongs to different native source')
        pressure=_count(raw.get('times_pressured'));sacks=_count(raw.get('times_sacked'))
        if pressure is not None and sacks is not None and sacks>pressure:raise ValueError('Sacks cannot exceed provider pressure exposure')
        if pressure!=attachment['metrics']['G13-M03']['pressure_count']:raise ValueError('Provider pressure count contradicts reviewed source receipt')
        if (gid,defense) not in expected:raise ValueError('Native passer game absent from expected schedule')
        groups[(gid,defense)].append(dict(pfr_player_id=native,player_master_id=attachment['player_master_id'],
            times_pressured=pressure,times_sacked=sacks,source_snapshot_id=sid,native_row=raw['_native_row']))
    rows=[]
    for key,game in sorted(expected.items()):
        members=sorted(groups.get(key,[]),key=lambda r:r['pfr_player_id']);unknown=sum(r['times_pressured']is None or r['times_sacked']is None for r in members)
        p=sum(r['times_pressured'] or 0 for r in members);s=sum(r['times_sacked'] or 0 for r in members)
        rows.append(dict(**game,metrics={'G14-M03':dict(value=s/p if members and not unknown and p else None,
            unit='provider_sacks_per_reported_pressured_passer_play',known_sack_lower_bound=s,
            known_pressure_lower_bound=p,source_passer_rows=len(members),unknown_count_rows=unknown,
            exact_sack_count=s if members and not unknown else None,exact_pressure_count=p if members and not unknown else None,
            source_game_status='observed_PFR_passer_cohort' if members else 'missing_native_passer_source_unknown_not_zero')},
            native_passers=members,canonical_unknown_passers=sum(r['player_master_id']is None for r in members)))
    semantic=[{**r,'native_passers':[{k:v for k,v in p.items() if k not in {'source_snapshot_id','native_row'}} for p in r['native_passers']]} for r in rows]
    basis=dict(version=VERSION,before_period=before_period,definition='Native PFR times_sacked / times_pressured, pooled across all retained opposing passers on identical game/team/source scope; no mean of individual fractions',game_rows=semantic,
        covered_source_seasons=sorted(seasons),G14_M01_source_gap='Weekly PFR lacks pass_attempts/scrambles/dropbacks; no denominator recovered from rounded pressure fraction or annual source')
    return basis|dict(game_rows=rows,semantic_sha256=digest(basis),
        provenance=dict(source_proof=deepcopy(source_proof),schedule=deepcopy(schedule['provenance'])),
        evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,
        limitations=['Observed retained PFR passer cohort; completeness versus every official NFL passing play is not independently certified',
            'Missing scheduled game-side source remains unknown, never a zero-pressure game',
            'No defender pressure votes, annual-to-week copying, rounded-percent denominator inversion or protection causality',
            'Provider pressure taxonomy includes sack plays; source count, not a newly invented pressure label',
            'Unknown canonical passer stays native and contributes to team totals; reviewed identity requests are retained upstream',
            'Historical original publication unavailable; current source games can be incomplete; no forecast/calibrated probability'],
        consumer_status='Features only; models/scenarios/optimizer/current serving pending')


def derive_pfr_sack_conversion(snapshots,canonical_ref,schedule_snapshot,*,before_period,cutoff,canonical_directory=None):
    """Authenticate managed canonical receipts and actual indexed original Parquet bytes."""
    from backend.app.services.source_capture import verify_snapshot_artifact
    from . import pfr_advanced_features as producer
    import polars as pl
    cutoff=clock(cutoff)
    if cutoff is None:raise ValueError('Actual read cutoff required')
    root=Path(canonical_directory or Path(__file__).resolve().parents[3]/'artifacts/pfr_advanced_features').resolve()
    path=Path(canonical_ref['path']).resolve()
    if path.parent!=root or path.name!=canonical_ref['sha256']+'.json' or not 0<path.stat().st_size==canonical_ref['bytes']<=32*1024*1024:raise ValueError('Managed canonical source path/size required')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=canonical_ref['sha256']:raise ValueError('Canonical source byte hash differs')
    canonical=json.loads(raw);features=canonical['features']
    published=clock(canonical.get('actual_derived_at'));original=clock(features['provenance'].get('decision_cutoff_at'))
    if (canonical['producer_code_sha256']!=hashlib.sha256(Path(producer.__file__).read_bytes()).hexdigest()
            or features['version']!=producer.VERSION or features['before_period']!=before_period
            or published is None or original is None or not original<=published<=cutoff):
        raise ValueError('Reviewed canonical producer/scope/actual clocks differ')
    alias_index,_=producer._alias_index(features['provenance']['alias_receipts'],original)
    for actor in features['actor_game_rows']:
        if 'G13-M03' not in actor['metrics']:continue
        ids=alias_index.get(actor['pfr_player_id'],set());expected=next(iter(ids)) if len(ids)==1 else None
        if actor['player_master_id']!=expected:raise ValueError('Canonical passer differs from cutoff-bounded native alias receipts')
    schedule=load_schedule_context(schedule_snapshot,cutoff=cutoff);records=[];proof=[];used=set()
    known_source={r['snapshot_id']:r for r in features['provenance']['source_refs']}
    for snapshot in snapshots:
        verify_snapshot_artifact(snapshot);name=Path(snapshot.artifact_path).name;scope=asset_scope(name)
        if scope['stat_type']!='pass' or scope['summary_level']!='week' or snapshot.source_system!='nflverse_pfr' or snapshot.dataset!='pfr_advstats_week_pass' or snapshot.media_type!='application/vnd.apache.parquet' or snapshot.source_uri!=BASE+name or snapshot.season!=scope['season']:
            raise ValueError('Indexed weekly PFR passing source contract required')
        observed,captured=clock(snapshot.observed_at),clock(snapshot.captured_at)
        if observed is None or captured is None or not observed<=captured<=cutoff or snapshot.byte_count>4*1024*1024:
            raise ValueError('PFR source clock/byte bound differs')
        sid=str(snapshot.snapshot_id)
        if sid in used or sid not in known_source or known_source[sid]['source_sha256']!=snapshot.content_sha256:raise ValueError('Exact native source revision/canonical receipt required')
        used.add(sid);frame=pl.read_parquet(snapshot.artifact_path);v=validate_pfr_frame(frame,**scope,max_season=cutoff.year)
        if not v['native_grain_valid'] or frame.height!=snapshot.row_count or not {'times_pressured','times_sacked'}<=set(frame.columns):raise ValueError('Validated native pressure/sack fields required')
        for index,row in enumerate(frame.to_dicts()):
            if row['game_type']=='REG' and int(row['season'])*100+int(row['week'])<before_period:
                records.append({**row,'_source_snapshot_id':sid,'_native_row':index})
        proof.append(dict(snapshot_id=sid,source_sha256=snapshot.content_sha256,season=scope['season'],observed_at=observed.isoformat(),captured_at=captured.isoformat()))
    result=build_pfr_sack_conversion(records,features['actor_game_rows'],proof,schedule,before_period=before_period)
    result['provenance'].update(canonical_input_ref=deepcopy(canonical_ref),canonical_alias_receipts=deepcopy(features['provenance']['alias_receipts']),
        identity_queue=deepcopy(canonical['identity_queue']),actual_read_at=cutoff.isoformat(),producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result
