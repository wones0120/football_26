"""Prospective thesis grouping, quality frontier, and joint selection contracts."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

import pytest

from backend.app.product_services.classic_prospective import digest_payload
from backend.app.product_services.classic_thesis_shadow import (
    _candidate_view, _dominance, _family_metrics, _overlap_summary,
    _solve_portfolio, canonical_game, analyze_saved_candidates,
    forced_candidate_swap_feasible,
)


def _candidate(rank: int, qb_id: str, qb_name: str, qb_team: str, opponent: str,
               roster: list[str], score: float, *, game_id: str = "JAX@CIN 10/04/2026",
               partners: int = 2, bringbacks: int = 1) -> tuple[dict, dict]:
    candidate = {
        "rank": rank, "player_ids": roster, "qb": {"player_id": qb_id,
            "name": qb_name, "team": qb_team}, "stack": {"partner_count": partners,
            "bring_back_count": bringbacks, "bring_backs": [{"position": "WR"}] if bringbacks else []},
        "game_environment": {"market_safe": True, "label": "high-total competitive",
            "game_total": 51.5, "team_spread": 2.5},
        "objective_score": score, "mean": 130 + score, "p90": 220 + score,
        "salary": 49900, "ownership_sum": 65,
        "roster": [{"player_id": pid, "name": pid, "position": "QB" if pid == qb_id else "WR",
                    "team": qb_team, "salary": 5000} for pid in roster],
        "components": {"context": 0.1, "correlation": 0.2},
        "component_statuses": {"context": {"status": "ACTIVE"}},
    }
    source = {"player_id": qb_id, "game_id": game_id, "opponent_team": opponent,
              "market_source_system": "nflverse_schedules", "market_observed_at": "2026-09-29T21:00:00Z"}
    return candidate, source


def test_canonical_games_ignore_qb_direction_and_preserve_away_home() -> None:
    lawrence = canonical_game("JAX@CIN 10/04/2026", "JAX", "CIN")
    burrow = canonical_game("JAX@CIN 10/04/2026", "CIN", "JAX")
    mahomes = canonical_game("KC@LV 10/04/2026", "KC", "LV")
    cousins = canonical_game("KC@LV 10/04/2026", "LV", "KC")
    assert lawrence == burrow == {"key": "CIN|JAX", "display": "JAX@CIN"}
    assert mahomes == cousins == {"key": "KC|LV", "display": "KC@LV"}
    assert canonical_game("CIN-JAX", "JAX", "CIN")["key"] == lawrence["key"]


def test_thesis_membership_uses_direction_and_stack_not_one_offs() -> None:
    a, source_a = _candidate(1, "lawrence", "Lawrence", "JAX", "CIN",
                             ["lawrence", "a", "b", "c", "d", "e", "f", "g", "h"], 5.6)
    b, _ = _candidate(2, "lawrence", "Lawrence", "JAX", "CIN",
                      ["lawrence", "a", "b", "c", "d", "i", "j", "k", "l"], 5.58)
    opposite, source_b = _candidate(3, "burrow", "Burrow", "CIN", "JAX",
                                    ["burrow", "a", "b", "c", "d", "m", "n", "o", "p"], 5.5)
    pool = {"lawrence": source_a, "burrow": source_b}
    first = _candidate_view(a, pool, {})
    second = _candidate_view(b, pool, {})
    reverse = _candidate_view(opposite, pool, {})
    assert first["thesis_id"] == second["thesis_id"]
    assert first["thesis_id"] != reverse["thesis_id"]
    assert first["game_key"] == reverse["game_key"]
    assert first["market_archetype"] == "high-total competitive"
    no_market = deepcopy(a)
    no_market["game_environment"]["market_safe"] = False
    assert _candidate_view(no_market, pool, {})["market_archetype"] is None


def test_depth_and_strict_dominance_are_deterministic() -> None:
    rows = [{"thesis_id": "A", "game_key": "CIN|JAX", "game": "JAX@CIN",
             "qb_id": "q", "qb": "Q", "qb_team": "JAX", "stack_family": "QB+2",
             "bring_back_count": 1, "bring_back_roles": ["WR"], "bring_back_player_ids": [],
             "market_archetype": None, "market_evidence": None, "partner_count": 2,
             "active_components": [], "components": {}, "questionable_ids": [], "elevated_ids": [],
             "availability_evidence_gap_ids": [], "fragile_cheap_ids": [],
             "ownership_complete": True, "rank": rank, "selector": score,
             "mean": 130 - rank, "p90": 230 - rank}
            for rank, score in enumerate((5.60, 5.58, 5.49, 5.39, 5.20), 1)]
    first = _family_metrics(rows, rows, 5.60)
    second = _family_metrics(list(reversed(rows)), rows, 5.60)
    assert first == second
    assert first["depth"]["within_0.05"] == 2
    assert first["depth"]["within_0.15"] == 3
    assert first["depth"]["selector_drop_to_3"] == pytest.approx(0.11)
    assert first["depth"]["ranks"] == {"1": 1, "2": 2, "3": 3, "5": 5}
    weaker = deepcopy(first)
    weaker["thesis_id"] = "B"
    weaker["peak_selector"] -= 0.1
    weaker["peak_mean"] -= 1
    weaker["peak_p90"] -= 1
    weaker["depth"]["within_0.10"] = 1
    weaker["risk"]["best_elevated_dependencies"] = 1
    _dominance([first, weaker])
    assert first["pareto_status"] == "frontier"
    assert weaker["dominated_by"] == ["A"]


def test_joint_selection_replaces_overlapping_peak_and_does_not_allocate_equally() -> None:
    common = ["c1", "c2", "c3", "c4"]
    rows = [
        {"rank": 1, "player_ids": common + ["a1", "a2", "a3", "a4", "a5"],
         "thesis_id": "A", "game_key": "G1", "selector": 5.60, "elevated_ids": []},
        {"rank": 2, "player_ids": common + ["b1", "b2", "b3", "b4", "b5"],
         "thesis_id": "B", "game_key": "G2", "selector": 5.55, "elevated_ids": []},
        {"rank": 3, "player_ids": common[:2] + ["a1", "a2", "z1", "z2", "z3", "z4", "z5"],
         "thesis_id": "A", "game_key": "G1", "selector": 5.585, "elevated_ids": []},
        {"rank": 4, "player_ids": common[:2] + ["a3", "z6", "z7", "z8", "z9", "z10", "z11"],
         "thesis_id": "A", "game_key": "G1", "selector": 5.57, "elevated_ids": []},
    ]
    # A's rank 1 and B's rank 2 overlap only in the four-player common core here;
    # add three shared one-offs to make the pair illegal at overlap six.
    rows[1]["player_ids"] = common + ["a1", "a2", "a3", "b4", "b5"]
    families = {key: {"pareto_status": "frontier"} for key in ("A", "B")}
    chosen, status = _solve_portfolio(rows, families, 2, {}, 0.6, 6)
    assert status == "optimal"
    assert {row["rank"] for row in chosen} == {2, 3}
    chosen_three, status_three = _solve_portfolio(rows, families, 3, {}, 0.6, 6)
    assert status_three == "optimal"
    assert {row["thesis_id"] for row in chosen_three} == {"A", "B"}
    assert sorted({key: sum(row["thesis_id"] == key for row in chosen_three)
                   for key in ("A", "B")}.values()) == [1, 2]
    assert _overlap_summary(chosen_three)["within_pairs"] == 1
    assert _overlap_summary(chosen_three)["across_pairs"] == 2


def test_dynamic_portfolio_sizes_and_deterministic_allocation() -> None:
    rows = [{"rank": index + 1, "player_ids": [f"p{index}_{slot}" for slot in range(9)],
             "thesis_id": f"T{index % 4}", "game_key": f"G{index % 3}",
             "selector": 6 - index * 0.001, "elevated_ids": []}
            for index in range(20)]
    families = {f"T{index}": {"pareto_status": "frontier"} for index in range(4)}
    for size in (1, 3, 5, 10, 20):
        chosen, status = _solve_portfolio(rows, families, size, {}, 0.6, 6)
        repeated, repeated_status = _solve_portfolio(rows, families, size, {}, 0.6, 6)
        assert status == repeated_status == "optimal"
        assert len(chosen) == size
        assert [row["rank"] for row in chosen] == [row["rank"] for row in repeated]
    five, _ = _solve_portfolio(rows, families, 5, {}, 0.6, 6)
    allocation = sorted(Counter(row["thesis_id"] for row in five).values())
    assert allocation == [1, 1, 1, 2]


def test_forced_candidate_admission_distinguishes_caps_from_search_omission() -> None:
    candidates = [{"player_ids": ["core", "a"]}, {"player_ids": ["b", "c"]}]
    assert forced_candidate_swap_feasible({"core", "new"}, candidates,
                                          {"core": 0.5, "new": 0.5})
    assert not forced_candidate_swap_feasible({"core", "new"}, candidates,
                                              {"core": 0.5, "new": 0.0})


def test_shadow_enforces_saved_qb_cap_and_multiple_qb_paths() -> None:
    rows = [{"rank": index + 1, "player_ids": [f"qb{index % 2}"] +
             [f"p{index}_{slot}" for slot in range(8)],
             "qb_id": f"qb{index % 2}", "thesis_id": f"T{index % 2}",
             "game_key": f"G{index % 2}", "selector": 6 - index * 0.01,
             "elevated_ids": []} for index in range(8)]
    families = {"T0": {"pareto_status": "frontier"},
                "T1": {"pareto_status": "frontier"}}
    chosen, status = _solve_portfolio(rows, families, 5,
                                      {"qb0": 0.6, "qb1": 0.6}, 0.6, 6)
    assert status == "optimal"
    assert sorted(Counter(row["qb_id"] for row in chosen).values()) == [2, 3]


def test_weak_fallback_thesis_is_not_rewarded_for_diversity_alone() -> None:
    rows = [
        {"rank": 1, "player_ids": [f"a{i}" for i in range(9)],
         "thesis_id": "strong", "game_key": "G1", "selector": 6.0, "elevated_ids": []},
        {"rank": 2, "player_ids": [f"b{i}" for i in range(9)],
         "thesis_id": "strong", "game_key": "G1", "selector": 5.99, "elevated_ids": []},
        {"rank": 3, "player_ids": [f"c{i}" for i in range(9)],
         "thesis_id": "weak", "game_key": "G2", "selector": 5.8, "elevated_ids": []},
    ]
    families = {"strong": {"pareto_status": "frontier", "global_selector_gap": 0.0},
                "weak": {"pareto_status": "frontier", "global_selector_gap": 0.25}}
    chosen, status = _solve_portfolio(rows, families, 2, {}, 0.6, 6)
    assert status == "optimal"
    assert {row["rank"] for row in chosen} == {1, 2}


def test_week4_frozen_fixture_has_complete_pregame_shadows() -> None:
    artifact = Path(__file__).resolve().parents[4] / "artifacts/week4-dynamic-thesis-shadow-8b5c114c.json"
    shadow = json.loads(artifact.read_text())
    assert shadow["contract"] == "classic_dynamic_thesis_shadow_v3"
    assert shadow["sha256"] == digest_payload({key: value for key, value in shadow.items()
                                                if key != "sha256"})
    assert shadow["source"]["optimizer_run_id"] == "8b5c114c-b0d2-419e-8f41-bdcbc2674c71"
    assert len(shadow["candidate_universe"]) == 205
    assert sorted(rank for family in shadow["families"] for rank in family["member_ranks"]) == list(range(1, 206))
    assert set(shadow["shadow_portfolios"]) == {"1", "3", "5", "10", "20"}
    assert all(portfolio["status"] == "optimal" and portfolio["entries"] == int(size)
               for size, portfolio in shadow["shadow_portfolios"].items())
    for size, portfolio in shadow["shadow_portfolios"].items():
        if int(size) > 1:
            assert len(portfolio["directional_qb_exposure"]) >= 2
            assert max(portfolio["directional_qb_exposure"].values()) <= int(int(size) * 0.6)
            for pid, appearances in portfolio["player_exposure"].items():
                cap = shadow["selection_caps"]["player_caps"][pid]
                assert appearances <= max(1, int(int(size) * cap))
    assert shadow["viability"]["0.20"]["qualified_count"] == 4
    assert shadow["viability"]["0.20"]["frontier_count"] == 2
    assert shadow["production_five"]["selected_ranks"] == [31, 48, 83, 90, 93]
    assert {"Jaxon Smith-Njigba", "Justin Jefferson", "Lamar Jackson", "Bucky Irving",
            "Brock Bowers"} <= {row["player"] for row in shadow["zero_candidate_diagnostics"]}
    assert shadow["postgame_contract"]["status"] == "pending_actuals"
    assert not any("actual_points" in candidate for candidate in shadow["candidate_universe"])


def test_postgame_fields_in_frozen_solver_snapshot_are_rejected() -> None:
    payload = {"metadata": {"optimizer_run_id": "run", "decision_cutoff_at": "2026-09-30T10:00:00Z"},
               "players": [{}], "eligible_player_ids": ["p"],
               "pool_rows": [{"player_id": "p", "actual_points": 20}],
               "source_pool_rows": []}
    snapshot = {"contract": "classic_solver_snapshot_v2", "payload": payload,
                "sha256": digest_payload(payload)}
    with pytest.raises(ValueError, match="Postgame field"):
        analyze_saved_candidates(optimizer_run_id="run", run_created_at="2026-09-30T10:00:00Z",
                                 snapshot=snapshot, candidates=[], selected_ranks=[], risk_rows=[],
                                 max_exposure=0.8, risk_policy={},
                                 first_kickoff_at="2026-10-04T13:00:00-04:00")


def test_postdecision_market_in_frozen_snapshot_is_rejected() -> None:
    payload = {"metadata": {"optimizer_run_id": "run", "decision_cutoff_at": "2026-09-30T10:00:00Z"},
               "players": [{}], "eligible_player_ids": ["p"],
               "pool_rows": [{"player_id": "p", "market_source_system": "example",
                              "market_observed_at": "2026-09-30T10:01:00Z"}],
               "source_pool_rows": []}
    snapshot = {"contract": "classic_solver_snapshot_v2", "payload": payload,
                "sha256": digest_payload(payload)}
    with pytest.raises(ValueError, match="post-decision"):
        analyze_saved_candidates(optimizer_run_id="run", run_created_at="2026-09-30T10:00:00Z",
                                 snapshot=snapshot, candidates=[], selected_ranks=[], risk_rows=[],
                                 max_exposure=0.8, risk_policy={},
                                 first_kickoff_at="2026-10-04T13:00:00-04:00")
