"""Opt-in Sunday execution: API control, common-frame discovery, saved replay.

Sources/models are refreshed separately. This command never submits entries.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from dataclasses import replace, asdict
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from itertools import combinations
import json, uuid
from hashlib import sha256
import requests
from backend.app.product_services.classic_prospective import digest_payload
from backend.app.product_services.classic_candidate_completeness import (
    load_context, compact_candidate, roster_key, rank_candidates, capture_model,
    discovery_requests, DiscoveryRequest, compare_targets, recall, saturation,
)
from backend.app.product_services.classic_portfolio_policy import validate_portfolio
from backend.app.product_services.optimizer import OptimizerService
from scripts.research_classic_candidate_completeness import _initialize, _solve
from scripts.reconcile_classic_discovery_selection import resolve_effective_policy, selected_caps, solve, summary, violations
from scripts.rerun_saved_optimizer_for_full_candidates import DERIVED_PARAM_KEYS


def write(path, value):
    with path.open('x') as f:json.dump(value,f,sort_keys=True,indent=2,allow_nan=False)


def report_of(response):return response['results'][0][0]['classic_small_field_report']


def control(p):
    if (p/'preview.json').exists():raise ValueError('Control already saved; use verify')
    old=json.loads(Path('artifacts/classic_reconciliation/20261002T022305Z/control_inputs.json').read_text())
    fresh=json.loads((p/'refresh_lineage.json').read_text());prepared=json.loads((p/'preparation.json').read_text())
    params={k:v for k,v in old['params'].items() if k not in DERIVED_PARAM_KEYS|{'decision_snapshot','projection_scenario_evidence','effective_policy_contract'}}
    params.update(diagnostic_source_optimizer_run_id=old['run']['optimizer_run_id'],
                  reconciliation_preview_policy_id='sunday_main_corrected_control_v1',
                  contest_intent={**prepared['contest_intent'],'intended_profile':'unknown_unassigned'})
    body={'season':2026,'week':4,'slate':'SUNDAY_MAIN','strategy':'classic_small_field_gpp','contest_format':'classic','objective':'gpp',
          'projection_run_id':fresh['projection_run_id'],'data_cutoff_at':fresh['data_cutoff_at'],'params':params,'optimizer_run_id':str(uuid.uuid4())}
    request_path=p/'application_request.json'
    if request_path.exists():body=json.loads(request_path.read_text())
    else:write(request_path,body)
    loaded=requests.get('http://127.0.0.1:8000/api/runtime-code',timeout=30);loaded.raise_for_status();runtime=loaded.json()
    for name,h in runtime['modules'].items():
        if sha256((Path('backend/app/product_services')/name).read_bytes()).hexdigest()!=h:raise ValueError('Service code differs: '+name)
    write(p/'service_loaded_code_final.json',runtime)
    print('POST control',body['optimizer_run_id'],flush=True)
    r=requests.post('http://127.0.0.1:8000/api/optimizer/run',json=body,timeout=1200);r.raise_for_status();response=r.json();write(p/'preview.json',response)
    if response['status']!='completed':raise ValueError(response['message'])
    report=report_of(response)
    inputs={'report':report,'params':body['params'],'run':{'optimizer_run_id':response['job_id'],'projection_run_id':response['projection_run_id'],'data_cutoff_at':response['data_cutoff_at']}}
    write(p/'preview_inputs.json',inputs)
    r=requests.get('http://127.0.0.1:8000/api/optimizer/results/'+response['job_id'],timeout=60);r.raise_for_status();readback=r.json();write(p/'application_readback.json',readback)
    if report!=report_of(readback):raise ValueError('Saved report changed on readback')
    print('Saved control',response['job_id'],report['selected_ranks'],{k:v for k,v in report['policy_validation'].items() if k!='player_appearances'},flush=True)


def independent(rows, inputs, ctx, contract):
    check=validate_portfolio(rows,contract)
    players={p.player_id:p for p in ctx['players']}
    for r in rows:
        if not set(r['player_ids'])<=set(players) or set(r['player_ids']) & ctx['excluded']:raise ValueError('Wrong slate/ineligible canonical roster')
    rosters=[[OptimizerService._gpp_player_to_dict(players[pid]) for pid in r['player_ids']] for r in rows]
    okay,reasons=OptimizerService._validate_classic_lineups(rosters,requested_lineups=contract['effective']['entry_count'],max_exposure=contract['effective']['global_max_exposure'],enforce_single_te=ctx['options']['enforce_single_te'],avoid_dst_opponents=ctx['options']['avoid_dst_opponents'],locked_player_ids=set(ctx['options'].get('locked_player_ids') or []),excluded_player_ids=set(ctx['options'].get('exclude_player_ids') or []),excluded_opponent_teams=set(inputs['params'].get('exclude_opponent_teams') or []))
    if not okay or check['status']!='verified':raise ValueError(str((check,reasons)))
    return check


def expanded(p, workers, per_qb_max):
    if (p/'comparison.json').exists():raise ValueError('Comparison already saved; use verify')
    inputs=json.loads((p/'preview_inputs.json').read_text());ctx=load_context(inputs);r=inputs['report']
    ctx['caps']=r['production_controls']['candidate_caps']
    original=rank_candidates([compact_candidate(c['player_ids'],ctx) for c in r['all_candidates']])
    for old,new in zip(sorted(r['all_candidates'],key=lambda v:-v['objective_score']),original):
        if abs(old['objective_score']-new['objective_score'])>1e-8:raise ValueError('Common scorer mismatch')
    raw={roster_key(c):c for c in original};provenance={roster_key(c):['saved_production_admission'] for c in original}
    for key,labels in r['candidate_discovery']['sources_by_lineup'].items():
        c=compact_candidate(key.split('|'),ctx);raw.setdefault(roster_key(c),c);provenance.setdefault(roster_key(c),[]).extend(labels)
    base=capture_model(ctx)
    from backend.app.product_services.classic_candidate_completeness import solve_request
    frontier=solve_request(base,ctx,DiscoveryRequest('global_frontier'),ctx['options']['solver_backend'])
    if not frontier['rows']:raise ValueError('No proven global frontier')
    peak=frontier['rows'][0]['objective_score']
    qbs=[x for x in ctx['players'] if x.position=='QB' and x.player_id not in ctx['excluded']]
    planned=[DiscoveryRequest('qb_frontier',qb_id=q.player_id,safety_max=per_qb_max,tolerance=.30) for q in sorted(qbs,key=lambda q:q.player_id)]+discovery_requests(ctx,original)
    print('Mandatory discovery requests',len(planned),'QB enumeration safety limit',per_qb_max,flush=True)
    results=[frontier]
    with ProcessPoolExecutor(max_workers=workers,mp_context=get_context('spawn'),initializer=_initialize,initargs=(base,ctx,ctx['options']['solver_backend'],peak)) as pool:
        for i,result in enumerate(pool.map(_solve,planned),1):
            results.append(result)
            if i%25==0:print('Discovery',i,'/',len(planned),flush=True)
    events=[]
    for result in results:
        for event in result['events']:
            event={**event,'source':result['request']['source']}
            if event['status']=='optimal':
                c=compact_candidate(event['player_ids'],ctx)
                if abs(c['objective_score']-event['objective_score'])>1e-8:raise ValueError('Discovery/scorer mismatch')
                raw.setdefault(roster_key(c),c);provenance.setdefault(roster_key(c),[]).append(event['source']);event['candidate']=c
            events.append(event)
    union=rank_candidates([c for c in raw.values() if len(set(c['player_ids'])&ctx['elevated'])<=ctx['policy']['max_elevated_per_lineup'] and not set(c['player_ids'])&ctx['excluded']])
    if not {roster_key(c) for c in original}<={roster_key(c) for c in union}:raise ValueError('Original legal candidates lost')
    # Freeze policy minima/family definitions and eligibility frontier from control.
    policy=resolve_effective_policy(inputs);policy=replace(policy,frontier=r['policy_contract']['effective']['selector_frontier'])
    caps=selected_caps(inputs);minimums=ctx['options'].get('minimum_exposure_by_player') or {}
    incumbent=[c for c in union if c['roster_sha256'] in {compact_candidate(v['player_ids'],ctx)['roster_sha256'] for v in r['all_candidates'] if v['rank'] in r['selected_ranks']}]
    solves={}
    def run(label,rows,pol=policy,cap=caps,warm=None):
        value=solve(rows,pol,cap,ctx['elevated'],minimum_caps=minimums,incumbent=warm,log_path=p/(label+'.cbc.log'))
        result=summary(value,ctx['source'],ctx['risk']);solves[label]=result
        print(label,result['status'],len(result['lineups']),result['selector_sum'],flush=True)
        return result
    run('corrected_control',original,warm=incumbent)
    full=run('expanded_full_legal_reference',union,warm=incumbent)
    targets=compare_targets(union,ctx,(400,),ctx['options']['solver_backend'],peak);admitted=targets['400']['admitted']
    admitted_result=run('expanded_admitted_400',admitted)
    # Supported canonical game-cap sensitivity, explicitly outside main policy.
    run('game_max_three_shadow',union,replace(policy,name='game_max_three_shadow',canonical_game_cap=3))
    core=[]
    if full['status']=='optimal':
        counts=Counter(pid for c in full['lineups'] for pid in c['player_ids'])
        for pid,n in counts.items():
            player=next(x for x in ctx['players'] if x.player_id==pid)
            if n==policy.count and player.position in {'RB','WR','TE'}:
                alternative=run('core_'+pid,union,cap={**caps,pid:(policy.count-1)/policy.count})
                before=Counter(v for c in full['lineups'] for v in c['player_ids']);after=Counter(v for c in alternative['lineups'] for v in c['player_ids'])
                core.append({'player_id':pid,'name':player.name,'approval_status':'PENDING_USER_REVIEW','selector_cost':full['selector_sum']-alternative['selector_sum'] if alternative['status']=='optimal' else None,'mean_cost':full['mean_sum']-alternative['mean_sum'] if alternative['status']=='optimal' else None,'p90_cost':full['p90_sum']-alternative['p90_sum'] if alternative['status']=='optimal' else None,'replacement_dependencies':{v:after[v]-before[v] for v in set(before)|set(after) if before[v]!=after[v]},'alternative':alternative})
    # Verify each explicit overlap on the same frame using the production selector.
    from backend.app.product_services.classic_small_field import _select_global
    runtime_overlap=[]
    for overlap in (4,5,6,None):
        requested={} if overlap is None else {'max_lineup_overlap':overlap}
        from backend.app.product_services.classic_portfolio_policy import resolve_overlap
        effective=resolve_overlap(requested,True)
        indexes=_select_global(union,policy.count,ctx['options']['selection_max_exposure'],set(ctx['options']['locked_player_ids']),caps,minimums,solver_backend=ctx['options']['solver_backend'],max_lineup_overlap=effective,distinct_qb_paths=policy.distinct_qb,max_objective_loss=policy.tolerance,minimum_qb_paths=policy.minimum_qbs,minimum_stack_families=policy.minimum_stack_types,max_lineups_with_any_player_ids=(ctx['elevated'],policy.elevated_share))
        chosen=[union[i] for i in indexes]
        runtime_overlap.append({'requested':requested,'effective':effective,'selected_count':len(chosen),'actual_max_overlap':max((len(set(a['player_ids'])&set(b['player_ids'])) for a,b in combinations(chosen,2)),default=0),'status':'proven_complete' if len(chosen)==policy.count else 'infeasible_or_unproven','runtime_path':'opt_in_current_production_selector_on_fresh_common_frame'})
    # Prefer the bounded admitted path only when it preserves the proven full objective.
    recommended='expanded_admitted_400' if admitted_result['status']=='optimal' and full['status']=='optimal' and abs(admitted_result['selector_sum']-full['selector_sum'])<1e-8 else 'expanded_full_legal_reference'
    if solves[recommended]['status']!='optimal':raise ValueError('Expanded requested portfolio unproven')
    chosen=solves[recommended]['lineups'];validation=independent(chosen,inputs,ctx,r['policy_contract'])
    body={'contract':'sunday_main_integration_preview_v1','preview_run_id':str(uuid.uuid4()),'mode':'OPT_IN_RESEARCH_PREVIEW','decision_at':datetime.now(UTC).isoformat(),'input_sha256':digest_payload(inputs),'control_run_id':inputs['run']['optimizer_run_id'],'projection_run_id':inputs['run']['projection_run_id'],'policy_contract':r['policy_contract'],'frozen_eligibility_policy':asdict(policy),'global_known_frontier':peak,'mandatory_requests_completed':len(planned),'requests':results,'provenance':{'|'.join(k):v for k,v in provenance.items()},'original':original,'union':union,'targets':targets,'solves':solves,'recommended_path':recommended,'core_audits':core,'runtime_overlap':runtime_overlap,'validation':validation,'recall':{'control':recall(union,original,peak),'admitted400':recall(union,admitted,peak)},'saturation':saturation(events,peak),'limits':['All mandatory source sweeps completed before measuring saturation.','Enumeration partitions may be safety-limited or unproven; coverage is known-reference, not exhaustive/global.','Five planning lineups are UNASSIGNED; no paid entry count inferred.','No selection/thesis/ownership weights promoted.','P90 is summed marginal player P90, not a joint lineup quantile or win probability.']}
    write(p/'comparison.json',{**body,'sha256':digest_payload(body)})
    print('Saved expanded',recommended,body['preview_run_id'],flush=True)


def verify(p):
    inputs=json.loads((p/'preview_inputs.json').read_text());ctx=load_context(inputs);bundle=json.loads((p/'comparison.json').read_text())
    if digest_payload({k:v for k,v in bundle.items() if k!='sha256'})!=bundle['sha256']:raise ValueError('Comparison content changed')
    if bundle['input_sha256']!=digest_payload(inputs):raise ValueError('Frozen inputs changed')
    for r in bundle['union']:
        if abs(compact_candidate(r['player_ids'],ctx)['objective_score']-r['objective_score'])>1e-8:raise ValueError('Saved candidate score changed')
    selected=bundle['solves'][bundle['recommended_path']]['lineups'];v=independent(selected,inputs,ctx,bundle['policy_contract'])
    if violations(selected,resolve_effective_policy(inputs),selected_caps(inputs),ctx['elevated']):raise ValueError('Policy mismatch')
    print(json.dumps({'status':'verified','preview_run_id':bundle['preview_run_id'],'saved_control_run_id':inputs['run']['optimizer_run_id'],'roster_hashes':[r['roster_sha256'] for r in selected],'input_sha256':bundle['input_sha256'],'comparison_sha256':bundle['sha256'],'validation':v},indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path);parser.add_argument('--phase',choices=['control','expanded','verify'],required=True);parser.add_argument('--workers',type=int,default=4);parser.add_argument('--per-qb-max',type=int,default=50);a=parser.parse_args()
    if a.phase=='control':control(a.directory)
    elif a.phase=='expanded':expanded(a.directory,a.workers,a.per_qb_max)
    else:verify(a.directory)

if __name__=='__main__':main()
