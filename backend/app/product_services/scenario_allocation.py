"""Scenario-first Classic planning and construction, separate from base truth.

Ordinal analyst preference, observed opportunity coverage and legal role capability
rank ideas before any roster solve. Scores are design priorities, not probabilities.
"""
from collections import Counter
from copy import deepcopy
from itertools import combinations
import math

import pulp
from pydantic import BaseModel, ConfigDict, Field

from .analyst_shadow import digest
from .cbc_solver import make_cbc_solver
from .workload_evidence import CONTRACT_ID as WORKLOAD_CONTRACT_ID, select_measurement


class AllocationControls(BaseModel):
    model_config=ConfigDict(extra='forbid')
    opportunity_shift: float = Field(default=.12,ge=.05,le=.25,allow_inf_nan=False)
    secondary_offense_limit: int = Field(default=2,ge=1,le=4,strict=True)
    receiving_core_max_fraction: float = Field(default=.6,ge=.2,le=1,allow_inf_nan=False)
    shared_triple_max_fraction: float = Field(default=.6,ge=.2,le=1,allow_inf_nan=False)
    game_repeat_penalty: float = Field(default=.65,ge=0,le=3,allow_inf_nan=False)
    idea_repeat_penalty: float = Field(default=.85,ge=0,le=3,allow_inf_nan=False)
    new_script_credit: float = Field(default=.18,ge=0,le=.5,allow_inf_nan=False)
    minimum_credibility: float = Field(default=.35,ge=.1,le=.8,allow_inf_nan=False)
    passing_receivers: int = Field(default=1,ge=1,le=2,strict=True)


def measurement(player,channel):
    return select_measurement(player, channel)


def role_measurement(player, channel):
    # New proxies may inform conditional sensitivity, never certify an observed
    # role. Archived v1 inputs retain their original consumer behavior.
    allow_proxy = (player.get('workload_evidence') or {}).get('contract_id') != WORKLOAD_CONTRACT_ID
    return select_measurement(player, channel, allow_proxy=allow_proxy)


def team(row):return row.get('player_team',row.get('team'))
def opponent(row):return row.get('opponent_team',row.get('opponent'))
def is_qb(row):return row['position']=='QB' and (row.get('is_starting_qb') is not False) and row.get('canonical_role') not in {'expected_backup','long_snapper'}


