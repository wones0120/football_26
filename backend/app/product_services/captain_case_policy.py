"""Explicit user opportunity preferences and whole-roster case diagnostics."""
import math


def preference(params):
    raw=params.get('scenario_role_preference') or {}
    enabled=raw.get('enabled',False)
    if not isinstance(enabled,bool):raise ValueError('Backup involvement preference must be true/false')
    result=dict(version='captain_backup_involvement_preference_v1',enabled=enabled,
        category='user_preference_not_model_truth',rb_min_opportunities=6.,receiver_min_targets=3.)
    for key in ('rb_min_opportunities','receiver_min_targets'):
        value=raw.get(key,result[key])
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
            raise ValueError('Involvement cutoffs must be finite nonnegative numbers')
        result[key]=float(value)
    return result


def assessment(actor, policy):
    counts=actor['counts'];position=actor['position']
    value=(counts.get('rush_attempts') or 0)+(counts.get('targets') or 0) if position=='RB' else counts.get('targets')
    cutoff=policy['rb_min_opportunities'] if position=='RB' else policy['receiver_min_targets']
    applies=policy['enabled'] and actor.get('world_activity') is not False and actor.get('canonical_role')=='expected_backup' and position in {'RB','WR','TE'}
    missing=applies and (counts.get('targets') is None or (position=='RB' and counts.get('rush_attempts') is None))
    if missing:value=None
    excluded=applies and (missing or value<cutoff)
    return dict(player_master_id=actor['player_master_id'],name=actor.get('name'),position=position,
        canonical_role=actor.get('canonical_role'),counts=counts.copy(),value=value,cutoff=cutoff,
        unit='carries + targets' if position=='RB' else 'targets',excluded=bool(excluded),
        category='user_preference' if excluded else 'model_assessment_retained',
        reason=('Missing post-condition opportunity evidence' if missing else 'Below explicit backup involvement cutoff') if excluded else 'Passes preference or preference does not apply',
        injury_order='Uses frozen post-availability counts/current role. Source-backed role/forecast changes must occur in Prepare first; injury flags and user exclusions do not waive cutoffs or donate workload.',
        conditional_on=actor.get('conditional_on'),current_role_evidence=actor.get('current_role_evidence'))


def metrics(roster, worlds, optima, target):
    values=[]
    for world in worlds:
        score=sum(world['player_scores'][p['player_master_id']]*(1.5 if p['role']=='CPT' else 1) for p in roster)
        ratio=score/optima[world['world_id']]
        values.append(dict(world_id=world['world_id'],lineup_score=score,best_legal_score=optima[world['world_id']],
            capture_ratio=ratio,competitive=ratio>=target-1e-7))
    covered=sum(v['competitive'] for v in values)
    return dict(case_evaluations=values,competitive_cases=covered,total_cases=len(worlds),capture_target=target,
        mean_capture_ratio=sum(v['capture_ratio'] for v in values)/len(worlds),
        worst_capture_ratio=min(v['capture_ratio'] for v in values),
        selection_value=(len(worlds)+1)*covered+sum(v['capture_ratio'] for v in values),
        interpretation='Case coverage count under unknown likelihood; not a win probability. Coverage first, mean relative capture only breaks ties.')


def describe(roster, pool):
    result=[]
    for member in roster:
        p=pool[member['player_master_id']];role=member['role']
        result.append(dict(**member,name=p.get('name'),team=p.get('player_team'),position=p.get('position'),
            salary=float(p['salary'])*(1.5 if role=='CPT' else 1)))
    return result
