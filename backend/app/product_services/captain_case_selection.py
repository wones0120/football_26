"""Bounded global whole-lineup selection across shared physical scoring cases."""
from copy import deepcopy
import math
import hashlib
from pathlib import Path
import time

import pulp

from .evaluation_record import digest
from .captain_game_cases import VERSION
from .shared_world_runtime import user_legal_kwargs
from .captain_case_policy import preference, assessment, metrics, describe


def solve(service, pool, *, receipt, params, contest_type, stack_params, locked_ids,
          flex_only_ids, avoid_dst_opponents, enforce_single_te, requested_captain_id):
    cases=receipt.get('scenario_first') or {}
    if cases.get('version')!=VERSION or contest_type!='captain':raise ValueError('Prepare the supported scenario-first Captain receipt')
    if int(params.get('num_lineups',1))!=1:raise ValueError('Scenario-first v1 requires exactly one requested lineup; settings were not relaxed')
    if params.get('require_team_leader') or params.get('require_home_team_leader'):
        raise ValueError('Scenario-first cannot consume points-leader selection requirements')
    actors={a['player_master_id']:a for a in receipt['players']}
    all_worlds=cases['worlds']
    if not 1<=len(all_worlds)<=20:raise ValueError('Shared scoring case bound exceeded')
    primary=cases.get('primary_scenario') or {}
    primary_ids=primary.get('case_ids') or []
    worlds=[w for w in all_worlds if w['world_id'] in primary_ids]
    diagnostics=[w for w in all_worlds if w['world_id'] not in primary_ids]
    if (primary.get('version')!='market_implied_primary_v1' or not worlds or
        len(primary_ids)!=len(set(primary_ids)) or len(worlds)!=len(primary_ids) or
        set(primary_ids)!={w['world_id'] for w in all_worlds if w.get('coordinate')=='central'} or
        set(primary.get('diagnostic_case_ids') or [])!={w['world_id'] for w in diagnostics}):
        raise ValueError('Prepare a valid market-centered primary scenario; no cross-script fallback')
    frame=pool.loc[pool.player_id.astype(str).map(lambda p: actors.get(p,{}).get('utility') is not None and actors[p]['utility']>0)].copy()
    policy=preference(params)
    assessments=[assessment(a,policy) for a in actors.values()]
    preference_excluded={a['player_master_id'] for a in assessments if a['excluded']}
    frame=frame.loc[~frame.player_id.astype(str).isin(preference_excluded)].copy()
    target=params.get('scenario_capture_target',.9)
    if isinstance(target,bool) or not isinstance(target,(int,float)) or not math.isfinite(target) or not 0<target<=1:
        raise ValueError('Competitive case capture target must be in (0,1]')
    frame=frame.sort_values('player_id').reset_index(drop=True)
    if set(locked_ids)-set(frame.player_id.astype(str)):raise ValueError('Locked actor lacks supported evidence or conflicts with backup involvement preference; no preference bypass')
    if frame.empty:return [],dict(status='failed_empty_supported_scenario_pool',version=VERSION,mode='scenario_first',requested=1,achieved=0,user_preference=policy,user_preference_assessments=assessments,forecast_sha256=receipt['sha256'],points_selection_gates_consumed=False)
    frame['workload_utility']=frame.player_id.astype(str).map(lambda p:actors[p]['utility'])
    teams=sorted(set(frame.player_team))
    if len(teams)!=2:raise ValueError('Both game teams require supported eligible actors')
    for a in actors.values():
        if a.get('utility') is not None and set(a['scenario_scores'])!={w['world_id'] for w in all_worlds}:
            raise ValueError('Actor/world scoring coverage mismatch')
    started=time.monotonic();deadline=started+65.;selection={};audit={}
    def constrain(model, rows, selected):
        for team in teams:
            model.addConstraint(pulp.lpSum(selected[i] for i in rows.index if rows.loc[i,'player_team']==team)==3,'scenario_three_'+team)
        original=deepcopy(model.toDict());case_optima={};oracles=[]
        for world in worlds:
            seconds=min(1.5,deadline-time.monotonic()-20.)
            if seconds<=0:raise ValueError('Scenario oracle deadline exhausted; no unproved fallback')
            variables,copy=pulp.LpProblem.fromDict(deepcopy(original))
            expressions=[]
            for i,row in rows.iterrows():
                score=world['player_scores'][str(row.player_id)]
                expressions.extend([variables[f'captain_{i}']*1.5*score,variables[f'flex_{i}']*score])
            copy.setObjective(pulp.lpSum(expressions))
            copy.solve(pulp.PULP_CBC_CMD(msg=False,timeLimit=seconds,threads=0,options=['randomSeed 17']))
            if copy.status!=pulp.LpStatusOptimal or copy.sol_status!=pulp.LpSolutionOptimal or not copy.valid(1e-6):
                raise ValueError(f'Case {world["world_id"]} lacks Optimal proof: status={copy.status}, solution={copy.sol_status}, valid={copy.valid(1e-6)}; no relaxation')
            optimum=pulp.value(copy.objective)
            if optimum is None or optimum<=0:raise ValueError('Unknown/nonpositive legal case benchmark')
            case_optima[world['world_id']]=float(optimum)
            roster=[dict(player_master_id=str(row.player_id),role=role) for i,row in rows.iterrows() for role,name in [('CPT','captain'),('FLEX','flex')]
                    if (pulp.value(variables[f'{name}_{i}']) or 0)>.5]
            oracles.append(dict(world_id=world['world_id'],objective=float(optimum),status='Optimal',roster=roster,canonical_id=digest(roster)))
        variables=model.variablesDict();coverage=[];relative=[]
        for index,world in enumerate(worlds):
            expression=pulp.lpSum(world['player_scores'][str(row.player_id)]*(1.5*variables[f'captain_{i}']+variables[f'flex_{i}']) for i,row in rows.iterrows())
            covered=pulp.LpVariable(f'scenario_covered_{index}',cat='Binary')
            model.addConstraint(expression>=target*case_optima[world['world_id']]*covered,'scenario_coverage_'+str(index))
            coverage.append(covered);relative.append(expression/case_optima[world['world_id']])
        # Every legal score / proven legal optimum is <=1. Thus N+1 makes
        # one extra covered case dominate all possible secondary-score changes.
        model.setObjective((len(worlds)+1)*pulp.lpSum(coverage)+pulp.lpSum(relative))
        selection.update(case_optima=case_optima,oracles=oracles,model_before_selection_sha256=digest(original),
            primary_case_ids=primary_ids,diagnostic_case_ids=[w['world_id'] for w in diagnostics],
            alternative_scripts_consumed=False,
            static_qb_strategy_rules='inactive; shared events evaluate dependence',
            policy='market-implied primary scenario only: maximize cases reaching declared fraction of best legal whole-roster score; primary mean relative capture breaks ties',
            capture_target=target,primary='competitive_case_count',secondary='mean_relative_capture',
            lexicographic_primary_weight=len(worlds)+1,
            solver_execution='CBC serial (threads=0); fixed seeds; no threaded branch worker',
            case_likelihood='unknown; coverage counts are not probabilities')
    from .classic_portfolio_controls import explicit_appearance_limit
    def limit(value):
        value=float(value);value=value/100 if value>1 else value
        if not 0<=value<=1:raise ValueError('Scenario exposure outside0..1')
        return explicit_appearance_limit(1,value)
    max_rate=params.get('max_exposure',1)
    remaining={}
    for row in frame.to_dict('records'):
        role_key='starting_qb_max_exposure' if row['position']=='QB' else 'cheap_punt_max_exposure' if float(row['salary'])<=1000 else 'core_player_max_exposure'
        remaining[str(row['player_id'])]=min(limit(max_rate),limit(params.get(role_key,1)),limit((params.get('maximum_exposure_by_player') or {}).get(str(row['player_id']),1)))
    base=user_legal_kwargs(dict(stack_params=stack_params))['stack_params']
    lineup=service._solve_lineup(frame,score_col='workload_utility',contest_type='captain',
        stack_params={**base,'scenario_serial_solver':True,'offensive_workload':True,'learned_opportunity_audit':audit},
        exposure_remaining=remaining,captain_exposure_remaining={str(p):limit(params.get('captain_max_exposure',1)) for p in frame.player_id},
        locked_player_ids=locked_ids,flex_only_player_ids=flex_only_ids,locked_captain_player_id=requested_captain_id,
        avoid_dst_opponents=avoid_dst_opponents,enforce_single_te=enforce_single_te,
        additional_constraints=constrain,rule_profile=None,include_control_comparison=False)
    report=dict(version=VERSION,mode='scenario_first',status='completed' if lineup else 'failed_no_relaxation',requested=1,achieved=int(bool(lineup)),
        selector_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        preference_code_sha256=hashlib.sha256(Path(__file__).with_name('captain_case_policy.py').read_bytes()).hexdigest(),
        forecast_sha256=receipt['sha256'],source_cutoff_at=receipt['source_cutoff_at'],supported_pool=len(frame),
        objective='whole_lineup_case_coverage',domain=receipt['domain'],scenario_first={k:v for k,v in cases.items() if k not in {'worlds','source_ids','excluded_historical_team_games'}},
        case_summaries=[dict(world_id=w['world_id'],likelihood='unknown',teams=w['teams']) for w in worlds],
        selection=selection,solver_audits=[audit],elapsed_seconds=time.monotonic()-started,
        inactive_point_preferences=params.get('inactive_point_preferences',{}),points_selection_gates_consumed=False,
        user_preference=policy,user_preference_assessments=assessments,
        excluded_domain_or_unknown=[dict(player_id=str(row['player_id']),name=row.get('name'),reasons=actors.get(str(row['player_id']),{}).get('reasons') or ['unsupported or zero scoring across declared shared cases'])
            for row in pool.to_dict('records') if str(row['player_id']) not in set(frame.player_id.astype(str)) and str(row['player_id']) not in preference_excluded])
    if not lineup:return [],report
    if audit.get('input_snapshot',{}).get('model',{}).get('parameters',{}).get('sol_status')!=pulp.LpSolutionOptimal:
        raise ValueError('Whole-lineup solve lacks proven optimality; no feasible-only fallback')
    if any(remaining[str(row['player_id'])]<1 for row in lineup):
        raise ValueError('Scenario selection violates explicit exposure; no lock override')
    for row in lineup:
        row['workload_forecast']=actors[str(row['player_id'])];row['workload_forecast_sha256']=receipt['sha256']
    scores=[]
    for world in worlds:
        score=sum(world['player_scores'][str(p['player_id'])]*(1.5 if p['roster_position']=='CPT' else 1) for p in lineup)
        scores.append(dict(world_id=world['world_id'],lineup_score=score,best_legal_score=selection['case_optima'][world['world_id']],capture_ratio=score/selection['case_optima'][world['world_id']],
            players=[dict(player_master_id=str(p['player_id']),name=p['name'],role=p['roster_position'],stats=world['player_stats'][str(p['player_id'])],
                score=world['player_scores'][str(p['player_id'])]*(1.5 if p['roster_position']=='CPT' else 1)) for p in lineup]))
    roster=[dict(player_master_id=str(p['player_id']),role=p['roster_position']) for p in lineup]
    evaluation=metrics(roster,worlds,selection['case_optima'],target)
    report.update({k:v for k,v in evaluation.items() if k!='case_evaluations'})
    report['case_evaluations']=scores
    report['alternative_script_evaluations']=[dict(world_id=w['world_id'],selection_consumed=False,
        lineup_score=sum(w['player_scores'][str(p['player_id'])]*(1.5 if p['roster_position']=='CPT' else 1) for p in lineup),
        team_points={team:t['points'] for team,t in w['teams'].items()}) for w in diagnostics]
    for value in scores:value['competitive']=value['capture_ratio']>=target-1e-7
    if not math.isclose(evaluation['selection_value'],audit['objective'],abs_tol=1e-5):
        raise ValueError('Whole-roster coverage objective differs from saved solver')
    audit.update(full_fantasy_projection_in_objective=False,partial_dk_yard_scoring_in_objective=False,shared_event_dk_scoring=True,
        selection_basis='complete-roster competitive case coverage, mean relative capture tie-break; worst-case capture is diagnostic only',incumbent_projection_consumed=False)
    native={str(p['player_id']):p for p in pool.to_dict('records')}
    frame_native={str(p['player_id']):p for p in frame.to_dict('records')}
    snapshot=audit['input_snapshot']['model']
    selected_captain=next(p['player_master_id'] for p in roster if p['role']=='CPT')
    def comparison_solve(*,forbid_captain=None,fix_captain=None):
        seconds=min(5.,deadline-time.monotonic())
        if seconds<=0:raise ValueError('Captain comparison deadline exhausted; no omitted comparison')
        variables,model=pulp.LpProblem.fromDict(deepcopy(snapshot))
        for i,row in frame.iterrows():
            if str(row.player_id)==forbid_captain:model+=variables[f'captain_{i}']==0
            if str(row.player_id)==fix_captain:model+=variables[f'captain_{i}']==1
        model.solve(pulp.PULP_CBC_CMD(msg=False,timeLimit=seconds,threads=0,options=['randomSeed 17']))
        proof=dict(status=pulp.LpStatus[model.status],solution_status=model.sol_status)
        if model.status==pulp.LpStatusInfeasible:return dict(**proof,requested=1,achieved=0,reason='Proven infeasible without relaxation')
        if model.status!=pulp.LpStatusOptimal or model.sol_status!=pulp.LpSolutionOptimal or not model.valid(1e-5):
            raise ValueError('Captain comparison lacks Optimal proof; no unproved fallback')
        decoded=[dict(player_master_id=str(row.player_id),role=role) for i,row in frame.iterrows()
            for role,key in [('CPT','captain'),('FLEX','flex')] if (variables[f'{key}_{i}'].varValue or 0)>.5]
        encoded=model.toDict()
        for constraint in encoded['constraints']:
            if constraint.get('pi')==0:constraint['pi']=0.
        result=dict(**proof,requested=1,achieved=1,roster=describe(decoded,native),model=encoded,model_sha256=digest(encoded),
            treatment=dict(forbidden_captain_id=forbid_captain,fixed_captain_id=fix_captain),
            **metrics(decoded,worlds,selection['case_optima'],target))
        if not math.isclose(result['selection_value'],pulp.value(model.objective),abs_tol=1e-5):
            raise ValueError('Captain comparison objective mismatch')
        return result
    alternative=comparison_solve(forbid_captain=selected_captain)
    report['different_captain_comparison']=alternative
    reference=params.get('scenario_reference_roster')
    reference_report=None;reference_captain_report=None
    if reference:
        ids=reference.get('player_ids') or [];captain=reference.get('captain_player_id')
        if len(ids)!=6 or len(set(ids))!=6 or captain not in ids or any(pid not in native or pid not in actors or actors[pid].get('utility') is None for pid in ids):
            raise ValueError('Reference requires six distinct supported native canonical actors and one Captain among them')
        reference_roster=[dict(player_master_id=pid,role='CPT' if pid==captain else 'FLEX') for pid in ids]
        reasons=[a for a in assessments if a['player_master_id'] in ids and a['excluded']]
        reference_report=dict(label='User-specified offensive reference; comparison only',roster=describe(reference_roster,native),
            user_preference_violations=reasons,**metrics(reference_roster,worlds,selection['case_optima'],target))
        variables,model=pulp.LpProblem.fromDict(deepcopy(snapshot))
        for variable in variables.values():variable.varValue=0.
        for i,row in frame.iterrows():
            pid=str(row.player_id)
            if pid in ids:variables[f'{"captain" if pid==captain else "flex"}_{i}'].varValue=1.
        for index,value in enumerate(reference_report['case_evaluations']):variables[f'scenario_covered_{index}'].varValue=int(value['competitive'])
        reference_report['legal_under_current_constraints']=not reasons and set(ids)<=set(frame_native) and model.valid(1e-5)
        reference_report['violated_constraints']=[name for name,constraint in model.constraints.items() if not constraint.valid(1e-5)]
        ci=next((i for i,row in frame.iterrows() if str(row.player_id)==captain),None)
        captain_supported=ci is not None and snapshot['variables'][next(i for i,v in enumerate(snapshot['variables']) if v['name']==f'captain_{ci}')]['upBound']!=0
        # Some user Captain restrictions are constraints rather than bounds.
        if captain_supported:
            if captain==selected_captain:reference_captain_report=dict(status='Optimal',achieved=1,roster=describe(roster,native),**evaluation,reused='selected global optimum')
            elif alternative.get('achieved') and any(p['role']=='CPT' and p['player_master_id']==captain for p in alternative['roster']):reference_captain_report={**alternative,'reused':'best different-Captain optimum'}
            else:reference_captain_report=comparison_solve(fix_captain=captain)
        else:reference_captain_report=dict(status='excluded',achieved=0,reason='Reference Captain outside eligible pool/current Captain preference; no exception added')
    report['reference_comparison']=reference_report
    report['reference_captain_comparison']=reference_captain_report
    report['elapsed_seconds']=time.monotonic()-started
    for row in lineup:
        row['scenario_first_lineup_report']=dict(version=VERSION,competitive_cases=evaluation['competitive_cases'],total_cases=len(worlds),
            capture_target=target,mean_capture_ratio=evaluation['mean_capture_ratio'],worst_capture_ratio=evaluation['worst_capture_ratio'],
            case_evaluations=scores,selection_policy=selection['policy'],assumptions=cases['assumptions'],market=cases['market'],
            construction_policy=cases['construction_policy'],likelihood='unknown',user_preference=policy,
            primary_scenario=primary,alternative_script_evaluations=report['alternative_script_evaluations'],
            kicking_reconciliation=dict(version='joint_source_kicking_v1',primary_cases=[dict(world_id=w['world_id'],
                teams={team:{**t['kicking_profile'],'recipient':t['kicker'],'name':actors.get(t['kicker'],{}).get('name') or 'Unmodeled kicker','case_pats':t['made_pats']}
                    for team,t in w['teams'].items()}) for w in worlds]),
            passing_reconciliation={**cases['passing_reconciliation'],'primary_cases':[dict(world_id=w['world_id'],
                teams={team:dict(donor_period=t['joint_role_profile']['period'],team_attempts=t['pass_attempts'],
                    unmodeled_attempts=t['quarterback_pass_residual'],passers=[dict(**p,
                        name=actors.get(p['player_master_id'],{}).get('name') or p['source_player_id']) for p in t['passing_allocation']])
                    for team,t in w['teams'].items()}) for w in worlds]},
            preference_exclusions=[a for a in assessments if a['excluded']],
            different_captain_comparison={k:v for k,v in alternative.items() if k!='model'},
            reference_comparison=reference_report,reference_captain_comparison={k:v for k,v in (reference_captain_report or {}).items() if k!='model'}) if row['roster_position']=='CPT' else None
    return [lineup],report
