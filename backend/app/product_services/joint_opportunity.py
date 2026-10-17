"""Opt-in, uncalibrated opportunity-supported lineup upside sensitivity.

A roster is never banned for teammates. Conditional means are unchanged. Only
existing individual-tail *credit* competes for shared normalized touch capacity.
This is neither a joint P90 nor a fitted scoring/event model.
"""
from collections import defaultdict
import math
import numpy as np
import pulp
from scipy.optimize import linprog
from .analyst_shadow import digest

POLICY='opportunity_supported_upside_v1'
PARAM='analyst_joint_opportunity_enabled'
TAIL_WEIGHT=.35


def pid(row):return str(row.get('player_id',row.get('player_master_id')))
def team(row):return row.get('player_team',row.get('team'))
def finite(value):return type(value) in (int,float) and math.isfinite(value) and value>=0


def prepare_world(world,source_rows,packet=None):
    from .scenario_allocation import measurement
    declared={p['player_master_id']:p for p in (packet or {}).get('players',[])}
    original={pid(r):r for r in source_rows};groups=defaultdict(list);costs={};missing=[]
    for key,row in original.items():
        if row['position'] not in {'QB','RB','WR','TE'}:continue
        if not team(row):continue
        costs[key]={}
        for channel in ('targets','carries'):
            if channel=='targets' and row['position']=='QB':continue # QB pass is the SAME receiver event, not another target.
            value,lineage=measurement(declared.get(key,row),channel)
            if value is None:missing.append(dict(player_master_id=key,channel=channel));continue
            groups[(team(row),channel)].append((key,value,lineage))
    budgets=[]
    for (t,channel),members in sorted(groups.items()):
        values={key:value for key,value,_ in members};factor=1.0;ratios={}
        for key in values:
            for change in world.get('moments',{}).get(key,{}).get('changes',[]):
                allocation=change.get('opportunity_budget')
                if allocation:factor=float(allocation['pass_ratio' if channel=='targets' else 'rush_ratio'])
                assumption=change.get('assumption') or {}
                applies=('targets' if assumption.get('kind') in {'passing_volume','target_concentration'} else assumption.get('workload','carries'))==channel
                if applies and assumption:
                    if assumption['kind'] in {'passing_volume','rushing_volume'}:factor=float(change['ratio'])
                    else:ratios[key]=ratios.get(key,1)*float(change['ratio'])
        paired=world.get('paired_opportunity_budget') or {}
        if paired.get('channel')==channel:
            for key,share in paired.get('base_shares',{}).items():
                if share>0:ratios[key]=paired['conditional_shares'][key]/share
        amounts={key:value*factor*ratios.get(key,1) for key,value in values.items()}
        totals=[float(r['team_'+channel+'_mean_3'])*factor for r in original.values() if team(r)==t and finite(r.get('team_'+channel+'_mean_3')) and r.get('team_'+channel+'_mean_3_available') is not False]
        attributed=sum(amounts.values());denominator=max([attributed,*totals],default=0)
        if denominator<=0:continue
        budget_id=t+':'+channel
        for key,amount in amounts.items():costs[key][budget_id]=amount/denominator
        budgets.append(dict(budget_id=budget_id,team=t,channel=channel,capacity=1.0,attributed_share=sum(amounts.values())/denominator,unattributed_share=max(0,1-attributed/denominator),attributed_amount=attributed,denominator=denominator,unit='normalized historical/attributed opportunity units; not forecast NFL attempts',basis='max of attributed source total and available observed team total',conditional_team_volume_factor=factor,member_player_master_ids=sorted(values),partial_coverage=any(m['player_master_id'] in original and team(original[m['player_master_id']])==t and m['channel']==channel for m in missing)))
    book=dict(policy_id=POLICY,scenario_id=world['scenario_id'],budgets=budgets,costs=costs,missing_measurements=missing,source_pool_sha256=digest(source_rows),packet_sha256=digest(packet or {}),probability_status='uncalibrated deterministic sensitivity; no calibrated probabilities or joint percentile',td_budget_status='No supported player scoring/goal-line TD budget fitted; efficiency/TD branches remain conditional unknowns.',assumption='Individual fantasy spread is tested as unit-elastic proportional touch demand. Tail credit can consume remaining team capacity; unselected players need not retain baseline shares, so concentration is a conditional upside path, never an absence fact.',unknown_policy='Missing opportunity data receives no invented zero workload or roster ban; its existing tail credit is unverified and reported.',qb_receiver_event_policy='Receiver targets counted once; QB passing and receiving fantasy points can benefit from the same event. QB rushing competes for carries.',captain_policy='1.5 applies to fantasy scoring only, never physical touches.')
    return book


def attach_objective(model,variables,mapping,world,book):
    credits={name:pulp.LpVariable('joint_tail_'+name,lowBound=0,upBound=1) for name in mapping}
    for name in mapping:model+=credits[name]<=variables[name]
    for budget in book['budgets']:
        key=budget['budget_id'];terms=[]
        for name,ref in mapping.items():
            p=ref['player_master_id'];share=book['costs'].get(p,{}).get(key,0);m=world['moments'][p];spread=max(0,m['p90']-m['mean']);ratio=spread/max(m['mean'],1)
            if share:terms.append(share*(variables[name]+ratio*credits[name]))
        model+=pulp.lpSum(terms)<=budget['capacity'],'joint_budget_'+str(len(model.constraints))
    model.setObjective(pulp.lpSum((1.5 if ref['role']=='CPT' else 1)*(world['moments'][ref['player_master_id']]['mean']*variables[name]+TAIL_WEIGHT*max(0,world['moments'][ref['player_master_id']]['p90']-world['moments'][ref['player_master_id']]['mean'])*credits[name]) for name,ref in mapping.items()))
    return credits


