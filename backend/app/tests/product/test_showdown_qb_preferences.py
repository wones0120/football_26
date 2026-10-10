from unittest.mock import MagicMock

import pandas as pd
import pytest

from backend.app.product_schemas import OptimizerRunRequest
from backend.app.product_services.optimizer import OptimizerService


def pool():
    return pd.DataFrame([
        {"player_id": f"p{i}", "player_master_id": f"p{i}", "name": f"Player {i}",
         "position": position, "salary": 5000, "projection": 40 - i, "p90": 50 - i,
         "player_team": "SEA" if i % 2 == 0 else "SF",
         "opponent_team": "SF" if i % 2 == 0 else "SEA",
         "is_starting_qb": position == "QB", "showdown_qb_eligible": position == "QB",
         "team_implied_total": 26 if i % 2 == 0 else 22}
        for i, position in enumerate(["QB", "QB", "WR", "WR", "RB", "RB", "K", "K", "TE", "TE", "DST", "DST"])
    ])


@pytest.fixture(autouse=True)
def offline_strategy_inputs(monkeypatch):
    # These policy fixtures are offline; live-source proofs are tested separately.
    monkeypatch.setattr("backend.app.product_services.showdown_data_readiness.is_live_slate", lambda *args, **kwargs: False)


@pytest.mark.parametrize("no_captain,no_two", [(False, False), (True, False), (False, True), (True, True)])
@pytest.mark.parametrize("hard_correlations", [False, True])
def test_solver_applies_independent_preferences_without_changing_model(no_captain, no_two, hard_correlations):
    players = pool()
    original = players.copy(deep=True)
    service = OptimizerService.__new__(OptimizerService)
    lineup = service._solve_lineup(players, contest_type="captain", stack_params={
        "no_qb_captain": no_captain, "no_two_qbs": no_two,
        "hard_qb_correlations": hard_correlations, "require_starting_qb": hard_correlations,
    }, include_control_comparison=False)
    assert lineup
    captain = next(row for row in lineup if row["roster_position"] == "CPT")
    qbs = [row for row in lineup if row["position"] == "QB"]
    if no_captain:
        assert captain["position"] != "QB"
    if no_two:
        assert len(qbs) == 1
    else:
        assert len(qbs) == 2
    if not no_captain and not hard_correlations:
        assert captain["position"] == "QB"
    for row in lineup:
        expected = original.loc[original.player_id == row["player_id"]].iloc[0]
        multiplier = 1.5 if row["roster_position"] == "CPT" else 1
        assert row["projection"] == expected.projection * multiplier
        assert row["p90"] == expected.p90 * multiplier
    pd.testing.assert_frame_equal(players, original)
    valid, reason = service._validate_showdown_lineups(
        [lineup], requested_lineups=1, max_exposure=1,
        no_qb_captain=no_captain, no_two_qbs=no_two, portfolio_policy=hard_correlations,
    )
    assert valid, reason


@pytest.mark.parametrize("key,label", [("no_qb_captain", "No QB Captain"), ("no_two_qbs", "No 2 QBs"), ("no_qbs", "No QBs")])
def test_final_validation_rejects_noncompliant_lineup(key, label):
    players = pool().iloc[:6].to_dict("records")
    for i, row in enumerate(players):
        row["roster_position"] = "CPT" if i == 0 else "FLEX"
    valid, reason = OptimizerService._validate_showdown_lineups(
        [players], requested_lineups=1, max_exposure=1, **{key: True},
    )
    assert not valid
    assert label in reason


@pytest.mark.parametrize("strategy", ["showdown_cash_baseline_v1", "showdown_gpp_baseline_v1",
    "showdown_gpp_portfolio_v3", "showdown_single_entry_gpp", "showdown_single_entry_portfolio",
    "showdown_3max_gpp", "showdown_small_max_gpp"])
def test_request_retains_preferences(strategy):
    request = OptimizerRunRequest(season=2026, week=4, slate="THURSDAY_NIGHT",
        strategy=strategy, contest_format="showdown", params={"no_qb_captain": True, "no_two_qbs": True})
    assert request.params["no_qb_captain"] is True
    assert request.params["no_two_qbs"] is True


@pytest.mark.parametrize("key", ["no_qb_captain", "no_two_qbs", "no_qbs"])
@pytest.mark.parametrize("value", ["false", "true", 0, 1, None])
def test_preferences_require_explicit_booleans(key, value):
    with pytest.raises(ValueError, match="explicit boolean"):
        OptimizerRunRequest(season=2026, week=4, slate="THURSDAY_NIGHT",
            strategy="showdown_cash_baseline_v1", contest_format="showdown", params={key: value})


@pytest.mark.parametrize("key", ["no_qb_captain", "no_two_qbs", "no_qbs"])
def test_classic_rejects_enabled_showdown_preferences(key):
    with pytest.raises(ValueError, match="requires Showdown"):
        OptimizerRunRequest(season=2026, week=4, slate="SUNDAY_MAIN",
            strategy="classic_cash_v1", contest_format="classic", params={key: True})


def service():
    result = OptimizerService.__new__(OptimizerService)
    result.engine = MagicMock()
    result._jobs = {}
    result._resolve_run_lineage = MagicMock(return_value=("projection-test", None, None))
    result._load_player_pool = MagicMock(return_value=pool())
    result._attach_symbolic_explanations = MagicMock()
    result._persist_optimizer_run = MagicMock(return_value=True)
    return result


