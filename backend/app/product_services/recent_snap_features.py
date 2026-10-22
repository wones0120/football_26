"""Measured snap trends from a frozen retained-DB revision, not role forecasts."""
from collections import defaultdict
from copy import deepcopy
import math,re
from .market_snapshots import canonical_team,utc_time
from .factual_designation import clock
from .pfr_advanced_features import _alias_index
from .evaluation_record import digest

VERSION='recent_observed_snap_trends_v1'
CHANNELS=('offense','defense','st')


def _number(v,*,count=False):
    if v is None or isinstance(v,bool):return None
    try:n=float(v)
    except (TypeError,ValueError):return None
    if not math.isfinite(n) or n<0 or count and n!=int(n) or not count and n>1:return None
    return int(n) if count else n


def build_recent_snap_features(records,aliases,*,before_period,cutoff,prior_logs=3,identity_blocks=()):
    cutoff=utc_time(cutoff)
    if type(before_period) is not int or not 1<=before_period%100<=18 or not 2012<=before_period//100<=cutoff.year or type(prior_logs) is not int or prior_logs<1:raise ValueError('Explicit REG target/window required')
    mapping,rejected=_alias_index(aliases,cutoff);normalized=[];quality=[];teams=defaultdict(dict);team_unknown=set();requests={};native_games={};source_rows=set();equivalent={}
    for r in records:
        if r['source_row_id'] in source_rows:raise ValueError('Duplicate native source row identity')
        source_rows.add(r['source_row_id'])
        if clock(r.get('created_at')) is None or clock(r['created_at'])>cutoff:raise ValueError('Retained row not available at actual extraction cutoff')
        raw=r['raw'];season=raw.get('season');week=raw.get('week');team=canonical_team(raw.get('team'))
        if type(season) not in {int,float} or type(week) not in {int,float} or not math.isfinite(season) or not math.isfinite(week) or int(season)!=season or int(week)!=week:raise ValueError('Native period must be integer')
        season,week=int(season),int(week);period=season*100+week
        if season!=before_period//100 or period>=before_period or raw.get('game_type')!='REG':
            quality.append(dict(source_row_id=r['source_row_id'],reason='outside_prior_same_season_REG_scope'))
            if season==before_period//100 and period<before_period and raw.get('game_type') is None and team:team_unknown.add(team)
            continue
        gid=raw.get('game_id');parts=str(gid).split('_')
        if not team or not 1<=week<=18 or len(parts)!=4 or parts[0]!=str(season) or parts[1]!=f'{week:02}' or team not in {canonical_team(p) for p in parts[2:]}:
            quality.append(dict(source_row_id=r['source_row_id'],reason='native_game_team_scope_unknown'))
            if team:team_unknown.add(team)
            continue
        if gid in teams[team] and teams[team][gid]!=period:raise ValueError('Contradictory native game period')
        teams[team][gid]=period
        native=raw.get('pfr_player_id')
        if not isinstance(native,str) or not re.fullmatch(r'[A-Za-z0-9]{5,20}',native):
            requests['row:'+str(r['source_row_id'])]=dict(source_row_id=r['source_row_id'],reason='native_pfr_id_missing_or_malformed',source_key=native,team=team,period=period)
            continue
        raw_sha=digest(raw);key=(gid,native)
        proof=dict(source_row_id=r['source_row_id'],ingest_run_id=r['ingest_run_id'],created_at=r['created_at'])
        if key in native_games:
            existing=native_games[key]
            if existing['raw_sha256']!=raw_sha or r['ingest_run_id'] in existing['ingest_run_ids']:raise ValueError('Duplicate native player/game has conflicting or same-ingest revisions')
            existing['ingest_run_ids'].add(r['ingest_run_id']);existing['source_records'].append(proof)
            equivalent[key]=existing
            continue
        native_games[key]=dict(game_id=gid,pfr_player_id=native,raw_sha256=raw_sha,ingest_run_ids={r['ingest_run_id']},source_records=[proof])
        ids=mapping.get(native,set());pid=next(iter(ids)) if len(ids)==1 else None
        values={};conflicts=[]
        for ch in CHANNELS:
            n=_number(raw.get(ch+'_snaps'),count=True);share=_number(raw.get(ch+'_pct'))
            if n==0 and share is not None and share>0:
                conflicts.append(ch);n=share=None
            values[ch]=dict(snaps=n,share=share)
        normalized.append(dict(source_row_id=r['source_row_id'],ingest_run_id=r['ingest_run_id'],game_id=gid,period=period,team=team,pfr_player_id=native,player_master_id=pid,values=values,source_conflicts=conflicts))
    joint=defaultdict(set)
    for r in normalized:
        if r['player_master_id']:joint[(r['game_id'],r['player_master_id'])].add(r['pfr_player_id'])
    collisions=[dict(game_id=g,player_master_id=pid,native_ids=sorted(ids)) for (g,pid),ids in joint.items() if len(ids)>1]
    quarantined={n for c in collisions for n in c['native_ids']}
    for b in identity_blocks:
        if b.get('source_system')!='pfr' or b.get('status')!='open' or b.get('reason_code')!='canonical_native_game_collision' or clock(b.get('first_seen_at')) is None or clock(b['first_seen_at'])>cutoff:raise ValueError('Bound current native identity-block proof required')
        quarantined.add(b['source_player_key'])
    actors=defaultdict(dict)
    for r in normalized:
        native=r['pfr_player_id']
        if native in quarantined:r['player_master_id']=None
        if r['player_master_id'] is None:
            requests[native]=dict(source_key=native,reason='canonical_native_game_collision' if native in quarantined else 'native_pfr_alias_unresolved',team=r['team'],period=r['period'],candidate_player_ids=sorted(mapping.get(native,set())))
        key=(native,r['team'])
        if r['game_id'] in actors[key]:raise ValueError('Duplicate native player/team/game')
        actors[key][r['game_id']]=r
    result=[]
    for (native,team),games in sorted(actors.items()):
        observed=sorted(teams[team],key=lambda g:(teams[team][g],g));selected=observed[-(prior_logs+1):]
        if len({teams[team][g] for g in observed})!=len(observed):raise ValueError('Multiple team games in same period')
        latest=selected[-1];current=games.get(latest);previous=[games.get(g) for g in selected[:-1]];complete=len(previous)==prior_logs and team not in team_unknown
        trends={}
        for ch in CHANNELS:
            channel={}
            for field in ('snaps','share'):
                now=current['values'][ch][field] if current else None
                prior=[r['values'][ch][field] if r else None for r in previous]
                mean=sum(prior)/prior_logs if complete and all(v is not None for v in prior) else None
                channel[field]=dict(latest=now,prior_mean=mean,delta=now-mean if now is not None and mean is not None else None,
                    known_prior_logs=sum(v is not None for v in prior),required_prior_logs=prior_logs)
            trends[ch]=channel
        any_row=next(iter(games.values()))
        result.append(dict(pfr_player_id=native,player_master_id=any_row['player_master_id'],team=team,latest_observed_team_game_id=latest,
            source_row_present_in_latest=current is not None,prior_observed_team_game_ids=selected[:-1],team_game_scope_unknown=team in team_unknown,channels=trends))
    facts=dict(version=VERSION,before_period=before_period,prior_observed_team_logs=prior_logs,actor_trends=result,
        team_observed_game_ids={team:sorted(games,key=lambda g:(games[g],g)) for team,games in sorted(teams.items())})
    return {**facts,'semantic_sha256':digest(facts),'identity_review_requests':list(requests.values()),'canonical_identity_collisions':collisions,'source_quality':quality,
        'provenance':dict(actual_extraction_cutoff=cutoff.isoformat(),alias_quality=rejected,identity_blocks=deepcopy(list(identity_blocks)),equivalent_revision_groups=[{k:v for k,v in group.items() if k!='ingest_run_ids'} for _,group in sorted(equivalent.items())]),
        'catalog_ids':['G17-M06','G22-M04'],
        'definition':f'Latest observed same-team REG game snaps/share minus mean of exactly {prior_logs} preceding observed team logs; offense/defense/ST separate',
        'limitations':['Missing actor row is unknown, not DNP or zero; no positive-game fallback','Player snaps overlap across teammates; never sum them as physical offensive plays',
            'Current DB revision freeze is not an original historical provider snapshot or original pregame availability proof'],
        'evidence_use':'postlock_descriptive_not_pregame_or_serving','pregame_serving_eligible':False,'forecast':None,'model_consumed':False,'optimizer_consumed':False}


