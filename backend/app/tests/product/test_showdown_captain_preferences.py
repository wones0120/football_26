import pandas as pd
import pytest

from backend.app.product_schemas import OptimizerRunRequest
from backend.app.product_services.optimizer import OptimizerService
from backend.app.product_services.showdown_captain_preferences import allowed_captain_positions
from backend.app.tests.product.test_showdown_qb_preferences import pool, service, offline_strategy_inputs


@pytest.mark.parametrize("positions", [["WR"], ["RB"], ["TE"], ["WR", "RB"], ["WR", "RB", "TE"]])
@pytest.mark.parametrize("no_qbs", [False, True])
def test_solver_restricts_only_captain_and_preserves_scored_pool(positions, no_qbs):
    players = pool()
    original = players.copy(deep=True)
    optimizer = OptimizerService.__new__(OptimizerService)
    lineup = optimizer._solve_lineup(players, contest_type="captain", stack_params={
        "captain_positions": positions, "no_qbs": no_qbs,
        "require_starting_qb": True, "hard_qb_correlations": True,
    }, include_control_comparison=False)
    assert lineup
    assert next(r for r in lineup if r['roster_position']=='CPT')['position'] in positions
    assert sum(r['position']=='QB' for r in lineup) == (0 if no_qbs else 2)
    valid, reason = optimizer._validate_showdown_lineups([lineup], requested_lineups=1,
        max_exposure=1, captain_positions=positions, no_qbs=no_qbs, portfolio_policy=True)
    assert valid, reason
    pd.testing.assert_frame_equal(players, original)


@pytest.mark.parametrize("positions", [["WR"], ["RB"], ["TE"], ["WR", "RB"], ["WR", "RB", "TE"]])
@pytest.mark.parametrize("strategy,objective,count", [
    ("showdown_cash_baseline_v1", "cash", 1), ("showdown_gpp_portfolio_v3", "gpp", 3),
])
def test_runs_save_captain_only_exclusions_and_unchanged_model(positions, strategy, objective, count):
    optimizer = service()
    original = optimizer._load_player_pool.return_value.copy(deep=True)
    job = optimizer.run_job(season=2026, week=4, slate="THURSDAY_NIGHT", strategy=strategy,
        contest_format="showdown", objective=objective, params={"num_lineups":count,"captain_positions":positions})
    assert job.status == "completed", job.message
    assert job.results
    for lineup in job.results:
        assert next(r for r in lineup if r['roster_position']=='CPT')['position'] in positions
        report = lineup[0]['showdown_captain_preferences']
        assert report['allowed_positions'] == positions
        assert report['reason_code'] == 'user_captain_positions'
        assert report['model_assessments_preserved']
        assert report['flex_eligibility_unchanged']
        assert lineup[0]['showdown_qb_preferences']['allow_qb_captain'] is False
    runtime = job.params['strategy_runtime']
    assert runtime['showdown_captain_preferences']['allowed_positions'] == positions
    for row in runtime['player_pool']['rows']:
        if row['player_id'] in ['p0','p1']:
            assert row['included'] is True
            assert row['model_assessment']['projection'] == original.loc[original.player_id==row['player_id']].iloc[0].projection
            assert row['captain_user_preference_exclusions'][0]['reason_code']=='user_captain_positions'
    pd.testing.assert_frame_equal(optimizer._load_player_pool.return_value, original)


@pytest.mark.parametrize("value", [None, "WR", ["QB"], ["K"], ["DST"], ["wr"], [1], [None], [{}]])
def test_api_rejects_invalid_position_lists(value):
    with pytest.raises(ValueError, match='captain_positions'):
        OptimizerRunRequest(season=2026, week=4, slate="THURSDAY_NIGHT",
            strategy="showdown_cash_baseline_v1", contest_format="showdown", params={'captain_positions':value})


def test_classic_rejects_captain_restriction_and_empty_list_remains_unrestricted():
    with pytest.raises(ValueError, match='requires Showdown'):
        OptimizerRunRequest(season=2026, week=4, slate="SUNDAY_MAIN", strategy="classic_cash_v1",
            contest_format="classic", params={'captain_positions':['WR']})
    request = OptimizerRunRequest(season=2026, week=4, slate="SUNDAY_MAIN", strategy="classic_cash_v1",
        contest_format="classic", params={'captain_positions':[]})
    assert request.params['captain_positions']==[]
    assert allowed_captain_positions({'captain_positions':['TE','WR','TE']})==['WR','TE']


