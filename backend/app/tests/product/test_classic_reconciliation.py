"""Decision-path invariants; production defaults are intentionally unchanged."""
from dataclasses import replace
from pathlib import Path
import json

import pulp
import pytest

from backend.app.product_services.classic_prospective import digest_payload
from backend.app.product_services.classic_thesis_shadow import canonical_game
from scripts.reconcile_classic_discovery_selection import (
    Policy, eligibility, evidence_value, resolve_effective_policy, solve,
    stage_attribution, violations,
)


ROOT=Path(__file__).resolve().parents[4]
FROZEN=ROOT/'artifacts/classic_reconciliation/20261002T022305Z'


def row(label,score=1,game='A|B'):
    return {'player_ids':[label+str(i) for i in range(9)],'objective_score':score,
            'qb':{'player_id':label},'stack':{'type':'QB+1'},'game_key':game,
            'roster_sha256':label,'mean':score,'p90':score,'rank':1}


def test_canonical_game_directions_are_one_outcome():
    assert canonical_game('JAX@CIN 10/04/2026 01:00PM ET','JAX','CIN')['key']=='CIN|JAX'
    assert canonical_game('CIN–JAX','CIN','JAX')['key']=='CIN|JAX'


def test_unavailable_sentinel_and_measured_zero_are_distinct():
    assert evidence_value({'team_targets_mean_3':0,'team_targets_mean_3_available':False},'team_targets_mean_3') is None
    assert evidence_value({'targets_mean_3':0,'targets_mean_3_available':True},'targets_mean_3')==0
    assert evidence_value({},'targets_mean_3') is None


def test_fixed_superset_preserves_incumbent_and_improves_optimum():
    policy=Policy('test',count=2,minimum_qbs=2,minimum_stack_types=1)
    original=[row('a',2),row('b',1)];expanded=original+[row('c',3)]
    a=solve(original,policy,{},set());b=solve(expanded,policy,{},set(),incumbent=a['lineups'])
    assert a['status']==b['status']=='optimal'
    assert sum(r['objective_score'] for r in b['lineups'])==5
    assert not violations(a['lineups'],policy,{},set())


def test_rejects_incumbent_removed_by_tightened_eligibility():
    policy=Policy('test',count=2,minimum_qbs=2,minimum_stack_types=1,tolerance=.1,frontier=2)
    with pytest.raises(ValueError,match='Incumbent'):
        solve([row('a',2),row('b',1)],policy,{},set(),incumbent=[row('a',2),row('b',1)])


def test_does_not_call_time_limited_integer_incumbent_optimal(monkeypatch):
    def incumbent(model,solver):
        for v in model.variables():v.varValue=1
        model.sol_status=pulp.LpSolutionIntegerFeasible
        return pulp.LpStatusOptimal
    monkeypatch.setattr(pulp.LpProblem,'solve',incumbent)
    result=solve([row('a')],Policy('test',count=1,minimum_qbs=1,minimum_stack_types=1),{},set())
    assert result['status']=='unproven'
    assert result['stages'][0]['proven_optimal'] is False


def test_discovery_admission_quality_selection_are_distinct():
    r=[row(str(i),10-i) for i in range(5)]
    policy=Policy('test',count=1,minimum_qbs=1,minimum_stack_types=1,tolerance=2,frontier=10)
    result=stage_attribution(r,r[:4],r[:3]+[r[3]],[r[0]],policy,set())
    assert result['counts']=={'selected':1,'eligible_not_selected':2,'admitted_rejected_by_lineup_quality':1,'never_discovered':1}
    result=stage_attribution(r,r[:4],r[:3],[r[0]],policy,set())
    assert result['counts']['discovered_not_admitted']==1


@pytest.fixture
def frozen():
    return json.loads((FROZEN/'comparison.json').read_text())


def test_requested_settings_current_default_and_override_are_visible():
    inputs=json.loads((FROZEN/'control_inputs.json').read_text())
    assert inputs['params']['portfolio_constraints']=={}
    policy=resolve_effective_policy(inputs)
    assert (policy.count,policy.overlap,policy.distinct_qb,policy.minimum_qbs,policy.minimum_stack_types)==(5,6,False,3,2)
    # Audits the confirmed current plumbing issue; does not promote a fix/default.
    inputs['report']['frozen_solver_snapshot']['payload']['options']['portfolio_constraints']={'max_lineup_overlap':4,'distinct_qb_paths':True}
    assert resolve_effective_policy(inputs).overlap==6
    assert resolve_effective_policy(inputs).distinct_qb is True


def test_real_control_incumbent_and_proven_superset(frozen):
    r=frozen['results'];assert r['original_fixed']['status']==r['union_fixed']['status']=='optimal'
    assert r['union_fixed']['selector_sum']>=r['original_fixed']['selector_sum']-1e-8
    assert set(frozen['saved_control']['roster_hashes'])<=set(r['original_fixed']['roster_hashes'])
    assert set(frozen['saved_control']['roster_hashes'])<={row['roster_sha256'] for row in frozen['union']}
    for row in frozen['original']:
        same=next(r for r in frozen['union'] if r['roster_sha256']==row['roster_sha256'])
        assert same['objective_score']==row['objective_score']


