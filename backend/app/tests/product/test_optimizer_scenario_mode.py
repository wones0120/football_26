from copy import deepcopy
from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.product_services.optimizer_scenario_mode import ScenarioMode,config,prepare,verify,solve
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.optimizer import OptimizerJob
from backend.app.product_services.slate_preparation import SlatePreparationRequest
from backend.app.product_schemas import OptimizerRunRequest
from backend.app.tests.product.test_count_component_response import fixture,IDS,NOW
from backend.app.tests.product.test_classic_highest_projection import pool_fixture,service
from backend.app.tests.product.test_slate_preparation import fixture as slate_fixture,enqueue,prepared_refresh,optimizer_payload

CONFIG=dict(team='BUF',passing_factor=1.2,rushing_factor=1,rationale='Authored faster passing game')


def count_inputs():
    weekly,reference,means=fixture()
    rows=[dict(player_id=p['player_master_id'],name=p['player_master_id'],player_team=p['team'],projection=means[p['player_master_id']],position=p['position']) for p in reference['players']]
    return weekly,reference,rows


def test_off_is_exact_noop_and_default_scope_unchanged():
    assert config(None) is None
    assert prepare(None,None,[],before_period=202604,cutoff=NOW,projection_run_id='p') is None
    request=SlatePreparationRequest(season=2026,week=4,slate='MAIN',action='prepare')
    assert request.scenario_mode is None and request.include_workload_forecast is False


@pytest.mark.parametrize('changed',[{'passing_factor':True},{'passing_factor':1.6},{'passing_factor':float('nan')},
    {'passing_factor':1},{'rationale':' '},{'team':'not-a-team'},{'extra':1}])
def test_typed_bounded_assumptions_rejected(changed):
    with pytest.raises(ValueError):ScenarioMode.model_validate(dict(CONFIG,**changed))


def test_prepare_reuses_count_components_shared_budgets_and_preserves_parent():
    weekly,reference,rows=count_inputs();before=deepcopy(reference)
    out=prepare(CONFIG,reference,rows,before_period=202604,cutoff=NOW,projection_run_id='p',weekly=weekly)
    assert reference==before and out['changed_player_count']>0 and out['status']=='CONDITIONAL_PARTIAL_COMPONENTS'
    verify(out,CONFIG,'p')
    assert out['players'][0]['baseline_mean']==10 and out['players'][0]['conditional_mean']>10
    assert out['count_budgets']['BUF']['pass_attempts']==12
    assert out['count_budgets']['BUF']['targets']==pytest.approx(9.6)
    for component in ('receiving_yards','receptions'):
        r=out['shared_budgets']['BUF']['reconciliation'][component]
        assert r['allocated']<=r['budget']+1e-9
    assert not out['baseline_projections_mutated']
    assert out['new_model_primary'] is False and out['full_game_simulator_consumed'] is False
    assert out['scoring_basis']=='incumbent_anchored_component_sensitivity'


def test_missing_history_keeps_baseline_with_visible_gaps_and_zero_changes():
    _,_,rows=count_inputs()
    out=prepare(CONFIG,None,rows,before_period=202604,cutoff=NOW,projection_run_id='p')
    assert out['status']=='UNAVAILABLE_BASELINE_RETAINED' and out['changed_player_count']==0
    assert all(p['baseline_mean']==p['conditional_mean'] and p['missing_evidence'] for p in out['players'])


def test_missing_individual_components_are_not_imputed_or_renormalized():
    weekly,reference,rows=count_inputs();weekly.loc[weekly.player_master_id.eq(IDS[2]),'receiving_yards']=None
    out=prepare(CONFIG,reference,rows,before_period=202604,cutoff=NOW,projection_run_id='p',weekly=weekly)
    p=next(p for p in out['players'] if p['player_master_id']==IDS[2])
    assert 'Unmatched component held at baseline: receiving_yards' in p['missing_evidence']


def test_config_checksum_projection_and_team_change_cannot_reuse_prepare():
    _,_,rows=count_inputs();out=prepare(CONFIG,None,rows,before_period=202604,cutoff=NOW,projection_run_id='p')
    with pytest.raises(ValueError):verify(out,dict(CONFIG,passing_factor=.8),'p')
    with pytest.raises(ValueError):verify(out,CONFIG,'other')
    out['players'][0]['conditional_mean']=100
    with pytest.raises(ValueError,match='checksum'):verify(out,CONFIG,'p')
    with pytest.raises(ValueError,match='outside'):prepare(dict(CONFIG,team='KC'),None,rows,before_period=202604,cutoff=NOW,projection_run_id='p')


