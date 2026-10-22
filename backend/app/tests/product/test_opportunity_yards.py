from copy import deepcopy
from datetime import timedelta
import json

import pandas as pd
import pytest

from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.opportunity_yards import add_yards, Efficiency, history_frame, WEIGHTS
from backend.app.product_services.slate_preparation import SlatePreparationRequest
from backend.app.product_services.workload_optimizer import solve
from backend.app.product_services.optimizer import OptimizerService
from backend.app.tests.product.test_workload_new_count_consumer import fixture, prepared, NOW, signature


def yard_receipt(monkeypatch):
    pool,receipt=prepared(monkeypatch)
    receipt.update(learned_opportunities=True,learned_model_consumption=dict(team={},player={},points_heads_consumed=False))
    receipt['sha256']=digest({k:v for k,v in receipt.items() if k!='sha256'})
    weekly,_=fixture()
    return pool,receipt,add_yards(receipt,weekly,before_period=202606,cutoff=NOW)


def test_shared_yards_and_residuals_do_not_change_original_counts(monkeypatch):
    _,original,yards=yard_receipt(monkeypatch)
    assert 'yardage_model' not in original
    assert [p['counts'] for p in original['players']]==[p['counts'] for p in yards['players']]
    assert yards['sha256']!=original['sha256']
    for team,a in yards['yardage_model']['accounting'].items():
        assert a['passing_yards']==pytest.approx(a['receiving_yards']+a['unallocated_receiving_yards'])
        assert a['passing_yards']==pytest.approx(a['known_qb_passing_yards']+a['unallocated_passing_yards'])
    for actor in yards['players']:
        keys=('passing_yards','rushing_yards') if actor['position']=='QB' else ('rushing_yards','receiving_yards')
        if any(actor['projected_yards'][k] is None for k in keys):
            assert actor['utility'] is None
            continue
        assert actor['utility']==pytest.approx(sum(WEIGHTS[k]*actor['projected_yards'][k] for k in keys))
        if actor['position']!='QB':
            assert actor['efficiency']['receiving_yards']['value']==8. # includes incompletions already
    json.dumps(yards,allow_nan=False)


def test_role_labels_and_efficiency_only_use_earlier_games():
    weekly,_=fixture()
    frame=history_frame(weekly,before_period=202606,cutoff=NOW)
    actor=frame.iloc[0].to_dict()
    before=Efficiency(frame,202604).estimate(actor,'passing_yards')
    changed=frame.copy();changed.loc[changed.period.ge(202604),'passing_yards']=999999
    assert Efficiency(changed,202604).estimate(actor,'passing_yards')==before
    assert set(frame.loc[frame.period.eq(202601),'prior_role'])=={'unknown'}
    weekly.loc[0,'imported_at']=(NOW+timedelta(days=1)).isoformat()
    with pytest.raises(ValueError,match='import clocks'):history_frame(weekly,before_period=202606,cutoff=NOW)


def test_signed_yards_missing_counts_and_sparse_role_are_explicit(monkeypatch):
    _,original,_=yard_receipt(monkeypatch)
    weekly,_=fixture()
    rb=next(a for a in original['players'] if a['position']=='RB')
    weekly.loc[weekly.player_master_id.eq(rb['player_master_id']),'rushing_yards']=-17
    changed=add_yards(original,weekly,before_period=202606,cutoff=NOW)
    actor=next(a for a in changed['players'] if a['player_master_id']==rb['player_master_id'])
    assert actor['efficiency']['rushing_yards']['player_yards']<0
    original['players'][0]['counts']['pass_attempts']=None
    missing=add_yards(original,weekly,before_period=202606,cutoff=NOW)
    assert missing['players'][0]['utility'] is None
    assert missing['players'][0]['projected_yards']['passing_yards'] is None
    # No same-team observations: explicit position population estimate, not fake history.
    model=Efficiency(history_frame(weekly,before_period=202606,cutoff=NOW),202606)
    cold=model.estimate(dict(player_master_id='new',position='QB',team='SF'),'passing_yards')
    assert cold['player_rows']==0 and cold['role']=='unknown'
    assert cold['reference']=='position_only_sparse_role'


def test_native_solver_uses_declared_yards_and_rejects_wrong_receipt(monkeypatch):
    pool,original,receipt=yard_receipt(monkeypatch)
    params=dict(workload_comparison='learned_yards',num_lineups=1,max_exposure=1,captain_max_exposure=1,
        prepared_input_evidence=dict(workload_forecast=receipt))
    def issue(rows):
        return solve(OptimizerService.__new__(OptimizerService),pd.DataFrame(rows),params=params,contest_type='captain',
            stack_params=dict(captain_positions=['RB','WR','TE'],max_players_per_team=4),locked_ids=set(),
            flex_only_ids=set(),avoid_dst_opponents=True,enforce_single_te=False,requested_captain_id=None)
    lineups,report=issue(pool)
    changed=deepcopy(pool)
    for row in changed:row.update(projection=-999999.,p90=float('nan'))
    alternative,_=issue(changed)
    assert signature(lineups)==signature(alternative)
    assert report['yardage_model']['selection_weights']==WEIGHTS
    assert report['points_selection_gates_consumed'] is False
    assert report['solver_audits'][0]['solver_status']=='Optimal'
    assert report['solver_audits'][0]['objective']==pytest.approx(sum(p['workload_forecast']['utility']*(1.5 if p['roster_position']=='CPT' else 1) for p in lineups[0]))
    params['prepared_input_evidence']['workload_forecast']=original
    with pytest.raises(ValueError,match='count/yard objective'):issue(pool)
    params['prepared_input_evidence']['workload_forecast']=receipt;params['workload_comparison']='learned_counts'
    with pytest.raises(ValueError,match='count/yard objective'):issue(pool)
    params['workload_comparison']='normalized_counts'
    with pytest.raises(ValueError,match='count/yard objective'):issue(pool)


