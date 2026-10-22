"""Feature-only extraction from immutable weekly-roster/depth snapshots.

No captures, forecasts or name joins. Supplied native-ID aliases remain the
identity authority; unresolved or ambiguous aliases are retained for review.
"""
from copy import deepcopy
import csv,math
from pathlib import Path
from uuid import UUID
from .factual_designation import clock
from .evaluation_record import digest
from ..services.source_capture import verify_snapshot_artifact

VERSION='retained_role_source_features_v1'
UNITS={'OL':{'C','OC','G','OG','OT','T','LT','RT','LG','RG','OL'},'DL':{'DL','DE','DT','NT','LDE','RDE','LDT','RDT'},'LB':{'LB','ILB','OLB','MLB','LLB','RLB','WLB','SLB','LILB','RILB'},'S':{'S','FS','SS'},'CB':{'CB','LCB','RCB','NB'},'RB':{'RB','HB','FB'}}


def _unit(position):
    return next((k for k,v in UNITS.items() if position in v),position)


def _verified_rows(snapshot,*,dataset,season,week,cutoff):
    if snapshot.dataset!=dataset or snapshot.season!=season or snapshot.week!=week:raise ValueError('Role source snapshot scope differs')
    if clock(snapshot.observed_at)>clock(snapshot.captured_at) or clock(snapshot.captured_at)>clock(cutoff):raise ValueError('Role snapshot unavailable at cutoff')
    verify_snapshot_artifact(snapshot)
    if snapshot.byte_count>4*1024*1024:raise ValueError('Role snapshot exceeds bounded source size')
    with Path(snapshot.artifact_path).open(newline='') as f:rows=list(csv.DictReader(f))
    if len(rows)!=snapshot.row_count:raise ValueError('Role source row cardinality differs')
    return rows


