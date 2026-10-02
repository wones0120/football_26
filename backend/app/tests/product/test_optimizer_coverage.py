from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from backend.app.product_services.optimizer_coverage import (
    evaluate_selector, lineup_diversity, portfolio_grid, pregame_coverage,
    selector_scores, stack_family, validate_generation_input_snapshot,
)
from backend.app.product_services.optimizer_effectiveness import extract_saved_pool


def _candidate(rank: int, qb: str, ids: list[str], *, mean: float, p90: float,
               objective: float, context: float = 0, correlation: float = 0,
               partners: int = 1, backs: int = 0) -> dict:
    roster = [{"player_id": pid, "name": pid, "team": "A" if pid == qb else "B",
               "position": "QB" if pid == qb else "WR", "ownership": 2} for pid in ids]
    return {"rank": rank, "player_ids": ids, "roster": roster,
            "qb": {"player_id": qb, "name": qb, "team": "A", "ownership": 2},
            "stack": {"partner_count": partners, "bring_back_count": backs},
            "primary_game": "A–B", "game_environment": {"market_safe": True, "game_total": 50,
                                                      "team_total": 27, "team_spread": -4},
            "mean": mean, "p90": p90, "objective_score": objective,
            "components": {"context": context, "correlation": correlation}}


def _pool():
    core = [f"core-{i}" for i in range(7)]
    return [
        _candidate(1, "qb-a", ["qb-a", *core, "a"], mean=100, p90=150,
                   objective=10, context=3, correlation=2),
        _candidate(2, "qb-b", ["qb-b", *core, "b"], mean=110, p90=140,
                   objective=9.9, backs=1),
        _candidate(3, "qb-c", ["qb-c", *[f"other-{i}" for i in range(8)]],
                   mean=90, p90=160, objective=9.8, partners=2),
    ]


def test_frozen_pool_selectors_do_not_mutate_or_use_actuals_for_ranking():
    rows = _pool()
    before = deepcopy(rows)
    scores = selector_scores(rows)
    assert rows == before
    assert scores["A_existing"] == [10, 9.9, 9.8]
    assert scores["B_mean"] == [100, 110, 90]
    assert scores["C_ceiling"] == [150, 140, 160]
    assert scores["E_without_context_correlation"] == [5, 9.9, 9.8]
    actuals = {pid: 1.0 for row in rows for pid in row["player_ids"]}
    actuals["qb-b"] = 20
    assert evaluate_selector(rows, scores["B_mean"], actuals, {})["top5_candidate_ranks"][0] == 2
    actuals["qb-a"] = 1000
    assert selector_scores(rows) == scores
    assert rows == before
    assert extract_saved_pool({"replayed_candidate_pool": rows}, "classic")["status"] == "unavailable"


def test_portfolio_grid_records_infeasibility_overlap_and_distinct_qb_paths():
    rows = _pool()
    actuals = {pid: 1.0 for row in rows for pid in row["player_ids"]}
    grid = portfolio_grid(rows, actuals, count=2, max_exposure=1.0,
                          original_selected_ranks=[1, 2],
                          thresholds={"contest": {"top_20_percent": 9}})
    assert len(grid) == 40
    baseline = next(row for row in grid if row["max_overlap"] is None
                    and not row["distinct_qb_paths"] and row["max_objective_loss"] is None)
    assert baseline["ranks"] == [1, 2]
    assert baseline["average_scoreable_actual"] == 9
    assert baseline["field_attainment_top5"]["contest"]["top_20_percent"]
    constrained = next(row for row in grid if row["max_overlap"] == 5
                       and row["distinct_qb_paths"] and row["max_objective_loss"] is None)
    assert constrained["ranks"] == [1, 3]
    assert constrained["qb_count"] == 2
    assert constrained["overlap_matrix"][0][1] <= 5
    assert next(row for row in grid if row["max_overlap"] == 5
                and row["max_objective_loss"] == .05)["status"] == "infeasible"


def test_pregame_qb_stack_player_and_overlap_reporting():
    rows = _pool()
    players = [{"player_id": pid, "player_name": pid, "included": True,
                "position": "QB" if pid.startswith("qb") else "WR", "team": "A",
                "salary": 5000, "projection": 10, "p90": 20}
               for pid in {pid for row in rows for pid in row["player_ids"]}]
    report = pregame_coverage(rows, [1, 2], players)
    assert stack_family(rows[1]) == "QB+1+1 bring-back"
    assert report["stack_families"]["QB+1+1 bring-back"] == 1
    assert len(report["qb"]) == 3
    assert next(row for row in report["qb"] if row["name"] == "qb-c")["selected_count"] == 0
    assert report["diversity"]["unique_roster_count"] == 3
    assert report["diversity"]["overlap_distribution"][7] == 1
    assert report["diversity"]["shared_at_least"]["7"] == 1 / 3
    assert report["players"]
    assert "actual_points" not in json.dumps(report)
    assert lineup_diversity(rows)["effective_family_count"] == 3


def test_generation_replay_requires_hash_verified_pregame_inputs():
    assert validate_generation_input_snapshot(None)["reason"] == "complete_frozen_generation_inputs_absent"
    payload = {"players": [{"player_id": "p", "team": "A", "opponent": "B", "position": "QB",
                            "salary": 5000, "projection": 20, "ceiling": 30, "ownership": 5}],
               "options": {"candidate_target": 120}}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()
    snapshot = {"contract": "classic_frozen_generation_inputs_v1", "sha256": digest, **payload}
    assert validate_generation_input_snapshot(snapshot)["status"] == "frozen_pregame_inputs"
    snapshot["players"][0]["actual_points"] = 55
    assert validate_generation_input_snapshot(snapshot)["reason"] == "frozen_generation_input_player_invalid"
    del snapshot["players"][0]["actual_points"]
    snapshot["players"][0]["projection"] = 999
    assert validate_generation_input_snapshot(snapshot)["reason"] == "frozen_generation_input_hash_mismatch"
