from unittest.mock import MagicMock

import pandas as pd
import pytest

from backend.app.product_services.optimizer import (
    CLASSIC_HEAD_TO_HEAD_STRATEGY_ID,
    SHOWDOWN_CASH_BASELINE_STRATEGY_ID,
    OptimizerService,
)


@pytest.mark.parametrize("contest_format", ["classic", "showdown"])
@pytest.mark.parametrize("enabled", [False, True])
def test_run_filters_questionable_before_solving_and_preserves_assessment(
    contest_format: str, enabled: bool, monkeypatch,
) -> None:
    # This synthetic preference-only pool has no live source evidence. Live
    # readiness and solver ordering are exercised by the readiness suites.
    monkeypatch.setattr("backend.app.product_services.showdown_data_readiness.is_live_slate", lambda *args, **kwargs: False)
    service = OptimizerService.__new__(OptimizerService)
    service._jobs = {}
    service.engine = MagicMock()
    service._resolve_run_lineage = MagicMock(return_value=("projection-test", None, None))
    positions = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "WR", "DST"]
    if contest_format == "showdown":
        positions[1] = "QB"
    size = 6 if contest_format == "showdown" else 9
    rows = [
        {
            "player_id": f"player-{index}", "player_master_id": f"player-{index}",
            "name": f"Player {index}", "position": position,
            "player_team": "AAA" if index % 2 else "BBB",
            "opponent_team": "BBB" if index % 2 else "AAA",
            "salary": 5000, "projection": 15.0, "p90": 25.0,
            "is_starting_qb": position == "QB",
        }
        for index, position in enumerate(positions[:size])
    ]
    questionable = {
        **rows[3], "player_id": "questionable", "player_master_id": "questionable",
        "name": "Questionable Player", "player_status": "Q",
        "projection": 18.4, "p90": 31.2, "pregame_role_label": "STARTER",
    }
    model_pool = pd.DataFrame([*rows, questionable])
    original = model_pool.copy(deep=True)
    service._load_player_pool = MagicMock(return_value=model_pool)
    lineup = [
        {**row, "roster_position": "CPT" if index == 0 else "FLEX"}
        for index, row in enumerate(rows)
    ]
    service._solve_lineup = MagicMock(return_value=lineup)
    service._lineups_satisfy_stack = MagicMock(return_value=(True, ""))
    service._validate_classic_lineups = MagicMock(return_value=(True, ""))
    service._validate_showdown_lineups = MagicMock(return_value=(True, ""))
    service._attach_symbolic_explanations = MagicMock()
    service._persist_optimizer_run = MagicMock(return_value=True)
    strategy = (
        SHOWDOWN_CASH_BASELINE_STRATEGY_ID if contest_format == "showdown"
        else CLASSIC_HEAD_TO_HEAD_STRATEGY_ID
    )
    request = dict(
        season=2026, week=4, slate="THURSDAY_NIGHT", strategy=strategy,
        contest_format=contest_format, objective="cash",
        params={"num_lineups": 1, "exclude_questionable": enabled},
    )
    job = service.run_job(**request)
    assert job.status == "completed", job.message
    solve_pool = service._solve_lineup.call_args.args[0]
    assert ("questionable" in set(solve_pool["player_id"])) is not enabled
    pd.testing.assert_frame_equal(model_pool, original)
    audit = next(
        row for row in job.params["strategy_runtime"]["player_pool"]["rows"]
        if row["player_id"] == "questionable"
    )
    assert audit["model_assessment"]["projection"] == 18.4
    assert audit["model_assessment"]["p90"] == 31.2
    assert audit["model_assessment"]["role_label"] == "STARTER"
    assert bool(audit["user_preference_exclusions"]) is enabled
    if enabled:
        assert audit["optimizer_eligibility"] == "excluded_by_user_preference"
        assert audit["user_preference_exclusions"][0]["reason_code"] == "user_excluded_questionable"
        request["params"]["locked_player_ids"] = ["questionable"]
        with pytest.raises(ValueError, match="user_excluded_questionable"):
            service.run_job(**request)


@pytest.mark.parametrize("value", ["false", "true", 0, 1, None])
def test_questionable_preference_requires_boolean(value) -> None:
    service = OptimizerService.__new__(OptimizerService)
    with pytest.raises(ValueError, match="exclude_questionable must be an explicit boolean"):
        service.run_job(
            season=2026, week=4, slate="SUNDAY_MAIN", strategy="gpp",
            params={"exclude_questionable": value},
        )