def extract_retained_role_sources(roster_snapshot,depth_snapshot,canonical_ids,*,season,week,teams,cutoff):
    """Preserve all provider roster actors before any salary/user filtering."""
    teams=set(teams);roster=_verified_rows(roster_snapshot,dataset='weekly_rosters',season=season,week=week,cutoff=cutoff)
    depth=_verified_rows(depth_snapshot,dataset='player_depth_charts',season=season,week=week,cutoff=cutoff)
    actors={};native_rows={};facts=[];requests=[];scope_exclusions=[];unresolved_teams=set();aliases={}
    for key,values in canonical_ids.items():
        values=[values] if isinstance(values,str) else list(values or [])
        aliases[str(key)]={str(UUID(str(v))) for v in values}
    for index,row in enumerate(roster):
        team=row.get('team')
        if team not in teams:continue
        try:scoped=int(row['season'])==season and int(row['week'])==week and row.get('game_type')=='REG'
        except (ValueError,TypeError,KeyError):scoped=False
        if not scoped:raise ValueError('Roster row type/period differs from captured scope')
        native=row.get('gsis_id') or None;matches=aliases.get(native,set())
        if len(matches)!=1:
            requests.append(dict(source_player_id=native,team=team,source_row=index,reason='ambiguous_native_alias' if len(matches)>1 else 'unresolved_native_alias'));unresolved_teams.add(team);continue
        pid=next(iter(matches));position=row.get('position') or 'UNKNOWN'
        if pid in actors:raise ValueError('Duplicate canonical actor in full provider roster')
        actors[pid]=dict(player_master_id=pid,team=team,position=position,source_player_id=native)
        native_rows[native]=actors[pid]
        facts.append(dict(player_id=pid,team=team,position=position,season=season,week=week,kind='roster_status',status=row.get('status'),
            source='retained_nflverse_weekly_rosters',source_ids=[roster_snapshot.snapshot_id,str(index)],source_uri=roster_snapshot.source_uri,
            observed_at=clock(roster_snapshot.observed_at).isoformat(),received_at=clock(roster_snapshot.captured_at).isoformat()))
    latest={}
    for row in depth:
        if row.get('team') not in teams:continue
        try:observed=clock(row['dt'])
        except (KeyError,TypeError,ValueError):continue
        if observed>clock(cutoff) or observed>clock(depth_snapshot.captured_at):continue
        latest[row['team']]=max(latest.get(row['team'],observed),observed)
    for index,row in enumerate(depth):
        team=row.get('team')
        if team not in teams:continue
        try:observed=clock(row['dt']);rank=float(row['pos_rank'])
        except (KeyError,ValueError,TypeError):continue
        if observed!=latest.get(team) or not math.isfinite(rank) or rank<1 or rank!=int(rank):continue
        native=row.get('gsis_id');actor=native_rows.get(native)
        if actor is None:
            requests.append(dict(source_player_id=native,team=team,source_row=index,reason='depth_actor_not_resolved_in_scoped_roster'));continue
        source_position=str(row.get('pos_abb') or '').upper().replace('PK','K')
        source_unit=_unit(source_position);roster_unit=_unit(actor['position'])
        if source_position in {'KR','PR','H'}:
            scope_exclusions.append(dict(source_player_id=native,player_master_id=actor['player_master_id'],team=team,depth_slot=source_position,reason='alternate_special_teams_depth_slot_not_primary_position'));continue
        compatible=(source_unit==roster_unit or (actor['position']=='DB' and source_unit in {'CB','S'}) or {source_unit,roster_unit}=={'LB','DL'})
        if actor['team']!=team or not compatible:
            requests.append(dict(source_player_id=native,team=team,source_row=index,reason='depth_roster_team_or_position_conflict'));continue
        base=dict(player_id=actor['player_master_id'],team=team,position=actor['position'],season=season,week=week,source='retained_nflverse_depth_chart',
            source_ids=[depth_snapshot.snapshot_id,str(index)],source_uri=depth_snapshot.source_uri,source_position=source_position,source_unit=source_unit,roster_position=actor['position'],
            observed_at=observed.isoformat(),received_at=clock(depth_snapshot.captured_at).isoformat(),effective_at=observed.isoformat(),depth_slot=row.get('pos_slot'))
        facts.append(dict(base,kind='depth_role',depth_position=int(rank)))
        facts.append(dict(base,kind='role',role='expected_starter' if rank==1 else 'expected_backup'))
    coverage={team:dict(complete=False,season=season,week=week,player_master_ids=sorted(pid for pid,a in actors.items() if a['team']==team),source_refs=[roster_snapshot.snapshot_id],
        observed_at=clock(roster_snapshot.observed_at).isoformat(),received_at=clock(roster_snapshot.captured_at).isoformat(),provider_rows_exhaustively_processed=True,
        native_aliases_complete=team not in unresolved_teams,missing_reason='Provider source universe processed; independent official full-team roster completeness not certified') for team in sorted(teams)}
    result=dict(version=VERSION,season=season,week=week,actors=sorted(actors.values(),key=lambda a:a['player_master_id']),facts=facts,roster_coverage=coverage,
        identity_review_requests=requests,role_scope_exclusions=scope_exclusions,forecast=False,model_consumed=False,optimizer_consumed=False)
    semantic=dict(version=VERSION,season=season,week=week,actors=result['actors'],facts=sorted([{k:v for k,v in f.items() if k not in {'source_ids','observed_at','received_at'}} for f in facts],key=digest),roster_coverage={t:{k:v for k,v in c.items() if k not in {'source_refs','observed_at','received_at'}} for t,c in coverage.items()},identity_review_requests=sorted([{k:v for k,v in q.items() if k!='source_row'} for q in requests],key=digest),role_scope_exclusions=sorted(scope_exclusions,key=digest))
    result['semantic_measurements_sha256']=digest(semantic)
    result['provenance']=dict(decision_cutoff_at=str(cutoff),source_snapshots=[dict(snapshot_id=s.snapshot_id,content_sha256=s.content_sha256,observed_at=str(s.observed_at),captured_at=str(s.captured_at)) for s in (roster_snapshot,depth_snapshot)])
    return result