def solver_inputs():
    pool=pool_fixture();players=[dict(player_master_id=r['player_id'],baseline_mean=r['projection'],
        conditional_mean=100 if r['player_id']=='w5' else r['projection'],delta=99 if r['player_id']=='w5' else 0,missing_evidence=[]) for r in pool.to_dict('records')]
    report=dict(config=CONFIG,projection_run_id='p',players=players,limitations=['Synthetic solver test'],changed_player_count=1)
    report['sha256']=digest(report)
    params=dict(scenario_mode=CONFIG,enforce_single_te=True,max_players_per_team=4,max_players_per_game=5,
        prepared_input_evidence=dict(scenario_mode=report,projection_run_id='p'))
    return pool,params


def test_two_real_solves_compare_same_pool_and_retain_baseline_projections():
    pool,params=solver_inputs();original=deepcopy(pool.to_dict('records'))
    lines,audit,comparison=solve(service(),pool,params=params,cutoff=NOW)
    assert audit['solver_status']==comparison['baseline_solver_status']=='Optimal'
    assert audit['objective_id']=='conditional_mean'
    assert 'w5' in {r['player_id'] for r in lines[0]}
    assert 'w5' not in {r['player_id'] for r in comparison['baseline_lineup']}
    assert next(r['projection'] for r in lines[0] if r['player_id']=='w5')==1
    assert comparison['baseline_mean']==144 and pool.to_dict('records')==original
    assert lines[0][0]['scenario_mode_report']['prepared']==params['prepared_input_evidence']['scenario_mode']


def test_solver_rejects_changed_baseline_instead_of_applying_old_delta():
    pool,params=solver_inputs();pool.loc[pool.player_id=='w1','projection']=99
    with pytest.raises(ValueError,match='baseline pool changed'):solve(service(),pool,params=params,cutoff=NOW)


def test_prepare_and_run_schemas_bound_scope_and_cannot_skip_prepare():
    request=SlatePreparationRequest(season=2026,week=4,slate='MAIN',action='prepare',scenario_mode=CONFIG)
    assert request.include_workload_forecast and request.scenario_mode==CONFIG
    for extra in ({'preliminary_research':True},{'action':'rebuild'}):
        with pytest.raises(ValueError):SlatePreparationRequest.model_validate(dict(dict(season=2026,week=4,slate='MAIN',action='prepare',scenario_mode=CONFIG),**extra))
    with pytest.raises(ValueError):OptimizerRunRequest(season=2026,week=4,slate='MAIN',contest_format='classic',objective='gpp',strategy='classic_large_gpp_v1',params={'scenario_mode':CONFIG})
    with pytest.raises(ValueError,match='different scoring comparison'):
        OptimizerRunRequest(season=2026,week=4,slate='MAIN',contest_format='classic',objective='gpp',strategy='classic_large_gpp_v1',params={'scenario_mode':CONFIG,'classic_selection_objective':'baseline_mean','prepared_input_job_id':'fixture','workload_comparison':'normalized_counts'})


def test_showdown_prepare_and_run_accept_same_frozen_contract():
    request=SlatePreparationRequest(season=2026,week=7,slate='THURSDAY_NIGHT',action='prepare',contest_format='showdown',scenario_mode=CONFIG)
    assert request.include_workload_forecast
    run=OptimizerRunRequest(season=2026,week=7,slate='THURSDAY_NIGHT',contest_format='showdown',objective='gpp',strategy='showdown_gpp_portfolio_v3',params={'scenario_mode':CONFIG,'prepared_input_job_id':'fixture','num_lineups':5})
    assert run.params['num_lineups']==1


def test_new_primary_allows_unmodified_model_volume_and_preserves_explicit_mode():
    selected=config(dict(CONFIG,passing_factor=1,scoring_mode='new_model_primary'))
    assert selected['scoring_mode']=='new_model_primary'
    assert selected['passing_factor']==selected['rushing_factor']==1