def load_frozen_snap_revision(snapshot,*,cutoff):
    from pathlib import Path
    import json
    from backend.app.services.source_capture import verify_snapshot_artifact
    verify_snapshot_artifact(snapshot);cutoff=utc_time(cutoff)
    expected_uri=f'retained-db://public.raw_nfl_snap_count/season={snapshot.season}'
    if snapshot.source_system!='retained_db' or snapshot.dataset!='snap_counts_revision' or snapshot.source_uri!=expected_uri or snapshot.media_type!='application/json':raise ValueError('Retained snap revision source required')
    observed,captured=clock(snapshot.observed_at),clock(snapshot.captured_at)
    if observed is None or captured is None or not observed<=captured<=cutoff:raise ValueError('Frozen source unavailable at cutoff')
    if not 0<snapshot.byte_count<=32*1024*1024:raise ValueError('Snap source byte bound exceeded')
    value=json.loads(Path(snapshot.artifact_path).read_text())
    if value.get('contract')!='retained_snap_count_revision_v1' or value['season']!=snapshot.season or value.get('original_provider_snapshot_claim') is not False:raise ValueError('Retained revision origin contract required')
    extracted=clock(value['actual_extract_completed_at']);started=clock(value['actual_extract_started_at'])
    if extracted is None or started is None or not started<=extracted<=captured:raise ValueError('Extraction/capture clock order invalid')
    rows=value['rows']
    if len(rows)!=snapshot.row_count or not 0<len(rows)<=30000:raise ValueError('Frozen snap row cardinality differs')
    runs={r['ingest_run_id']:r for r in value['original_ingest_runs']}
    if any(r['ingest_run_id'] not in runs or runs[r['ingest_run_id']]['status']!='completed' for r in rows):raise ValueError('Complete retained ingest evidence required')
    for run in runs.values():
        began,ended=clock(run.get('started_at')),clock(run.get('completed_at'))
        if began is None or ended is None or not began<=ended<=extracted:raise ValueError('Retained ingest completion clocks unavailable at extraction')
    if any(r['raw'].get('season')!=snapshot.season for r in rows):raise ValueError('Frozen source season differs')
    result=build_recent_snap_features(rows,value['aliases'],before_period=snapshot.season*100+snapshot.week,cutoff=extracted,identity_blocks=value['identity_blocks'])
    result['provenance'].update(source_snapshot_id=str(snapshot.snapshot_id),source_sha256=snapshot.content_sha256,source_observed_at=observed.isoformat(),source_captured_at=captured.isoformat(),
        actual_extract_started_at=started.isoformat(),actual_extract_completed_at=extracted.isoformat(),actual_read_cutoff=cutoff.isoformat(),alias_receipts=deepcopy(value['aliases']),
        original_ingest_runs=deepcopy(value['original_ingest_runs']),source_origin=value['source_origin'],source_revision_not_original_snapshot=True)
    return result


