"""Append-only official status refresh for Tiers; frozen projections remain truth."""
from copy import deepcopy
from datetime import UTC,datetime
from pathlib import Path
import hashlib
import json
from sqlalchemy import text
from ..models import SourceSnapshot
from . import tiers


def apply_refresh(pool,refresh,facts,*,directory=None,now=None):
    now=now or datetime.now(UTC)
    if pool['kind']!='pool':raise ValueError('A saved Tiers pool is required')
    if tiers.clock(refresh['observed_at'])>now:raise ValueError('Official status observation is in the future')
    if refresh.get('identity_unresolved') or not refresh.get('complete_team_coverage'):raise ValueError('Official identity or team coverage is incomplete')
    by_id={str(f['player_master_id']):f for f in facts};value=deepcopy({k:v for k,v in pool.items() if k!='sha256'});value['created_at']=now.isoformat();value['parent_pool_sha256']=pool['sha256']
    for p in value['players']:
        fact=by_id.get(p['player_master_id']);designation=str((fact or {}).get('injury_status') or '').upper();practice=((fact or {}).get('evidence_json') or {}).get('practice_report',{})
        p['refreshed_status']=dict(source_snapshot_id=refresh['snapshot_id'],context_run_id=refresh.get('context_run_id'),observed_at=refresh['observed_at'],listed_in_official_report=fact is not None,game_status=designation or None,practice_status=practice.get('practice_status') or None,final_clearance=False)
        # A blank designation, full practice or omission cannot revoke an existing
        # OUT/Q/unknown exclusion. No role, workload or mean is inferred here.
        if designation in {'OUT','DOUBTFUL','IR','PUP','SUSPENDED','INACTIVE'}:p['reason_codes']=sorted(set(p['reason_codes']+['refreshed_official_unavailable_or_doubtful']))
        if designation=='QUESTIONABLE':p['questionable']=True
    value['status_refresh']={**refresh,'status':'SOURCE_REFRESHED_FINAL_STATUS_INCOMPLETE','source_failure_repaired':True,'projection_source_unchanged':True,'final_entry_ready':False,'players_reviewed':len(value['players']),'policy':'Retain known OUT/Q/unknown exclusions. Blank status, practice participation and report omission never establish health or final clearance.'}
    return tiers.save(value,directory)


def refresh_pool(pool_key,session,*,directory=None,now=None):
    now=now or datetime.now(UTC);pool=tiers.load(pool_key,directory)
    from .official_injuries import refresh_official_injuries
    source=tiers.snapshots.load_snapshot(pool['projection_snapshot_sha256']);games=source['source_manifest']['games'];lock=min(tiers.clock(g['kickoff_at']) for g in games)
    if now>=lock:raise ValueError('Tiers official status refresh is locked')
    refreshed=refresh_official_injuries(session.get_bind(),season=pool['season'],week=pool['week'],slate='SUNDAY_MAIN',games=games,slate_lock_at=lock)
    return apply_saved_refresh(pool,refreshed,session,directory=directory,now=datetime.now(UTC))


def apply_saved_refresh(pool,refreshed,session,*,directory=None,now=None):
    snapshot=session.get(SourceSnapshot,refreshed['snapshot_id'])
    if snapshot is None or (snapshot.source_system,snapshot.dataset,snapshot.season,snapshot.week,str(snapshot.slate).upper())!=('nfl_official','official_injuries',pool['season'],pool['week'],'SUNDAY_MAIN'):raise ValueError('Official source snapshot scope mismatch')
    raw=Path(snapshot.artifact_path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=snapshot.content_sha256:raise ValueError('Official source content hash mismatch')
    with session.get_bind().connect() as connection:
        facts=[dict(r) for r in connection.execute(text('SELECT player_master_id,injury_status,evidence_json FROM public.pregame_player_context WHERE context_run_id=:run'),{'run':refreshed['context_run_id']}).mappings()]
    return apply_refresh(pool,{**refreshed,'source_content_sha256':snapshot.content_sha256,'source_uri':snapshot.source_uri},facts,directory=directory,now=now)
