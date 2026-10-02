"""Exact baseline rescoring and final A–E research solves; no persisted entries."""
import argparse
from collections import Counter
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path
import time

import pandas as pd
import pulp

from backend.app.product_services.cbc_solver import make_cbc_solver
from backend.app.product_services.optimizer import _json_safe
from backend.app.product_services.rule_library import resolve_strategy_profile
from backend.app.product_services.showdown_single_entry import select_single_entry_lineups, DEFAULT_WEIGHTS
from scripts.audit_showdown_gameday import save
from scripts.finalize_showdown_gameday_shadow import read_frozen, mask_diagnostic_ownership
from scripts.research_showdown_prelock import FrozenService, capture_model, render_solution, signature, thesis, validate_lineup, joint_portfolio


def metrics(records, lineups, chosen):
    if len(chosen)!=3:
        return {'feasible':False,'count':len(chosen),'ranks':[records[i]['rank'] for i in chosen]}
    selected = [lineups[i] for i in chosen]
    exposure = Counter(p['name'] for lineup in selected for p in lineup)
    return {'feasible':True,'count':3,'ranks':[records[i]['rank'] for i in chosen],
        'total_selector':sum(records[i]['single_entry_score'] for i in chosen),
        'projected_mean':sum(records[i]['mean'] for i in chosen),
        'summed_marginal_p90':sum(records[i]['p90'] for i in chosen),
        'captains':dict(Counter(records[i]['captain'] for i in chosen)),
        'theses':dict(Counter(records[i]['research_thesis'] for i in chosen)),
        'pairwise_overlap':[len({p['player_id'] for p in selected[i]}&{p['player_id'] for p in selected[j]}) for i,j in ((0,1),(0,2),(1,2))],
        'players_3_of_3':sorted(name for name,count in exposure.items() if count==3),
        'exposures':dict(exposure),'lineups':selected,'records':[records[i] for i in chosen]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory',type=Path)
    parser.add_argument('--morning',type=Path,required=True)
    args = parser.parse_args()
    b, start = args.directory,time.monotonic()
    if (b/'decision.json').exists():raise ValueError('Decision freezes are immutable')
    fenv = read_frozen(b/'refreshed_database_freeze.json')
    qenv = read_frozen(b/'quality_shadow.json');q = qenv['payload']
    assert q['input_sha256']==fenv['sha256']
    morning = read_frozen(args.morning/'quality_shadow.json')['payload']
    frame = pd.DataFrame(q['prepared_pool']).reset_index(drop=True)
    profile = resolve_strategy_profile(contest_format='showdown',objective='gpp')
    kwargs = {'contest_type':'captain','score_col':'optimizer_context_ceiling_score',
              'rule_profile':profile,'stack_params':q['stack'],'include_control_comparison':False}
    with (b/'baseline_model.log').open('w') as log,redirect_stdout(log):
        baseline = capture_model(FrozenService(fenv['payload']),frame,kwargs)
    by_id = {str(frame.loc[i,'player_id']):i for i in frame.index}
    prior = {tuple(tuple(pair) for pair in r['signature']):r for r in q['all_candidates']}
    raw = {signature(l):l for l in q['raw_lineups']}
    morning_keys = [signature(morning['raw_lineups'][rank-1]) for rank in morning['primary_three_ranks']]
    for key in morning_keys:raw.setdefault(key,None)
    rescored, infeasible, changes = {},[],[]
    for key,old_lineup in raw.items():
        if any(pid not in by_id for pid,slot in key):
            infeasible.append({'signature':key,'reason':'Player absent from final eligible model pool'});continue
        evaluation = deepcopy(baseline)
        variables = {v.name:v for v in evaluation.variables()}
        for pid,slot in key:evaluation += variables[('captain_' if slot=='CPT' else 'flex_')+str(by_id[pid])]==1
        if evaluation.solve(make_cbc_solver('native'))!=pulp.LpStatusOptimal:
            infeasible.append({'signature':key,'reason':'Fails exact final baseline legality'});continue
        lineup = _json_safe(mask_diagnostic_ownership(render_solution(frame,evaluation,evaluation.objective,q['stack'],profile)))
        validate_lineup(lineup)
        if old_lineup is not None:
            delta = lineup[0]['solver_objective_value']-old_lineup[0]['solver_objective_value']
            if abs(delta)>1e-8:changes.append({'signature':key,'baseline_objective_delta':delta})
        rescored[key] = lineup
    assert not infeasible or all(tuple(tuple(x) for x in r['signature']) in morning_keys for r in infeasible)
    _,ranking = select_single_entry_lineups(list(rescored.values()),num_contests=1,report_candidate_limit=None)
    assert ranking['objective_weights']==q['weights']==DEFAULT_WEIGHTS
    records = ranking['all_candidates']
    lineups = [rescored[tuple(tuple(pair) for pair in r['signature'])] for r in records]
    slots = {r['ID']:r for r in read_frozen(b/'salary_verification.json')['payload']['rows']}
    for r,l in zip(records,lineups):
        key = signature(l)
        sources = list(prior.get(key,{}).get('discovery_sources',[]))
        if key in morning_keys:sources.append('morning_primary_exact_final_re_evaluation')
        r.update(research_thesis=thesis(l),salary=sum(p['salary'] for p in l),team_counts=dict(Counter(p['player_team'] for p in l)),discovery_sources=sources)
        for p in l:
            slot = slots[p['dk_player_id']]
            assert slot['canonical_player_id']==p['player_id'] and slot['Roster Position']==p['roster_position'] and int(slot['Salary'])==p['salary']
            assert all(p[field] is None for field in ('ownership','captain_ownership','flex_ownership'))
    universe = {'frozen_at':datetime.now(UTC).isoformat(),'input_sha256':fenv['sha256'],
        'full_discovery_sha256':qenv['sha256'],'all_candidates':records,'raw_lineups':lineups,
        'all_candidates_exact_baseline_rescored':True,'baseline_objective_corrections':changes,
        'morning_infeasible':infeasible,'weights':q['weights'],'stack':q['stack']}
    save(b/'final_common_universe.json',universe)
    best = records[0]['single_entry_score']
    eligible = [i for i,r in enumerate(records) if best-r['single_entry_score']<=.10+1e-8]
    er,el = [records[i] for i in eligible],[lineups[i] for i in eligible]
    # This conservative final eligibility gate preserves every model assessment.
    # Roster presence alone does not establish offensive touches for a cheap punt.
    fragile_names = {'Jaleel McLaughlin','Germie Bernard','Eli Heidenreich','Travis Homer','Blake Whiteheart'}
    unsupported = {p['player_id'] for p in q['prepared_pool'] if p['name'] in fragile_names or p['salary']<=1000}
    supported = [i for i,l in enumerate(el) if not ({p['player_id'] for p in l}&unsupported)]
    cr,cl = [er[i] for i in supported],[el[i] for i in supported]
    limits = q['research_policy']['primary_fragile_limits']
    policy = {'different_captains':True,'different_theses':True,'max_shared':4,'exposure_limits':limits}
    A = joint_portfolio(er,el,3)
    B = joint_portfolio(er,el,3,different_captains=True)
    C = joint_portfolio(cr,cl,3,**policy)
    metcalf = next(p['player_id'] for p in q['prepared_pool'] if p['name']=='DK Metcalf')
    E = joint_portfolio(cr,cl,3,**{**policy,'exposure_limits':{**limits,metcalf:2}})
    containing = [i for i,l in enumerate(cl) if any(p['player_id']==metcalf for p in l)]
    three = joint_portfolio([cr[i] for i in containing],[cl[i] for i in containing],3,**policy)
    all_three = metrics(cr,cl,[containing[i] for i in three])
    by_key = {signature(l):i for i,l in enumerate(lineups)}
    D = [by_key[k] for k in morning_keys if k in by_key]
    portfolios = {'A':metrics(er,el,A),'B':metrics(er,el,B),'C':metrics(cr,cl,C),'D':metrics(records,lineups,D),'E':metrics(cr,cl,E)}
    capped = portfolios['E']
    cost = {}
    if all_three['feasible'] and capped['feasible']:
        cost = {field:all_three[field]-capped[field] for field in ('total_selector','projected_mean','summed_marginal_p90')}
        cost['selector_percentage'] = 100*cost['total_selector']/all_three['total_selector']
    frontier = {}
    for r in records:
        group = frontier.setdefault(r['captain'],{'best':r,'counts':{str(t):0 for t in (.05,.10,.15,.20,.30)}})
        for t in (.05,.10,.15,.20,.30):group['counts'][str(t)]+=best-r['single_entry_score']<=t+1e-8
    primary = portfolios['C']
    exposure = '3/3' if primary.get('exposures',{}).get('DK Metcalf')==3 else '2/3' if primary.get('exposures',{}).get('DK Metcalf')==2 else 'other'
    result = {'frozen_at':datetime.now(UTC).isoformat(),'common_universe_sha256':read_frozen(b/'final_common_universe.json')['sha256'],
        'portfolio_alternatives':portfolios,'metcalf_3_of_3':all_three,'metcalf_2_of_3':capped,'alternative_cost':cost,
        'model_supported_portfolio':'C' if primary['feasible'] else None,'model_supported_metcalf_exposure':exposure,
        'candidate_count':len(records),'frontier_count':len(eligible),'captain_frontier':frontier,
        'unsupported_fragile_gate':{'excluded_player_ids':sorted(unsupported),'excluded_names':sorted(fragile_names),
            'reason':'Final dressing and credible current offensive role are not jointly verified. Model truth and raw candidates retained.'},
        'selector_tolerance':.10,'ownership_diagnostic_only':True,'production_selector_used':False,
        'entry_ready':False,'readiness_reason':'Final official inactive/elevation and QB dressing checks still pending at this afternoon freeze.',
        'runtime_seconds':time.monotonic()-start}
    save(b/'decision.json',result)
    print(json.dumps({'candidates':len(records),'exact_rescore_corrections':len(changes),'ranks':{k:v['ranks'] for k,v in portfolios.items()},'metcalf':exposure,'cost':cost,'runtime':result['runtime_seconds']},indent=2))


if __name__=='__main__':main()
