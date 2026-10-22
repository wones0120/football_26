"""Opt-in Classic conditional count sensitivity, frozen by Prepare."""
from copy import deepcopy
from typing import Literal
import math

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .evaluation_record import digest

VERSION='prepared_optimizer_scenario_v1'


class ScenarioMode(BaseModel):
    model_config=ConfigDict(extra='forbid')
    team: str = Field(pattern=r'^[A-Z]{2,3}$')
    passing_factor: float = Field(default=1,ge=.5,le=1.5,allow_inf_nan=False,strict=True)
    rushing_factor: float = Field(default=1,ge=.5,le=1.5,allow_inf_nan=False,strict=True)
    rationale: str = Field(min_length=1,max_length=500)
    scoring_mode: Literal['sensitivity','new_model_primary'] = 'sensitivity'

    @model_validator(mode='after')
    def validate_values(self):
        from .market_snapshots import canonical_team
        self.team=canonical_team(self.team)
        self.rationale=self.rationale.strip()
        if not self.rationale:raise ValueError('Describe the scenario assumption')
        if self.passing_factor==self.rushing_factor==1 and self.scoring_mode!='new_model_primary':raise ValueError('Change at least one volume factor')
        return self


def config(value):
    if value is None:return None
    result=ScenarioMode.model_validate(value).model_dump(mode='json')
    if result['scoring_mode']=='sensitivity':result.pop('scoring_mode')
    return result


def prepare(value, forecast, rows, *, before_period, cutoff, projection_run_id, weekly=None):
    """Hold unsupported components at baseline and disclose every such hold."""
    selected=config(value)
    if selected is None:return None
    if selected['team'] not in {r.get('player_team') or r.get('team') for r in rows}:
        raise ValueError('Scenario team is outside the prepared slate')
    assumptions=[dict(kind=k,team=selected['team'],factor=selected[f],rationale=selected['rationale'])
        for k,f in [('passing_volume','passing_factor'),('rushing_volume','rushing_factor')] if selected[f]!=1]
    base={str(r['player_id']):float(r['projection']) for r in rows
          if r.get('projection') is not None and math.isfinite(float(r['projection']))}
    response=None;issue=None
    try:
        if forecast is None:raise ValueError('Prepared workload reference unavailable')
        receipt=deepcopy(forecast)
        if not receipt.get('reference_count_forecast') or not receipt.get('component_response'):
            if weekly is None:raise ValueError('Matched prior component history unavailable')
            from .count_component_response import component_response
            from .opportunity_role_allocation import allocate_factual_vacancies, unavailable_from_canonical_rows
            anchor={k:deepcopy(receipt[k]) for k in ('version','before_period','teams','players')}
            unavailable,unresolved=unavailable_from_canonical_rows(rows,before_period=before_period,cutoff=cutoff)
            current=allocate_factual_vacancies(anchor,unavailable=unavailable,cutoff=cutoff)
            receipt.update(current,reference_count_forecast=anchor,
                component_response=component_response(weekly,anchor,current,base,before_period=before_period,cutoff=cutoff),
                unresolved_vacancy_proofs=unresolved)
            receipt.pop('sha256',None)
            receipt['sha256']=digest(receipt)
        from .count_scenario_response import count_world
        response=count_world(receipt,dict(scenario_id=VERSION,label=selected['rationale'],assumptions=assumptions),base,cutoff=cutoff)['response']
    except (ValueError,KeyError) as exc:
        issue=str(exc)
    by_id={p['player_master_id']:p for p in (response or {}).get('players',[])}
    players=[]
    for row in rows:
        pid=str(row['player_id']);original=base.get(pid);actor=by_id.get(pid)
        supported=actor.get('supported_components',[]) if actor else []
        mean=actor.get('conditional_mean') if actor else original
        if mean is None:mean=original
        missing=[]
        if not actor:missing.append(issue or 'No matched count/component actor; baseline retained')
        if actor:
            missing+=['Unmatched component held at baseline: '+c for c in actor['unchanged_unsupported_components']]
            missing+=actor.get('reasons',[])
            if actor.get('anchor_inconsistency'):missing.append('Baseline/component anchor inconsistent; sensitivity is provisional')
        players.append(dict(player_master_id=pid,name=row.get('name'),team=row.get('player_team') or row.get('team'),
            baseline_mean=original,conditional_mean=mean,delta=None if mean is None or original is None else mean-original,
            supported_components=supported,missing_evidence=missing))
    report=dict(version=VERSION,config=selected,assumptions=assumptions,before_period=before_period,
        scoring_basis='incumbent_anchored_component_sensitivity',new_model_primary=False,
        full_game_simulator_consumed=False,
        team_model_consumption=deepcopy((forecast or {}).get('team_opportunity_model_inference') or
            {'status':'not_consumed','reason':'No published team-model inference in the prepared workload receipt'}),
        cutoff=str(cutoff),projection_run_id=projection_run_id,
        status='UNAVAILABLE_BASELINE_RETAINED' if response is None else 'CONDITIONAL_PARTIAL_COMPONENTS',
        issue=issue,players=players,changed_player_count=sum(p['delta'] is not None and abs(p['delta'])>1e-9 for p in players),
        count_parent_sha256=(forecast or {}).get('sha256'),
        shared_budgets=(response or {}).get('new_shared_budgets'),
        count_budgets=((response or {}).get('semantic_values',{}).get('new') or {}).get('teams'),
        component_response_sha256=(response or {}).get('semantic_sha256'),
        limitations=['Incumbent projection plus supported component deltas; this is not standalone new-model primary scoring.',
            'Authored volume assumptions; likelihood unknown.',
            'Only matched prior non-TD linear components change; TDs, bonuses and undecomposed baseline contributions stay fixed.',
            'Participation, role stability and clock/continuation uncertainty are not jointly simulated.',
            'Unsupported components/players retain baseline values and are listed explicitly; no evidence of predictive improvement.'],
        baseline_projections_mutated=False)
    report['sha256']=digest(report)
    return report


