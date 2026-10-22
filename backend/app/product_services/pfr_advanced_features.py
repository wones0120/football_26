"""Source-measured PFR contact/pressure features; no prediction or name joins."""
from collections import defaultdict
from pathlib import Path
from uuid import UUID
import math
import polars as pl
from backend.app.services.source_capture import verify_snapshot_artifact
from .evaluation_record import digest
from .factual_designation import clock
from .market_snapshots import canonical_team,utc_time
from .pfr_source_components import asset_scope,validate_pfr_frame,BASE

VERSION='pfr_weekly_contact_pressure_features_v1'


def _number(value,*,count=False):
    if value is None or isinstance(value,bool):return None
    try:value=float(value)
    except (ValueError,TypeError):return None
    if not math.isfinite(value) or count and (value<0 or not value.is_integer()):return None
    return value


def _alias_index(aliases,cutoff):
    mapping=defaultdict(set);rejected=[]
    for a in aliases:
        if a.get('source_system')!='pfr' or not a.get('source_key'):raise ValueError('Persisted native PFR aliases required')
        created=clock(a.get('created_at'))
        if created is None or created>cutoff:
            rejected.append(dict(source_key=a['source_key'],reason='alias_creation_not_available_at_cutoff'));continue
        mapping[a['source_key']].add(str(UUID(str(a['player_master_id']))))
    return mapping,rejected


def _derive(records,aliases,*,before_period,cutoff):
    mapping,rejected=_alias_index(aliases,cutoff);actors={};teams=defaultdict(list);requests={};canonical_games={}
    for r in records:
        native=r['pfr_player_id'];team=canonical_team(r['team']);gid=r['game_id'];period=int(r['season'])*100+int(r['week'])
        if r['game_type']!='REG' or period>=before_period:raise ValueError('Prior REG records required')
        sides={canonical_team(t) for t in gid.split('_')[2:]};opponent=next(t for t in sides if t!=team)
        if r.get('opponent') and canonical_team(r['opponent'])!=opponent:raise ValueError('Opponent differs from native game')
        ids=mapping.get(native,set());pid=next(iter(ids)) if len(ids)==1 else None
        if pid is not None:
            ckey=(gid,pid);identity=(native,team)
            if ckey in canonical_games and canonical_games[ckey]!=identity:raise ValueError('Canonical player/game identity collision')
            canonical_games[ckey]=identity
        if pid is None:
            q=requests.setdefault(native,dict(source_key=native,source_system='pfr',reason='conflicting_native_alias' if ids else 'native_pfr_alias_missing',
                display_name=r.get('pfr_player_name'),team=team,period=period,candidate_player_ids=sorted(ids),source_refs=[]))
            if period>q['period']:q.update(period=period,team=team,display_name=r.get('pfr_player_name'))
            q['source_refs'].append(dict(source_snapshot_id=r['_source_snapshot_id'],native_row=r['_native_row'],game_id=gid))
        key=(gid,team,native)
        actor=actors.setdefault(key,dict(game_id=gid,period=period,team=team,opponent=opponent,pfr_player_id=native,
            player_master_id=pid,canonical_identity_status='resolved_native_alias' if pid else 'requires_review',metrics={},source_refs=[]))
        actor['source_refs'].append(dict(snapshot_id=r['_source_snapshot_id'],native_row=r['_native_row'],stat_type=r['_stat_type']))
        if r['_stat_type']=='rush':
            carry=_number(r.get('carries'),count=True)
            for mid,column in (('G07-M07','rushing_yards_before_contact'),('G07-M08','rushing_yards_after_contact')):
                value=_number(r.get(column))
                invalid=carry==0 and value is not None and value!=0
                actor['metrics'][mid]=dict(value=None if invalid else value,unit='PFR_reported_yards',kind='observed_weekly_vendor_measure',
                    per_carry=value/carry if not invalid and value is not None and carry is not None and carry>0 else None,
                    carry_exposure=carry,source_reported_value=value,
                    missing_reason='yardage_with_zero_source_carries' if invalid else 'source_yardage_unknown' if value is None else None,
                    definition='Original PFR weekly total, with matched same-row carry denominator; source contact attribution, not tracking causality',forecast=False)
            broken=_number(r.get('rushing_broken_tackles'),count=True)
            actor['metrics']['G07-M09']=dict(value=broken if carry!=0 or broken==0 else None,unit='PFR_broken_tackles',
                variant='broken_tackles_not_all_missed_tackles_forced',forecast=False)
            teams[(gid,opponent)].append(dict(native_id=native,canonical_id=pid,carries=carry,
                before=actor['metrics']['G07-M07']['value'],after=actor['metrics']['G07-M08']['value']))
        elif r['_stat_type']=='pass':
            fraction=_number(r.get('times_pressured_pct'))
            if fraction is not None and not 0<=fraction<=1:fraction=None
            actor['metrics']['G13-M03']=dict(value=fraction,unit='vendor_reported_fraction',
                variant='per_passer_PFR_pressure_fraction_not_team_OL_causal_rate',pressure_count=_number(r.get('times_pressured'),count=True),
                denominator='Provider reported; not reverse-engineered from rounded fraction',forecast=False)
    defense=[]
    for (gid,team),members in sorted(teams.items()):
        metrics={};carry=[m['carries'] for m in members];denominator=sum(carry) if all(v is not None for v in carry) else None
        for mid,col in (('G15-M05','before'),('G15-M06','after')):
            values=[m[col] for m in members];known=[v for v in values if v is not None]
            total=sum(known) if len(known)==len(values) else None
            metrics[mid]=dict(observed_source_sum=total,known_actor_component_sum=sum(known),
                observed_source_carries=denominator,per_source_carry=total/denominator if total is not None and denominator is not None and denominator>0 else None,
                unknown_actor_components=len(values)-len(known),unmapped_actors=sum(m['canonical_id'] is None for m in members),
                variant='Full_retained_PFR_rusher_source_not_certified_complete_NFL_team',unit='PFR_reported_yards',forecast=False)
        defense.append(dict(game_id=gid,defense_team=team,metrics=metrics,source_actor_count=len(members)))
    for a in actors.values():a['source_refs'].sort(key=lambda r:(r['stat_type'],r['snapshot_id'],r['native_row']))
    semantic=dict(version=VERSION,before_period=before_period,actor_game_rows=sorted(actors.values(),key=lambda a:(a['game_id'],a['team'],a['pfr_player_id'])),defense_game_rows=defense)
    # Native fact refs and alias clocks remain provenance, not numerical values.
    numerical={**semantic,'actor_game_rows':[{k:v for k,v in a.items() if k!='source_refs'} for a in semantic['actor_game_rows']]}
    return {**semantic,'semantic_sha256':digest(numerical),'identity_review_requests':list(requests.values()),
        'alias_quality':rejected,'forecast':None,'model_consumed':False,'optimizer_consumed':False}


