from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from backend.app.product_services.optimizer_effectiveness import (
    actual_points_by_player,
    build_optimizer_effectiveness,
    candidate_signature,
    candidate_snapshot,
    chronological_validation,
    evaluate_run,
    extract_saved_pool,
    field_benchmarks,
    field_rank,
    score_signature,
    top_field_constructions,
)


def _classic_candidate(ids: list[str], rank: int, mean: float) -> dict:
    return {"player_ids": ids, "rank": rank, "mean": mean, "p90": mean + 20,
            "objective_score": 10 - rank, "ownership_sum": 100 - rank}


@pytest.mark.parametrize("points", [79, 80, 90, 99.994, 99.995, 100, 100.005, 100.006, 120, 121])
def test_field_rank_preserves_ties_and_half_cent_tolerance(points):
    scores = [120.0, 100.005, 100.0, 100.0, 99.995, 90.0, 80.0]
    above = sum(score > points + 0.005 for score in scores)
    tied_or_above = sum(score >= points - 0.005 for score in scores)
    assert field_rank(points, scores) == {
        "best_rank": above + 1,
        "worst_rank": max(above + 1, tied_or_above),
        "top_percent_conservative": 100 * tied_or_above / len(scores),
    }


def test_classic_candidate_scoring_selection_regret_and_ties():
    shared = [f"p{i}" for i in range(8)]
    candidates = [_classic_candidate(shared + [last], rank, 100 + rank)
                  for rank, last in enumerate(("low", "high", "mid"), 1)]
    run = {"optimizer_run_id": "run-1", "contest_format": "classic", "strategy": "classic_small_field_gpp",
           "constraint_config_json": {"strategy_runtime": {"classic_small_field": {"all_candidates": candidates}}}}
    selected = [{"signature": candidate_signature(candidates[0], "classic")}]
    actuals = {**{pid: 10 for pid in shared}, "low": 10, "high": 50, "mid": 30}
    field = field_benchmarks({"field_size": 5},
                             [{"entry_points": value} for value in (120, 110, 110, 90, 80)],
                             [{"max_rank": 3, "payout": 1}])
    assert field["thresholds"]["top_20_percent"] == 120
    assert field["cash_line"] == 110
    assert field_rank(110, field["field_scores_desc"]) == {
        "best_rank": 2, "worst_rank": 3, "top_percent_conservative": 60.0,
    }
    result = evaluate_run(run, selected, selected, actuals, {"contest": field})
    assert result["status"] == "complete"
    assert result["best_generated_actual"] == 130
    assert result["best_selected_actual"] == 90
    assert result["selection_regret_observed"] == 40
    assert result["candidates"][0]["postgame"]["actual_rank"] == 3
    assert result["top_k_capture"]["1"]["best_scored_actual"] == 90
    assert result["top_k_capture"]["3"]["best_scored_actual"] == 130
    assert result["field"]["contest"]["attainment"]["cash"]["generated_scored"] == 2
    assert result["correlations"]["mean"]["n"] == 3


def test_showdown_captain_multiplier_and_flex_identity():
    candidate = {"players": [{"player_id": "captain", "slot": "CPT"}] +
                 [{"player_id": f"f{i}", "slot": "FLEX"} for i in range(5)]}
    signature = candidate_signature(candidate, "showdown")
    observations = [{"player_id": "captain", "roster_position": "CPT", "actual_points": 30,
                     "resolution_status": "resolved"},
                    {"player_id": "captain", "roster_position": "FLEX", "actual_points": 20,
                     "resolution_status": "resolved"}] + [
                         {"player_id": f"f{i}", "roster_position": "FLEX", "actual_points": 1,
                          "resolution_status": "resolved"} for i in range(5)]
    actuals = actual_points_by_player(observations, "showdown")
    assert actuals["captain"] == 20
    assert score_signature(signature, actuals) == (35, [])
    assert candidate_signature({"players": [{"player_id": "captain", "slot": "FLEX"}] +
                                candidate["players"][1:]}, "showdown") is None