def persist_snap_identity_requests(connection,features):
    """Persist review evidence only; never infer aliases or reopen decisions."""
    import hashlib,json
    from sqlalchemy import text
    from .pfr_advanced_features import persist_feature_identity_requests,VERSION as REQUEST_CONTRACT
    if features.get('version')!=VERSION:raise ValueError('Snap feature request contract required')
    provenance=features['provenance'];snapshot_id=provenance['source_snapshot_id'];sha=provenance['source_sha256']
    if not re.fullmatch(r'[0-9a-f]{64}',sha):raise ValueError('Immutable snap source hash required')
    normal=[];other=[];records=[]
    blocks=provenance['identity_blocks']
    for q in features['identity_review_requests']:
        if q['reason']=='canonical_native_game_collision':
            existing=[b for b in blocks if b['source_player_key']==q['source_key']]
            current=[c for c in features['canonical_identity_collisions'] if q['source_key'] in c['native_ids']]
            if existing and not current:
                records.extend(dict(identity_quarantine_id=b['identity_quarantine_id'],source_player_key=q['source_key'],existing_frozen_conflict=True) for b in existing)
                continue
            key='snap-alias-conflict:'+q['source_key']+':'+digest(current)
            other.append((q,key,'player_alias','pfr'))
        elif q['reason']=='native_pfr_id_missing_or_malformed':
            other.append((q,f"snap-row:{sha}:{q['source_row_id']}",'source_snapshot','retained_db'))
        else:
            normal.append({**q,'source_system':'pfr','source_refs':[dict(snapshot_id=snapshot_id,source_sha256=sha,native_player_id=q['source_key'])]})
    saved=persist_feature_identity_requests(connection,dict(version=REQUEST_CONTRACT,identity_review_requests=normal));records.extend(saved['records'])
    for q,key,table,system in other:
        qid='snap-identity:'+hashlib.sha256(key.encode()).hexdigest()[:32]
        connection.execute(text("""
            INSERT INTO target.identity_quarantine
            (identity_quarantine_id,entity_type,source_schema,source_table,source_record_key,source_system,
             season,week,slate,source_player_key,display_name,team_id,position,reason_code,candidate_player_ids,status,first_seen_at,updated_at)
            VALUES (:qid,'player','public',:table,:key,:system,:season,:week,'FEATURE_INVENTORY',
                    :native,NULL,:team,NULL,:reason,CAST(:candidates AS jsonb),'open',now(),now())
            ON CONFLICT (source_schema,source_table,source_record_key) DO NOTHING
        """),dict(qid=qid,table=table,key=key,system=system,season=q['period']//100,week=q['period']%100,native=q.get('source_key') or key,team=q['team'],reason=q['reason'],candidates=json.dumps(q.get('candidate_player_ids',[]))))
        records.append(dict(identity_quarantine_id=qid,source_record_key=key,source_player_key=q.get('source_key'),source_snapshot_id=snapshot_id))
    return dict(requests=len(records),records=records,aliases_changed=False,resolved_records_reopened=False,
        display_name_limitation='Frozen projection excludes player display names; native keys or immutable source-row references remain explicit')
