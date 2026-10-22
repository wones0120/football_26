"""Native weekly PFR defender measurements; no event-level team rate proxies."""
from collections import defaultdict
from uuid import UUID
from .evaluation_record import digest
from .factual_designation import clock
from .market_snapshots import canonical_team,utc_time

VERSION='pfr_weekly_defender_measurements_v1'
COUNTS={'pressures':'def_pressures','missed_tackles':'def_missed_tackles','combined_tackles':'def_tackles_combined',
        'targets':'def_targets','completions_allowed':'def_completions_allowed','sacks':'def_sacks'}


def _number(value,*,count=False):
    import math
    if value is None or isinstance(value,bool):return None
    try:value=float(value)
    except (ValueError,TypeError):return None
    if not math.isfinite(value) or count and (value<0 or not value.is_integer()):return None
    return value


def build_defender_measurements(records,aliases,*,before_period,cutoff):
    """Caller supplies authenticated weekly source rows; not a serving interface."""
    cutoff=utc_time(cutoff)
    if type(before_period) is not int or not 2000<=before_period//100<=cutoff.year or not 1<=before_period%100<=18:
        raise ValueError('Prior REG target period required')
    mapping=defaultdict(set);alias_proofs=[]
    for a in aliases:
        if a.get('source_system')!='pfr' or not a.get('source_key'):raise ValueError('Native PFR alias required')
        created=clock(a.get('created_at'))
        if created is None or created>cutoff:continue
        pid=str(UUID(str(a['player_master_id'])))
        mapping[a['source_key']].add(pid)
        alias_proofs.append(dict(source_key=a['source_key'],player_master_id=pid,created_at=created.isoformat()))
    # A persisted alias can be wrong even when each native key maps uniquely.
    # Two native actors in one game cannot share canonical identity: quarantine
    # implicated keys throughout this batch, retaining original alias proofs.
    joint=defaultdict(set)
    for r in records:
        ids=mapping.get(r.get('pfr_player_id'),set())
        if len(ids)==1:joint[(r.get('game_id'),next(iter(ids)))].add(r.get('pfr_player_id'))
    collisions=[dict(game_id=g,player_master_id=pid,native_ids=sorted(keys)) for (g,pid),keys in joint.items() if len(keys)>1]
    quarantined={native for c in collisions for native in c['native_ids']}
    rows=[];seen=set();queue={}
    for r in records:
        if r.get('summary_level')!='week' or r.get('stat_type')!='def':raise ValueError('Weekly defense source grain required')
        period=r['season']*100+r['week']
        if r.get('game_type')!='REG' or period>=before_period:raise ValueError('Prior REG record required')
        native=r.get('pfr_player_id');gid=r.get('game_id');team=canonical_team(r.get('team'))
        if not native or not gid or not team:raise ValueError('Native actor/game/team required')
        parts=gid.split('_')
        if len(parts)!=4 or int(parts[0])*100+int(parts[1])!=period or team not in {canonical_team(x) for x in parts[2:]}:
            raise ValueError('Native game scope mismatch')
        key=(gid,native)
        if key in seen:raise ValueError('Duplicate native defender/game')
        seen.add(key);ids=mapping.get(native,set());pid=next(iter(ids)) if len(ids)==1 else None
        if native in quarantined:pid=None
        if pid is None:
            q=queue.setdefault(native,dict(source_system='pfr',source_key=native,reason='canonical_native_game_collision' if native in quarantined else 'conflicting_native_alias' if ids else 'native_pfr_alias_missing',candidate_player_ids=sorted(ids),period=period,team=team,source_refs=[]))
            q['source_refs'].append(dict(game_id=gid,source_ref=r.get('source_ref')))
            if period>q['period']:q.update(period=period,team=team)
        measures={name:_number(r.get(col),count=name!='sacks') for name,col in COUNTS.items()}
        if measures['sacks'] is not None and measures['sacks']<0:measures['sacks']=None
        fraction=_number(r.get('def_missed_tackle_pct'))
        if fraction is not None and not 0<=fraction<=1:fraction=None
        measures['G15-M07']=dict(value=fraction,unit='vendor_reported_fraction',
            variant='individual_defender_PFR_missed_tackle_fraction_not_certified_team_rate',
            original_reported_value=_number(r.get('def_missed_tackle_pct')),
            denominator='Provider-defined; not reconstructed from rounded percent or overlapping tackles')
        rows.append(dict(game_id=gid,period=period,team=team,pfr_player_id=native,player_master_id=pid,
            metrics=measures,source_ref=r.get('source_ref')))
    rows.sort(key=lambda r:(r['game_id'],r['team'],r['pfr_player_id']))
    semantic=dict(version=VERSION,before_period=before_period,actor_game_rows=[{k:v for k,v in r.items() if k!='source_ref'} for r in rows])
    return {**semantic,'actor_game_rows':rows,'semantic_sha256':digest(semantic),'identity_review_requests':list(queue.values()),'canonical_identity_collisions':collisions,
        'provenance':dict(alias_receipts=sorted(alias_proofs,key=lambda a:(a['source_key'],a['player_master_id'])),decision_cutoff_at=cutoff.isoformat()),
        'limitations':['Individual defender pressure counts are not unique team pressure events or pressure rates',
            'Individual tackle opportunities can overlap; no sum of percentages or invented team denominator',
            'Source measures are revised descriptive facts, not original historical availability or complete final-game proof'],
        'forecast':None,'model_consumed':False,'optimizer_consumed':False}