def build_ideas(packet,rows,controls):
    games={g['game_id']:g for g in packet['games']}
    declared={p['player_master_id']:p for p in packet['players']}
    assessments={a['game_id']:a for a in packet.get('analyst_assessments',[]) if 'CLASSIC' in a.get('formats',[])}
    ranks={r['assessment_id']:r['rank'] for r in (packet.get('slate_synthesis') or {}).get('ranked_upside_leans',[])}
    sources={s['source_id']:s for s in packet['sources']}
    hypotheses={h['hypothesis_id']:h for h in packet['hypotheses']}
    ideas=[];rejected=[];seen=set()
    for scenario in packet['scenario_assumptions']['scenarios']:
        gids={a['game_id'] for a in scenario['assumptions']}
        if len(gids)!=1:
            rejected.append(dict(scenario_id=scenario['scenario_id'],reason='composite stress world retained as evidence, not a single construction idea'));continue
        gid=next(iter(gids));game=games[gid];assessment=assessments.get(gid,{})
        linked=set(assessment.get('player_master_ids') or [])
        assumptions=[a for a in scenario['assumptions'] if a['kind'] in {'passing_volume','rushing_volume'} and a['factor']>1]
        if not assumptions:
            rejected.append(dict(scenario_id=scenario['scenario_id'],reason='no typed positive opportunity channel'));continue
        # Select the supported leading side, not the highest-priced player.
        linked_order=assessment.get('player_master_ids') or []
        def leading_priority(a):
            role_ids=[str(r['player_id']) for r in rows if team(r)==a['team'] and ((is_qb(r) and a['kind']=='passing_volume') or (r['position']=='RB' and a['kind']=='rushing_volume'))]
            indices=[linked_order.index(pid) for pid in role_ids if pid in linked_order]
            return (bool(indices),-min(indices) if indices else -999,a['factor'],a['team'])
        leading=max(assumptions,key=leading_priority)
        primary='passing' if leading['kind']=='passing_volume' else 'run_control'
        branches = [(primary, False)] if packet.get('intent_scope') else [(primary,False),('run_control' if primary=='passing' else 'passing',True)]
        for script,derived in branches:
            key=(gid,leading['team'],script)
            if key in seen:continue
            seen.add(key)
            members=[r for r in rows if team(r)==leading['team'] and opponent(r) in game['teams']]
            qbs=[r for r in members if is_qb(r)];receivers=[r for r in members if r['position'] in {'WR','TE'}]
            runners=[r for r in members if r['position']=='RB']
            refs=sorted(set(assessment.get('source_ids',[]))|{sid for hid in scenario['hypothesis_ids'] for sid in hypotheses[hid].get('source_ids',[])})
            verified=[sid for sid in refs if sources.get(sid,{}).get('coverage')=='verified']
            target_metrics=[role_measurement(declared.get(str(r['player_id']),r),'targets')[0] for r in receivers]
            carry_metrics=[role_measurement(declared.get(str(r['player_id']),r),'carries')[0] for r in runners]
            usage_evidence=[dict(player_id=str(r['player_id']),channel=channel,
                value=role_measurement(declared.get(str(r['player_id']),r),channel)[0],
                basis=role_measurement(declared.get(str(r['player_id']),r),channel)[1])
                for members,channel in ((receivers,'targets'),(runners,'carries')) for r in members]
            eligible=(bool(qbs) and len(receivers)>=controls.passing_receivers and max((v or 0 for v in target_metrics),default=0)>0) if script=='passing' else (bool(runners) and max((v or 0 for v in carry_metrics),default=0)>0)
            # Archived fixtures retain their proxy-only behavior. New evidence
            # must not certify a construction role solely from a proxy.
            proxy_only=not any(v is not None for v in (target_metrics if script=='passing' else carry_metrics))
            role_members=receivers if script=='passing' else runners
            v2_role=any((declared.get(str(r['player_id']),r).get('workload_evidence') or {}).get('contract_id')==WORKLOAD_CONTRACT_ID for r in role_members)
            if proxy_only:eligible=False if v2_role else bool(qbs and receivers) if script=='passing' else bool(runners)
            capability=(max((float(r['projection']) for r in qbs),default=0)+max((float(r['projection']) for r in receivers),default=0))/60 if script=='passing' else max((float(r['projection']) for r in runners),default=0)/30
            usage=min(1,max((v or 0 for v in (target_metrics if script=='passing' else carry_metrics)),default=0)/(8 if script=='passing' else 20))
            editorial=(1/(1+(ranks.get(assessment.get('assessment_id'),6)-1)/4)) if script=='passing' else .5
            score=min(1,.3*min(1,capability)+.3*usage+.2*min(1,len(verified)/3)+.2*editorial)
            if derived:score*=.82
            if proxy_only:score*=.6
            reason=None if eligible and verified and score>=controls.minimum_credibility else 'insufficient eligible role/observed opportunity/source capability'
            if proxy_only and v2_role:reason='original workload unavailable; allocated proxy cannot certify construction role'
            opp=next(t for t in game['teams'] if t!=leading['team'])
            opp_members=[r for r in rows if team(r)==opp and opponent(r) in game['teams']]
            opp_qb=max((float(r['projection']) for r in opp_members if is_qb(r)),default=0)
            own_qb=max((float(r['projection']) for r in qbs),default=1)
            supported_responders=[str(r['player_id']) for r in opp_members if r['position'] in {'WR','TE'} and (role_measurement(declared.get(str(r['player_id']),r),'targets')[0] or 0)>=4]
            explicit_opponent_pass=any(a['kind']=='passing_volume' and a['team']==opp and a['factor']>1 for a in assumptions)
            bringback=script=='passing' and explicit_opponent_pass and opp_qb>=.65*own_qb and bool(supported_responders)
            idea=dict(idea_id=gid+':'+leading['team']+':'+script,game_id=gid,team=leading['team'],opponent=opp,script=script,source_scenario_id=scenario['scenario_id'],hypothesis_ids=scenario['hypothesis_ids'],assessment_id=assessment.get('assessment_id'),source_ids=refs,verified_source_ids=verified,derived_alternative=derived,
                alternative_lineage=assessment.get('strongest_alternative') if derived else assessment.get('lean',scenario['label']),credibility_score=score,usage_evidence=usage_evidence,score_components=dict(role_capability=capability,observed_usage=usage,editorial_preference=editorial,proxy_only=proxy_only),
                bringback_required=bringback,opponent_capability=dict(qb_mean_ratio=opp_qb/own_qb,observed_receiver_ids=supported_responders,explicit_two_sided_passing=explicit_opponent_pass),
                eligible_qb_ids=[str(r['player_id']) for r in qbs],eligible_receiver_ids=[str(r['player_id']) for r in receivers],eligible_rb_ids=[str(r['player_id']) for r in runners],label=scenario['label'] if not derived else 'Conditional contrary '+script+' branch for '+leading['team'],rejection_reason=reason)
            (rejected if reason else ideas).append(idea)
    return ideas,rejected


