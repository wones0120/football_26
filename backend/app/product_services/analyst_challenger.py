"""Bounded, opt-in counter-scenario search after initial candidate construction."""
from collections import Counter
from copy import deepcopy
from itertools import combinations
import math
import time
import pulp
from pydantic import BaseModel,ConfigDict,Field
from .analyst_shadow import digest
from .cbc_solver import make_cbc_solver

class ChallengerControls(BaseModel):
    model_config=ConfigDict(extra='forbid')
    max_failure_modes:int=Field(default=3,ge=1,le=6,strict=True)
    max_solver_calls:int=Field(default=2,ge=1,le=3,strict=True)
    max_seconds:float=Field(default=20,ge=1,le=60,allow_inf_nan=False)
    max_portfolio_size:int=Field(default=20,ge=1,le=20,strict=True)
    expensive_rb_salary_threshold:int=Field(default=6500,ge=4000,le=10000,strict=True)
    dependence_fraction:float=Field(default=.8,ge=.5,le=1,allow_inf_nan=False)
    opportunity_shift:float=Field(default=.2,ge=.05,le=.25,allow_inf_nan=False)
    minimum_credibility:float=Field(default=.45,ge=.35,le=1,allow_inf_nan=False)
    minimum_coverage_gain:float=Field(default=.02,ge=0,le=.2,allow_inf_nan=False)
    counter_world_weight:float=Field(default=.25,ge=0,le=1,allow_inf_nan=False)


def canonical_roster(candidate):return tuple(sorted((str(p['player_master_id']),p.get('role','SELECTED')) for p in candidate['roster']))
def ids(candidate):return {str(p['player_master_id']) for p in candidate['roster']}
def team(row):return row.get('player_team',row.get('team'))
def metric(candidate,world):
    from .joint_opportunity import candidate_metric
    return candidate_metric(candidate,world)


