import copy
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pandas as pd
import pulp
import pytest

from backend.app.product_services.optimizer import OptimizerService, OptimizerJob, _json_safe
from backend.app.product_services.optimizer_control import replay_control
from backend.app.product_services.rule_library import resolve_strategy_profile
from backend.app.product_services.gpp_optimizer import Player, generate_portfolio, build_large_gpp_config


def pool():
    positions = ["QB", "RB", "RB", "RB", "WR", "WR", "WR", "DST", "TE", "TE"]
    rows = []
    for i, position in enumerate(positions):
        adjustment = 2 if i == 9 else 0
        projection = 20 - i if i < 8 else (10 if i == 8 else 9)
        rows.append(dict(player_id=f"id-{i}", name=f"Player {i}", position=position,
                         salary=4000, projection=projection, p90=projection + 10,
                         optimizer_context_adjustment=adjustment,
                         optimizer_context_ceiling_score=projection + 10 + adjustment,
                         player_team=f"T{i % 4}", opponent_team=f"T{(i + 1) % 4}",
                         optimizer_context_rule_evaluation={"triggered_rules": [
                             {"rule_id": "test_context", "score_contribution": adjustment}
                         ]} if adjustment else {}))
    return pd.DataFrame(rows)


def classic(**kwargs):
    return OptimizerService.__new__(OptimizerService)._solve_lineup(
        pool(), score_col="optimizer_context_ceiling_score", enforce_single_te=True,
        stack_params={"enabled": False}, **kwargs)


def test_classic_swap_cost_missing_metrics_and_reproducible_control():
    lineup = classic()
    report = lineup[0]["lineup_control_comparison"]
    assert [p["player_id"] for p in report["selected_only"]] == ["id-9"]
    assert [p["player_id"] for p in report["control_only"]] == ["id-8"]
    assert report["deltas_scored_minus_control"]["mean"] == -1
    assert report["deltas_scored_minus_control"]["individual_ceiling_sum"] == -1
    assert report["deltas_scored_minus_control"]["ownership_sum"] is None
    assert report["deltas_scored_minus_control"]["leverage_sum"] is None
    assert report["base_objective_opportunity_cost"] == pytest.approx(1)
    assert report["selection_effect"] == "rules_preferred_selection"
    assert report["rule_contributions"][0]["delta"] == 2
    persisted = json.loads(json.dumps(_json_safe(report), allow_nan=False))
    replayed = replay_control(persisted["replay"])
    assert replayed["objective"] == report["replay"]["control_objective"]
    assert {p["player_id"] for p in replayed["selected_players"]} == {p["player_id"] for p in report["control_lineup"]}
    corrupted = copy.deepcopy(persisted["replay"])
    corrupted["model"]["constraints"][0]["constant"] += 1
    with pytest.raises(ValueError, match="checksum"):
        replay_control(corrupted)


def test_control_preserves_lock_exposure_and_previous_lineup_exclusion():
    locked = classic(locked_player_ids={"id-9"})[0]["lineup_control_comparison"]
    assert not locked["selection_changed"]
    capped = classic(exposure_remaining={"id-8": 0})[0]["lineup_control_comparison"]
    assert not capped["selection_changed"]
    previous = [(f"id-{i}", None) for i in range(9)]
    excluded = classic(exclude_signatures=[previous])[0]["lineup_control_comparison"]
    assert "id-9" in {p["player_id"] for p in excluded["control_lineup"]}


@pytest.mark.parametrize("objective", ["cash", "gpp"])
def test_showdown_control_keeps_captain_multiplier_and_flex_only(objective):
    frame = pool().iloc[:7].copy()
    frame["position"] = ["QB", "WR", "RB", "QB", "WR", "TE", "K"]
    frame["player_team"] = ["A", "A", "A", "B", "B", "B", "B"]
    frame["opponent_team"] = ["B", "B", "B", "A", "A", "A", "A"]
    frame["projection"] = [30, 20, 15, 25, 19, 9, 8]
    frame["p90"] = frame["projection"] + 10
    frame["optimizer_context_adjustment"] = [0, 0, 0, 0, 0, 0, 5]
    frame["optimizer_context_ceiling_score"] = frame["p90"] + frame["optimizer_context_adjustment"]
    frame["showdown_cash_score"] = frame["projection"] + frame["optimizer_context_adjustment"]
    result = OptimizerService.__new__(OptimizerService)._solve_lineup(
        frame, score_col="showdown_cash_score" if objective == "cash" else "optimizer_context_ceiling_score",
        contest_type="captain", stack_params={"require_qb_captain_receiver": True},
        locked_player_ids={"id-0"}, flex_only_player_ids={"id-0"},
        rule_profile=resolve_strategy_profile(contest_format="showdown", objective=objective))
    report = result[0]["lineup_control_comparison"]
    for lineup in (result, report["control_lineup"]):
        assert sum(p["roster_position"] == "CPT" for p in lineup) == 1
        assert next(p for p in lineup if p["player_id"] == "id-0")["roster_position"] == "FLEX"
        assert sum(p["salary"] for p in lineup) <= 50000
    assert report["control_metrics"]["mean"] == sum(p["projection"] for p in report["control_lineup"])
    assert replay_control(report["replay"])["objective"] == report["replay"]["control_objective"]