def test_prepare_request_is_opt_in_showdown_only():
    request=SlatePreparationRequest(season=2026,week=7,slate='THURSDAY_NIGHT',action='prepare',contest_format='showdown',opportunity_yards=True)
    assert request.learned_opportunities and request.include_workload_forecast
    assert not SlatePreparationRequest(season=2026,week=7,slate='THURSDAY_NIGHT',action='prepare').opportunity_yards
    with pytest.raises(ValueError,match='Showdown Prepare'):
        SlatePreparationRequest(season=2026,week=7,slate='MAIN',action='prepare',opportunity_yards=True)


def test_handoff_and_captain_qualification_bind_the_selected_objective(monkeypatch):
    from backend.app.product_services.analyst_preparation import bind_handoff
    from backend.app.product_services.showdown_captain_shortlist import build_captain_shortlist
    pool,counts,receipt=yard_receipt(monkeypatch)
    payload=dict(params=dict(workload_comparison='learned_yards'))
    with pytest.raises(ValueError,match='count/yard objective'):
        bind_handoff(payload,dict(workload_forecast=counts))
    bind_handoff(payload,dict(workload_forecast=receipt))
    assert payload['params']['analyst_handoff_applied']['workload_forecast_sha256']==receipt['sha256']
    frame=pd.DataFrame(pool);frame['p90']=float('nan')
    _,report=build_captain_shortlist(frame,params=dict(workload_comparison='learned_yards',
        captain_positions=['RB','WR','TE'],prepared_input_evidence=dict(workload_forecast=receipt)),flex_only_ids=set())
    assert report['captain_score']=='1.5 * weighted_projected_yards'
    assert report['shortlist']
    assert all(r['pregame_p90'] is None for r in report['shortlist'])
    assert all(e['reason_code']!='missing_finite_pregame_p90' for p in report['exclusions'] for e in p['exclusions'])


def test_changed_weights_and_forged_forecast_are_not_consumed(monkeypatch):
    pool,_,receipt=yard_receipt(monkeypatch)
    params=dict(workload_comparison='learned_yards',prepared_input_evidence=dict(workload_forecast=receipt))
    def issue():
        return solve(None,pd.DataFrame(pool),params=params,contest_type='captain',stack_params={},locked_ids=set(),
            flex_only_ids=set(),avoid_dst_opponents=True,enforce_single_te=False,requested_captain_id=None)
    next(a for a in receipt['players'] if a['utility'] is not None)['utility']+=1
    with pytest.raises(ValueError,match='checksum'):issue()
    receipt['yardage_model']['selection_weights']=dict(WEIGHTS,passing_yards=1.)
    receipt['sha256']=digest({k:v for k,v in receipt.items() if k!='sha256'})
    with pytest.raises(ValueError,match='selection weights'):issue()


def test_status_compacts_full_history_without_hiding_validation(monkeypatch):
    from backend.app.product_services.slate_preparation import preparation_summary
    _,_,receipt=yard_receipt(monkeypatch)
    original=deepcopy(receipt)
    summary=preparation_summary(dict(workload_forecast=receipt))['workload_forecast']
    assert 'source_ids' not in summary['yardage_model']
    assert summary['yardage_model']['validation']==receipt['yardage_model']['validation']
    assert summary['yardage_model']['selection_weights']==WEIGHTS
    assert summary['players'][0]['projected_yards']==receipt['players'][0]['projected_yards']
    assert receipt==original


def test_sparse_factual_nonparticipation_survives_count_and_yard_adapters(monkeypatch):
    from backend.app.product_services.feature_block_model_inputs import apply_player_count_predictions
    from backend.app.product_services.single_stat_learned_yards import actor_forecast
    _,reference,_=yard_receipt(monkeypatch)
    actor=next(a for a in reference['players'] if a['position']=='RB')
    actor.update(world_activity=False,counts=dict.fromkeys(('pass_attempts','rush_attempts','targets'),0.),
        hypothetical_active_role_reference_counts=dict.fromkeys(('pass_attempts','rush_attempts','targets'),None))
    prediction=dict(player_master_id=actor['player_master_id'],team=actor['team'],period=reference['before_period'],
        history_supported=False,counts=dict.fromkeys(('pass_attempts','rush_attempts','targets'),99.))
    counts=apply_player_count_predictions(reference,[prediction])
    counts['sha256']=digest(counts)
    weekly,_=fixture()
    yards=add_yards(counts,weekly,before_period=202606,cutoff=NOW)
    fixed=next(a for a in yards['players'] if a['player_master_id']==actor['player_master_id'])
    single=actor_forecast(fixed,dict(team=actor['team'],position='RB'))
    assert single['value']==0. and single['missing_components']==[]
    assert fixed['hypothetical_active_role_reference_counts']['targets'] is None
    assert actor['counts']['targets']==0. and 'player_model_components' not in actor
    for accounting in yards['yardage_model']['accounting'].values():
        assert accounting['passing_yards']==pytest.approx(accounting['receiving_yards']+accounting['unallocated_receiving_yards'])
