"""Append-only source attachment incidents for descriptive fumble features."""
from copy import deepcopy
from .post_fumble_workload import require_feature_use

def persist_identity_requests(connection,features,*,artifact_ref,source_root=None):
    """Append immutable source-attachment incidents, not alias repair assertions."""
    from pathlib import Path
    import hashlib,json,re
    from sqlalchemy import text
    root=Path(source_root or 'artifacts/post_fumble_workload').resolve();p=Path(artifact_ref['path']).resolve()
    if p.parent!=root or p.name!=artifact_ref['sha256']+'.json' or p.stat().st_size!=artifact_ref['bytes'] or p.stat().st_size>8*1024*1024:raise ValueError('Managed post-fumble artifact required')
    raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=artifact_ref['sha256'] or json.loads(raw)!=features:raise ValueError('Immutable post-fumble source differs')
    require_feature_use(features,purpose='offline_descriptive')
    attached={(r['game_id'],r['team'],r['source_player_id']):r for r in features['rows']};records=[]
    for q in features['identity_review_requests']:
        actor=attached[(q['game_id'],q['team'],q['source_player_id'])]
        if actor['player_master_id'] is not None or not re.fullmatch(r'00-\d{7}',q['source_player_id']):raise ValueError('Native unresolved fumbler proof required')
        key='post-fumble:'+features['source_event_sha256']+':'+q['game_id']+':'+q['source_player_id'];year,week=map(int,q['game_id'].split('_')[:2])
        qid='post-fumble:'+hashlib.sha256(key.encode()).hexdigest()[:32]
        connection.execute(text('''INSERT INTO target.identity_quarantine
        (identity_quarantine_id,entity_type,source_schema,source_table,source_record_key,source_system,season,week,slate,source_player_key,display_name,team_id,position,reason_code,candidate_player_ids,status,first_seen_at,updated_at)
        VALUES (:qid,'player','public','source_snapshot',:key,'nflreadpy',:season,:week,'FEATURE_INVENTORY',:native,NULL,:team,NULL,'native_fumbler_attachment_missing_in_frozen_parent','[]'::jsonb,'open',now(),now())
        ON CONFLICT (source_schema,source_table,source_record_key) DO NOTHING'''),dict(qid=qid,key=key,season=year,week=week,native=q['source_player_id'],team=q['team']))
        records.append(dict(source_record_key=key,identity_quarantine_id=qid,source_player_key=q['source_player_id'],artifact_ref=deepcopy(artifact_ref)))
    return dict(records=records,requests=len(records),aliases_changed=False,resolved_issues_reopened=False)