def plan_slots(ideas,requested,controls,reserved_idea_ids=None):
    game_counts=Counter();idea_counts=Counter();script_counts=Counter();slots=[]
    for index in range(requested):
        ranked=[]
        for idea in ideas:
            if idea_counts[idea['idea_id']]>=idea.get('discovery_max_lineups',requested):continue
            adjusted=(idea['credibility_score']+ (controls.new_script_credit if not script_counts[idea['script']] else 0))/(1+controls.game_repeat_penalty*game_counts[idea['game_id']]+controls.idea_repeat_penalty*idea_counts[idea['idea_id']])
            ranked.append((adjusted,idea['idea_id'],idea))
        ranked.sort(key=lambda item:(-item[0],item[1]))
        if not ranked:break
        reserved=(reserved_idea_ids or [])
        reserved_id=reserved[index] if index<len(reserved) else None
        score,_,chosen=next((item for item in ranked if item[1]==reserved_id),ranked[0])
        slots.append(dict(slot=index+1,idea_id=chosen['idea_id'],priority_score=score,repeated=bool(idea_counts[chosen['idea_id']]),reason='Bounded sourced discovery finding reserved before generation' if reserved_id else 'Highest evidence/capability priority after game/idea overlap penalties and new-script credit',next_credible_alternative=dict(idea_id=ranked[1][1],priority_score=ranked[1][0]) if len(ranked)>1 else None,
            repetition_justification='Repeat adjusted priority exceeds next credible alternative' if idea_counts[chosen['idea_id']] else 'Distinct supported construction idea'))
        game_counts[chosen['game_id']]+=1;idea_counts[chosen['idea_id']]+=1;script_counts[chosen['script']]+=1
    return dict(contract_id='scenario_allocation_plan_v1',phase='before_any_roster_solve',requested=requested,slots=slots,ideas=ideas,controls=controls.model_dump(),probability_status='ordinal uncalibrated design priority; not event or lineup probability')


