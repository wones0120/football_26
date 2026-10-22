"""Declared count sensitivity in matched non-TD linear DraftKings components.

This is not a decomposition/training replacement for the FP model. The frozen
base is assumed anchored at reference counts. Only supported matched components
change; its undecomposed remainder is held fixed and may be inconsistent.
"""
from copy import deepcopy
import math

import pandas as pd
import numpy as np
from uuid import UUID

from .evaluation_record import digest
from .opportunity_history_evidence import source_history

VERSION='matched_linear_count_response_v1'
WEIGHTS={'passing_yards':.04,'passing_interceptions':-1.,'rushing_yards':.1,'receptions':1.,'receiving_yards':.1}


def _number(value):
    if isinstance(value,(bool,np.bool_)):return None
    try:
        n=float(value)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None


def _rate(rows,numerator,denominator,*,bounded=False):
    """Same row cohort for numerator/denominator; never independent null sums."""
    pairs=[];missing=[];zero_missing=[]
    for r in rows.to_dict('records'):
        n=_number(r.get(numerator));d=_number(r.get(denominator))
        identity={k:r.get(k) for k in ('player_master_id','source_player_id','team','period','source_id')}
        if d==0 and n is None:
            zero_missing.append(identity);continue
        if d is None or d<0 or n is None:
            missing.append(identity);continue
        if d==0 and n!=0 or bounded and not 0<=n<=d:
            return dict(status='inconsistent_source_pair',value=None,numerator=numerator,denominator=denominator,invalid_row=identity)
        pairs.append((n,d,identity))
    numerator_sum=sum(x[0] for x in pairs);denominator_sum=sum(x[1] for x in pairs)
    return dict(status='supported_matched_prior_rate' if denominator_sum>0 and not missing else 'unavailable_matched_rate',
        value=numerator_sum/denominator_sum if denominator_sum>0 and not missing else None,
        numerator=numerator,denominator=denominator,numerator_sum=numerator_sum,denominator_sum=denominator_sum,
        matched_source_rows=[p[2] for p in pairs],missing_pairs=missing,zero_denominator_missing_numerator=zero_missing,
        interpretation='Prior observed conditional rate, not calibrated efficiency or participation probability')


def efficiency_receipt(weekly,reference,*,before_period,cutoff):
    prior=source_history(weekly,before_period=before_period,cutoff=cutoff)
    if prior.loc[prior.player_master_id.notna()].duplicated(['player_master_id','period']).any():
        raise ValueError('Component efficiency contains duplicate canonical player-game rows')
    teams={}
    for team in reference['teams']:
        history=prior.loc[prior.team.eq(team)]
        periods=sorted(history.period.unique())[-8:]
        full=history.loc[history.period.isin(periods)]
        teams[team]=dict(periods=[int(p) for p in periods],
            passing_yards_per_attempt=_rate(full,'passing_yards','pass_attempts'),
            completions_per_attempt=_rate(full,'completions','pass_attempts',bounded=True),
            source_population='Full source including unmapped actors; before user preferences')
    actors={}
    for actor in reference['players']:
        pid=actor['player_master_id'];team=actor['team'];rates={}
        for output,numerator,channel,bounded in [('rushing_yards_per_attempt','rushing_yards','rush_attempts',False),
                ('receptions_per_target','receptions','targets',True),('receiving_yards_per_target','receiving_yards','targets',False),
                ('interceptions_per_attempt','passing_interceptions','pass_attempts',True)]:
            periods=(actor.get('raw_history',{}).get(channel) or {}).get('periods',[])
            matched=prior.loc[prior.player_master_id.eq(pid)&prior.team.eq(team)&prior.period.isin(periods)]
            rates[output]=_rate(matched,numerator,channel,bounded=bounded)
            rates[output]['requested_periods']=periods
            if len(matched)!=len(periods):rates[output].update(status='missing_original_component_rows',value=None)
        actors[pid]=dict(team=team,rates=rates)
    result=dict(version=VERSION,before_period=before_period,teams=teams,actors=actors,
        definitions=dict(scoring='DK PPR linear non-TD only',weights=WEIGHTS,
            window='Full-team last8 observed prior games; actor exact same-team count-reference observed role window',
            no_inferred_zero=True,no_cross_team_history=True,preferences_not_inputs=True))
    result['semantic_sha256']=digest(result)
    return result


