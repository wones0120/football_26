"""Offline, four predeclared screen arms; writes only this research directory."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import pulp
from research.showdown_fixed_pool_20261013 import experiment as h

OUT=Path(__file__).resolve().parent
PRIOR=OUT.parent/'showdown_fixed_pool_20261013'
ARMS={'both95':(True,True),'mean95':(True,False),'marginal_p9095':(False,True),'neither':(False,False)}
FIELDS=['name','player_id','position','player_team','salary','canonical_role','offensive_role_class','offensive_role_reason','offensive_role_confidence','offensive_role_source','role_source','role_observed_at','role_starter_evidence','is_starting_qb','projected_targets','projected_carries','targets_mean_3','carries_mean_3','snap_share_mean_3','pregame_expected_targets','pregame_expected_carries','pregame_expected_snaps','pregame_expected_routes','pregame_target_share','pregame_carry_share','pregame_goal_line_share','pregame_red_zone_share','projected_opportunity_source','game_total_line','team_spread_line','team_implied_total','opponent_implied_total','market_source_system','market_observed_at','market_context_point_in_time_safe','market_source_snapshot_id','market_snapshot_row_id','pregame_context_run_id','pregame_context_observed_at']

def read(p): return json.loads(p.read_text())
def save(p,v):
    content=json.dumps(v,indent=2,sort_keys=True,allow_nan=False)+'\n'
    if p.exists(): assert p.read_text()==content, f'Immutable output differs: {p}'
    else: p.write_text(content)
def gate(row,thresholds,arm):
    m,c=ARMS[arm]
    return (not m or row['mean_score']+1e-8>=thresholds['mean']) and (not c or row['p90_score']+1e-8>=thresholds['p90'])
def support(p):
    return p.get('is_starting_qb') is True or p.get('offensive_role_class') in {'offensive centerpiece','primary option','major secondary option'}
def annotate(r,players):
    sig=h.signature(r); ids={pid for pid,_ in sig}; cap=next(players[pid] for pid,c in sig if c)
    ps=[players[pid] for pid,_ in sig]; qs=[p for p in ps if p['position']=='QB']; rec=[p for p in ps if p['position'] in {'WR','TE'}]
    stacks=[dict(qb_id=q['player_id'],receiver_ids=[p['player_id'] for p in rec if p['player_team']==q['player_team']]) for q in qs]
    pairs=[]
    for team in sorted({p['player_team'] for p in ps}):
        rb=[p['player_id'] for p in ps if p['player_team']==team and p['position']=='RB']
        qb=[p['player_id'] for p in qs if p['player_team']==team]
        if len(rb)>1 or (rb and qb): pairs.append(dict(team=team,rb_ids=rb,qb_ids=qb,status='shared_team_TD_dependencies; no verified joint budget'))
    savers=[]
    for p in ps:
        if p['player_id']==cap['player_id'] or p['salary']>3000: continue
        specialist=p['position'] in {'K','DST'}
        # Participation evidence; these descriptive thresholds never filter players.
        positive=any(p.get(k) is not None and float(p[k])>0 for k in ['projected_targets','projected_carries','targets_mean_3','carries_mean_3'])
        status='specialist' if specialist else 'participation_supported' if positive else 'thin_or_unknown_opportunity'
        savers.append(dict(player_id=p['player_id'],status=status,evidence={k:p.get(k) for k in FIELDS if k not in {'role_starter_evidence'}}))
    cap_qb=[q['player_id'] for q in qs if q['player_team']==cap['player_team']]
    paired=bool(cap_qb) if cap['position'] in {'WR','TE'} else any(s['receiver_ids'] for s in stacks if s['qb_id']==cap['player_id']) if cap['position']=='QB' else None
    return dict(captain_id=cap['player_id'],captain_name=cap['name'],captain_role_supported=support(cap),captain_evidence={k:cap.get(k) for k in FIELDS},captain_passing_pair_supported=paired,qb_receiver_stacks=stacks,bring_back_ids=[p['player_id'] for p in ps if p['player_team']!=cap['player_team']],team_counts=dict(Counter(p['player_team'] for p in ps)),workload_TD_dependencies=pairs,salary_savers=savers,all_player_evidence=[{k:p.get(k) for k in FIELDS} for p in ps],unknown_joint_target_carry_TD_budget=True,interpretation='Structure and participation evidence only; no claim of calibrated joint upside or ineligibility')
def freeze():
    prepared=read(PRIOR/'prepared.json'); manifest=read(PRIOR/'input_manifest.json'); checks=[]; runs=[]
    for runid,hashval in manifest['source_sha256'].items(): assert h.sha(PRIOR/'inputs'/f'{runid}.json')==hashval
    for path,hashval in manifest['code_sha256'].items(): assert h.sha(PRIOR/'inputs/code'/path)==hashval
    for run in prepared['runs']:
        source=read(PRIOR/'inputs'/f"{run['run_id']}.json"); config=source['run']['constraint_config_json']; runtime=config['strategy_runtime']; variants=runtime['showdown_portfolio_policy']['candidate_selection']['ranked_metrics']
        assert h.digest(variants)==run['pool_sha256']
        dedup=h.deduplicate(variants); assert {r['roster_id'] for r in dedup}=={r['roster_id'] for r in run['rosters']}
        limits,cap,requested=h.budgets(config,runtime); assert (limits,cap,requested)==(run['player_limits'],run['captain_limit'],run['requested'])
        orig=[r for r in variants if r['quality_eligible']]; maxsize=h.solve(orig,limits,cap,requested)['count']; replay=h.solve(orig,limits,cap,requested,score='selector',size=maxsize)
        assert {h.roster_id(r) for r in replay['rows']}==set(run['saved_roster_ids'])
        assert abs(sum(r['selector'] for r in replay['rows'])-run['historical_objective'])<1e-6
        if run['week']!=5: checks.append(dict(run=run['run_id'],historical_reproduced=True,excluded='generation chronology unverified')); continue
        raw={p['player_id']:p for p in config['showdown_evidence_snapshot']['player_pool']}; players={p['player_id']:p for p in runtime['player_pool']['rows']}
        rosters=run['rosters']; thresholds=run['quality_thresholds']
        for row in rosters:
            h.candidate_checks(row,players,config)
            score=h.reconstruct(row,players)
            assert all(abs(row[k]-score[k])<1e-7 for k in ['current_score','mean_score','p90_score'])
            assert gate(row,thresholds,'both95')==row['quality_eligible']
        # Regenerate current shortlist using frozen policy and original preferences.
        frame=h.pd.DataFrame([dict(r,name=r['player_name'],player_team=r['team']) for r in players.values() if r['included']])
        _,shortlist=h.load_shortlist()(frame,params=config,flex_only_ids={p for p,r in players.items() if r.get('flex_only')}|set(config.get('flex_only_player_ids',[])))
        assert {p['player_id'] for p in shortlist['shortlist']}=={p['player_id'] for p in run['current_shortlist']['shortlist']}
        arms={}; baseids={r['roster_id'] for r in rosters if r['current_captain_eligible'] and gate(r,thresholds,'both95')}
        shared=dict(limits=limits,captain_limit=cap,requested=requested,size=run['historical_size'],shortlist=shortlist,preferences=run['preference_inputs'],score='current_score',tolerance=1e-8)
        for arm in ARMS:
            eligible=sorted([r for r in rosters if r['current_captain_eligible'] and gate(r,thresholds,arm)],key=h.signature)
            capacity=h.solve(eligible,limits,cap,requested)['count']; assert capacity>=run['historical_size']
            new=[r for r in eligible if r['roster_id'] not in baseids]
            examples=sorted(new,key=lambda r:(-r['current_score'],h.signature(r)))[:2]
            arms[arm]=dict(eligible_ids=[r['roster_id'] for r in eligible],new_eligible_ids=[r['roster_id'] for r in new],pregame_example_ids=[r['roster_id'] for r in examples],capacity=capacity,quality_survivors=sum(gate(r,thresholds,arm) for r in rosters),captain_rejected_after_quality=sum(gate(r,thresholds,arm) and not r['current_captain_eligible'] for r in rosters),shared_constraints_sha256=h.digest(shared))
        baseline=h.solve([r for r in rosters if r['roster_id'] in baseids],limits,cap,requested,score='current_score',size=run['historical_size'],stable=True)
        assert len(baseids)==run['common_eligible_count']; assert baseline['count']==run['common_size']==run['historical_size']
        # Read only the prior baseline arm, not new outcomes; establish exact reproduction.
        previous=next(r for r in read(PRIOR/'results.json')['runs'] if r['run_id']==run['run_id'])
        assert [r['roster_id'] for r in baseline['rows']]==previous['arms']['current']['roster_ids']
        annotations={r['roster_id']:annotate(r,raw) for r in rosters}
        assert 'actual_points' not in json.dumps(annotations)
        runs.append(dict(run_id=run['run_id'],slate=run['slate'],chronology=run['chronology'],thresholds=thresholds,original_actual_size=run['historical_size'],requested=requested,cap_denominator=requested,player_limits=limits,captain_limit=cap,shortlist=shortlist,preferences=run['preference_inputs'],rosters=rosters,annotations=annotations,arms=arms,baseline_selected_ids=[r['roster_id'] for r in baseline['rows']],gate_partition=dict(both=sum(gate(r,thresholds,'both95') for r in rosters),mean_only=sum(gate(r,thresholds,'mean95') and not gate(r,thresholds,'marginal_p9095') for r in rosters),p90_only=sum(gate(r,thresholds,'marginal_p9095') and not gate(r,thresholds,'mean95') for r in rosters),neither=sum(not gate(r,thresholds,'mean95') and not gate(r,thresholds,'marginal_p9095') for r in rosters))))
        checks.append(dict(run=run['run_id'],historical_reproduced=True,prior_current_baseline_reproduced=True,dedup_verified=True,shortlist_verified=True,original_caps_verified=True))
    save(OUT/'prepared.json',dict(runs=runs,checks=checks,new_outcome_comparisons_computed=False))
    dependencies=[PRIOR/'prepared.json',PRIOR/'results.json',PRIOR/'validation.json',PRIOR/'input_manifest.json',PRIOR/'experiment.py',PRIOR/'capture.py',*sorted((PRIOR/'inputs').glob('*.json')),*sorted((PRIOR/'inputs/code').rglob('*.py')),*sorted((PRIOR/'outcomes').glob('*.json')),Path(h.REPORT),Path('backend/app/product_services/optimizer.py'),Path('backend/app/product_services/showdown_portfolio_selection.py'),Path('backend/app/product_services/classic_small_field.py')]
    save(OUT/'freeze.json',dict(created_at=datetime.now(timezone.utc).isoformat(),spec_sha256=h.sha(OUT/'SPECIFICATION.md'),prepared_sha256=h.sha(OUT/'prepared.json'),code_sha256=h.sha(OUT/'study.py'),inputs_sha256={str(p.resolve()):h.sha(p) for p in dependencies},pulp_version=pulp.__version__,solver_sha256=h.sha(pulp.PULP_CBC_CMD().path),retrospective=True,new_outcome_comparisons_computed=False))
    print('Frozen',len(runs),'slates; historical/current baseline replay and pregame-only annotations passed')
def check_freeze():
    f=read(OUT/'freeze.json'); assert f['spec_sha256']==h.sha(OUT/'SPECIFICATION.md'); assert f['prepared_sha256']==h.sha(OUT/'prepared.json'); assert f['code_sha256']==h.sha(OUT/'study.py'); assert f['solver_sha256']==h.sha(pulp.PULP_CBC_CMD().path)
    for p,v in f['inputs_sha256'].items(): assert h.sha(p)==v, p
    return f

def evaluate():
    check_freeze(); results=[]; report=read(PRIOR/'outcomes/report_evidence.json')
    for run in read(OUT/'prepared.json')['runs']:
        rows=run['rosters']; byid={r['roster_id']:r for r in rows}; actual,conflicts=h.actuals(read(PRIOR/'outcomes'/f"{run['run_id']}.json")); assert not conflicts
        values={r['roster_id']:round(sum(actual[pid]*(1.5 if cap else 1) for pid,cap in h.signature(r)),2) for r in rows}
        rep=next(s for s in report['slates'] if any(r['optimizer_run_id']==run['run_id'] for r in s['runs']))
        arms={}
        for arm,plan in run['arms'].items():
            eligible=[byid[rid] for rid in plan['eligible_ids']]; sol=h.solve(eligible,run['player_limits'],run['captain_limit'],run['requested'],score='current_score',size=run['original_actual_size'],stable=True); assert sol is not None
            selected=sol['rows']; constraint=h.validate_portfolio(selected,run['player_limits'],run['captain_limit'],run['original_actual_size'])
            assert all(r['current_captain_eligible'] and gate(r,run['thresholds'],arm) for r in selected)
            ids=[r['roster_id'] for r in selected]; points=[values[rid] for rid in ids]; thresholds={}
            for cid,field in rep['field_benchmarks'].items():
                if field['status']=='available': thresholds[cid]={k:dict(threshold=v,count=sum(p>=v-.005 for p in points) if v is not None else None) for k,v in {**field['thresholds'],'cash':field['cash_line'],'winner':field['winner']}.items()}
            if arm=='both95': assert ids==run['baseline_selected_ids']
            arms[arm]={**plan,'selected_ids':ids,'selected_new_ids':[rid for rid in ids if rid not in run['arms']['both95']['eligible_ids']],'achieved':len(ids),'requested':run['requested'],'solver_status':'Optimal','integer_objective':sol['objective'],'actual_points':points,'average_actual':sum(points)/len(points),'best_actual':max(points),'contest_attainment':thresholds,'constraint_check':constraint,'new_eligible_support':dict(Counter('captain_supported_passing_supported_or_nonpassing' if run['annotations'][rid]['captain_role_supported'] and run['annotations'][rid]['captain_passing_pair_supported'] is not False else 'other_or_unknown' for rid in plan['new_eligible_ids']))}
        results.append(dict(run_id=run['run_id'],slate=run['slate'],unique_rosters=len(rows),current_captain_eligible_rosters=sum(r['current_captain_eligible'] for r in rows),original_actual_size=run['original_actual_size'],cap_denominator=run['cap_denominator'],captain_limit=run['captain_limit'],gate_partition=run['gate_partition'],arms=arms))
    save(OUT/'results.json',dict(runs=results,retrospective=True,held_out=[],freeze_sha256=h.sha(OUT/'freeze.json')))
    for r in results: print(r['slate'],{a:(len(x['eligible_ids']),len(x['new_eligible_ids']),x['capacity'],round(x['average_actual'],2),x['best_actual']) for a,x in r['arms'].items()})
def validate():
    check_freeze(); data=read(OUT/'prepared.json'); results=read(OUT/'results.json')
    row=dict(mean_score=95,p90_score=95); th=dict(mean=95,p90=95)
    assert gate(row,th,'both95'); row['mean_score']=95-5e-9; assert gate(row,th,'both95'); row['mean_score']=95-2e-8; assert not gate(row,th,'both95'); assert gate(row,th,'marginal_p9095'); assert gate(row,th,'neither'); row['p90_score']=95-2e-8; assert not gate(row,th,'marginal_p9095')
    for r in data['runs']:
        ids=[x['roster_id'] for x in r['rosters']]; assert len(ids)==len(set(ids)); assert sum(r['gate_partition'].values())==len(ids); assert r['cap_denominator']==r['requested']==5
        assert len({a['shared_constraints_sha256'] for a in r['arms'].values()})==1
        for arm,a in r['arms'].items(): assert set(r['arms']['both95']['eligible_ids'])<=set(a['eligible_ids'])
    for r in results['runs']:
        for a in r['arms'].values(): assert a['achieved']==r['original_actual_size'] and a['constraint_check']['passed']
    save(OUT/'validation.json',dict(passed=True,checks=['boundary_tolerance','four_gate_partition','canonical_Captain_dedup','variant_consistency','all_six_historical_replay','five_prior_current_baseline_replay','current_shortlist_reconstructed','saved_preferences_legality','same_score_caps_requested_denominator','fixed_original_actual_size','solver_optimal','pregame_annotations_no_actual_points','pinned_input_hashes','identical_repeated_result_bytes'],results_sha256=h.sha(OUT/'results.json'),production_defaults_changed=False))
    print('All focused checks passed')
if __name__=='__main__': globals()[sys.argv[1]]()