def conditional_world(idea,rows,packet,controls):
    declared={p['player_master_id']:p for p in packet['players']};members=[r for r in rows if team(r)==idea['team'] and opponent(r)==idea['opponent']]
    measured=[(measurement(declared.get(str(r['player_id']),r),'targets')[0],measurement(declared.get(str(r['player_id']),r),'carries')[0]) for r in members if r['position'] in {'RB','WR','TE'}]
    targets=sum(t or 0 for t,_ in measured);carries=sum(c or 0 for _,c in measured)
    complete=all(t is not None and c is not None for t,c in measured) and bool(measured)
    pass_share=targets/(targets+carries) if complete and targets+carries>0 else .55
    pass_share=max(.3,min(.7,pass_share))
    shift=idea.get('focused_opportunity_shift',controls.opportunity_shift)*(1 if idea['script']=='passing' else -1)
    conditional_pass=max(.2,min(.8,pass_share+shift));pass_ratio=conditional_pass/pass_share;rush_ratio=(1-conditional_pass)/(1-pass_share)
    budget=dict(unit='normalized skill opportunity units; not forecast NFL attempts',baseline_total=100,conditional_total=100,baseline_targets=100*pass_share,baseline_carries=100*(1-pass_share),conditional_targets=100*conditional_pass,conditional_carries=100*(1-conditional_pass),evidence_basis='complete measured skill-player counts' if complete else 'declared 55/45 allocation prior with explicit partial coverage',complete_measured_coverage=complete,pass_ratio=pass_ratio,rush_ratio=rush_ratio,shift=shift)
    from .team_game_outlook import conditional_factors
    fitted=conditional_factors(packet,idea['game_id'],idea['team'],'competitive_scoring' if idea['script']=='passing' else 'drive_stall_runout')
    if fitted:
        fitted_pass,fitted_rush=fitted;weighted_pass=conditional_pass*fitted_pass;weighted_rush=(1-conditional_pass)*fitted_rush
        conditional_pass=max(.2,min(.8,weighted_pass/(weighted_pass+weighted_rush)));pass_ratio=conditional_pass/pass_share;rush_ratio=(1-conditional_pass)/(1-pass_share)
        budget.update(conditional_targets=100*conditional_pass,conditional_carries=100*(1-conditional_pass),pass_ratio=pass_ratio,rush_ratio=rush_ratio,optional_outlook_ratios=list(fitted),outlook_use='Explicit saved outlook sensitivity tilts conditional opportunity mix, renormalized to conserved100units; unproven calibration, no base model promotion')
    moments={}
    for row in rows:
        pid=str(row['player_id']);mean=float(row['projection']);p90=max(mean,float(row.get('p90',row.get('ceiling'))));ratio=1;changes=[]
        if row in members and row['position'] in {'QB','RB','WR','TE'}:
            t,ts=measurement(declared.get(pid,row),'targets');c,cs=measurement(declared.get(pid,row),'carries')
            if row['position']=='QB':receiving_weight=.7
            elif row['position'] in {'WR','TE'}:receiving_weight=1
            else:receiving_weight=t/(t+c) if t is not None and c is not None and t+c>0 else .15
            opportunity=receiving_weight*pass_ratio+(1-receiving_weight)*rush_ratio
            ratio=1+.7*(opportunity-1)
            changes=[dict(opportunity_budget=budget,receiving_component_weight=receiving_weight,component_basis='position response design; RB measured touch mix when available',elasticity=.7,targets_lineage=ts,carries_lineage=cs)]
        moments[pid]=dict(mean=mean*ratio,p90=mean*ratio+(p90-mean)*math.sqrt(ratio),opportunity_ratio=ratio,changes=changes)
    return dict(scenario_id=idea['idea_id'],label=idea['label'],hypothesis_ids=idea['hypothesis_ids'],moments=moments,opportunity_budget=budget,design_weight=1,probability_status='uncalibrated conditional sensitivity; allocation uses explicit priority plan')


def apply_idea(model,variables,mapping,rows,idea,controls):
    by_id={str(r['player_id']):r for r in rows};selected={ref['player_master_id']:variables[name] for name,ref in mapping.items()}
    if idea['script']=='passing':
        model+=pulp.lpSum(selected[p] for p in idea['eligible_qb_ids'])==1,'idea_primary_qb'
        model+=pulp.lpSum(selected[p] for p in idea['eligible_receiver_ids'])>=controls.passing_receivers,'idea_receivers'
        if idea['bringback_required']:model+=pulp.lpSum(selected[p] for p in idea['opponent_capability']['observed_receiver_ids'])>=1,'supported_opponent_response'
    else:
        model+=pulp.lpSum(selected[p] for p in idea['eligible_rb_ids'])>=1,'idea_rushing_core'
        model+=pulp.lpSum(selected[p] for p in idea['eligible_qb_ids'])==0,'run_control_not_primary_passing'
        model+=pulp.lpSum(selected[p] for p in idea['eligible_receiver_ids'])<=1,'run_control_receiving_limit'
    for t in sorted({team(r) for r in rows}):
        if t!=idea['team']:model+=pulp.lpSum(selected[pid] for pid,r in by_id.items() if team(r)==t and r['position']!='DST')<=controls.secondary_offense_limit,'secondary_offense_'+t


def audit_construction(ids,rows,idea,controls):
    chosen=set(ids);lookup={str(r['player_id']):r for r in rows}
    qb=len(chosen & set(idea['eligible_qb_ids']));rb=len(chosen & set(idea['eligible_rb_ids']));receivers=len(chosen & set(idea['eligible_receiver_ids']))
    opponent_receivers=len(chosen & set(idea['opponent_capability']['observed_receiver_ids']))
    secondary=Counter(team(lookup[p]) for p in chosen if team(lookup[p])!=idea['team'] and lookup[p]['position']!='DST')
    passed=(qb==1 and receivers>=controls.passing_receivers and (not idea['bringback_required'] or opponent_receivers>=1)) if idea['script']=='passing' else (rb>=1 and qb==0 and receivers<=1)
    return dict(passed=passed and all(n<=controls.secondary_offense_limit for n in secondary.values()) and set(idea.get('discovery_required_player_ids',[]))<=chosen,primary_qb_count=qb,primary_rb_count=rb,primary_receiver_count=receivers,opponent_receiver_count=opponent_receivers,secondary_offense_counts=dict(secondary))