def test_saved_pool_manifest_is_deterministic_and_replay_is_never_implied():
    candidates = [_classic_candidate([f"p{i}" for i in range(9)], 1, 100)]
    config = {"strategy_runtime": {"classic_small_field": {"all_candidates": candidates}}}
    manifest = candidate_snapshot(config, "classic")
    assert manifest == candidate_snapshot(deepcopy(config), "classic")
    assert manifest["status"] == "original_candidate_pool"
    config["strategy_runtime"]["candidate_pool_manifest"] = manifest
    assert extract_saved_pool(config, "classic")["status"] == "original_candidate_pool"
    config["strategy_runtime"]["classic_small_field"]["all_candidates"][0]["mean"] = 999
    assert extract_saved_pool(config, "classic")["reason"] == "candidate_pool_hash_mismatch"
    assert extract_saved_pool({"replayed_candidate_pool": candidates}, "classic")["status"] == "unavailable"


def test_missing_actuals_and_incomplete_field_remain_explicit():
    candidate = _classic_candidate([f"p{i}" for i in range(9)], 1, 100)
    run = {"optimizer_run_id": "run", "contest_format": "classic", "strategy": "test",
           "constraint_config_json": {"strategy_runtime": {"classic_small_field": {"all_candidates": [candidate]}}}}
    field = field_benchmarks({"field_size": 2}, [{"entry_points": 100}], [])
    result = evaluate_run(run, [], [], {"p0": 10}, {"contest": field})
    assert result["status"] == "incomplete_player_actuals"
    assert result["best_generated_actual"] is None
    assert result["field"]["contest"]["status"] == "unavailable"
    assert result["candidate_pool"]["status"] == "original_candidate_pool"


def test_incomplete_pool_rank_is_a_bound_and_postgame_input_is_rejected():
    shared = [f"p{i}" for i in range(8)]
    candidates = [_classic_candidate(shared + [last], rank, 100)
                  for rank, last in enumerate(("known", "missing"), 1)]
    run = {"optimizer_run_id": "run", "contest_format": "classic", "strategy": "test",
           "constraint_config_json": {"strategy_runtime": {"classic_small_field": {"all_candidates": candidates}}}}
    result = evaluate_run(run, [], [], {**{pid: 10 for pid in shared}, "known": 5}, {})
    assert result["status"] == "incomplete_player_actuals"
    assert result["candidates"][0]["postgame"]["actual_rank"] is None
    assert result["candidates"][0]["postgame"]["actual_rank_bounds"] == [1, 2]
    assert result["correlations_scope"] == "scoreable_saved_variants_only"
    contaminated = deepcopy(run["constraint_config_json"])
    contaminated["strategy_runtime"]["classic_small_field"]["all_candidates"][0]["actual_points"] = 85
    assert extract_saved_pool(contaminated, "classic")["reason"] == "postgame_data_in_saved_candidate_pool"


def test_top_field_construction_requires_contest_scoped_identity():
    slots = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]
    names = [f"Player {index}" for index in range(9)]
    lineup = " ".join(f"{slot} {name}" for slot, name in zip(slots, names))
    entries = [{"entry_points": 150, "lineup_text": lineup} for _ in range(5)]
    observations = [{"contest_id": "contest", "resolution_status": "resolved",
                     "player_id": f"p{index}", "player_display_name": name,
                     "roster_position": "WR" if slot == "FLEX" else slot,
                     "actual_ownership": 5}
                    for index, (slot, name) in enumerate(zip(slots, names))]
    salary = [{"player_id": f"p{index}", "roster_position": "WR" if slot == "FLEX" else slot,
               "salary": 5000, "team_id": "A", "opponent_team_id": "B", "game_id": "A-B"}
              for index, slot in enumerate(slots)]
    benchmark = field_benchmarks({"field_size": 5}, entries, [])
    summary = top_field_constructions("contest", entries, observations, salary, benchmark, "classic")
    assert summary["groups"]["top_1_percent"]["field_lineups_including_ties"] == 5
    assert summary["groups"]["top_1_percent"]["canonical_lineups_summarized"] == 5
    assert summary["groups"]["top_1_percent"]["average_salary_left"] == 5000
    observations[0]["contest_id"] = "wrong-contest"
    missing = top_field_constructions("contest", entries, observations, salary, benchmark, "classic")
    assert missing["groups"]["top_1_percent"]["canonical_lineups_summarized"] == 0