def test_primary_solver_uses_new_scores_and_does_not_borrow_the_old_p90_shortlist():
    from backend.app.tests.product.test_showdown_qb_preferences import pool as showdown_pool
    pool=showdown_pool();pool['showdown_captain_shortlisted']=pool.player_id.isin(['p0','p1','p2','p3'])
    pool['showdown_captain_p90']=pool.p90;pool['showdown_flex_mean']=pool.projection
    players=[dict(player_master_id=r['player_id'],baseline_mean=r['projection'],conditional_mean=None if r['player_id']=='p2' else 80. if r['player_id']=='p8' else r['projection']) for r in pool.to_dict('records')]
    selected=dict(CONFIG,scoring_mode='new_model_primary')
    report=dict(config=selected,projection_run_id='p',players=players,new_model_primary=True);report['sha256']=digest(report)
    params=dict(scenario_mode=selected,prepared_input_evidence=dict(scenario_mode=report,projection_run_id='p'))
    lines,audit,comparison=solve(service(),pool,params=params,cutoff=NOW,contest_format='showdown',stack_params={})
    assert next(p for p in lines[0] if p['roster_position']=='CPT')['player_id']=='p8'
    assert next(p for p in comparison['baseline_lineup'] if p['roster_position']=='CPT')['player_id']=='p0'
    assert comparison['model_coverage_exclusions'][0]['player_id']=='p2'
    assert not comparison['matched_pool']
    assert comparison['comparison_type']=='new_forecast_and_generation_policy_vs_incumbent'
    assert audit['conditional_mean']==sum(p['objective_score'] for p in lines[0])


def test_showdown_matched_comparison_preserves_roles_means_and_user_rules():
    import pandas as pd
    from backend.app.tests.product.test_showdown_qb_preferences import pool as showdown_pool
    pool=showdown_pool();original=pool.copy(deep=True)
    players=[dict(player_master_id=r['player_id'],baseline_mean=r['projection'],conditional_mean=r['projection']+(10 if r['player_id']=='p3' else 0)) for r in pool.to_dict('records')]
    report=dict(config=CONFIG,projection_run_id='p',players=players)
    report['sha256']=digest(report)
    params=dict(scenario_mode=CONFIG,prepared_input_evidence=dict(scenario_mode=report,projection_run_id='p'),maximum_exposure_by_player={'p2':0})
    lines,audit,comparison=solve(service(),pool,params=params,cutoff=NOW,contest_format='showdown',stack_params={'captain_positions':['WR','RB'],'no_two_qbs':True,'max_players_per_team':4})
    assert audit['solver_status']==comparison['baseline_solver_status']=='Optimal'
    for lineup in [lines[0],comparison['baseline_lineup']]:
        assert len(lineup)==6 and len({p['player_id'] for p in lineup})==6
        assert sum(p['roster_position']=='CPT' for p in lineup)==1
        assert 'p2' not in {p['player_id'] for p in lineup}
        assert sum(p['position']=='QB' for p in lineup)<=1
        for p in lineup:
            assert p['projection']==float(pool.loc[pool.player_id.eq(p['player_id']),'projection'].iloc[0])*(1.5 if p['roster_position']=='CPT' else 1)
    assert next(p for p in lines[0] if p['roster_position']=='CPT')['player_id']=='p3'
    assert audit['conditional_mean']==sum(p['objective_score'] for p in lines[0])
    assert audit['conditional_mean']==sum(p['scenario_mean'] for p in lines[0])
    captain=next(p for p in lines[0] if p['roster_position']=='CPT')
    assert captain['scenario_mean']==captain['base_scenario_mean']*1.5
    pd.testing.assert_frame_equal(pool,original)


