"""Reproducible common-universe shadows for the frozen Showdown parity audit."""
from collections import Counter
from contextlib import redirect_stdout
from copy import deepcopy
from itertools import combinations
from pathlib import Path
import argparse
import time

import pandas as pd
import pulp

from backend.app.product_services.cbc_solver import make_cbc_solver
from backend.app.product_services.rule_library import resolve_strategy_profile
from backend.app.product_services.showdown_game_scenarios import define_game_scenarios, condition_player_pool
from backend.app.product_services.showdown_portfolio_selection import candidate_metrics, select_showdown_portfolio
from backend.app.product_services.showdown_single_entry import select_single_entry_lineups
from scripts.audit_showdown_production_parity import read, write
from scripts.research_showdown_prelock import FrozenService, capture_model, render_solution, signature, thesis, joint_portfolio


def exact(model, frame, key, stack, profile):
    model = deepcopy(model)
    variables = {v.name:v for v in model.variables()}
    indexes = {str(row.player_id):i for i,row in frame.iterrows()}
    for pid,slot in key:
        model += variables[("captain_" if slot=="CPT" else "flex_")+str(indexes[pid])] == 1
    if model.solve(make_cbc_solver("native")) != pulp.LpStatusOptimal:
        return None
    return render_solution(frame, model, model.objective, stack, profile)


def summary(lineups):
    return {"count":len(lineups), "selector":sum(candidate_metrics(l)["selector"] for l in lineups),
            "mean":sum(candidate_metrics(l)["mean"] for l in lineups),
            "p90":sum(candidate_metrics(l)["p90"] for l in lineups),
            "baseline_mean":sum(candidate_metrics(l)["baseline_mean"] for l in lineups),
            "baseline_p90":sum(candidate_metrics(l)["baseline_p90"] for l in lineups),
            "conditioned_mean":sum(sum(r.get('conditioned_projection',r['projection']) for r in l) for l in lineups),
            "conditioned_p90":sum(sum(r.get('conditioned_p90',r['p90']) for r in l) for l in lineups),
            "captains":[candidate_metrics(l)["captain_name"] for l in lineups],
            "scenarios":dict(Counter(candidate_metrics(l)["scenario_id"] for l in lineups)),
            "theses":[thesis(l) for l in lineups],
            "overlap":[len({r['player_id'] for r in a}&{r['player_id'] for r in b}) for a,b in combinations(lineups,2)],
            "lineups":lineups}


def main(directory, research_dir, output_name='common_scored_universe.json'):
    start=time.monotonic()
    production=read(directory/'production_replay.json')
    research=read(research_dir/'quality_shadow.json')
    frozen=read(directory/'production_input_freeze.json')
    job=read(directory/'production_job.json')
    frame=pd.DataFrame(deepcopy(research['prepared_pool'])).reset_index(drop=True)
    raw={r['player_id']:r for r in frozen['player_pool']}
    for _,row in frame.iterrows():
        for k in ('salary','projection','p90','dk_player_id','dk_captain_id'):
            assert row[k]==raw[row.player_id][k], (row.player_id,k)
    # Reuse verified preparation scores, but retain the exact pinned job's
    # projection, feature and source lineage on every common-universe row.
    frame=pd.DataFrame([{**row,**deepcopy(raw[row['player_id']])} for row in frame.to_dict('records')])
    for field in ('ownership','captain_ownership','flex_ownership'):
        frame['diagnostic_'+field]=frame[field]
        frame[field]=None
    profile=resolve_strategy_profile(contest_format='showdown',objective='gpp')
    stack={**research['stack'],'use_role_ownership':False}
    kwargs={'contest_type':'captain','score_col':'optimizer_context_ceiling_score',
            'rule_profile':profile,'stack_params':stack,'include_control_comparison':False,
            'avoid_dst_opponents':job['params']['avoid_dst_opponents']}
    service=FrozenService(frozen)
    scenarios=define_game_scenarios(frame,job['params']['showdown_decisive_margin'])
    frames={s.scenario_id:(frame if not s.winner else condition_player_pool(frame,s)) for s in scenarios}
    with (directory/'common_scoring.log').open('w') as log,redirect_stdout(log):
        models={sid:capture_model(service,f,kwargs) for sid,f in frames.items()}
    prodkeys={signature(l) for l in production['candidates']}
    reskeys={signature(l) for l in research['raw_lineups']}
    rawlines={signature(l):l for l in research['raw_lineups']+production['candidates']}
    sources={tuple(tuple(x) for x in r['signature']):r['discovery_sources'] for r in research['all_candidates']}
    evaluated={}; rejected=[]
    for index,key in enumerate(sorted(rawlines)):
        worlds={}
        for scenario in scenarios:
            sid=scenario.scenario_id
            l=exact(models[sid],frames[sid],key,stack,profile)
            if l is None:
                break
            for r in l:
                factor=1.5 if r['roster_position']=='CPT' else 1
                r['baseline_projection']=raw[r['player_id']]['projection']*factor
                r['baseline_p90']=raw[r['player_id']]['p90']*factor
                r['showdown_scenario_id']=sid
                r['showdown_scenario']=scenario.audit()
                r['diagnostic_ownership']=raw[r['player_id']]['captain_ownership' if factor==1.5 else 'flex_ownership']
                r['ownership']=None
            worlds[sid]=l
        if len(worlds)!=3:
            rejected.append({'signature':key,'reason':'saved production legality (including avoid DST opponents)'})
        else:
            evaluated[key]=worlds
        if index%100==0:print('scored',index,len(rawlines),'seconds',round(time.monotonic()-start,1),flush=True)
    write(directory/output_name,{'input_sha256':production['input_sha256'],
        'records':[{'signature':k,'worlds':v,'production':k in prodkeys,'research':k in reskeys,
                    'research_sources':sources.get(k,[])} for k,v in evaluated.items()],
        'rejected':rejected,'raw_production_rosters':len(prodkeys),'raw_research_rosters':len(reskeys),
        'seconds':time.monotonic()-start})
    print('common complete',len(evaluated),'rejected',len(rejected),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);parser.add_argument('research_dir',type=Path)
    parser.add_argument('--output-name',default='common_scored_universe.json')
    a=parser.parse_args();main(a.directory,a.research_dir,a.output_name)
