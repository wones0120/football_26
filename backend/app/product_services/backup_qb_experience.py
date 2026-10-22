"""Observed prior same-team QB experience attached to a sourced backup role."""
from copy import deepcopy
from datetime import datetime,UTC
import math
from uuid import UUID
from .evaluation_record import digest
from .factual_designation import clock
from .active_workload_distributions import VERSION as ACTIVE_VERSION

VERSION='observed_backup_qb_experience_v1'


def build_backup_qb_experience(roles,history,*,season,week,cutoff):
    decision=clock(cutoff)
    if decision>datetime.now(UTC):raise ValueError('Nonfuture actual cutoff required')
    if roles.get('evidence_use')!='postlock_descriptive_not_pregame_or_serving' or history.get('version')!=ACTIVE_VERSION:raise ValueError('Reviewed descriptive role/history contracts required')
    if clock(roles['actual_derived_at'])>decision or clock(history['provenance']['actual_publication_at'])>decision:raise ValueError('Input unavailable at cutoff')
    actors={};latest={}
    for a in roles['extracted']['actors']:
        pid=str(UUID(a['player_master_id']))
        if pid!=a['player_master_id'] or pid in actors:raise ValueError('Unique canonical role actor required')
        actors[pid]=a
    for fact in roles['extracted']['facts']:
        if fact.get('kind')!='role' or fact.get('position')!='QB' or fact.get('season')!=season or fact.get('week')!=week:continue
        if fact.get('source_position')!='QB' or fact.get('source_unit')!='QB':continue
        times=[clock(fact[k]) for k in ('observed_at','received_at','effective_at')]
        if any(t>decision for t in times):raise ValueError('Future role fact')
        pid=fact['player_id'];actor=actors[pid]
        if actor['team']!=fact['team'] or actor['position']!='QB':raise ValueError('Backup identity/role scope differs')
        at=times[2];previous=latest.get(pid)
        if previous is not None and at==previous[0] and fact['role']!=previous[1]['role']:raise ValueError('Conflicting current QB role')
        if previous is None or at>previous[0]:latest[pid]=(at,fact)
    seen=set();by_actor={}
    for row in history['rows']:
        if row['season']!=season or row.get('source_position')!='QB':continue
        key=(row['player_master_id'],row['team'])
        if key in by_actor:raise ValueError('Duplicate same-team QB history')
        prior=[]
        for log in row['logs']:
            if type(log['week']) is not int or not 1<=log['week']<=18:raise ValueError('Valid REG history week required')
            if log['week']>=week:continue
            n=log['counts']['pass_attempts']
            if n is not None and (type(n) not in (int,float) or not math.isfinite(n) or n<0 or int(n)!=n):raise ValueError('Nonnegative official attempts required')
            prior.append(log)
            k=(row['player_master_id'],row['team'],log['week'])
            if k in seen:raise ValueError('Duplicate QB observed game')
            seen.add(k)
        by_actor[key]=dict(row,logs=prior)
    output=[]
    for pid,(_,fact) in sorted(latest.items()):
        if fact['role']!='expected_backup':continue
        actor=actors[pid];r=by_actor.get((pid,actor['team']));logs=deepcopy(r['logs']) if r else []
        known=[];unknown_participation=0;proven=0
        for log in logs:
            n=log['counts']['pass_attempts']
            if n is not None:known.append(n)
            positive=log['positive_offensive_participation_proven'] or (n is not None and n>0)
            proven+=positive
            unknown_participation+=not positive
        missing_positive=[r for r in history.get('positive_participants_missing_weekly_rows',[]) if r['season']==season and r['week']<week and r['team']==actor['team'] and r['player_master_id']==pid]
        exact_attempts=sum(known) if logs and len(known)==len(logs) and not missing_positive else None
        output.append(dict(player_master_id=pid,source_player_id=actor['source_player_id'],team=actor['team'],role_proof=deepcopy(fact),observed_prior_qb_logs=len(logs),
            official_pass_attempts=exact_attempts,known_attempt_sum=sum(known) if known else None,known_attempt_logs=len(known),unknown_attempt_logs=len(logs)-len(known),
            proven_participating_games=proven if logs and not unknown_participation and not missing_positive else None,proven_participating_games_lower_bound=proven,
            unknown_participation_logs=unknown_participation,positive_participants_missing_weekly_rows=missing_positive,logs=logs))
    basis=dict(version=VERSION,candidate_id='G18-M02',season=season,week=week,rows=output,estimand='Observed prior same-team/current-season source-QB logs and proven participation; not career completeness or future starter share')
    return basis|dict(semantic_sha256=digest(basis),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,model_consumed=False,optimizer_consumed=False)