@pytest.mark.parametrize('primary',[False,True])
def test_normal_showdown_pipeline_saves_matched_comparison(primary):
    from sqlalchemy import create_engine
    from backend.app.tests.product.test_showdown_qb_preferences import service as showdown_service
    svc=showdown_service();svc.engine=create_engine('sqlite://')
    rows=svc._load_player_pool.return_value.to_dict('records')
    selected=dict(CONFIG,team='SF',**({'scoring_mode':'new_model_primary'} if primary else {}))
    report=prepare(selected,None,rows,before_period=202604,cutoff=NOW,projection_run_id='projection-test')
    if primary:
        report['new_model_primary']=True
        report['sha256']=digest({k:v for k,v in report.items() if k!='sha256'})
    evidence=dict(scenario_mode=report,projection_run_id='projection-test')
    with patch('backend.app.product_services.showdown_data_readiness.is_live_slate',return_value=False), \
         patch('backend.app.product_services.analyst_preparation.bind_saved_preparation'), \
         patch('backend.app.product_services.slate_preparation.validate_prepared_optimizer',return_value=evidence):
        job=svc.run_job(2026,4,'THURSDAY_NIGHT','showdown_gpp_portfolio_v3',
            dict(scenario_mode=selected,prepared_input_job_id='fixture-prep',no_two_qbs=True,captain_positions=['WR','RB'],num_lineups=1),
            contest_format='showdown',objective='gpp',projection_run_id='projection-test',data_cutoff_at=NOW)
    assert job.status=='completed',job.message
    assert len(job.results)==1 and len(job.results[0])==6
    assert job.params['objective_config']['objective_id']==('new_model_primary' if primary else 'conditional_mean')
    if primary:
        assert job.params['objective_config']['incumbent_p90_shortlist_consumed_for_primary'] is False
        assert job.params['objective_config']['objective_weights']=={'new_model_captain_score':1.5,'new_model_flex_score':1.0}
        assert job.params['strategy_runtime']['scenario_incumbent_captain_shortlist']
    assert job.params['strategy_runtime']['scenario_mode']['prepared']['sha256']==report['sha256']
    assert job.params['strategy_runtime']['scenario_mode']['baseline_lineup']
    audit=job.params['strategy_runtime']['highest_projection']
    assert audit['input_snapshot_sha256']==digest(audit['input_snapshot'])
    assert audit['conditional_mean']==sum(p['scenario_mean'] for p in job.results[0])
    assert job.params.get('gpp_recommendation') is None


def test_reopen_saved_api_returns_assumptions_comparison_and_missing_evidence():
    from backend.app.main import app
    from backend.app.api.product_routes import get_optimizer_service
    pool,params=solver_inputs();lines,audit,comparison=solve(service(),pool,params=params,cutoff=NOW)
    now=datetime.now(timezone.utc)
    job=OptimizerJob(job_id='scenario-saved',status='completed',created_at=now,updated_at=now,season=2026,week=4,slate='MAIN',strategy='classic_large_gpp_v1',contest_format='classic',objective='gpp',projection_run_id='p',results=lines,params=dict(strategy_runtime={'scenario_mode':comparison,'highest_projection':audit}),lineage_persisted=True)
    app.dependency_overrides[get_optimizer_service]=lambda:SimpleNamespace(get_job=lambda job_id:job)
    try:
        with patch('backend.app.product_services.classic_game_environment.review_job',return_value=None):
            response=TestClient(app).get('/api/optimizer/results/scenario-saved')
        assert response.status_code==200,response.text
        out=response.json();assert out['scenario_mode']['prepared']['config']==CONFIG
        assert out['scenario_mode']['baseline_lineup'] and out['highest_projection']['objective_id']=='conditional_mean'
        assert out['results'][0][0]['scenario_mode_report']['prepared']['limitations']
    finally:app.dependency_overrides.pop(get_optimizer_service,None)