def score_roster(roster,world,book,rows):
    ids=[p['player_master_id'] for p in roster]
    if len(set(ids))!=len(ids):raise ValueError('Joint opportunity roster must use distinct canonical players, including Captain')
    lookup={pid(r):r for r in rows};weights=np.array([1.5 if p['role']=='CPT' else 1 for p in roster]);means=np.array([world['moments'][p]['mean'] for p in ids]);spreads=np.array([max(0,world['moments'][p]['p90']-world['moments'][p]['mean']) for p in ids]);ratios=spreads/np.maximum(means,1)
    a=[];b=[];balances=[]
    for budget in book['budgets']:
        shares=np.array([book['costs'].get(p,{}).get(budget['budget_id'],0) for p in ids]);base=float(shares.sum());extra=shares*ratios
        if base>1+1e-6:raise ValueError('Canonical opportunity source exceeds normalized team budget')
        a.append(extra);b.append(max(0,1-base));balances.append({**budget,'selected_base_share':base,'independent_tail_extra_share':float(extra.sum())})
    fitted=linprog(-weights*spreads,A_ub=np.array(a) if a else None,b_ub=np.array(b) if b else None,bounds=[(0,1)]*len(ids),method='highs')
    if not fitted.success:raise ValueError('Opportunity-supported sensitivity could not be evaluated: '+fitted.message)
    tail=fitted.x;mean=float(weights@means);credit=float(weights@(spreads*tail));raw=float(weights@spreads)
    for audit,extra in zip(balances,a):
        used=audit['selected_base_share']+float(extra@tail);audit.update(supported_tail_extra_share=float(extra@tail),total_used_share=used,remaining_share=max(0,1-used));assert used<=1+1e-6
    names={p:lookup[p].get('name',lookup[p].get('player_name',p)) for p in ids}
    relationships=[]
    for i,left in enumerate(ids):
        for right in ids[i+1:]:
            l,r=lookup[left],lookup[right];same=team(l)==team(r);opp=l.get('opponent_team',l.get('opponent'))==team(r)
            if same and ('QB' in {l['position'],r['position']}) and ({l['position'],r['position']}&{'WR','TE'}):kind='shared passing scoring event; positive football dependence, not two physical targets'
            elif same and l['position'] in {'RB','WR','TE'} and r['position'] in {'RB','WR','TE'}:kind='shared drives can support both; target/carry/TD allocation and finishing path matter'
            elif opp:kind='two-sided sustained drives can support both; lead/runout can change opportunity'
            else:continue
            relationships.append(dict(player_master_ids=[left,right],players=[names[left],names[right]],relationship=kind))
    return dict(policy_id=POLICY,scenario_id=world['scenario_id'],score=mean+TAIL_WEIGHT*credit,conditional_mean_sum=mean,independent_tail_sum=raw,supported_tail_credit=credit,credit_weight=TAIL_WEIGHT,not_joint_p90=True,budget_balances=balances,player_tail_credit=[dict(player_master_id=p,player=names[p],role=roster[i]['role'],fraction=float(tail[i]),verified_channels=sorted(book['costs'].get(p,{}))) for i,p in enumerate(ids)],relationships=relationships,how_lineup_succeeds=world.get('label',world['scenario_id'])+'; selected roles share this conditional environment and compete only for credited physical opportunity. Full legal roster and salary tradeoffs remain in the original solver.',key_dependencies=['Unit-elastic touch-demand sensitivity is heuristic, not a fitted fantasy distribution.','Efficiency/multiple touchdowns can beat a touch-only proxy; TD allocation and opponent pace are not calibrated here.','Concentrated selected-player upside may require other active teammates to lose share, not become unavailable.'],source_pool_sha256=book['source_pool_sha256'])


def enable_world(world,source_rows,packet=None):
    if 'joint_opportunity' not in world:
        world['joint_opportunity']=prepare_world(world,source_rows,packet)
        world['joint_opportunity_players']=[{k:r.get(k) for k in ('player_id','player_master_id','name','player_name','position','player_team','team','opponent_team','opponent')} for r in source_rows]
    return world


def candidate_metric(candidate,world):
    if world.get('joint_opportunity'):
        return score_roster(candidate['roster'],world,world['joint_opportunity'],world['joint_opportunity_players'])['score']
    return sum((1.5 if p.get('role')=='CPT' else 1)*(world['moments'][p['player_master_id']]['mean']+TAIL_WEIGHT*max(0,world['moments'][p['player_master_id']]['p90']-world['moments'][p['player_master_id']]['mean'])) for p in candidate['roster'])


def summary(candidate,world):
    if not world.get('joint_opportunity'):return None
    return score_roster(candidate['roster'],world,world['joint_opportunity'],world['joint_opportunity_players'])


def annotate_report(report):
    report['joint_opportunity']=dict(policy_id=POLICY,activation='INACTIVE_PROTOTYPE_RESEARCH_ONLY',not_joint_p90=True,validation_status='Not recommended for activation: touch-only stress can clip marginal RB tails without teammate competition; efficiency/TD modeling and marginal-consistency validation are missing.')
    report['mathematical_assumptions']['candidate_objective']='sum unchanged conditional means + 0.35 * opportunity-supported individual-tail credit; deterministic unit-elastic touch stress, not joint percentile'
    report['selection']['selection_reason']+='; isolated uncalibrated shared-opportunity stress, not demonstrated predictive improvement'
    return report