def test_gpp_controls_preserve_portfolio_step_and_normalization():
    players = [Player(row["player_id"], row["name"], row["player_team"], row["opponent_team"],
                      row["position"], row["salary"], row["projection"], row["p90"], 0,
                      optimizer_context_adjustment=row["optimizer_context_adjustment"],
                      optimizer_context_rule_evaluation=row["optimizer_context_rule_evaluation"])
               for row in pool().to_dict("records")]
    result = generate_portfolio(2026, 1, "TEST", 2, engine=object(), players=players,
                                config_builder=build_large_gpp_config, ownership_available=False,
                                max_exposure=1, minimum_uniqueness=1, enforce_single_te=True,
                                stack_templates=[(0, 0)], minimum_exposure_by_player={"id-9": 0.5})
    assert result.status == "completed"
    assert len(result.control_comparisons) == 2
    for comparison in result.control_comparisons:
        assert comparison["control_metrics"]["ownership_sum"] is None
        assert comparison["control_metrics"]["leverage_sum"] is None
        assert comparison["base_objective_opportunity_cost"] >= -1e-6
        assert len(replay_control(comparison["replay"])["selected_players"]) == 9
    first_ids = {p.player_id for p in result.lineups[0]}
    second_control = {p["player_id"] for p in result.control_comparisons[1]["control_lineup"]}
    assert len(first_ids & second_control) <= result.config.uniqueness_overlap


def test_comparison_survives_database_payload_reload_and_api():
    from backend.app.api.product_routes import get_optimizer_results
    service = OptimizerService.__new__(OptimizerService)
    service._jobs = {}
    service.engine = MagicMock()
    connection = service.engine.begin.return_value.__enter__.return_value
    now = datetime.now(timezone.utc)
    job = OptimizerJob("control-test", "completed", now, now, 2026, 1, "TEST", "baseline",
                       "classic", "gpp", {}, results=[classic()])
    assert service._persist_optimizer_run(job)
    player_payloads = next(call.args[1] for call in connection.execute.call_args_list
                           if len(call.args) > 1 and isinstance(call.args[1], list)
                           and call.args[1] and "player_json" in call.args[1][0])
    run_result, lineup_result, player_result = MagicMock(), MagicMock(), MagicMock()
    run_result.mappings.return_value.first.return_value = dict(
        optimizer_run_id=job.job_id, status="completed", created_at=now, updated_at=now,
        season=2026, week=1, slate_id="TEST", strategy="baseline", contest_format="classic",
        objective="gpp", constraint_config_json={}, projection_run_id=None, rule_run_id=None,
        data_cutoff_at=None, message="completed")
    lineup_result.mappings.return_value.all.return_value = [{"lineup_id": "control-test:1", "lineup_number": 1}]
    player_result.mappings.return_value.all.return_value = [
        {"slot_index": row["slot_index"], "roster_position": row["roster_position"],
         "player_json": json.loads(row["player_json"])} for row in player_payloads]
    connection.execute.side_effect = [run_result, lineup_result, player_result]
    response = get_optimizer_results(job.job_id, service=service)
    report = response.results[0][0]["lineup_control_comparison"]
    assert report == _json_safe(job.results[0][0]["lineup_control_comparison"])
    assert len(replay_control(report["replay"])["selected_players"]) == 9


def test_no_soft_rules_keeps_selection_and_zero_opportunity_cost():
    frame = pool()
    frame["optimizer_context_adjustment"] = 0
    frame["optimizer_context_ceiling_score"] = frame["p90"]
    frame["optimizer_context_rule_evaluation"] = [{} for _ in range(len(frame))]
    result = OptimizerService.__new__(OptimizerService)._solve_lineup(
        frame, score_col="optimizer_context_ceiling_score", enforce_single_te=True,
        stack_params={"enabled": False})
    report = result[0]["lineup_control_comparison"]
    assert report["selection_effect"] == "unchanged"
    assert report["base_objective_opportunity_cost"] == 0
    assert report["rule_contributions"] == []


def test_captain_slot_changes_are_reported_even_with_identical_players():
    frame = pool().iloc[:6].copy()
    frame["player_team"] = ["A", "A", "A", "B", "B", "B"]
    frame["opponent_team"] = ["B", "B", "B", "A", "A", "A"]
    frame["optimizer_context_adjustment"] = [0, 5, 0, 0, 0, 0]
    frame["optimizer_context_ceiling_score"] = frame["p90"] + frame["optimizer_context_adjustment"]
    result = OptimizerService.__new__(OptimizerService)._solve_lineup(
        frame, score_col="optimizer_context_ceiling_score", contest_type="captain",
        stack_params={})
    report = result[0]["lineup_control_comparison"]
    assert {p["player_id"] for p in result} == {p["player_id"] for p in report["control_lineup"]}
    assert report["selection_effect"] == "rules_preferred_selection"
    assert {(p["player_id"], p["roster_position"]) for p in report["selected_only"]} == {("id-1", "CPT"), ("id-0", "FLEX")}
    assert report["base_objective_opportunity_cost"] == pytest.approx(0.5)
