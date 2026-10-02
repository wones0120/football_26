#!/usr/bin/env python3
"""Complete application-persisted Coker/Flowers outage portfolios."""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from backend.app.product_services.classic_frontier_diagnostic import add_relative_chalk, candidate_ownership
from backend.app.product_services.classic_small_field import describe_candidate
from backend.app.product_services.gpp_optimizer import (
    _build_lineup, build_format_specific_terms, build_lineup_correlation_terms,
)
from backend.app.product_services.rule_library import resolve_strategy_profile
from scripts.audit_sunday_main_portfolio_frontier import load_frozen
from scripts.finalize_sunday_main_portfolio_2026w3 import (
    BONUS_KEYS, COKER, FLOWERS, OUTPUT, SOURCE_RUN, _best_portfolio,
    _persist, _select, _slots,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reselect-only", action="store_true")
    args = parser.parse_args()
    report = json.loads(OUTPUT.read_text())
    frozen = load_frozen(SOURCE_RUN)
    players = [player for player in frozen["players"]
               if player.player_id not in set(report.get("snapshot_out_ids") or [])]
    config = frozen["config"]
    by_id = {p.player_id: p for p in players}
    source = {str(row["player_id"]): row for row in frozen["pool"].to_dict("records")}
    profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
    game_totals = sorted({float(p.game_total) for p in players if p.game_total is not None})
    known = {tuple(sorted(row["player_ids"])) for row in report["candidates"]}
    scenarios = {"coker_out": {COKER}, "both_out": {COKER, FLOWERS}}
    for gap in (() if args.reselect_only else (10.0, 12.0, 15.0)):
        requests = [(name, excluded, p.player_id) for name, excluded in scenarios.items()
                    for p in players if p.position == "QB"]

        def solve(request):
            name, excluded, qb_id = request
            active = [p for p in players if p.player_id not in excluded]
            indexes = _build_lineup(
                active, config, None, [], required_player_ids={qb_id},
                enforce_single_te=True, avoid_dst_opponents=True,
                minimum_mean=report["global_mean"]-gap,
                minimum_p90=report["global_p90"]-gap,
                precomputed_correlation_terms=build_lineup_correlation_terms(active, profile=profile),
                precomputed_format_terms=build_format_specific_terms(active, profile=profile),
            )
            return name, qb_id, ([active[i].player_id for i in indexes]
                                 if indexes is not None else None)

        with ThreadPoolExecutor(max_workers=4) as executor:
            for future in as_completed([executor.submit(solve, request) for request in requests]):
                name, qb_id, ids = future.result()
                if ids is None:
                    continue
                key = tuple(sorted(ids))
                if key in known:
                    continue
                row = describe_candidate([by_id[pid] for pid in ids], all_players=players,
                                         config=config, pool_by_id=source,
                                         ownership_available=False,
                                         candidate_aware_ownership=True,
                                         game_totals=game_totals)
                row["sources"] = [f"exact_{name}_guard_{gap:g}_qb_{qb_id}"]
                row["mean_loss"] = report["global_mean"]-row["mean"]
                row["p90_loss"] = report["global_p90"]-row["p90"]
                row["ownership"] = candidate_ownership(row, frozen["ownership"])
                row["correlation_context_gain"] = sum(row["components"].get(k, 0.0)
                                                      for k in BONUS_KEYS)
                report["candidates"].append(row)
                known.add(key)
        report["candidates"].sort(key=lambda row: -row["objective_score"])
        add_relative_chalk(report["candidates"])
        for rank, row in enumerate(report["candidates"], 1):
            row["rank"] = rank
        print(f"guard {gap:g}: {len(report['candidates'])} candidates", flush=True)
        for name, excluded in scenarios.items():
            if report["scenarios"][name]["status"] == "optimal":
                continue
            eligible = [row for row in report["candidates"]
                        if row["mean_loss"] <= gap+1e-8 and row["p90_loss"] <= gap+1e-8]
            selected = _best_portfolio(eligible, exclude=excluded)
            print(name, selected["status"], selected.get("score_sum"), flush=True)
            if selected["status"] != "optimal":
                continue
            summary = {key: value for key, value in selected.items() if key != "rows"}
            summary["quality_guard_used"] = gap
            summary["lineups"] = []
            for row in selected["rows"]:
                roster = _slots(row["player_ids"], by_id, source)
                control = max((other for other in eligible
                               if other["qb"]["player_id"] == row["qb"]["player_id"]),
                              key=lambda other: other["mean"]+other["p90"])
                summary["lineups"].append({
                    "rank": row["rank"], "roster": roster, "salary": row["salary"],
                    "mean": row["mean"], "p90": row["p90"],
                    "selector": row["objective_score"], "ownership": row["ownership"],
                    "qb": row["qb"], "primary_game": row.get("primary_game"),
                    "stack": row["stack"], "mean_loss": row["mean_loss"],
                    "p90_loss": row["p90_loss"], "sources": row["sources"],
                    "strongest_same_qb_raw_control": {
                        "rank": control["rank"], "mean": control["mean"],
                        "p90": control["p90"],
                        "mean_sacrifice": control["mean"]-row["mean"],
                        "p90_sacrifice": control["p90"]-row["p90"],
                        "correlation_context_gain": row["correlation_context_gain"]-
                                                    control["correlation_context_gain"],
                    },
                })
            report["candidate_count"] = len(report["candidates"])
            summary["optimizer_run_id"] = _persist(name, selected, frozen, by_id, source,
                                                    report, excluded, guard=gap)
            report["scenarios"][name] = summary
            OUTPUT.write_text(json.dumps(report, indent=2, default=str, allow_nan=False)+"\n")
        if all(report["scenarios"][name]["status"] == "optimal" for name in scenarios):
            break
    # Select the smallest attainable joint allowance. A universal core may be
    # preferable to a much larger mean/P90 sacrifice in an outage scenario.
    thresholds = sorted({max(row["mean_loss"], row["p90_loss"])
                         for row in report["candidates"]
                         if max(row["mean_loss"], row["p90_loss"]) >= report["guard"]})
    for name, excluded in scenarios.items():
        best = None
        for cap in (4, 5):
            low, high = 0, len(thresholds)-1
            while low <= high:
                middle = (low+high)//2
                threshold = thresholds[middle]
                eligible = [row for row in report["candidates"]
                            if row["mean_loss"] <= threshold+1e-8
                            and row["p90_loss"] <= threshold+1e-8]
                candidate = _select(eligible, exclude=excluded, exposure_limit=cap,
                                    distinct_qbs=5)
                if candidate["status"] == "optimal":
                    if best is None or threshold < best[0]-1e-8 or (
                            abs(threshold-best[0]) <= 1e-8 and cap < best[1]):
                        best = (threshold, cap, candidate)
                    high = middle-1
                else:
                    low = middle+1
        if best is None:
            continue
        gap, cap, selected = best
        if abs(report["scenarios"][name].get("quality_guard_used", 999)-gap) <= 1e-8:
            continue
        summary = {key: value for key, value in selected.items() if key != "rows"}
        summary["quality_guard_used"] = gap
        summary["lineups"] = []
        for row in selected["rows"]:
            roster = _slots(row["player_ids"], by_id, source)
            control = max((other for other in report["candidates"]
                           if other["qb"]["player_id"] == row["qb"]["player_id"]
                           and other["mean_loss"] <= gap+1e-8
                           and other["p90_loss"] <= gap+1e-8),
                          key=lambda other: other["mean"]+other["p90"])
            summary["lineups"].append({
                "rank": row["rank"], "roster": roster, "salary": row["salary"],
                "mean": row["mean"], "p90": row["p90"], "selector": row["objective_score"],
                "ownership": row["ownership"], "qb": row["qb"],
                "primary_game": row.get("primary_game"), "stack": row["stack"],
                "mean_loss": row["mean_loss"], "p90_loss": row["p90_loss"],
                "sources": row["sources"],
                "strongest_same_qb_raw_control": {
                    "rank": control["rank"], "mean": control["mean"], "p90": control["p90"],
                    "mean_sacrifice": control["mean"]-row["mean"],
                    "p90_sacrifice": control["p90"]-row["p90"],
                    "correlation_context_gain": row["correlation_context_gain"]-
                                                control["correlation_context_gain"],
                },
            })
        summary["optimizer_run_id"] = _persist(name, selected, frozen, by_id, source,
                                                report, excluded, guard=gap)
        report["scenarios"][name] = summary
        print(name, "minimum candidate-universe guard", round(gap, 6),
              "cap", cap, "run", summary["optimizer_run_id"], flush=True)
    # Keep the actual active-role decision as the newest visible optimizer run.
    active_summary = report["scenarios"]["active"]
    by_key = {tuple(sorted(row["player_ids"])): row for row in report["candidates"]}
    active_rows = [by_key[tuple(sorted(player["player_id"] for player in lineup["roster"]))]
                   for lineup in active_summary["lineups"]]
    active_selection = {"status": "optimal", "rows": active_rows,
                        "exposure_limit": active_summary["exposure_limit"],
                        "distinct_qbs": active_summary["distinct_qbs"]}
    active_summary["optimizer_run_id"] = _persist(
        "active_final", active_selection, frozen, by_id, source, report, set(),
        guard=report["guard"],
    )
    print("active_final", active_summary["optimizer_run_id"], flush=True)
    OUTPUT.write_text(json.dumps(report, indent=2, default=str, allow_nan=False)+"\n")


if __name__ == "__main__":
    main()
