from collections import Counter

import pandas as pd
import pytest

from backend.app.product_schemas import OptimizerRunRequest
from backend.app.product_services.optimizer import OptimizerService
from backend.app.tests.product.test_showdown_qb_preferences import pool, service


@pytest.fixture(autouse=True)
def offline_strategy_inputs(monkeypatch):
    # These policy fixtures are offline; live-source proofs are tested separately.
    monkeypatch.setattr("backend.app.product_services.showdown_data_readiness.is_live_slate", lambda *args, **kwargs: False)


@pytest.mark.parametrize("limit", [3, 4, 5])
def test_team_limit_counts_captain_and_flex_without_changing_assessments(limit):
    players = pool()
    players.loc[players.player_team == "SEA", ["projection", "p90"]] += 50
    original = players.copy(deep=True)
    lineup = OptimizerService.__new__(OptimizerService)._solve_lineup(
        players, contest_type="captain", stack_params={"max_players_per_team": limit},
        include_control_comparison=False,
    )
    assert lineup
    assert sorted(Counter(row["player_team"] for row in lineup).values()) == [6 - limit, limit]
    valid, reason = OptimizerService._validate_showdown_lineups(
        [lineup], requested_lineups=1, max_exposure=1, max_players_per_team=limit,
    )
    assert valid, reason
    if limit > 3:
        valid, reason = OptimizerService._validate_showdown_lineups(
            [lineup], requested_lineups=1, max_exposure=1, max_players_per_team=limit - 1,
        )
        assert not valid
        assert "showdown team limit" in reason
    pd.testing.assert_frame_equal(players, original)


@pytest.mark.parametrize("value", [2, 6, True, 3.0, "4"])
def test_bad_team_limits_are_rejected_before_queueing(value):
    with pytest.raises(ValueError, match="max_players_per_team"):
        OptimizerRunRequest(season=2026, week=4, slate="THURSDAY_NIGHT",
            strategy="showdown_cash_baseline_v1", contest_format="showdown",
            params={"max_players_per_team": value})


@pytest.mark.parametrize("limit", [3, 4])
@pytest.mark.parametrize("strategy,objective,count", [
    ("showdown_cash_baseline_v1", "cash", 1),
    ("showdown_gpp_portfolio_v3", "gpp", 5),
])
def test_runs_enforce_and_persist_team_limit(limit, strategy, objective, count):
    optimizer = service()
    job = optimizer.run_job(season=2026, week=4, slate="THURSDAY_NIGHT", strategy=strategy,
        contest_format="showdown", objective=objective,
        params={"num_lineups": count, "max_players_per_team": limit})
    assert job.status == "completed", job.message
    assert job.results
    assert job.params["objective_config"]["max_players_per_team"] == limit
    report = job.params["strategy_runtime"]["showdown_team_constraints"]
    assert report["reason_code"] == "user_max_players_per_team"
    for lineup in job.results:
        assert max(Counter(row["player_team"] for row in lineup).values()) <= limit
        assert lineup[0]["showdown_team_constraints"] == report


def test_omitted_limit_preserves_five_player_default():
    job = service().run_job(season=2026, week=4, slate="THURSDAY_NIGHT",
        strategy="showdown_cash_baseline_v1", contest_format="showdown", objective="cash", params={})
    assert job.status == "completed", job.message
    assert job.params["max_players_per_team"] == 5


def test_conflicting_team_locks_fail_explicitly():
    with pytest.raises(ValueError, match="Locked players conflict with Max players per team"):
        service().run_job(season=2026, week=4, slate="THURSDAY_NIGHT",
            strategy="showdown_cash_baseline_v1", contest_format="showdown", objective="cash",
            params={"max_players_per_team": 3, "locked_player_ids": ["p0", "p2", "p4", "p6"]})