def verify(report, value, projection_run_id):
    if not report or report.get('config')!=config(value) or report.get('projection_run_id')!=projection_run_id:
        raise ValueError('Scenario changed or missing; Prepare slate again')
    stored=deepcopy(report);sha=stored.pop('sha256',None)
    if sha!=digest(stored):raise ValueError('Prepared scenario receipt checksum mismatch')


def normalize_showdown_request(params):
    config(params.get('scenario_mode'))
    if any(params.get(k) for k in ('locked_player_ids','lock_player_ids','locked_players','locked_captain_player_id','long_shot_mode')):
        raise ValueError('Scenario comparison requires no player locks or long-shot scoring; clear them explicitly')
    if any(float(v)>0 for v in (params.get('minimum_exposure_by_player') or {}).values()):
        raise ValueError('Scenario comparison cannot retain minimum-exposure player locks')
    for key in tuple(params):
        if key.startswith('analyst_'):params.pop(key)
    params.update(num_lineups=1,analyst_handoff_mode='BASELINE',analyst_optimization_intent='MIXED')


def stable_solver_snapshot(value):
    """JSONB drops negative-zero signs; duals must not break replay hashes."""
    if isinstance(value,dict):return {k:stable_solver_snapshot(v) for k,v in value.items()}
    if isinstance(value,list):return [stable_solver_snapshot(v) for v in value]
    if isinstance(value,float) and value==0:return 0.
    return value


def _showdown_exact(service,pool,*,params,cutoff,stack_params,conditional_means=None,flex_only_ids=(),primary=False):
    """Matched Captain mean solve with existing hard football/user rules."""
    import pulp
    from .optimizer import _json_safe
    from .classic_portfolio_controls import explicit_appearance_limit
    frame=pool.copy(deep=True)
    incumbent=primary and conditional_means is None
    column='scenario_mean' if conditional_means is not None else 'projection'
    if conditional_means is not None:frame[column]=frame.player_id.astype(str).map(conditional_means)
    if primary and conditional_means is not None:
        # Model coverage and factual/user rules determine eligibility. The old
        # model's P90 shortlist cannot constrain the new-model primary arm.
        frame['showdown_captain_shortlisted']=True
    if not frame[column].map(lambda v:v is not None and math.isfinite(float(v))).all():
        raise ValueError('Every eligible scenario actor requires a finite frozen mean')
    captured={}
    def objective(model,rows,selected):
        variables=model.variablesDict()
        model.setObjective(pulp.lpSum(1.5*float(rows.loc[i,'showdown_captain_p90' if incumbent else column])*variables[f'captain_{i}']+
            float(rows.loc[i,column])*variables[f'flex_{i}'] for i in rows.index))
        for i in rows.index:
            row=rows.loc[i];pid=str(row['player_id'])
            role='starting_qb_max_exposure' if row['position']=='QB' and row.get('showdown_qb_eligible') else 'cheap_punt_max_exposure' if float(row['salary'])<=1000 else 'core_player_max_exposure'
            rates=[params.get('max_exposure',1),params.get(role,1),(params.get('maximum_exposure_by_player') or {}).get(pid,1)]
            if any(explicit_appearance_limit(1,float(v))==0 for v in rates):model+=selected[i]==0
            if explicit_appearance_limit(1,float(params.get('captain_max_exposure',1)))==0:model+=variables[f'captain_{i}']==0
        captured.update(model=model,rows=rows)
    lineup=service._solve_lineup(frame,score_col=column,contest_type='captain',
        stack_params={**stack_params,'bounded_scenario_comparison':True,'scenario_incumbent_control':incumbent},
        flex_only_player_ids=set(flex_only_ids),avoid_dst_opponents=bool(params.get('avoid_dst_opponents')),
        include_control_comparison=False,additional_constraints=objective)
    model=captured.get('model')
    frozen=stable_solver_snapshot(dict(players=_json_safe(frame.to_dict('records')),model=_json_safe(model.toDict()) if model is not None else None))
    audit=dict(policy_id=VERSION,objective_id='new_model_primary' if primary and conditional_means is not None else 'conditional_mean' if conditional_means is not None else 'baseline_mean',
        objective_label='New-model primary score' if primary and conditional_means is not None else 'Existing Captain P90/FLEX mean scoring' if incumbent else 'Experimental scenario mean' if conditional_means is not None else 'Highest baseline mean under matched Captain eligibility',
        solver_status=pulp.LpStatus[model.status] if model is not None else 'Not Solved',
        solution_status=pulp.LpSolution.get(model.sol_status) if model is not None else None,
        input_snapshot=frozen,input_snapshot_sha256=digest(frozen),locked_player_ids=[],constraints_relaxed=False,
        captain_multiplier=1.5,physical_count_multiplier=1,conditional_adjustments=conditional_means is not None,
        base_mean=sum(float(p['projection']) for p in lineup) if lineup else None,
        salary=sum(float(p['salary']) for p in lineup) if lineup else None,
        conditional_mean=sum(float(p['objective_score']) for p in lineup) if lineup and conditional_means is not None else None)
    if lineup:
        assert model.valid(1e-5)
        assert abs(sum(float(p['objective_score']) for p in lineup)-pulp.value(model.objective))<1e-6
        for row in lineup:
            row.update(selection_objective=audit['objective_id'],selection_policy_id=VERSION,solver_scoring_policy='new_model_primary_v1' if primary and conditional_means is not None else VERSION)
            if conditional_means is not None:
                row['base_scenario_mean']=conditional_means[str(row['player_id'])]
                row['scenario_mean']=row['objective_score']
    return ([lineup] if lineup else []),audit


