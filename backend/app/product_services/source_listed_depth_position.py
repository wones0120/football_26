"""Current-at-document literal chart role and order, not confirmed game role."""
from copy import deepcopy
from .observed_depth_changes import VERSION as PARENT_VERSION,SPECIAL
from .evaluation_record import digest
from .factual_designation import clock

VERSION='source_listed_depth_position_v1'


def build_source_listed_depth_position(parent,*,cutoff):
    actual=clock(cutoff)
    if actual is None:raise ValueError('Explicit actual source cutoff required')
    if parent.get('version')!=PARENT_VERSION or parent.get('forecast')is not False or parent.get('evidence_use')!='postlock_descriptive_not_pregame_or_serving':raise ValueError('Reviewed literal depth source required')
    sources={};perteam={}
    for s in parent['provenance']['sources']:
        sid=s['snapshot_id'];observed,captured=clock(s['observed_at']),clock(s['captured_at'])
        if sid in sources or observed is None or captured is None or not observed<=captured<=actual:raise ValueError('Unique available source capture required')
        if (s['season'],s['week'])!=(parent['season'],parent['week']):raise ValueError('Depth capture scope differs')
        if not isinstance(s.get('source_uri'),str)or not s['source_uri']:raise ValueError('Original source URI required')
        sources[sid]=s
        for team in s['teams']:
            if team not in perteam or captured>perteam[team][0]:perteam[team]=(captured,[sid])
            elif captured==perteam[team][0]:perteam[team][1].append(sid)
    incoming={}
    for c in parent['comparisons']:
        sid=c['current_snapshot_id']
        if sid not in sources or sid in incoming:raise ValueError('Unique current comparison source required')
        incoming[sid]=c
    facts=[];unknown=[];frames=[]
    for team,(_,ids)in sorted(perteam.items()):
        if len(ids)!=1:
            unknown.append(dict(team=team,reason='ambiguous_simultaneous_latest_capture',source_snapshot_ids=ids));continue
        sid=ids[0];s=sources[sid];c=incoming.get(sid)
        if c is None:
            unknown.append(dict(team=team,source_snapshot_id=sid,reason='latest_frame_not_reconstructible_from_reviewed_comparison'));continue
        rows=[r for r in c['matched_roles']+c['newly_observed_roles']if r['team']==team];seen=set();documents=set()
        for r in rows:
            key=(r['source_player_id'],r['source_position'],r['source_slot'])
            if key in seen:raise ValueError('Unique literal current role key required')
            seen.add(key);document=clock(r['document_at'])
            if document is None or document>clock(s['captured_at']):raise ValueError('Current source document unavailable')
            documents.add(document)
            rank=r['rank']
            if rank is not None and(type(rank)is not int or rank<1):raise ValueError('Positive literal depth order or unknown required')
            unit='special_teams'if r['source_position']in SPECIAL else'non_special_teams'
            if r['unit']!=unit:raise ValueError('Literal special-unit classification differs')
            facts.append(dict(team=team,source_player_id=r['source_player_id'],player_master_id=r['player_master_id'],source_position=r['source_position'],source_slot=r['source_slot'],source_depth_order=rank,
                source_listed_role=dict(literal_position=r['source_position'],literal_slot=r['source_slot'],listed_order=rank),unit=unit,source_snapshot_id=sid,source_row=r['source_row'],document_at=r['document_at'],observed_at=s['observed_at'],captured_at=s['captured_at'],source_uri=s['source_uri'],
                current_meaning='Source-listed chart role/order current at this document, not confirmed upcoming dressing or workload',effective_season_week=None,target_game_applicability=None,expected_workload_share=None,primary_offense_starter=None))
        if len(documents)>1:raise ValueError('Latest-per-team document selection differs')
        unresolved=[deepcopy(r)for r in parent['unkeyed_source_roles']if r['source_snapshot_id']==sid and r['team']==team]
        unknown.extend(unresolved);frames.append(dict(team=team,source_snapshot_id=sid,document_at=next(iter(documents)).isoformat()if documents else None,source_native_role_rows=len(rows),unkeyed_source_rows=len(unresolved),provider_football_completeness='unknown'))
    core=dict(version=VERSION,candidate_ids=['G17-M05'],capture_scope=dict(season=parent['season'],week=parent['week'],meaning='Indexed source capture scope only; not independently proven provider effective-week truth'),frames=frames,role_facts=facts,unknown_source_roles=unknown,inherited_identity_requests=deepcopy(parent['identity_review_requests']),definition='Literal sourced current-at-document team/position/slot chart order and chart-role expectation; rank1 is not automatically a primary offensive starter')
    return dict(**core,semantic_sha256=digest(core),model_consumed=False,optimizer_consumed=False,pregame_serving_eligible=False,evidence_use='source_reported_chart_expectation_not_dressing_health_or_opportunity_forecast')


def load_reviewed_depth_parent(ref,*,cutoff):
    from pathlib import Path
    from datetime import datetime,UTC
    import json,hashlib
    from . import observed_depth_changes
    p=Path(ref['path']).resolve();actual=clock(cutoff)
    if p.parent!=Path('artifacts/observed_depth_changes').resolve()or p.name!=ref['sha256']+'.json'or not 0<ref['bytes']<=4*1024*1024:raise ValueError('Managed bounded depth parent required')
    b=p.read_bytes()
    if len(b)!=ref['bytes']or hashlib.sha256(b).hexdigest()!=ref['sha256']:raise ValueError('Reviewed depth bytes differ')
    x=json.loads(b);derived=clock(x['provenance'].get('actual_derived_at'))
    if actual is None or actual>datetime.now(UTC)or derived is None or derived>actual:raise ValueError('Actual depth derivation/read clocks unavailable')
    if x['provenance'].get('producer_sha256')!=hashlib.sha256(Path(observed_depth_changes.__file__).read_bytes()).hexdigest():raise ValueError('Reviewed depth measurement producer differs')
    keys=('version','season','week','comparisons','unkeyed_source_roles')
    if digest({k:x[k]for k in keys})!=x['semantic_sha256']:raise ValueError('Depth parent semantic binding differs')
    return x