def vulnerabilities(candidates,rows,controls):
    lookup={str(r['player_id']):r for r in rows};count=Counter(pid for c in candidates for pid in ids(c));n=len(candidates);result=[]
    for pid,appearances in count.items():
        row=lookup[pid]
        if row['position'] not in {'RB','WR','TE'} or appearances<math.ceil(n*controls.dependence_fraction):continue
        peers=[float(r['salary']) for r in rows if r['position']==row['position']];median=sorted(peers)[len(peers)//2]
        result.append(dict(vulnerability_id='shared_player:'+pid,player_master_ids=[pid],player_name=row.get('name',row.get('player_name',pid)),team=team(row),position=row['position'],appearances=appearances,portfolio_size=n,salary=float(row['salary']),expensive_for_position=float(row['salary'])>=median,central_mean_dependence=float(row['projection'])*appearances,football_failure_mode='Primary rushing control suppresses a shared receiver ceiling' if row['position'] in {'WR','TE'} else 'Primary passing-led scoring suppresses a shared rushing ceiling',source_status='Hypothesized game script plus saved forecast downside; player remains eligible/available as originally sourced'))
    result.sort(key=lambda v:(-v['central_mean_dependence'],v['vulnerability_id']))
    rb_pairs=Counter(tuple(sorted(p for p in ids(c) if lookup[p]['position']=='RB' and float(lookup[p]['salary'])>=controls.expensive_rb_salary_threshold)) for c in candidates)
    return result,dict(expensive_rb_threshold=controls.expensive_rb_salary_threshold,expensive_rb_groups=[dict(player_master_ids=list(p),count=count) for p,count in rb_pairs.items() if len(p)>=2],meaning='Salary concentration is a vulnerability screen, not a star exclusion or factual scoring prediction')


def covered(candidate,idea,vulnerability):
    chosen=ids(candidate)
    if chosen & set(vulnerability['player_master_ids']):return False
    if idea['script']=='passing':return (bool(chosen & set(idea['eligible_qb_ids'])) and bool(chosen & set(idea['eligible_receiver_ids']))) or len(chosen & set(idea['eligible_receiver_ids']))>=2
    return bool(chosen & set(idea['eligible_rb_ids'])) and not (chosen & set(idea['eligible_qb_ids']))


def counter_world(idea,vulnerability,rows,packet,allocation_controls,controls):
    from .scenario_allocation import conditional_world
    configured=allocation_controls.model_copy(update={'opportunity_shift':controls.opportunity_shift});world=conditional_world(idea,rows,packet,configured)
    world['scenario_id']='challenger:'+vulnerability['vulnerability_id']+':'+idea['idea_id'];lookup={str(r['player_id']):r for r in rows};stress=[]
    for pid in vulnerability['player_master_ids']:
        p10=lookup[pid].get('predicted_p10')
        if type(p10) not in (int,float) or not math.isfinite(p10) or p10<0 or p10>float(lookup[pid]['projection']):raise ValueError('No valid saved modeled downside endpoint')
        previous=world['moments'][pid]['mean'];world['moments'][pid]['mean']=min(previous,float(p10));world['moments'][pid]['p90']=world['moments'][pid]['mean']
        stress.append(dict(player_master_id=pid,stored_model_p10=p10,conditional_mean_before_downside=previous,meaning='Assume this core realizes the saved modeled downside in a sourced contrary-script stress test; no injury/absence assertion or calibrated joint probability'))
    world['modeled_downside_stress']=stress;world['design_weight']=controls.counter_world_weight;return world


def feasible_portfolio(candidates,rows,params,requested,allocation_controls,discovery_reservations):
    if len(candidates)!=requested:return False
    from .classic_portfolio_controls import explicit_appearance_limit
    from .single_lineup import elevated_player
    from .classic_primary_game import canonical_primary_game
    lookup={str(r['player_id']):r for r in rows};count=Counter(p for c in candidates for p in ids(c));locks=set(params.get('locked_player_ids') or [])
    for pid,n in count.items():
        limit=requested if pid in locks else math.ceil(requested*float(params.get('max_exposure',1)))
        if pid in (params.get('maximum_exposure_by_player') or {}):limit=min(limit,explicit_appearance_limit(requested,float(params['maximum_exposure_by_player'][pid])))
        if params.get('elevated_player_max_exposure') is not None and elevated_player(lookup[pid],params.get('data_cutoff_at')):limit=min(limit,explicit_appearance_limit(requested,float(params['elevated_player_max_exposure'])))
        if n>limit:return False
    if any(count[p]<math.ceil(requested*float(rate)) for p,rate in (params.get('minimum_exposure_by_player') or {}).items()):return False
    overlap=min(int(params.get('max_lineup_overlap',9)),9-int(params.get('minimum_uniqueness',0)))
    if any(len(ids(a)&ids(b))>overlap for a,b in combinations(candidates,2)):return False
    pairs=Counter();triples=Counter();games=Counter()
    for c in candidates:
        chosen=ids(c);triples.update(combinations(sorted(chosen),3))
        for t in {team(lookup[p]) for p in chosen}:pairs.update(combinations(sorted(p for p in chosen if team(lookup[p])==t and lookup[p]['position'] in {'WR','TE'}),2))
        for p in chosen:
            if lookup[p]['position']=='QB':games[canonical_primary_game(team(lookup[p]),lookup[p].get('opponent_team'))]+=1
    if any(n>math.ceil(requested*allocation_controls.receiving_core_max_fraction) and not set(p)<=locks for p,n in pairs.items()):return False
    if any(n>math.ceil(requested*allocation_controls.shared_triple_max_fraction) and not set(p)<=locks for p,n in triples.items()):return False
    if params.get('max_lineups_per_primary_game') is not None and any(n>params['max_lineups_per_primary_game'] for n in games.values()):return False
    for idea in discovery_reservations:
        if not any(c['allocated_idea_id']==idea and c.get('discovery_finding_ids') for c in candidates):return False
    if any(n>1 for n in Counter(fid for c in candidates for fid in c.get('discovery_finding_ids',[])).values()):return False
    return True


def hunt(snapshot,packet,rows,initial_candidates,ideas,worlds,params,requested,allocation_controls,discovery,candidate_pool=None,source_rows=None):
    controls=ChallengerControls.model_validate(params.get('analyst_challenger_controls') or {});initial=deepcopy(initial_candidates);pool=deepcopy(candidate_pool if candidate_pool is not None else initial);lookup={str(r['player_id']):r for r in rows};vulns,salary_audit=vulnerabilities(initial,rows,controls)
    report=dict(contract_id='analyst_challenger_v1',phase='after_initial_candidate_pool',controls=controls.model_dump(),initial_selected_count=len(initial),initial_candidate_count=len(pool),initial_roster_sha256=[digest(c['roster']) for c in initial],vulnerabilities=vulns,salary_dependence=salary_audit,attempts=[],solver_calls=0,accepted_candidate_count=0,quality_screen='none',probability_status='Uncalibrated contrary-script and saved model downside stress, not event probability',format_scope='CLASSIC only; Captain-aware canonical dedup helper, no Showdown activation')
    if requested>controls.max_portfolio_size or len(initial)!=requested or len(pool)>requested+3:
        report.update(status='unsupported_size_or_initial_underfill',reason='Bounded first implementation requires a complete Classic portfolio of at most20');return initial,worlds,report
    start=time.monotonic();new_worlds=[]
    for vulnerability in vulns[:controls.max_failure_modes]:
        if time.monotonic()-start>=controls.max_seconds:break
        pid=vulnerability['player_master_ids'][0];desired='run_control' if vulnerability['position'] in {'WR','TE'} else 'passing'
        choices=[i for i in ideas if i['team']==vulnerability['team'] and i['script']==desired and i['credibility_score']>=controls.minimum_credibility and i.get('verified_source_ids')]
        entry=dict(vulnerability_id=vulnerability['vulnerability_id'],source_player_ids=[pid],failure_mode=vulnerability['football_failure_mode'])
        if pid in set(params.get('locked_player_ids') or []):entry.update(classification='unavoidable_locked_dependence',status='rejected',reason='User lock retained; no contrary roster may exclude locked core');report['attempts'].append(entry);continue
        if not choices:entry.update(classification='unsupported_counter_scenario',status='rejected',reason='No sourced credible contrary idea; unusual salary dependence alone is insufficient');report['attempts'].append(entry);continue
        idea=max(choices,key=lambda i:(i['credibility_score'],i['idea_id']));entry.update(idea_id=idea['idea_id'],source_ids=idea['source_ids'],counterevidence=idea.get('alternative_lineage'),credibility_score=idea['credibility_score'])
        existing=[c for c in pool if covered(c,idea,vulnerability)];selected_existing=[c for c in initial if covered(c,idea,vulnerability)]
        entry['classification']='selection_gap' if existing and not selected_existing else 'already_covered' if selected_existing else 'generation_gap'
        try:world=counter_world(idea,vulnerability,rows,packet,allocation_controls,controls)
        except ValueError as exc:entry.update(status='rejected',reason=str(exc));report['attempts'].append(entry);continue
        if params.get('analyst_joint_opportunity_enabled'):
            from .joint_opportunity import enable_world
            enable_world(world,source_rows or rows,packet)
        if selected_existing:
            new_worlds.append(world);entry.update(status='no_search',reason='Selected roster already represents the contrary script without this dependency; retain this condition in the coverage audit during reallocation');report['attempts'].append(entry);continue
        if existing:candidate=max(existing,key=lambda c:metric(c,world));entry['solver_status']='not_called_existing_candidate'
        else:
            if report['solver_calls']>=controls.max_solver_calls:entry.update(status='rejected',reason='Bounded solver-call budget exhausted; gap remains explicit');report['attempts'].append(entry);continue
            from .scenario_allocation import apply_idea,audit_construction
            variables,model=pulp.LpProblem.fromDict(deepcopy(snapshot['model']));mapping=snapshot['variable_players'];player_vars={ref['player_master_id']:variables[n] for n,ref in mapping.items()};apply_idea(model,variables,mapping,rows,idea,allocation_controls)
            model+=player_vars[pid]==0,'conditional_core_failure_challenge'
            for required in idea.get('discovery_required_player_ids',[]):model+=player_vars[required]==1
            model.setObjective(pulp.lpSum((world['moments'][p]['mean']+.35*(world['moments'][p]['p90']-world['moments'][p]['mean']))*v for p,v in player_vars.items()))
            if params.get('analyst_joint_opportunity_enabled'):
                from .joint_opportunity import enable_world,attach_objective
                enable_world(world,source_rows or rows,packet);attach_objective(model,variables,snapshot['variable_players'],world,world['joint_opportunity'])
            solver=make_cbc_solver();solver.timeLimit=max(.1,controls.max_seconds-(time.monotonic()-start));solver.options.extend(['randomSeed 7','randomCbcSeed 7']);model.solve(solver);report['solver_calls']+=1;entry['solver_status']=pulp.LpStatus[model.status]
            if model.status!=pulp.LpStatusOptimal:entry.update(status='rejected',reason='Targeted counter roster infeasible or solver budget exhausted; hard constraints not relaxed');report['attempts'].append(entry);continue
            chosen=sorted(p for p,v in player_vars.items() if pulp.value(v)>.5);candidate=dict(roster=[dict(player_master_id=p,role='SELECTED') for p in chosen],allocated_idea_id=idea['idea_id'],allocation_slot=requested+report['solver_calls'],planned_idea_id=idea['idea_id'],scenario_ids=[world['scenario_id']],opportunity_budget=world['opportunity_budget'],construction_compliance=True,construction_audit=audit_construction(chosen,rows,idea,allocation_controls),discovery_finding_ids=idea.get('discovery_finding_ids',[]),challenger_vulnerability_id=vulnerability['vulnerability_id'])
            if not candidate['construction_audit']['passed']:raise ValueError('Challenger roster construction audit failed')
        score=metric(candidate,world);original_best=max(metric(c,world) for c in initial);gain=score/max(original_best,1e-9)-1
        entry.update(candidate_roster_sha256=digest(candidate['roster']),conditional_score=score,initial_best_conditional_score=original_best,relative_coverage_gain=gain,central_mean=sum(float(lookup[p]['projection']) for p in ids(candidate)),changed_player_ids=sorted(ids(candidate)^ids(max(initial,key=lambda c:len(ids(c)&ids(candidate))))))
        if gain<controls.minimum_coverage_gain:entry.update(status='rejected',reason='Own-condition coverage gain below disclosed minimum; no forced alternative');report['attempts'].append(entry);continue
        if existing:
            new_worlds.append(world);entry.update(status='existing_candidate_supported',reason='Selection gap: represented candidate reused without regeneration');report['attempts'].append(entry);continue
        if canonical_roster(candidate) in {canonical_roster(c) for c in pool}:entry.update(status='rejected_duplicate',reason='Canonical role-aware roster already in pool');report['attempts'].append(entry);continue
        candidate['challenger_conditions']=world['scenario_id'];pool.append(candidate);new_worlds.append(world);entry.update(status='admitted',reason='Sourced credible counter script closes audited generation gap with meaningful downside-condition coverage');report['attempts'].append(entry);report['accepted_candidate_count']+=1
    all_worlds=worlds+new_worlds
    for c in pool:c['scores']={w['scenario_id']:metric(c,w) for w in all_worlds}
    # Bounded exact portfolio comparison: at most23 candidates, choose at most20.
    best_by_world={w['scenario_id']:max(metric(c,w) for c in pool) for w in all_worlds}
    def objective(cs):return sum((controls.counter_world_weight if w in new_worlds else 1/len(worlds))*max(metric(c,w) for c in cs)/max(best_by_world[w['scenario_id']],1e-9) for w in all_worlds)
    initial_objective=objective(initial);best=initial;best_score=initial_objective;examined=0
    reservations=[i for i in discovery['reserved_idea_ids'] if any(c['allocated_idea_id']==i and c.get('discovery_finding_ids') for c in initial)]
    for combo in combinations(pool,requested):
        if time.monotonic()-start>=controls.max_seconds:
            report['portfolio_time_budget_exhausted']=True;break
        examined+=1
        if not feasible_portfolio(combo,rows,params,requested,allocation_controls,reservations):continue
        score=objective(combo)
        if score>best_score+1e-9:best=list(combo);best_score=score
    report.update(status='reallocated' if {canonical_roster(c) for c in best}!={canonical_roster(c) for c in initial} else 'retained_initial',candidate_pool_count=len(pool),portfolio_combinations_examined=examined,initial_coverage_objective=initial_objective,selected_coverage_objective=best_score,initial_base_mean_sum=sum(float(lookup[p]['projection']) for c in initial for p in ids(c)),selected_base_mean_sum=sum(float(lookup[p]['projection']) for c in best for p in ids(c)),candidate_pool=pool,selected_roster_sha256=[digest(c['roster']) for c in best],remaining_dependence=vulnerabilities(best,rows,controls)[0],constraints_relaxed=False)
    return deepcopy(best),all_worlds,report
