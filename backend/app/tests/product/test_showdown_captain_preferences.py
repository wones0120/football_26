import pandas as pd
import pytest

from backend.app.product_schemas import OptimizerRunRequest
from backend.app.product_services.optimizer import OptimizerService
from backend.app.product_services.showdown_captain_preferences import allowed_captain_positions
from backend.app.tests.product.test_showdown_qb_preferences import pool, service, offline_strategy_inputs


@pytest.mark.parametrize("positions", [["WR"], ["RB"], ["TE"], ["WR", "RB", "TE"]])
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


@pytest.mark.parametrize("positions", [["WR"], ["RB"], ["TE"], ["WR", "RB", "TE"]])
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
