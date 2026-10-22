"""All-player forecast diagnostics; review flags never rewrite model truth.

Ratios are transparent triage heuristics, not calibrated plausibility limits.
Hard errors are identity, chronology and accounting violations only.
"""
from collections import Counter
from copy import deepcopy
import math
from .evaluation_record import digest

VERSION='all_player_forecast_audit_v1'
CHANNELS=('pass_attempts','rush_attempts','targets')
EVENTS=dict(pass_attempts='official_pass_attempts',rush_attempts='official_rush_attempts',targets='targets')


def applicable(position):
    return ('pass_attempts','rush_attempts') if position=='QB' else ('rush_attempts','targets') if position in {'RB','WR','TE'} else ()


def number(value):
    if value is None or isinstance(value,bool):return None
    try:value=float(value)
    except (ValueError,TypeError):return None
    return value if math.isfinite(value) else None


def audit_inputs(actors,matrix,predictions,*,before_period):
    """One row per canonical actor, including non-modeled positions and absences."""
    errors=[];ids=[str(a['player_master_id']) for a in actors]
    if len(set(ids))!=len(ids):errors.append(dict(code='duplicate_canonical_actor'))
    rows={r['player_master_id']:r for r in matrix.get('rows',[])}
    preds={p['player_master_id']:p for p in predictions}
    if len(rows)!=len(matrix.get('rows',[])) or len(preds)!=len(predictions):errors.append(dict(code='duplicate_model_identity'))
    if set(preds)-set(ids) or set(rows)-set(ids):errors.append(dict(code='model_actor_outside_audit_universe'))
    output=[]
    for a in actors:
        pid=str(a['player_master_id']);row=rows.get(pid);p=preds.get(pid);findings=[];channels=[]
        if row and (row['period']!=before_period or any(v>=before_period for v in row.get('history_periods',[])+row.get('context_periods',[]))):
            errors.append(dict(code='future_or_wrong_period_features',player_master_id=pid))
        for channel in applicable(a['position']):
            f=(row or {}).get('features',{});mean=number(f.get(channel+'_mean3'));pred=number((p or {}).get('counts',{}).get(channel))
            metric=EVENTS[channel];known=number(f.get(f'event_{metric}_known3'));unknown=number(f.get(f'event_{metric}_unknown3'))
            weekly_known=number(f.get(channel+'_known3'))
            channels.append(dict(channel=channel,prior_observed_mean3=mean,raw_model_count=pred,event_known3=known,event_unknown3=unknown))
            if p and (pred is None or pred<0):errors.append(dict(code='invalid_model_count',player_master_id=pid,channel=channel))
            if known is not None and unknown is not None and (known<0 or unknown<0 or known+unknown!=3):
                errors.append(dict(code='invalid_event_coverage_mask',player_master_id=pid,channel=channel))
            # Zero weekly volume is not proof of actor-level PBP attribution.
            if mean is not None and mean>0 and weekly_known==3 and known is not None and known<3:
                findings.append(dict(code='incomplete_event_window',channel=channel,known_games=int(known),reason='Weekly observations exist; event measurement/attribution remains incomplete'))
            if mean is not None and mean>=1 and pred is not None and (pred<.5*mean or pred>2*mean):
                findings.append(dict(code='workload_ratio_review',channel=channel,ratio=pred/mean,reason='Outside 0.5–2 times prior observed mean; diagnostic only, no floor or penalty'))
            parts=[number((p or {}).get('components',{}).get(family,{}).get(channel)) for family in ('tree','neural')]
            if all(v is not None for v in parts) and abs(parts[0]-parts[1])>=2 and max(parts)>=2*max(min(parts),.01):
                findings.append(dict(code='family_disagreement',channel=channel,tree=parts[0],neural=parts[1]))
        output.append(dict(player_master_id=pid,name=a.get('name'),team=a['team'],position=a['position'],
            model_input_present=row is not None,raw_prediction_present=p is not None,channels=channels,findings=findings))
    result=dict(version=VERSION,before_period=before_period,scope='all supplied actors before user preferences',players=output,
        errors=errors,counts=dict(players=len(output),raw_model_rows=len(predictions),review_players=sum(bool(r['findings']) for r in output),
            findings=dict(Counter(f['code'] for r in output for f in r['findings']))),
        interpretation='Raw regressor diagnostics do not establish current-role eligibility or prepared slate readiness; review flags do not change projections or eligibility')
    result['sha256']=digest(result)
    return result


def audit_primary(players,counts,matrix,predictions,*,before_period):
    """Check the actual served counts and scores, retaining full-source residuals."""
    result=audit_inputs(counts['players'],matrix,predictions,before_period=before_period)
    actors={a['player_master_id']:a for a in counts['players']};by_id={p['player_master_id']:p for p in players}
    budgets=[]
    for team,budget in counts['teams'].items():
        if budget is None:continue
        for channel in CHANNELS:
            total=0.;unknown=0
            for a in counts['players']:
                if a['team']!=team:continue
                value=a['counts'].get(channel)
                if value is None:
                    unknown+=int(channel in applicable(a['position']));continue
                v=number(value)
                if v is None or v<0:result['errors'].append(dict(code='invalid_served_count',player_master_id=a['player_master_id'],channel=channel));continue
                total+=v
            available=number(budget.get(channel));rec=budget.get('reconciliation',{}).get(channel,{})
            residual=number(rec.get('unallocated'))
            if available is None and total>1e-7:
                result['errors'].append(dict(code='known_counts_without_team_budget',team=team,channel=channel))
            if available is not None and (total>available+1e-7 or residual is None or residual< -1e-7 or abs(total+residual-available)>1e-7):
                result['errors'].append(dict(code='team_count_accounting',team=team,channel=channel))
            budgets.append(dict(team=team,channel=channel,team_budget=available,known_player_sum=total,unallocated=residual,applicable_unknown_actors=unknown))
        if budget.get('targets') is not None and (budget.get('pass_attempts') is None or budget['targets']>budget['pass_attempts']+1e-7):
            result['errors'].append(dict(code='target_budget_exceeds_passes',team=team))
    for p in players:
        pid=p['player_master_id'];a=actors.get(pid,{});e=p.get('new_model_evidence',{});position=e.get('position') or a.get('position')
        value=p.get('conditional_mean');source=e.get('source')
        if value is not None and number(value) is None:result['errors'].append(dict(code='invalid_complete_score',player_master_id=pid))
        if value is not None and position in {'QB','RB','WR','TE'} and source!='factual_unavailable_zero':
            if any(a.get('counts',{}).get(c) is None for c in applicable(position)):
                result['errors'].append(dict(code='scored_unknown_required_count',player_master_id=pid))
    for row in result['players']:
        p=by_id.get(row['player_master_id']);a=actors[row['player_master_id']]
        row.update(native_pool_actor=p is not None,served_counts=a['counts'],world_activity=a.get('world_activity'),
            history_window_status=a.get('history_window_status'),current_role_evidence=a.get('current_role_evidence'),
            served_score=p.get('conditional_mean') if p else None,score_source=(p or {}).get('new_model_evidence',{}).get('source'),
            missing_evidence=(p or {}).get('missing_evidence',[]))
    result.update(team_accounting=budgets,status='errors' if result['errors'] else 'completed_with_review_flags' if result['counts']['review_players'] else 'completed',
        native_player_count=len(players),unknown_native_scores=sum(p.get('conditional_mean') is None for p in players))
    result=deepcopy(result)  # Later report formatting must not mutate this receipt.
    result.pop('sha256',None);result['sha256']=digest(result)
    return result