def test_public_prepare_worker_pins_config_and_rejects_changed_optimizer_request(slate_fixture):
    import pandas as pd
    from backend.app.product_services.slate_preparation import validate_prepared_optimizer
    f=slate_fixture
    enqueue(f);initial=f.work()['result']
    _,_,rows=count_inputs()
    with patch('backend.app.product_services.classic_data_readiness.refresh_live_sources',return_value=prepared_refresh(initial)), \
         patch('backend.app.product_services.slate_preparation.assess_prepared_inputs',return_value={'status':'READY','reason_codes':[]}), \
         patch('backend.app.product_services.optimizer.OptimizerService._load_player_pool',return_value=pd.DataFrame(rows)), \
         patch('backend.app.product_services.workload_count_forecast.prepare_receipt',side_effect=ValueError('Synthetic missing prior reference')):
        response=f.client.post('/api/slate/preparation/jobs',headers={'Idempotency-Key':'scenario-prepare'},json=dict(season=2000,week=1,slate='SUNDAY_MAIN',action='prepare',analyst_mode='BASELINE',scenario_mode=CONFIG))
        assert response.status_code==202,response.text
        finished=f.work();assert finished['status']=='completed',finished
        result=finished['result'];assert result['scenario_mode']['config']==CONFIG
        assert result['scenario_mode']['status']=='UNAVAILABLE_BASELINE_RETAINED'
        assert any('Synthetic missing prior reference' in reason for reason in result['scenario_mode']['limitations'])
        status=f.client.get('/api/slate/preparation?season=2000&week=1&slate=SUNDAY_MAIN').json()
        result=status['latest_build']
        payload={**optimizer_payload(result),'contest_format':'classic'}
        payload['params']['scenario_mode']=CONFIG
        with f.factory() as db:
            evidence=validate_prepared_optimizer(db,payload)
            assert evidence['scenario_mode']['sha256']==result['scenario_mode']['sha256']
            payload['params']['scenario_mode']=dict(CONFIG,passing_factor=1.3)
            with pytest.raises(ValueError,match='Scenario changed'):validate_prepared_optimizer(db,payload)
        status=f.client.get('/api/slate/preparation?season=2000&week=1&slate=SUNDAY_MAIN').json()
        assert status['build_current'] and status['latest_build']['scenario_mode']['sha256']==result['scenario_mode']['sha256']


def test_normal_optimizer_pipeline_saves_scenario_runtime_without_mutating_baseline():
    import pandas as pd
    from sqlalchemy import create_engine
    from backend.app.product_services.optimizer import OptimizerService
    from backend.app.tests.product.test_preliminary_optimizer import snapshot_fixture
    source,_=snapshot_fixture();rows=deepcopy(source['pool'])
    for row in rows:
        if row['player_team']=='AAA':row['player_team']='BUF';row['team']='BUF'
    receipt=prepare(CONFIG,None,rows,before_period=209901,cutoff=source['data_cutoff_at'],projection_run_id=source['projection_run_id'])
    evidence=dict(scenario_mode=receipt,projection_run_id=source['projection_run_id'])
    svc=OptimizerService();svc.engine=create_engine('sqlite://');saved=[]
    frame=pd.DataFrame(rows);frame.attrs=deepcopy(source['pool_attrs'])
    with patch.object(svc,'_load_player_pool',side_effect=lambda *a,**kw:frame.copy(deep=True)), \
         patch.object(svc,'_persist_optimizer_run',side_effect=lambda job:saved.append(deepcopy(job)) or True), \
         patch('backend.app.product_services.analyst_preparation.bind_saved_preparation'), \
         patch('backend.app.product_services.slate_preparation.validate_prepared_optimizer',return_value=evidence):
        job=svc.run_job(2099,1,'SYNTHETIC_CLASSIC','classic_large_gpp_v1',
            dict(scenario_mode=CONFIG,classic_selection_objective='baseline_mean',prepared_input_job_id='fixture-prep',
                 exclude_questionable=True,enforce_single_te=True,max_players_per_team=4,num_lineups=1),
            contest_format='classic',objective='gpp',projection_run_id=source['projection_run_id'],
            data_cutoff_at=datetime.fromisoformat(source['data_cutoff_at']),allow_incomplete_evidence=True)
    assert job.status=='completed',job.message
    assert job.params['strategy_runtime']['scenario_mode']['prepared']['sha256']==receipt['sha256']
    assert job.params['objective_config']['objective_id']=='conditional_mean'
    assert job.params.get('gpp_recommendation') is None
    baseline={r['player_id']:r['projection'] for r in rows}
    assert all(p['projection']==baseline[p['player_id']] for p in job.results[0])
    assert saved[-1].params['strategy_runtime']['scenario_mode']['baseline_lineup']


def test_solver_snapshot_hash_survives_jsonb_negative_zero_normalization():
    from backend.app.product_services.optimizer_scenario_mode import stable_solver_snapshot
    old={'model':{'constraints':[{'pi':-0.0,'constant':0}]},'players':[{'projection':1.5}]}
    frozen=stable_solver_snapshot(old)
    jsonb={'model':{'constraints':[{'pi':0.0,'constant':0}]},'players':[{'projection':1.5}]}
    assert digest(frozen)==digest(jsonb)
    import math
    assert math.copysign(1.,old['model']['constraints'][0]['pi'])==-1
