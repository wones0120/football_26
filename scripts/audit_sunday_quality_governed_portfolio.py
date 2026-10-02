#!/usr/bin/env python3
"""Prelock-only joint-quality QB and portfolio replay for frozen Sunday Main."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from backend.app.product_services.classic_frontier_diagnostic import (
    add_relative_chalk, candidate_ownership, lineup_key, select_portfolio,
)
from backend.app.product_services.classic_small_field import describe_candidate
from backend.app.product_services.gpp_optimizer import (
    _build_lineup, build_format_specific_terms, build_lineup_correlation_terms,
)
from backend.app.product_services.rule_library import resolve_strategy_profile
from scripts.audit_sunday_main_portfolio_frontier import SHADOWS, load_frozen


RUN_ID = "a6d7f5e7-db0f-44ae-87c4-60a826973408"
SOURCE = Path("artifacts/sunday-main-portfolio-frontier-2026w3.json")
OUTPUT = Path("artifacts/sunday-main-quality-governed-portfolio-2026w3.json")
FLOORS = (5.0, 6.0, 7.0)


def main() -> None:
    frozen = load_frozen(RUN_ID)
    old = json.loads(SOURCE.read_text())
    players, config = frozen["players"], frozen["config"]
    by_id = {player.player_id: player for player in players}
    source = {str(row["player_id"]): row for row in frozen["pool"].to_dict("records")}
    game_totals = sorted({float(player.game_total) for player in players
                          if player.game_total is not None})
    profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
    terms = build_lineup_correlation_terms(players, profile=profile)
    formats = build_format_specific_terms(players, profile=profile)
    global_mean = float(old["discovery"]["global_mean"])
    global_p90 = float(old["discovery"]["global_p90"])
    qbs = [player for player in players if player.position == "QB"]

    def solve(qb, gap):
        indexes = _build_lineup(
            players, config, None, [],
            required_player_ids={qb.player_id},
            enforce_single_te=bool(frozen["params"]["enforce_single_te"]),
            avoid_dst_opponents=bool(frozen["params"]["avoid_dst_opponents"]),
            minimum_mean=global_mean-gap,
            minimum_p90=global_p90-gap,
            precomputed_correlation_terms=terms,
            precomputed_format_terms=formats,
        )
        return [players[index].player_id for index in indexes] if indexes is not None else None

    requests = [(qb, gap) for qb in qbs for gap in FLOORS]
    solved = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(solve, qb, gap): (qb, gap) for qb, gap in requests}
        for index, future in enumerate(as_completed(futures), 1):
            qb, gap = futures[future]
            solved[(qb.player_id, gap)] = future.result()
            if index % 10 == 0 or index == len(futures):
                print(f"joint quality solves {index}/{len(futures)}", flush=True)

    # Minimize the larger of the two quality losses for every QB that misses
    # the five-point joint floor. Saved QB-family candidates give legal uppers.
    closest = {}
    unresolved = [qb for qb in qbs if solved[(qb.player_id, 5.0)] is None]
    bounds = {}
    for qb in unresolved:
        existing = [row for row in old["candidates"]
                    if row["qb"]["player_id"] == qb.player_id]
        upper_row = min(existing, key=lambda row: max(global_mean-row["mean"],
                                                      global_p90-row["p90"]))
        upper = max(global_mean-upper_row["mean"], global_p90-upper_row["p90"])+0.01
        bounds[qb.player_id] = [5.0, upper, upper_row["player_ids"]]
    for iteration in range(10):
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(solve, qb, sum(bounds[qb.player_id][:2])/2): qb
                       for qb in unresolved}
            for future in as_completed(futures):
                qb = futures[future]
                low, high, best_ids = bounds[qb.player_id]
                middle = (low+high)/2
                ids = future.result()
                bounds[qb.player_id] = ([low, middle, ids] if ids is not None
                                        else [middle, high, best_ids])
        print(f"closest joint floor iteration {iteration+1}/10", flush=True)
    for qb in unresolved:
        low, high, ids = bounds[qb.player_id]
        closest[qb.player_id] = {"minimum_joint_gap_upper": high,
                                  "search_precision": high-low,
                                  "player_ids": ids}

    guard_solved = {}
    for metric, gaps in (("mean", (3, 4, 5, 6, 7)), ("p90", (3, 5, 7))):
        for gap in gaps:
            indexes = _build_lineup(
                players, config, None, [],
                enforce_single_te=bool(frozen["params"]["enforce_single_te"]),
                avoid_dst_opponents=bool(frozen["params"]["avoid_dst_opponents"]),
                minimum_mean=global_mean-gap if metric == "mean" else None,
                minimum_p90=global_p90-gap if metric == "p90" else None,
                precomputed_correlation_terms=terms,
                precomputed_format_terms=formats,
            )
            guard_solved[(metric, gap)] = ([players[index].player_id for index in indexes]
                                          if indexes is not None else None)

    rows = {lineup_key(row): dict(row) for row in old["candidates"]}
    for (qb_id, gap), ids in solved.items():
        if ids is None:
            continue
        key = tuple(sorted(ids))
        if key not in rows:
            row = describe_candidate(
                [by_id[player_id] for player_id in ids], all_players=players,
                config=config, pool_by_id=source, ownership_available=False,
                candidate_aware_ownership=True, game_totals=game_totals,
            )
            row["sources"] = []
            rows[key] = row
        rows[key]["sources"].append(f"joint_quality:{qb_id}:{gap:g}")
    for qb_id, attempt in closest.items():
        ids = attempt["player_ids"]
        key = tuple(sorted(ids))
        if key not in rows:
            row = describe_candidate(
                [by_id[player_id] for player_id in ids], all_players=players,
                config=config, pool_by_id=source, ownership_available=False,
                candidate_aware_ownership=True, game_totals=game_totals,
            )
            row["sources"] = []
            rows[key] = row
        rows[key]["sources"].append(f"closest_joint_floor:{qb_id}")
    for (metric, gap), ids in guard_solved.items():
        if ids is None:
            continue
        key = tuple(sorted(ids))
        if key not in rows:
            row = describe_candidate(
                [by_id[player_id] for player_id in ids], all_players=players,
                config=config, pool_by_id=source, ownership_available=False,
                candidate_aware_ownership=True, game_totals=game_totals,
            )
            row["sources"] = []
            rows[key] = row
        rows[key]["sources"].append(f"exact_{metric}_guard:{gap}")

    base_context = {player.player_id: player.optimizer_context_adjustment for player in players}
    from dataclasses import replace
    for name, context_factor, correlation_factor in SHADOWS:
        for player in players:
            player.optimizer_context_adjustment = base_context[player.player_id] * context_factor
        active_config = replace(config, correlation_bonus=config.correlation_bonus*correlation_factor)
        for row in rows.values():
            scored = describe_candidate(
                [by_id[player_id] for player_id in row["player_ids"]],
                all_players=players, config=active_config, pool_by_id=source,
                ownership_available=False, candidate_aware_ownership=True,
                game_totals=game_totals,
            )
            if name == "production":
                row.update(scored)
            row.setdefault("shadow_scores", {})[name] = scored["objective_score"]
            row.setdefault("shadow_components", {})[name] = scored["components"]
        order = sorted(rows.values(), key=lambda row: -row["shadow_scores"][name])
        for rank, row in enumerate(order, 1):
            row.setdefault("shadow_ranks", {})[name] = rank
    for player in players:
        player.optimizer_context_adjustment = base_context[player.player_id]
    candidates = sorted(rows.values(), key=lambda row: -row["shadow_scores"]["production"])
    for row in candidates:
        row["objective_score"] = row["shadow_scores"]["production"]
        row["mean_loss_vs_global"] = global_mean-row["mean"]
        row["p90_loss_vs_global"] = global_p90-row["p90"]
        row["ownership"] = candidate_ownership(row, frozen["ownership"])
    add_relative_chalk(candidates)
    for rank, row in enumerate(candidates, 1):
        row["rank"] = rank
        raw = row["shadow_components"]["production"]
        row["correlation_context_bonus"] = sum(raw.get(key, 0.0) for key in
            ("context", "qb_stack", "bring_back", "game_environment", "correlation"))
    raw_quality_best = max(candidates, key=lambda row:
                           row["shadow_components"]["production"]["mean"]
                           +row["shadow_components"]["production"]["p90"])
    baseline = raw_quality_best["shadow_components"]["production"]
    bonus_keys = ("context", "qb_stack", "bring_back", "game_environment", "correlation")
    for row in candidates:
        component = row["shadow_components"]["production"]
        sacrifice = (baseline["mean"]+baseline["p90"]
                     -component["mean"]-component["p90"])
        gain = sum(component.get(key, 0.0)-baseline.get(key, 0.0)
                   for key in bonus_keys)
        row["raw_objective_quality_sacrifice"] = sacrifice
        row["correlation_context_objective_gain"] = gain
        row["raw_sacrifice_per_bonus_gain"] = sacrifice/gain if gain > 0 else None

    family_report = []
    for qb in qbs:
        qualifying = {str(int(gap)): next((row["rank"] for row in candidates
            if solved[(qb.player_id, gap)] is not None
            and lineup_key(row) == tuple(sorted(solved[(qb.player_id, gap)]))), None)
            for gap in FLOORS}
        best = (next((row for row in candidates if lineup_key(row) ==
                      tuple(sorted(closest[qb.player_id]["player_ids"]))), None)
                if qb.player_id in closest else None)
        family_report.append({"qb_id": qb.player_id, "qb": qb.name, "team": qb.team,
                              "joint_guard_best_rank": qualifying,
                              "qualifies_5": qualifying["5"] is not None,
                              "closest_exact_attempt_rank": best["rank"] if best else None,
                              "closest_minimax_gap": max(best["mean_loss_vs_global"],
                                                        best["p90_loss_vs_global"]) if best else None,
                              "closest_exact_search": closest.get(qb.player_id)})
    portfolios = {}
    for gap in FLOORS:
        eligible = [row for row in candidates
                    if row["mean_loss_vs_global"] <= gap+1e-9
                    and row["p90_loss_vs_global"] <= gap+1e-9]
        branch = {"candidate_count": len(eligible),
                  "qb_count": len({row["qb"]["player_id"] for row in eligible})}
        for count in (3, 4, 5):
            found = select_portfolio(eligible, count, max_overlap=6, max_same_qb=1)
            branch[str(count)] = {"status": found["status"],
                                  "ranks": [eligible[i]["rank"] for i in found["indices"]],
                                  "score_sum": found["score_sum"]}
        portfolios[str(int(gap))] = branch
    guards = {}
    for metric, limits in (("mean", (3, 4, 5, 6, 7)), ("p90", (3, 5, 7))):
        for gap in limits:
            ids = guard_solved[(metric, gap)]
            winner = next((row for row in candidates
                           if ids is not None and lineup_key(row) == tuple(sorted(ids))), None)
            guards[f"{metric}_{gap}"] = winner["rank"] if winner else None
    payload = {
        "source_optimizer_run_id": RUN_ID,
        "source_data_cutoff_at": str(frozen["run"]["data_cutoff_at"]),
        "no_current_game_outcomes_used": True,
        "base_football_weights": vars(config.objective_weights),
        "ownership_old_vs_corrected": {
            "old_slate_coverage": "522/535 => ownership unavailable for every candidate",
            "corrected_complete_candidates": sum(row["ownership"]["status"] == "available"
                                                   for row in candidates),
            "corrected_incomplete_candidates": sum(row["ownership"]["status"] != "available"
                                                     for row in candidates),
            "top20_rank_changed": False,
            "reason": "No optimal-lineup probabilities or soft ownership objective; the frozen partial-coverage profile has no ownership cap. Corrected reporting preserves football score.",
        },
        "candidate_count": len(candidates), "global_mean": global_mean,
        "global_p90": global_p90, "quality_guards": guards,
        "qb_families": family_report, "portfolios": portfolios,
        "candidates": candidates,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, default=str, allow_nan=False)+"\n")
    print(json.dumps({"output": str(OUTPUT), "candidates": len(candidates),
                      "qualifying_qbs_5": sum(row["qualifies_5"] for row in family_report),
                      "portfolios": portfolios}, indent=2), flush=True)


if __name__ == "__main__":
    main()
