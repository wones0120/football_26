"""Literal provider depth-rank changes; no inferred role, absence or forecast."""
from uuid import UUID
import re
from .evaluation_record import digest
from .factual_designation import clock
from .player_role_source_features import _verified_rows

VERSION='observed_depth_changes_v1'
SPECIAL={'KR','PR','H','PK','K','P','LS'}


def build_observed_depth_changes(sources,canonical_ids,*,season,week,cutoff):
    aliases={str(k):{str(UUID(str(v))) for v in ([values] if isinstance(values,str) else values)} for k,values in canonical_ids.items()}
    frames=[];requests=[];unkeyed=[]
    for source in sources:
        if source['season']!=season or source['week']!=week:raise ValueError('Depth period differs')
        observed=clock(source['observed_at']);captured=clock(source['captured_at'])
        if observed>captured or captured>clock(cutoff):raise ValueError('Depth source unavailable')
        teams=set(source['teams']);latest={};indexed={}
        for i,r in enumerate(source['rows']):
            team=r.get('team')
            if team not in teams:raise ValueError('Depth team scope differs')
            dt=clock(r['dt'])
            if dt>captured or dt>clock(cutoff):raise ValueError('Future depth document')
            latest[team]=max(latest.get(team,dt),dt)
        if set(latest)!=teams:raise ValueError('Missing scoped team document')
        for i,r in enumerate(source['rows']):
            team=r['team'];dt=clock(r['dt'])
            if dt!=latest[team]:continue
            native=r.get('gsis_id');position=r.get('pos_abb');slot=r.get('pos_slot')
            if not native or not re.fullmatch(r'00-\d{7}',native) or not position or not slot:
                fact=dict(source_snapshot_id=source['snapshot_id'],source_row=i,team=team,source_player_id=native,raw_depth_role=dict(r),reason='incomplete_native_depth_role_key')
                requests.append(fact);unkeyed.append(fact);continue
            key=(team,native,position,slot)
            if key in indexed:raise ValueError('Duplicate native depth role key')
            rank=r.get('pos_rank');rank=int(rank) if rank and rank.isdigit() and int(rank)>0 else None
            matches=aliases.get(native,set());pid=next(iter(matches)) if len(matches)==1 else None
            if pid is None:requests.append(dict(source_player_id=native,team=team,source_snapshot_id=source['snapshot_id'],source_row=i,reason='depth_native_identity_unresolved_or_ambiguous'))
            indexed[key]=dict(team=team,source_player_id=native,player_master_id=pid,source_position=position,source_slot=slot,unit='special_teams' if position in SPECIAL else 'non_special_teams',rank=rank,document_at=dt.isoformat(),source_row=i)
        frames.append(dict(source=source,indexed=indexed,latest=latest))
    # Only identical scope is comparable. Different team captures cannot imply loss.
    groups={}
    for f in frames:groups.setdefault(tuple(sorted(f['source']['teams'])),[]).append(f)
    comparisons=[]
    for scope,fs in sorted(groups.items()):
        fs.sort(key=lambda f:(clock(f['source']['captured_at']),f['source']['snapshot_id']))
        for previous,current in zip(fs,fs[1:]):
            if clock(previous['source']['captured_at'])==clock(current['source']['captured_at']):raise ValueError('Ambiguous simultaneous depth captures')
            if any(current['latest'][t]<previous['latest'][t] for t in scope):raise ValueError('Depth document chronology regressed')
            a,b=previous['indexed'],current['indexed'];matched=[]
            for key in sorted(a.keys()&b.keys()):
                old,new=a[key],b[key]
                delta=None if old['rank'] is None or new['rank'] is None else new['rank']-old['rank']
                matched.append(dict(**new,prior_rank=old['rank'],rank_delta=delta,change='unknown' if delta is None else 'unchanged' if delta==0 else 'rank_number_increased' if delta>0 else 'rank_number_decreased',prior_source_row=old['source_row']))
            comparisons.append(dict(teams=list(scope),prior_snapshot_id=previous['source']['snapshot_id'],current_snapshot_id=current['source']['snapshot_id'],matched_roles=matched,newly_observed_roles=[b[k] for k in sorted(b.keys()-a.keys())],not_observed_roles=[a[k] for k in sorted(a.keys()-b.keys())],absence_interpretation='source_presence_only_not_promotion_demotion_or_inactive'))
    result=dict(version=VERSION,season=season,week=week,comparisons=comparisons,identity_review_requests=requests,unkeyed_source_roles=unkeyed,forecast=False,evidence_use='postlock_descriptive_not_pregame_or_serving')
    result['semantic_sha256']=digest(dict(version=VERSION,season=season,week=week,comparisons=comparisons,unkeyed_source_roles=unkeyed))
    result['provenance']=dict(actual_read_cutoff=str(cutoff),sources=[{k:v for k,v in s.items() if k!='rows'} for s in sources])
    return result