def dependence_audit(candidates,rows,requested):
    lookup={str(r['player_id']):r for r in rows};pairs=Counter();triples=Counter();primary=Counter();heavy=Counter()
    for c in candidates:
        ids=sorted(p['player_master_id'] for p in c['roster']);primary[c['allocated_idea_id']]+=1
        triples.update(combinations(ids,3))
        for t in {team(lookup[p]) for p in ids}:
            receivers=[p for p in ids if team(lookup[p])==t and lookup[p]['position'] in {'WR','TE'}]
            pairs.update(combinations(receivers,2))
            if sum(team(lookup[p])==t and lookup[p]['position']!='DST' for p in ids)>=3:heavy[t]+=1
    return dict(requested=requested,achieved=len(candidates),allocated_ideas=dict(primary),heavy_team_offense_counts=dict(heavy),
        receiving_pairs=[dict(player_master_ids=list(ids),count=count) for ids,count in pairs.most_common()],shared_triples=[dict(player_master_ids=list(ids),count=count) for ids,count in triples.most_common() if count>1],
        all_lineups_share_three_players=bool(candidates and any(n==len(candidates) for n in triples.values())),meaning='Pair/triple dependence is counted across actual canonical rosters, not distinct labels or generation IDs.')


def generate_allocated(snapshot,packet,rows,params,requested,on_plan=None,source_rows=None):
    controls=AllocationControls.model_validate(params.get('scenario_allocation_controls') or {})
    ideas,rejected=build_ideas(packet,rows,controls)
    if params.get('analyst_scenario_focus_mode')=='SELECTED_ONLY':
        requirements={s['scenario_id']:s.get('focus_requirement') for s in packet['scenario_assumptions']['scenarios']}
        kept=[]
        for idea in ideas:
            requirement=requirements.get(idea['source_scenario_id'])
            if requirement and idea['team']==requirement['team'] and idea['script']==requirement['script']:
                idea['focused_opportunity_shift']=requirement['opportunity_shift'];kept.append(idea)
            else:rejected.append({**idea,'rejection_reason':'outside explicitly selected football story'})
        ideas=kept
        if not ideas:raise ValueError('Selected football stories lack credible source/role construction; no generic fallback')
    from .analyst_discovery import prepare_actions,apply_opportunity_transfer
    discovery=prepare_actions(packet,rows,ideas,requested,params)
    plan=plan_slots(ideas,requested,controls,discovery['reserved_idea_ids']);plan['discovery']=discovery
    plan['rejected_ideas']=rejected;plan['planning_snapshot']=deepcopy(plan);plan['sha256_before_generation']=digest(plan['planning_snapshot'])
    if on_plan:on_plan(deepcopy(plan))
    worlds={idea['idea_id']:conditional_world(idea,rows,packet,controls) for idea in ideas}
    for idea in ideas:apply_opportunity_transfer(worlds[idea['idea_id']],idea,rows)
    from .joint_opportunity import PARAM,enable_world,attach_objective,candidate_metric,summary
    if params.get(PARAM):
        for world in worlds.values():enable_world(world,source_rows or rows,packet)
    mapping=snapshot['variable_players'];selected=[];attempts=[];counts=Counter();pairs=Counter();triples=Counter();by_id={str(r['player_id']):r for r in rows}
    from .classic_portfolio_controls import explicit_appearance_limit
    locks=set(params.get('locked_player_ids') or []);minimums=params.get('minimum_exposure_by_player') or {};maximums=params.get('maximum_exposure_by_player') or {}
    if any(pid not in by_id and float(rate)>0 for pid,rate in minimums.items()):raise ValueError('Minimum exposure references an ineligible canonical player')
    for rate in [params.get('max_exposure',1),*minimums.values(),*maximums.values()]:
        if type(rate) not in (int,float) or not math.isfinite(rate) or not 0<=rate<=1:raise ValueError('Invalid scenario-first exposure limit')
    for slot in plan['slots']:
        primary=next(i for i in ideas if i['idea_id']==slot['idea_id'])
        actual_ideas=Counter(c['allocated_idea_id'] for c in selected)
        actual_games=Counter(next(i['game_id'] for i in ideas if i['idea_id']==c['allocated_idea_id']) for c in selected)
        actual_scripts=Counter(next(i['script'] for i in ideas if i['idea_id']==c['allocated_idea_id']) for c in selected)
        def fallback_priority(i):return (i['credibility_score']+(controls.new_script_credit if not actual_scripts[i['script']] else 0))/(1+controls.game_repeat_penalty*actual_games[i['game_id']]+controls.idea_repeat_penalty*actual_ideas[i['idea_id']])
        alternatives=[primary]+sorted([i for i in ideas if i['idea_id']!=primary['idea_id']],key=lambda i:(-fallback_priority(i),i['idea_id']))
        achieved=False
        for idea in alternatives:
            if sum(c['allocated_idea_id']==idea['idea_id'] for c in selected)>=idea.get('discovery_max_lineups',requested):
                attempts.append(dict(slot=slot['slot'],attempted_idea_id=idea['idea_id'],solver_status='discovery_slot_budget_exhausted'));continue
            variables,model=pulp.LpProblem.fromDict(deepcopy(snapshot['model']));player_vars={ref['player_master_id']:variables[name] for name,ref in mapping.items()}
            apply_idea(model,variables,mapping,rows,idea,controls)
            for pid in idea.get('discovery_required_player_ids',[]):model+=player_vars[pid]==1
            remaining=requested-len(selected)
            for pid,var in player_vars.items():
                limit=requested if pid in locks else math.ceil(requested*float(params.get('max_exposure',1)))
                if pid in maximums:limit=min(limit,explicit_appearance_limit(requested,float(maximums[pid])))
                if params.get('elevated_player_max_exposure') is not None:
                    from .single_lineup import elevated_player
                    if elevated_player(by_id[pid],params.get('data_cutoff_at')):limit=min(limit,explicit_appearance_limit(requested,float(params['elevated_player_max_exposure'])))
                if counts[pid]>=limit:model+=var==0
                if math.ceil(requested*float(minimums.get(pid,0)))-counts[pid]>=remaining:model+=var==1
            overlap=params.get('max_lineup_overlap',9)
            if params.get('minimum_uniqueness') is not None:overlap=min(overlap,9-int(params['minimum_uniqueness']))
            for previous in selected:model+=pulp.lpSum(player_vars[p['player_master_id']] for p in previous['roster'])<=int(overlap)
            for ids,count in pairs.items():
                if count>=math.ceil(requested*controls.receiving_core_max_fraction) and not set(ids)<=locks:model+=pulp.lpSum(player_vars[p] for p in ids)<=1
            for ids,count in triples.items():
                if count>=math.ceil(requested*controls.shared_triple_max_fraction) and not set(ids)<=locks:model+=pulp.lpSum(player_vars[p] for p in ids)<=2
            if params.get('max_lineups_per_primary_game') is not None:
                from .classic_primary_game import canonical_primary_game
                used=Counter(canonical_primary_game(team(by_id[p['player_master_id']]),opponent(by_id[p['player_master_id']])) for c in selected for p in c['roster'] if by_id[p['player_master_id']]['position']=='QB')
                for pid,row in by_id.items():
                    if row['position']=='QB' and used[canonical_primary_game(team(row),opponent(row))]>=params['max_lineups_per_primary_game']:model+=player_vars[pid]==0
            world=worlds[idea['idea_id']]
            model.setObjective(pulp.lpSum((world['moments'][pid]['mean']+.35*(world['moments'][pid]['p90']-world['moments'][pid]['mean']))*var for pid,var in player_vars.items()))
            if params.get(PARAM):attach_objective(model,variables,mapping,world,world['joint_opportunity'])
            solver=make_cbc_solver();solver.options.extend(['randomSeed 7','randomCbcSeed 7']);model.solve(solver)
            attempts.append(dict(slot=slot['slot'],planned_idea_id=slot['idea_id'],attempted_idea_id=idea['idea_id'],solver_status=pulp.LpStatus[model.status],replacement=idea is not primary,adjusted_fallback_priority=fallback_priority(idea)))
            if model.status!=pulp.LpStatusOptimal:continue
            ids=sorted(pid for pid,v in player_vars.items() if pulp.value(v)>.5)
            c=dict(roster=[dict(player_master_id=pid,role='SELECTED') for pid in ids],scenario_ids=[idea['idea_id']],allocated_idea_id=idea['idea_id'],allocation_slot=slot['slot'],planned_idea_id=slot['idea_id'],opportunity_budget=world['opportunity_budget'],discovery_finding_ids=idea.get('discovery_finding_ids',[]),construction_compliance=True,construction_audit=audit_construction(ids,rows,idea,controls))
            if not c['construction_audit']['passed']:raise ValueError('Scenario construction failed independent roster audit')
            c['scores']={sid:candidate_metric(c,w) for sid,w in worlds.items()}
            c['joint_opportunity_summary']=summary(c,world)
            selected.append(c);counts.update(ids);triples.update(combinations(ids,3))
            for t in {team(by_id[p]) for p in ids}:pairs.update(combinations([p for p in ids if team(by_id[p])==t and by_id[p]['position'] in {'WR','TE'}],2))
            slot.update(actual_idea_id=idea['idea_id'],status='constructed',replacement_reason='Planned idea infeasible under unchanged legal/user/dependence constraints' if idea is not primary else None)
            achieved=True;break
        if not achieved:slot.update(status='underfilled',reason='No credible idea feasible under hard constraints; no generic fallback or relaxation')
    if params.get('analyst_challenger_enabled',False):
        from .analyst_challenger import hunt
        initial=deepcopy(selected);selected,expanded_worlds,challenge=hunt(snapshot,packet,rows,selected,ideas,list(worlds.values()),params,requested,controls,discovery,source_rows=source_rows or rows)
        worlds={w['scenario_id']:w for w in expanded_worlds};plan['challenger']=challenge
        plan['portfolio_revision']={'initial_allocations':[{'slot':c['allocation_slot'],'idea_id':c['allocated_idea_id'],'roster_sha256':digest(c['roster'])} for c in initial],'final_allocations':[{'slot':i,'idea_id':c['allocated_idea_id'],'roster_sha256':digest(c['roster']),'origin_allocation_slot':c['allocation_slot']} for i,c in enumerate(selected,1)],'reason':challenge['status']}
        for i,c in enumerate(selected,1):c['origin_allocation_slot']=c['allocation_slot'];c['allocation_slot']=i
    if params.get('analyst_teammate_enabled',False):
        from .teammate_opportunity import investigate
        plan['teammate_opportunity']=investigate(snapshot,packet,source_rows or rows,rows,ideas,params,controls,selected,discovery)
        if params.get('analyst_teammate_choice'):
            from .teammate_opportunity import apply_choice
            before=deepcopy(selected);selected,expanded=apply_choice(selected,list(worlds.values()),plan['teammate_opportunity'],rows,params,controls,discovery);worlds={w['scenario_id']:w for w in expanded}
            plan['teammate_portfolio_revision']={'initial_rosters':[digest(c['roster']) for c in before],'final_rosters':[digest(c['roster']) for c in selected],'choice':plan['teammate_opportunity']['applied_choice']}
            for i,c in enumerate(selected,1):c['origin_allocation_slot']=c['allocation_slot'];c['allocation_slot']=i
    if params.get(PARAM):
        for c in selected:
            relevant=next((w for w in worlds.values() if w['scenario_id'] in c['scenario_ids']),None)
            if relevant:c['joint_opportunity_summary']=summary(c,relevant)
    audit=dependence_audit(selected,rows,requested)
    plan['actual_roster_audit']=audit;plan['generation_attempts']=attempts
    for finding in discovery['findings']:
        influenced=[c['allocation_slot'] for c in selected if finding['finding_id'] in c.get('discovery_finding_ids',[])]
        finding['actual_allocation_slots']=influenced
        finding['actual_roster_sha256']=[digest(c['roster']) for c in selected if finding['finding_id'] in c.get('discovery_finding_ids',[])]
        finding['actual_scenario_ids']=[c['allocated_idea_id'] for c in selected if finding['finding_id'] in c.get('discovery_finding_ids',[])]
        if finding.get('action_status')=='reserved_before_generation' and not influenced:finding.update(action_status='infeasible_or_displaced',decision_reason='Hard legal/user/dependence constraints prevented the reserved finding construction; no relaxation')
    plan['locked_core_exemptions']={'player_master_ids':sorted(locks),'meaning':'A pair/triple consisting entirely of explicitly locked players is exempt from shared-core limits; user locks retain priority.'}
    return selected,list(worlds.values()),dict(solver_status='Optimal' if len(selected)==requested else 'underfilled',requested=requested,achieved=len(selected),quality_screen='none',quality_rejected=0,constraints_relaxed=False,selection_reason='Football idea slots allocated before roster solves; each constructed roster satisfies its idea and shared outcome-dependence limits'),plan