def build_verified_defender_features(snapshots,aliases,*,before_period,cutoff):
    from pathlib import Path
    import polars as pl
    from backend.app.services.source_capture import verify_snapshot_artifact
    from .pfr_source_components import asset_scope,validate_pfr_frame,BASE
    cutoff=utc_time(cutoff);records=[];proof=[];seen=set()
    for snapshot in snapshots:
        verify_snapshot_artifact(snapshot);name=Path(snapshot.artifact_path).name;scope=asset_scope(name)
        if snapshot.source_system!='nflverse_pfr' or snapshot.source_uri!=BASE+name:raise ValueError('Indexed PFR source required')
        if scope['summary_level']!='week' or scope['stat_type']!='def':raise ValueError('Explicit weekly defense snapshots required')
        if snapshot.dataset!='pfr_advstats_week_def' or snapshot.season!=scope['season']:raise ValueError('Indexed scope mismatch')
        if scope['season'] in seen:raise ValueError('Explicit single revision required')
        seen.add(scope['season'])
        observed,captured=clock(snapshot.observed_at),clock(snapshot.captured_at)
        if observed is None or captured is None or not observed<=captured<=cutoff:raise ValueError('Source clock unavailable at cutoff')
        if snapshot.byte_count>4*1024*1024:raise ValueError('Source byte bound exceeded')
        frame=pl.read_parquet(snapshot.artifact_path)
        if not validate_pfr_frame(frame,**scope,max_season=cutoff.year)['native_grain_valid']:raise ValueError('Native source requires review')
        for index,row in enumerate(frame.to_dicts()):
            if row['game_type']=='REG' and int(row['season'])*100+int(row['week'])<before_period:
                records.append({**row,'summary_level':'week','stat_type':'def','source_ref':dict(snapshot_id=str(snapshot.snapshot_id),native_row=index)})
        proof.append(dict(snapshot_id=str(snapshot.snapshot_id),sha256=snapshot.content_sha256,captured_at=captured.isoformat()))
    result=build_defender_measurements(records,aliases,before_period=before_period,cutoff=cutoff)
    result['provenance']['source_refs']=proof
    result.update(evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False)
    return result


def persist_defender_identity_requests(connection,features):
    """Preserve decisions; new contradictory evidence gets its own review key."""
    import hashlib,json
    from sqlalchemy import text
    from .pfr_advanced_features import persist_feature_identity_requests,VERSION as QUEUE_CONTRACT
    if features.get('version')!=VERSION:raise ValueError('Defender feature contract required')
    normal=[q for q in features['identity_review_requests'] if q['reason']!='canonical_native_game_collision']
    result=persist_feature_identity_requests(connection,dict(version=QUEUE_CONTRACT,identity_review_requests=normal))
    for q in features['identity_review_requests']:
        if q['reason']!='canonical_native_game_collision':continue
        evidence=sorted((c for c in features['canonical_identity_collisions'] if q['source_key'] in c['native_ids']),key=lambda c:(c['game_id'],c['player_master_id']))
        key='pfr-alias-conflict:'+q['source_key']+':'+digest(evidence)
        qid='pfr-conflict:'+hashlib.sha256(key.encode()).hexdigest()[:32]
        connection.execute(text("""
            INSERT INTO target.identity_quarantine
            (identity_quarantine_id,entity_type,source_schema,source_table,source_record_key,source_system,
             season,week,slate,source_player_key,display_name,team_id,position,reason_code,candidate_player_ids,status,first_seen_at,updated_at)
            VALUES (:qid,'player','public','player_alias',:key,'pfr',:season,:week,'FEATURE_INVENTORY',
                :native,NULL,:team,NULL,:reason,CAST(:candidates AS jsonb),'open',now(),now())
            ON CONFLICT (source_schema,source_table,source_record_key) DO NOTHING
        """),dict(qid=qid,key=key,season=q['period']//100,week=q['period']%100,native=q['source_key'],team=q['team'],reason=q['reason'],candidates=json.dumps(q['candidate_player_ids'])))
        result['records'].append(dict(source_record_key=key,source_player_key=q['source_key'],identity_quarantine_id=qid,collision_evidence=evidence))
    result['requests']=len(result['records'])
    return result