def solve(service,pool,*,params,cutoff,contest_format='classic',stack_params=None,flex_only_ids=()):
    from .classic_highest_projection import solve as exact
    prepared=params.get('prepared_input_evidence') or {}
    report=prepared.get('scenario_mode')
    verify(report,params.get('scenario_mode'),prepared.get('projection_run_id'))
    values={p['player_master_id']:p for p in report['players']}
    original_pool=pool
    scores={}
    exclusions=[]
    for row in pool.to_dict('records'):
        pid=str(row['player_id']);actor=values.get(pid)
        if actor is None or actor['baseline_mean']!=float(row['projection']):
            raise ValueError('Scenario baseline pool changed; Prepare again')
        if actor['conditional_mean'] is None and report.get('new_model_primary'):
            exclusions.append(dict(player_id=pid,name=row.get('name'),reason='Unknown complete new-model score; no incumbent fallback'))
        else:scores[pid]=actor['conditional_mean']
    if report.get('new_model_primary'):
        pool=pool.loc[pool.player_id.astype(str).isin(scores)].copy()
        if pool.empty:raise ValueError('No supported new-model player scores; no incumbent fallback')
    if contest_format=='showdown':
        kwargs=dict(params=params,cutoff=cutoff,stack_params=stack_params or {},flex_only_ids=flex_only_ids,primary=bool(report.get('new_model_primary')))
        baseline_lines,baseline=_showdown_exact(service,original_pool if report.get('new_model_primary') else pool,**kwargs)
        lines,audit=_showdown_exact(service,pool,conditional_means=scores,**kwargs)
    else:
        baseline_lines,baseline=exact(service,pool,params=params,cutoff=cutoff)
        lines,audit=exact(service,pool,params=params,cutoff=cutoff,conditional_means=scores)
    comparison=dict(prepared=report,baseline_solver_status=baseline['solver_status'],
        baseline_lineup=baseline_lines[0] if baseline_lines else [],baseline_mean=baseline.get('base_mean'),
        baseline_input_snapshot=baseline.get('input_snapshot'),
        conditional_mean=audit.get('conditional_mean'),scenario_lineup_baseline_mean=audit.get('base_mean'),
        baseline_lineup_conditional_mean=sum(scores[str(p['player_id'])]*(1.5 if p.get('roster_position')=='CPT' else 1) for p in baseline_lines[0]) if baseline_lines and all(str(p['player_id']) in scores for p in baseline_lines[0]) else None,
        matched_pool=not bool(exclusions),settings_unchanged=True,model_coverage_exclusions=exclusions,
        comparison_type='new_forecast_and_generation_policy_vs_incumbent' if report.get('new_model_primary') else 'matched_mean_sensitivity',
        baseline_policy=baseline['objective_label'],new_captain_policy='All score-supported actors under factual/user rules; no incumbent P90 shortlist' if report.get('new_model_primary') else 'Matched incumbent Captain shortlist')
    for lineup in lines:
        for row in lineup:
            row['scenario_mode_player']=deepcopy(values[str(row['player_id'])])
        if lineup:lineup[0]['scenario_mode_report']={k:v for k,v in comparison.items() if k!='baseline_input_snapshot'}
    return lines,audit,comparison