def load_observed_depth_sources(snapshots,canonical_ids,*,season,week,teams,cutoff):
    sources=[]
    for snapshot in snapshots:
        rows=_verified_rows(snapshot,dataset='player_depth_charts',season=season,week=week,cutoff=cutoff)
        if set(r.get('team') for r in rows)!=set(teams):raise ValueError('Captured depth team universe differs')
        sources.append(dict(snapshot_id=str(snapshot.snapshot_id),content_sha256=snapshot.content_sha256,source_uri=snapshot.source_uri,season=season,week=week,teams=sorted(teams),observed_at=str(snapshot.observed_at),captured_at=str(snapshot.captured_at),rows=rows))
    return build_observed_depth_changes(sources,canonical_ids,season=season,week=week,cutoff=cutoff)


def persist_depth_identity_requests(connection,features,*,artifact_ref,source_root='artifacts/observed_depth_changes'):
    """Append frozen source attachment incidents; never repair or reopen aliases."""
    import hashlib,json
    from pathlib import Path
    from sqlalchemy import text
    p=Path(artifact_ref['path']).resolve();root=Path(source_root).resolve()
    if p.parent!=root or p.name!=artifact_ref['sha256']+'.json' or p.stat().st_size!=artifact_ref['bytes'] or p.stat().st_size>4*1024*1024:raise ValueError('Managed depth artifact required')
    raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=artifact_ref['sha256'] or json.loads(raw)!=features or features.get('version')!=VERSION:raise ValueError('Depth artifact differs')
    if features.get('evidence_use')!='postlock_descriptive_not_pregame_or_serving':raise ValueError('Descriptive depth evidence required')
    sources={s['snapshot_id']:s for s in features['provenance']['sources']};records=[]
    for q in features['identity_review_requests']:
        source=sources[q['source_snapshot_id']]
        key='depth-attachment:'+digest(dict(source_sha256=source['content_sha256'],source_row=q['source_row'],reason=q['reason']))
        qid='depth:'+hashlib.sha256(key.encode()).hexdigest()[:32]
        connection.execute(text('''INSERT INTO target.identity_quarantine
        (identity_quarantine_id,entity_type,source_schema,source_table,source_record_key,source_system,season,week,slate,source_player_key,display_name,team_id,position,reason_code,candidate_player_ids,status,first_seen_at,updated_at)
        VALUES (:qid,'player','public','source_snapshot',:key,'nflreadpy',:season,:week,'FEATURE_INVENTORY',:native,NULL,:team,NULL,'frozen_depth_source_attachment_unresolved','[]'::jsonb,'open',now(),now())
        ON CONFLICT (source_schema,source_table,source_record_key) DO NOTHING'''),dict(qid=qid,key=key,season=features['season'],week=features['week'],native=q.get('source_player_id'),team=q['team']))
        records.append(dict(identity_quarantine_id=qid,source_record_key=key,source_snapshot_id=q['source_snapshot_id'],source_row=q['source_row'],source_player_id=q.get('source_player_id')))
    return dict(records=records,aliases_changed=False,resolved_issues_reopened=False)