def linear_vector(counts,efficiency):
    """One physical passing/receiving-yard and catch budget, no upward donation."""
    players={str(p['player_master_id']):p for p in counts['players']}
    if len(players)!=len(counts['players']):raise ValueError('Duplicate canonical component count actor')
    if set(players)!=set(efficiency['actors']):raise ValueError('Component count universe differs from matched efficiency universe')
    if set(counts['teams'])!=set(efficiency['teams']):raise ValueError('Component team universe changed')
    for pid,p in players.items():
        UUID(pid)
        if p['team']!=efficiency['actors'][pid]['team']:raise ValueError('Component actor changed canonical team')
    for team,budget in counts['teams'].items():
        for channel in ('pass_attempts','rush_attempts','targets'):
            values=[(budget or {}).get(channel)]+[p['counts'].get(channel) for p in players.values() if p['team']==team]
            if any(v is not None and (_number(v) is None or _number(v)<0) for v in values):
                raise ValueError('Invalid negative/nonfinite physical count')
            known=sum(v for v in values[1:] if v is not None)
            if known>0 and values[0] is None or values[0] is not None and known>values[0]+1e-6:
                raise ValueError('Known actor count allocation exceeds full-team budget')
        if (budget or {}).get('targets') is not None and ((budget or {}).get('pass_attempts') is None or budget['targets']>budget['pass_attempts']+1e-6):
            raise ValueError('Target budget exceeds physical pass attempts')
    outputs={pid:dict(team=p['team'],components=dict.fromkeys(WEIGHTS),reasons=[]) for pid,p in players.items()}
    budgets={}
    for team,budget in counts['teams'].items():
        rates=efficiency['teams'][team];passes=_number((budget or {}).get('pass_attempts'))
        ypa=rates['passing_yards_per_attempt']['value'];cpa=rates['completions_per_attempt']['value']
        budgets[team]=dict(passing_yards=passes*ypa if passes is not None and ypa is not None else None,
            receptions=passes*cpa if passes is not None and cpa is not None else None,reconciliation={})
    for pid,p in players.items():
        team=p['team'];rates=efficiency['actors'][pid]['rates'];components=outputs[pid]['components']
        channels=p['counts']
        for output,channel,rate in [('rushing_yards','rush_attempts','rushing_yards_per_attempt'),
                ('receptions','targets','receptions_per_target'),('receiving_yards','targets','receiving_yards_per_target'),
                ('passing_interceptions','pass_attempts','interceptions_per_attempt')]:
            count=_number(channels.get(channel));value=rates[rate]['value']
            if count==0:components[output]=0.  # Verified forecast zero opportunities, not an imputed rate.
            elif count is not None and value is not None:components[output]=count*value
        passes=_number(channels.get('pass_attempts'));ypa=efficiency['teams'][team]['passing_yards_per_attempt']['value']
        if passes==0:components['passing_yards']=0.
        elif passes is not None and ypa is not None:components['passing_yards']=passes*ypa
    for team,budget in budgets.items():
        members=[r for r in outputs.values() if r['team']==team]
        for output,team_channel in [('receiving_yards','passing_yards'),('receptions','receptions')]:
            known=[r for r in members if r['components'][output] is not None]
            available=budget[team_channel]
            raw=sum(r['components'][output] for r in known)
            if available is None:
                for r in known:r['components'][output]=None;r['reasons'].append(output+': shared team budget unavailable')
                budget['reconciliation'][output]=dict(status='unavailable',budget=None,unallocated=None);continue
            negative=sum(min(0.,r['components'][output]) for r in known)
            positive=sum(max(0.,r['components'][output]) for r in known)
            if available-negative<0:
                for r in known:r['components'][output]=None;r['reasons'].append(output+': signed shared budget cannot support known allocation')
                budget['reconciliation'][output]=dict(status='unavailable_signed_budget',budget=available,unallocated=None);continue
            factor=min(1.,(available-negative)/positive) if positive>0 else 1.
            for r in known:
                if r['components'][output]>0:r['components'][output]*=factor
            allocated=sum(r['components'][output] for r in known)
            budget['reconciliation'][output]=dict(status='downward_only',budget=available,raw_sum=raw,downward_factor=factor,
                allocated=allocated,unallocated=available-allocated,unknown_actors=sum(r['components'][output] is None for r in members))
        passing_sum=sum(r['components']['passing_yards'] for r in members if r['components']['passing_yards'] is not None)
        budget['passing_yard_residual']=budget['passing_yards']-passing_sum if budget['passing_yards'] is not None else None
        if budget['passing_yard_residual'] is not None and budget['passing_yard_residual'] < -1e-6:
            raise ValueError('QB passing yards exceed full-source physical team passing budget')
    return dict(players=outputs,teams=budgets)