def test_final_validator_catches_out_of_position_captain():
    lineup = pool().iloc[:6].to_dict('records')
    for i, row in enumerate(lineup): row['roster_position']='CPT' if i==0 else 'FLEX'
    valid, reason = OptimizerService._validate_showdown_lineups([lineup], requested_lineups=1,
        max_exposure=1, captain_positions=['WR','RB','TE'])
    assert not valid
    assert 'Captain position restricted' in reason


def test_locked_captain_conflict_is_explicit():
    with pytest.raises(ValueError, match='Locked Captain conflicts.*WR'):
        service().run_job(season=2026, week=4, slate="THURSDAY_NIGHT", strategy="showdown_cash_baseline_v1",
            contest_format="showdown", objective="cash",
            params={'captain_positions':['WR'],'locked_captain_player_id':'p4'})


def test_missing_requested_position_cannot_fall_back_to_other_captain():
    players=pool()
    players=players[players.position!='TE'].reset_index(drop=True)
    assert OptimizerService.__new__(OptimizerService)._solve_lineup(players, contest_type='captain',
        stack_params={'captain_positions':['TE']},include_control_comparison=False) is None


@pytest.mark.parametrize('qb_count', [0, 1, 2])
def test_rb_captain_qb_count_is_optional_and_model_unchanged(qb_count):
    players=pool()
    players.loc[players.position=='QB',['projection','p90']]=0
    for i in range(qb_count):
        players.loc[players.player_id==f'p{i}',['projection','p90']]=100
    players.loc[players.player_id=='p4',['projection','p90']]=150
    # Include both SEA receivers without SEA QB when neither QB is attractive.
    players.loc[players.player_id.isin(['p2','p8']),['projection','p90']]=80
    original=players.copy(deep=True)
    optimizer=OptimizerService.__new__(OptimizerService)
    lineup=optimizer._solve_lineup(players,contest_type='captain',stack_params={
        'captain_positions':['RB'],'require_starting_qb':True,'hard_qb_correlations':True,
    },include_control_comparison=False)
    assert lineup
    assert sum(p['position']=='QB' for p in lineup)==qb_count
    assert next(p for p in lineup if p['roster_position']=='CPT')['position']=='RB'
    valid,reason=optimizer._validate_showdown_lineups([lineup],requested_lineups=1,max_exposure=1,
        captain_positions=['RB'],portfolio_policy=True)
    assert valid,reason
    pd.testing.assert_frame_equal(players,original)


def test_wr_captain_still_requires_own_qb_when_qbs_project_poorly():
    players=pool()
    players.loc[players.position=='QB',['projection','p90']]=0
    optimizer=OptimizerService.__new__(OptimizerService)
    lineup=optimizer._solve_lineup(players,contest_type='captain',stack_params={
        'captain_positions':['WR'],'require_starting_qb':True,'hard_qb_correlations':True,
    },include_control_comparison=False)
    captain=next(p for p in lineup if p['roster_position']=='CPT')
    assert any(p['position']=='QB' and p['player_team']==captain['player_team'] for p in lineup)
    # An otherwise legal WR-Captain lineup without its QB must fail final validation.
    without=[p.copy() for p in lineup]
    for p in without:
        if p['position']=='QB': p.update(position='K',showdown_qb_eligible=False)
    valid,_=optimizer._validate_showdown_lineups([without],requested_lineups=1,max_exposure=1,
        captain_positions=['WR'],portfolio_policy=True)
    assert not valid


@pytest.mark.parametrize('value', [-1, 1.5, 50001, '1700', True])
def test_minimum_salary_rejects_invalid_requests(value):
    with pytest.raises(ValueError,match='minimum_player_salary'):
        OptimizerRunRequest(season=2026,week=4,slate='THURSDAY_NIGHT',contest_format='showdown',
            strategy='showdown_cash_baseline_v1',params={'minimum_player_salary':value})


