from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.app.product_services.showdown_portfolio_selection import captain_family_summaries
from backend.app.product_services.showdown_readiness import assess_showdown_inputs
from backend.app.product_services.showdown_game_scenarios import condition_player_pool, define_game_scenarios
from backend.app.product_services.slate_preparation import validate_prepared_optimizer
from backend.app.models import OperationalJob
from backend.app.product_services.optimizer import OptimizerService
from backend.app.tests.product.slate_preparation_fixture import PreparationFixture
from backend.app.tests.product.test_slate_preparation import enqueue, optimizer_payload
from backend.app.tests.product.test_showdown_game_scenarios import player


def test_family_reports_eligible_alternative_without_changing_saved_selection():
    report = {"selected_ranks": [1], "omission_reasons": {67: "mean short", 68: "player exposure"},
              "ranked_metrics": [{"captain_player_id": "rb", "rank": 67, "quality_eligible": False},
                                 {"captain_player_id": "rb", "rank": 68, "quality_eligible": True}]}
    original = deepcopy(report)
    row = captain_family_summaries(report)[0]
    assert row["best_unscreened_rank"] == 67
    assert row["best_eligible_candidate"]["rank"] == 68
    assert row["reason"] == "player exposure"
    assert report == original


def test_showdown_prepared_preferences_do_not_change_scenario_api_worker_contract():
    fixture = PreparationFixture()
    try:
        enqueue(fixture)
        assert fixture.work()["status"] == "completed"
        build = fixture.client.get("/api/slate/preparation?season=2000&week=1&slate=SUNDAY_MAIN").json()["latest_build"]
        payload = {**optimizer_payload(build), "strategy": "showdown_gpp_portfolio_v3",
                   "contest_format": "showdown", "objective": "gpp"}
        payload["params"].update(exclude_questionable=True, exclude_player_ids=["synthetic-player"],
                                 availability_overrides=[])
        with fixture.factory() as db:
            assert validate_prepared_optimizer(db, payload)["projection_run_id"] == build["projection_run_id"]
            changed = deepcopy(payload)
            changed["params"]["availability_overrides"] = [{"player_id": "synthetic-player", "availability": "assume_out"}]
            with pytest.raises(ValueError, match="scenario changed"):
                validate_prepared_optimizer(db, changed)
        # Real queue API accepts the same preference-only request after worker
        # preparation, without invoking an optimizer or application data.
        response = fixture.client.post("/api/optimizer/jobs", json=payload)
        assert response.status_code == 202, response.text
        with fixture.factory() as db:
            queued = db.get(OperationalJob, response.json()["job"]["job_id"])
            assert queued.request_json["params"]["exclude_questionable"] is True
            assert queued.request_json["params"]["availability_overrides"] == []
    finally:
        fixture.close()


def test_readiness_distinguishes_stale_missing_and_unevaluated_without_refresh():
    rows = [{"game_id": "A@B 10/04/2026 08:20PM ET", "projection_run_id": "frozen",
             "market_observed_at": "2026-09-30T01:22:11Z", "market_context_point_in_time_safe": True,
             "game_total_line": 50.5, "team_spread_line": 3.5, "team_implied_total": 23.5,
             "market_source_system": "nflverse_schedules"}]
    original = deepcopy(rows)
    report = assess_showdown_inputs([rows], {}, datetime(2026, 10, 4, 18, tzinfo=UTC))
    assert report["checks"]["Market observation age"]["status"] == "WARNING"
    assert report["market_coverage"]["games"][0]["status"] == "stale"
    assert report["checks"]["Availability evidence"]["status"] == "MISSING"
    assert report["checks"]["Current entry availability clearance"]["status"] == "UNEVALUATED"
    assert report["entry_ready"] is False
    assert rows == original


def test_conditioning_legitimate_unchanged_zero_and_baseline_cases():
    pool = pd.DataFrame([player("a", "A", "QB"), player("b", "B", "WR")])
    pool.loc[1, ["projection", "p90"]] = 0.0
    baseline, decisive, _ = define_game_scenarios(pool)
    assert condition_player_pool(pool, baseline)["projection"].tolist() == [10.0, 0.0]
    result = condition_player_pool(pool, decisive)
    assert result.loc[0, "projection"] != 10.0
    assert result.loc[1, "projection"] == 0.0
    assert result.loc[1, "p90"] == 0.0


def test_normal_v3_service_revalidates_preparation_in_showdown_frame():
    run_method = OptimizerService.run_job
    fixture = PreparationFixture()
    try:
        enqueue(fixture)
        fixture.work()
        build = fixture.client.get("/api/slate/preparation?season=2000&week=1&slate=SUNDAY_MAIN").json()["latest_build"]
        rows = []
        for index, position in enumerate(["QB", "QB", "WR", "WR", "RB", "TE"]):
            team = "AAA" if index % 2 == 0 else "BBB"
            rows.append({"player_id": f"synthetic-{index}", "name": f"Synthetic {index}",
                         "position": position, "player_team": team,
                         "opponent_team": "BBB" if team == "AAA" else "AAA",
                         "salary": 5000, "projection": 10.0, "p90": 20.0,
                         "is_starting_qb": position == "QB"})
        service = OptimizerService.__new__(OptimizerService)
        service.engine = fixture.engine
        service._jobs = {}
        service._resolve_run_lineage = MagicMock(return_value=(build["projection_run_id"], None, None))
        service._load_player_pool = MagicMock(return_value=pd.DataFrame(rows))
        service._persist_optimizer_run = MagicMock(return_value=True)
        with patch.object(OptimizerService, "run_job", run_method), patch(
                "backend.app.product_services.slate_preparation.validate_prepared_optimizer",
                wraps=validate_prepared_optimizer) as validate:
            job = service.run_job(season=2000, week=1, slate="SUNDAY_MAIN",
                contest_format="showdown", objective="gpp", strategy="showdown_gpp_portfolio_v3",
                projection_run_id=build["projection_run_id"], params={
                    "num_lineups": 1, "exclude_questionable": True,
                    "prepared_input_job_id": build["prepared_input_job_id"]})
        assert job.status == "completed", job.message
        assert validate.call_count == 2
        assert all(call.args[1]["contest_format"] == "showdown" for call in validate.call_args_list)
        assert job.params["entry_readiness"]["entry_ready"] is False
        assert job.params["strategy_runtime"]["showdown_portfolio_policy"]["candidate_selection"]["family_rows"]
    finally:
        fixture.close()