def test_entered_field_gaps_use_imported_population_without_payouts():
    report = {"run_ids": {}, "entries": [{"contest_id": "c", "entry_id": "e",
                                            "entry_points": 110}]}
    evidence = {"contests": [{"contest_id": "c", "field_size": 5}],
                "field_entries": [{"contest_id": "c", "entry_points": value}
                                  for value in (150, 140, 130, 120, 110)],
                "payout_tiers": [], "lineup_players": [], "observations": []}
    result = build_optimizer_effectiveness(report, evidence)
    entered = result["entered_field_comparisons"][0]
    assert entered["points_from_winner"] == -40
    assert entered["points_from_top_1_percent"] == -40
    assert entered["points_from_cash"] is None
    assert result["field_benchmarks"]["c"]["cash_line_reason"] == "paid_rank_or_payout_unavailable"


def test_chronological_gate_requires_saved_kickoff_and_predecision_creation():
    pool = {"status": "original_candidate_pool", "candidates": [{
        "games_represented": ["NYJ@DET 09/27/2026 01:00PM ET"]}]}
    eastern = ZoneInfo("America/New_York")
    run = {"data_cutoff_at": datetime(2026, 9, 25, 8, tzinfo=eastern),
           "optimizer_created_at": datetime(2026, 9, 27, 12, tzinfo=eastern)}
    assert chronological_validation(run, pool)["status"] == "predecision"
    run["optimizer_created_at"] = datetime(2026, 9, 27, 14, tzinfo=eastern)
    assert chronological_validation(run, pool)["status"] == "unavailable"


def test_showdown_scenario_variants_keep_exact_pool_and_one_selected_variant():
    roster = [{"player_id": "captain", "slot": "CPT"}] + [
        {"player_id": f"f{i}", "slot": "FLEX"} for i in range(5)]
    variants = [{"rank": 1, "players": roster, "selector": 10, "mean": 50, "p90": 80,
                 "scenario": "baseline"},
                {"rank": 2, "players": roster, "selector": 9, "mean": 48, "p90": 78,
                 "scenario": "decisive"}]
    config = {"strategy_runtime": {"showdown_portfolio_policy": {
        "candidate_selection": {"ranked_metrics": variants, "selected_ranks": [2]}}}}
    pool = extract_saved_pool(config, "showdown")
    assert pool["status"] == "original_candidate_pool"
    assert pool["count"] == 2
    assert pool["unique_roster_count"] == 1
    run = {"optimizer_run_id": "run", "contest_format": "showdown", "strategy": "showdown_gpp_portfolio_v3",
           "constraint_config_json": config}
    selected = [{"signature": candidate_signature(variants[0], "showdown")}]
    actuals = {"captain": 20, **{f"f{i}": 1 for i in range(5)}}
    result = evaluate_run(run, selected, selected, actuals, {})
    assert result["unique_roster_count"] == 1
    assert result["unique_scored_roster_count"] == 1
    assert result["selected_matched_count"] == 1
    assert [row["postgame"]["selected"] for row in result["candidates"]] == [False, True]
    assert [row["postgame"]["entered"] for row in result["candidates"]] == [False, True]


def test_completed_saved_pool_runs_are_audited_separately_from_entered_run():
    candidate = _classic_candidate([f"p{i}" for i in range(9)], 1, 100)
    saved = {"optimizer_run_id": "research-run", "contest_format": "classic",
             "strategy": "classic_small_field_gpp",
             "constraint_config_json": {"strategy_runtime": {"classic_small_field": {
                 "all_candidates": [candidate]}}}}
    unavailable = {"optimizer_run_id": "no-pool", "contest_format": "classic",
                   "strategy": "classic_gpp", "constraint_config_json": {}}
    evidence = {"optimizer_runs": [saved, unavailable], "lineup_players": [],
                "contests": [], "observations": [{"resolution_status": "resolved",
                                                "player_id": f"p{i}", "roster_position": "QB",
                                                "actual_points": 1} for i in range(9)]}
    result = build_optimizer_effectiveness({"run_ids": {}, "entries": []}, evidence)
    assert len(result["runs"]) == 1
    assert result["runs"][0]["run_scope"] == "other_completed_saved_pool"
    assert result["runs"][0]["best_generated_actual"] == 9
    assert result["unavailable_completed_run_ids"] == ["no-pool"]