def test_minimum_salary_filters_selection_and_preserves_model_assessment():
    optimizer=service()
    players=optimizer._load_player_pool.return_value
    players.loc[players.player_id=='p8','salary']=1600
    players.loc[players.player_id=='p9','salary']=1700
    original=players.copy(deep=True)
    job=optimizer.run_job(season=2026,week=4,slate='THURSDAY_NIGHT',strategy='showdown_cash_baseline_v1',
        contest_format='showdown',objective='cash',params={'num_lineups':1,'minimum_player_salary':1700})
    assert job.status=='completed',job.message
    assert all(p['player_id']!='p8' for r in job.results for p in r)
    audit=next(r for r in job.params['strategy_runtime']['player_pool']['rows'] if r['player_id']=='p8')
    assert 'user_minimum_player_salary' in audit['exclusion_reasons']
    assert audit['user_preference_exclusions']
    assert next(r for r in job.params['strategy_runtime']['player_pool']['rows'] if r['player_id']=='p9')['included']
    assert audit['model_assessment']['projection']==original.loc[original.player_id=='p8'].iloc[0].projection
    pd.testing.assert_frame_equal(players,original)


def test_minimum_salary_captain_uses_base_not_multiplied_salary():
    rows=pool().iloc[:6].to_dict('records')
    for i,row in enumerate(rows): row['roster_position']='CPT' if i==0 else 'FLEX'
    rows[0].update(salary=2400,base_salary=1600)
    valid,reason=OptimizerService._validate_showdown_lineups([rows],requested_lineups=1,max_exposure=1,minimum_player_salary=1700)
    assert not valid and 'minimum base salary' in reason
    rows[0].pop('base_salary')
    assert not OptimizerService._validate_showdown_lineups([rows],requested_lineups=1,max_exposure=1,minimum_player_salary=1700)[0]


def test_minimum_salary_accepts_classic_and_rejects_locked_conflicts():
    request=OptimizerRunRequest(season=2026,week=4,slate='SUNDAY_MAIN',contest_format='classic',
        strategy='classic_cash_v1',params={'minimum_player_salary':1700})
    assert request.params['minimum_player_salary']==1700
    optimizer=service()
    optimizer._load_player_pool.return_value.loc[lambda p:p.player_id=='p4','salary']=1600
    with pytest.raises(ValueError,match='minimum player salary'):
        optimizer.run_job(season=2026,week=4,slate='THURSDAY_NIGHT',strategy='showdown_cash_baseline_v1',
            contest_format='showdown',objective='cash',params={'num_lineups':1,'minimum_player_salary':1700,'locked_captain_player_id':'p4'})


def test_named_captain_position_exception_is_narrow_and_preserves_other_filters():
    from backend.app.product_services.showdown_captain_shortlist import build_captain_shortlist
    from backend.app.product_services.showdown_captain_preferences import captain_preference_exclusions
    players = pool()
    params = {'captain_positions':['WR','RB'], 'captain_position_exception_ids':['p0'], 'analyst_strategy':'MERGED_SCENARIOS'}
    framed, report = build_captain_shortlist(players, params=params, flex_only_ids=set())
    assert framed.loc[framed.player_id=='p0','showdown_captain_shortlisted'].all()
    assert not captain_preference_exclusions(params, 'QB', 'p0')
    assert captain_preference_exclusions(params, 'QB', 'p1')
    _, blocked = build_captain_shortlist(players, params={**params,'no_qb_captain':True}, flex_only_ids=set())
    assert 'p0' not in {row['player_id'] for row in blocked['shortlist']}
    lineup = OptimizerService.__new__(OptimizerService)._solve_lineup(players, contest_type='captain', stack_params=params, locked_captain_player_id='p0', include_control_comparison=False)
    assert lineup and next(r for r in lineup if r['roster_position']=='CPT')['player_id']=='p0'
    valid, reason = OptimizerService._validate_showdown_lineups([lineup], requested_lineups=1, max_exposure=1, captain_positions=['WR','RB'], captain_position_exception_ids={'p0'})
    assert valid, reason


def test_named_exception_flows_from_run_to_solver_and_saved_audit():
    optimizer=service()
    job=optimizer.run_job(season=2026,week=4,slate='THURSDAY_NIGHT',strategy='showdown_gpp_portfolio_v3',contest_format='showdown',objective='gpp',params={'num_lineups':1,'captain_positions':['WR','RB'],'captain_position_exception_ids':['p0'],'locked_captain_player_id':'p0'})
    assert job.status=='completed',job.message
    assert next(r for r in job.results[0] if r['roster_position']=='CPT')['player_id']=='p0'
    audit=next(r for r in job.params['strategy_runtime']['player_pool']['rows'] if r['player_id']=='p0')
    assert not audit['captain_user_preference_exclusions']
    assert job.results[0][0]['showdown_captain_preferences']['named_position_exception_ids']==['p0']