def component_response(weekly,reference,new,base_means,*,before_period,cutoff,efficiency=None):
    """Signed partial-component delta; no count bonus or total-FP scaling."""
    if reference.get('before_period')!=before_period or new.get('before_period')!=before_period:
        raise ValueError('Component reference/current forecast period mismatch')
    rates=deepcopy(efficiency) if efficiency is not None else efficiency_receipt(weekly,reference,before_period=before_period,cutoff=cutoff)
    if rates.get("before_period")!=before_period:raise ValueError("Frozen efficiency period mismatch")
    before=linear_vector(reference,rates);after=linear_vector(new,rates);actors=[]
    activity={str(p['player_master_id']):p.get('world_activity') for p in new['players']}
    for pid,old in before['players'].items():
        updated=after['players'][pid]
        supported=[k for k in WEIGHTS if old['components'][k] is not None and updated['components'][k] is not None]
        old_points=sum(old['components'][k]*WEIGHTS[k] for k in supported)
        new_points=sum(updated['components'][k]*WEIGHTS[k] for k in supported)
        delta=new_points-old_points if supported else None;base=_number(base_means.get(pid))
        mean=base+delta if base is not None and delta is not None else base
        if activity.get(pid) is False:
            mean=0.  # Factual OUT overrides all production, not just supported linear components.
        if mean is not None and mean<0:
            raise ValueError('Declared component response produces invalid negative full mean for '+pid)
        remainder=base-old_points if base is not None and supported else None
        actors.append(dict(player_master_id=pid,team=old['team'],world_activity=activity.get(pid),supported_components=supported,
            unchanged_unsupported_components=[k for k in WEIGHTS if k not in supported],reference_components=old['components'],
            new_components=updated['components'],reference_linear_points=old_points if supported else None,
            new_linear_points=new_points if supported else None,delta_points=delta,linear_component_delta_points=delta,
            conditional_delta_points=mean-base if mean is not None and base is not None else None,
            inactive_override=activity.get(pid) is False,base_fp=base,conditional_mean=mean,
            anchoring_diagnostic=remainder,anchor_inconsistency=remainder is not None and remainder<0,
            anchoring_meaning='Base FP minus supported reference linear points is an anchoring diagnostic, NOT measured TD/bonus/fumble/nonlinear decomposition',
            assumption='Frozen base FP anchored at reference counts; unmatched and undecomposed contributions stay unchanged',
            reasons=old['reasons']+updated['reasons']))
    result=dict(version=VERSION,before_period=before_period,reference_count_sha256=digest(reference),new_count_sha256=digest(new),
        efficiency_receipt=rates,reference_shared_budgets=before['teams'],new_shared_budgets=after['teams'],players=actors,
        response_ancestry='Single signed matched linear-component difference; no legacy total-FP elasticity added',
        probability_status='Conditional first approximation; no fitted total-FP model or calibrated role/TD probabilities')
    def rate_semantics(value):
        if isinstance(value,dict):return {k:rate_semantics(v) for k,v in value.items() if k not in {'source_id','semantic_sha256'}}
        if isinstance(value,list):return [rate_semantics(v) for v in value]
        return value
    def count_semantics(value):
        return dict(version=value.get('version'),before_period=value['before_period'],teams=value['teams'],
            model_contract=value.get('team_budget_model_contract') or value.get('model'),
            availability_conditions={k:(value.get('availability_conditions') or {}).get(k) for k in ('version','semantic_sha256')},
            players=[{k:deepcopy(p.get(k)) for k in ('player_master_id','team','position','counts','conditional_on','world_activity')} for p in sorted(value['players'],key=lambda p:p['player_master_id'])])
    result['semantic_values']=dict(version=VERSION,before_period=before_period,reference=count_semantics(reference),
        new=count_semantics(new),efficiency=rate_semantics(rates),players=deepcopy(actors),
        reference_shared_budgets=before['teams'],new_shared_budgets=after['teams'],response_ancestry=result['response_ancestry'])
    result['semantic_sha256']=digest(result['semantic_values'])
    return result