def test_real_dynamic_tolerance_changes_feasible_set(frozen):
    assert frozen['results']['thesis_original_tolerance_0.2']['selector_sum']==pytest.approx(27.687854307504555)
    assert frozen['results']['thesis_original_expanded015']['selector_sum']==pytest.approx(27.64397737627836)
    assert frozen['results']['density_only_same_game015']['status']=='optimal'
    assert frozen['dynamic_exclusions']['qb_counts']['Jacoby Brissett']==23
    assert frozen['results'][frozen['dynamic_chosen']]['canonical_primary_games']=={'CIN|JAX':5}


def test_historical_freezes_remain_content_identical(frozen):
    for path,expected in frozen['files'].items():
        assert __import__('hashlib').sha256((ROOT/path).read_bytes()).hexdigest()==expected
    assert frozen['sha256']==digest_payload({k:v for k,v in frozen.items() if k!='sha256'})


def test_actual_production_call_overrides_overlap_but_forwards_distinct_qb(monkeypatch):
    from types import SimpleNamespace
    from backend.app.product_services import classic_small_field as service
    from backend.app.product_services.classic_candidate_completeness import load_context

    inputs=json.loads((FROZEN/'control_inputs.json').read_text())
    ctx=load_context(inputs);report=inputs['report'];by_id={p.player_id:p for p in ctx['players']}
    lineups=[[by_id[pid] for pid in r['player_ids']] for r in report['all_candidates']
             if r['rank'] in report['selected_ranks']]
    pool=[{**row,'gpp_player':by_id[row['player_id']]} for row in ctx['source'].values()]
    controls={**report['production_controls'],'classifications':ctx['risk']}
    monkeypatch.setattr(service,'_admit_candidate_caps',lambda candidates,lineups,*args:
                        (candidates,lineups,{}))
    captured={}
    class SelectionReached(Exception):
        pass
    def capture(*args,**kwargs):
        captured.update(kwargs)
        raise SelectionReached
    monkeypatch.setattr(service,'_select_global',capture)
    with pytest.raises(SelectionReached):
        service.analyze_small_field(SimpleNamespace(lineups=lineups,config=ctx['config']),
            pool_rows=pool,count=5,max_exposure=1,ownership_available=True,
            requested_candidate_count=5,production_controls=controls,
            portfolio_constraints={'max_lineup_overlap':4,'distinct_qb_paths':True})
    assert captured['max_lineup_overlap']==6
    assert captured['distinct_qb_paths'] is True
    assert captured['minimum_qb_paths']==2


def test_saved_preview_api_readback_identifies_exact_frame_universe_and_rosters():
    from scripts.run_classic_reconciliation_preview import saved_report
    base=FROZEN.parent/'20261002T023356Z_sunday_preview'
    request=json.loads((base/'application_request.json').read_text())
    response=json.loads((base/'preview.json').read_text())
    readback=json.loads((base/'application_readback.json').read_text())
    verified=json.loads((base/'execution_verification.json').read_text())
    replay=json.loads((base/'offline_replay_verification.json').read_text())
    a,b=saved_report(response),saved_report(readback)
    assert request['optimizer_run_id']==response['job_id']==readback['job_id']==verified['run_id']
    assert request['projection_run_id']==response['projection_run_id']==readback['projection_run_id']
    assert a['frozen_solver_snapshot']==b['frozen_solver_snapshot']
    assert a['all_candidates']==b['all_candidates']
    assert a['selected_ranks']==b['selected_ranks']==verified['selected_ranks']
    assert verified['proven_optimal'] and verified['same_objective'] and verified['exact_rosters_reselected']
    for key in ['input_sha256','candidate_sha256','saved_roster_hashes','policy','selector_sum']:
        assert replay[key]==verified[key]
    assert verified['policy']['overlap']==6 and verified['policy']['minimum_qbs']==3


def test_fresh_usage_excludes_week4_and_lar_missing_features_are_repaired():
    import pandas as pd
    base=FROZEN.parent/'20261002T023356Z_sunday_preview'
    manifest=json.loads((base/'capture_manifest.json').read_text())
    for key in ['nflreadpy_weekly_stats','nflreadpy_snap_counts']:
        frame=pd.read_csv(manifest['pipeline_lineage'][key]['path'])
        assert frame['week'].between(1,3).all()
    features=json.loads((base/'projection_features.json').read_text())
    kyren=next(r['feature_json'] for r in features if r['player_id']=='319a7e5c-7967-4405-90f9-36ddfea66dfd')
    assert kyren['team_targets_mean_3_available'] is True
    assert evidence_value(kyren,'team_targets_mean_3')==pytest.approx(35.333333333333336)
    assert kyren['pregame_expected_targets'] is None
    assert kyren['official_availability_status'] is None