@pytest.mark.parametrize("strategy,objective,count", [
    ("showdown_cash_baseline_v1", "cash", 1),
    ("showdown_gpp_portfolio_v3", "gpp", 5),
])
def test_run_persists_constraints_and_audits_without_removing_qb_assessment(strategy, objective, count):
    optimizer = service()
    original = optimizer._load_player_pool.return_value.copy(deep=True)
    job = optimizer.run_job(season=2026, week=4, slate="THURSDAY_NIGHT", strategy=strategy,
        contest_format="showdown", objective=objective,
        params={"num_lineups": count, "no_qb_captain": True, "no_two_qbs": True})
    assert job.status == "completed", job.message
    assert len(job.results) == count
    for lineup in job.results:
        assert sum(row["position"] == "QB" for row in lineup) <= 1
        assert next(row for row in lineup if row["roster_position"] == "CPT")["position"] != "QB"
        assert lineup[0]["showdown_qb_preferences"]["model_assessments_preserved"] is True
    runtime = job.params["strategy_runtime"]
    assert {item["reason_code"] for item in runtime["showdown_qb_preferences"]["exclusions"]} == {
        "user_no_qb_captain", "user_no_two_qbs"}
    if objective == "gpp":
        assert len(runtime["showdown_qb_preferences"]["excluded_scripts"]) == 2
    for qb_id in ("p0", "p1"):
        audit = next(row for row in runtime["player_pool"]["rows"] if row["player_id"] == qb_id)
        assert audit["included"] is True
        assert audit["model_assessment"]["projection"] == original.loc[original.player_id == qb_id].iloc[0].projection
        assert audit["captain_user_preference_exclusions"][0]["reason_code"] == "user_no_qb_captain"
    pd.testing.assert_frame_equal(optimizer._load_player_pool.return_value, original)
    optimizer._persist_optimizer_run.assert_called_once()


@pytest.mark.parametrize("params,reason", [
    ({"no_qb_captain": True, "locked_captain_player_id": "p0"}, "Locked QB Captain"),
    ({"no_two_qbs": True, "locked_player_ids": ["p0", "p1"]}, "Locked QBs"),
    ({"no_two_qbs": True, "locked_player_ids": ["p1"], "locked_captain_player_id": "p0"}, "Locked QBs"),
    ({"no_qbs": True, "locked_player_ids": ["p0"]}, "Locked QB"),
    ({"no_qbs": True, "locked_captain_player_id": "p1"}, "Locked QB"),
])
def test_conflicting_locks_have_explicit_user_preference_error(params, reason):
    with pytest.raises(ValueError, match=reason):
        service().run_job(season=2026, week=4, slate="THURSDAY_NIGHT", strategy="showdown_cash_baseline_v1",
            contest_format="showdown", objective="cash", params=params)


@pytest.mark.parametrize("limit", [3, 4])
def test_no_qbs_overrides_qb_required_constructions_without_changing_model(limit):
    players = pool()
    original = players.copy(deep=True)
    optimizer = OptimizerService.__new__(OptimizerService)
    lineup = optimizer._solve_lineup(players, contest_type="captain", stack_params={
        "no_qbs": True, "require_starting_qb": True, "hard_qb_correlations": True,
        "max_players_per_team": limit,
    }, include_control_comparison=False)
    assert lineup
    assert all(row["position"] != "QB" for row in lineup)
    assert next(row for row in lineup if row["roster_position"] == "CPT")["position"] == "WR"
    valid, reason = optimizer._validate_showdown_lineups([lineup], requested_lineups=1,
        max_exposure=1, portfolio_policy=True, no_qbs=True, max_players_per_team=limit)
    assert valid, reason
    pd.testing.assert_frame_equal(players, original)


@pytest.mark.parametrize("limit", [3, 4])
@pytest.mark.parametrize("strategy,objective,count", [
    ("showdown_cash_baseline_v1", "cash", 1),
    ("showdown_gpp_portfolio_v3", "gpp", 5),
])
def test_no_qbs_runs_keep_model_audit_and_save_zero_qb_policy(limit, strategy, objective, count):
    optimizer = service()
    original = optimizer._load_player_pool.return_value.copy(deep=True)
    job = optimizer.run_job(season=2026, week=4, slate="THURSDAY_NIGHT", strategy=strategy,
        contest_format="showdown", objective=objective,
        params={"num_lineups": count, "no_qbs": True, "max_players_per_team": limit})
    assert job.status == "completed", job.message
    assert job.results
    for lineup in job.results:
        assert all(row["position"] != "QB" for row in lineup)
        policy = lineup[0]["showdown_qb_preferences"]
        assert policy["effective_starting_qb_lineup_limit"] == 0
        assert policy["allow_qb_captain"] is False
        assert policy["exclusions"][0]["reason_code"] == "user_no_qbs"
    for qb_id in ("p0", "p1"):
        audit = next(row for row in job.params["strategy_runtime"]["player_pool"]["rows"] if row["player_id"] == qb_id)
        assert audit["optimizer_eligibility"] == "excluded_by_user_preference"
        assert audit["included"] is False
        assert audit["model_assessment"]["projection"] == original.loc[original.player_id == qb_id].iloc[0].projection
        assert audit["user_preference_exclusions"][0]["reason_code"] == "user_no_qbs"
    pd.testing.assert_frame_equal(optimizer._load_player_pool.return_value, original)