def build_pfr_advanced_features(snapshots,aliases,*,before_period,cutoff):
    cutoff=utc_time(cutoff)
    if type(before_period) is not int or not 2000<=before_period//100<=cutoff.year or not 1<=before_period%100<=18:raise ValueError('REG measurement target required')
    records=[];proof=[];excluded=[];seen=set()
    for snapshot in snapshots:
        verify_snapshot_artifact(snapshot);name=Path(snapshot.artifact_path).name;scope=asset_scope(name)
        if snapshot.source_system!='nflverse_pfr' or snapshot.source_uri!=BASE+name:raise ValueError('Indexed native PFR source required')
        if snapshot.dataset!='pfr_advstats_'+scope['summary_level']+'_'+scope['stat_type'] or scope['season'] is not None and snapshot.season!=scope['season']:raise ValueError('Indexed PFR dataset/season differs')
        if not clock(snapshot.observed_at)<=clock(snapshot.captured_at)<=cutoff:raise ValueError('PFR source unavailable at feature cutoff')
        if scope['summary_level']!='week' or scope['stat_type'] not in {'pass','rush'}:
            excluded.append(dict(snapshot_id=str(snapshot.snapshot_id),reason='separate_annual_or_other_stat_grain'));continue
        key=(scope['stat_type'],scope['season'])
        if key in seen:raise ValueError('Explicit single revision per PFR asset scope required')
        seen.add(key)
        if snapshot.byte_count>4*1024*1024:raise ValueError('PFR byte bound exceeded')
        frame=pl.read_parquet(snapshot.artifact_path);validation=validate_pfr_frame(frame,**scope,max_season=cutoff.year)
        if not validation['native_grain_valid']:raise ValueError('Unresolved native PFR weekly source requires review')
        for index,row in enumerate(frame.to_dicts()):
            if row['game_type']=='REG' and int(row['season'])*100+int(row['week'])<before_period:
                records.append({**row,'_stat_type':scope['stat_type'],'_source_snapshot_id':str(snapshot.snapshot_id),'_native_row':index})
        proof.append(dict(snapshot_id=str(snapshot.snapshot_id),source_sha256=snapshot.content_sha256,scope=scope,captured_at=str(snapshot.captured_at)))
    result=_derive(records,aliases,before_period=before_period,cutoff=cutoff)
    used_native={r['pfr_player_id'] for r in records}
    result['provenance']=dict(source_refs=proof,excluded_sources=excluded,decision_cutoff_at=cutoff.isoformat(),
        evidence_use='revised_retrospective_feature_only_not_original_historical_pregame_or_serving',
        complete_final_game_statistics='Not independently established by native source rows',
        native_alias_asof='Persisted native PFR aliases available at actual extraction cutoff, not claimed historical originals',
        alias_receipts=[dict(source_system=a['source_system'],source_key=a['source_key'],player_master_id=str(a['player_master_id']),
            created_at=clock(a['created_at']).isoformat() if a.get('created_at') else None) for a in aliases if a['source_key'] in used_native])
    return result


def persist_feature_identity_requests(connection,features):
    """Native PFR review keys resolve once across games; never guess from name."""
    import hashlib,json
    from sqlalchemy import text
    if features.get('version')!=VERSION:raise ValueError('PFR feature identity contract required')
    records=[]
    for q in features['identity_review_requests']:
        native=q['source_key'];key='pfr-player:'+native;qid='pfr-player:'+hashlib.sha256(key.encode()).hexdigest()[:32]
        connection.execute(text("""
            INSERT INTO target.identity_quarantine
            (identity_quarantine_id,entity_type,source_schema,source_table,source_record_key,source_system,
             season,week,slate,source_player_key,display_name,team_id,position,reason_code,candidate_player_ids,status,first_seen_at,updated_at)
            VALUES (:qid,'player','public','source_snapshot',:key,'pfr',:season,:week,'FEATURE_INVENTORY',
                :native,:name,:team,NULL,:reason,CAST(:candidates AS jsonb),'open',now(),now())
            ON CONFLICT (source_schema,source_table,source_record_key) DO NOTHING
        """),dict(qid=qid,key=key,season=q['period']//100,week=q['period']%100,native=native,
            name=q.get('display_name'),team=q['team'],reason=q['reason'],candidates=json.dumps(q['candidate_player_ids'])))
        records.append(dict(source_record_key=key,source_player_key=native,identity_quarantine_id=qid,source_refs=q['source_refs']))
    return dict(requests=len(records),records=records,aliases_guessed_or_overwritten=False)
