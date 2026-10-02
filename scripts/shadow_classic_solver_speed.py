#!/usr/bin/env python3
"""Compare native parallel Classic discovery against a pinned saved run."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

from sqlalchemy import create_engine, text

from backend.app.product_services.classic_small_field import (
    analyze_small_field, expand_candidate_discovery,
)
from backend.app.product_services.gpp_optimizer import generate_portfolio, tag_players
from backend.app.product_services.optimizer import OptimizerService
from scripts.benchmark_classic_solver_performance import _load_frozen


def signature(lineup) -> tuple[str, ...]:
    return tuple(sorted(player.player_id for player in lineup))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--solver", choices=("bundled", "native"), default="native")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--reuse-saved-sequential", action="store_true")
    args = parser.parse_args()

    players, config, _, saved, pool = _load_frozen(args.run_id)
    with OptimizerService().engine.connect() as connection:
        season, week, slate_id = connection.execute(text(
            "SELECT season, week, slate_id FROM target.optimizer_run "
            "WHERE optimizer_run_id = :run_id"
        ), {"run_id": args.run_id}).one()
    baseline = saved["strategy_runtime"]["classic_small_field"]
    expected = {tuple(sorted(row["player_ids"])) for row in baseline["all_candidates"]}
    expected_sequential = {
        tuple(sorted(row["player_ids"])) for row in baseline["all_candidates"]
        if "sequential" in row["discovery_sources"]
    }
    starting_qb_ids = {
        str(row["player_id"]) for row in pool.to_dict("records")
        if row.get("position") == "QB" and row.get("is_starting_qb") in (True, 1)
    }
    if args.reuse_saved_sequential:
        by_id = {player.player_id: player for player in players}
        result = SimpleNamespace(
            config=config,
            lineups=[[by_id[player_id] for player_id in row["player_ids"]]
                     for row in baseline["all_candidates"]
                     if "sequential" in row["discovery_sources"]],
        )
        sequential_seconds = 0.0
    else:
        started = perf_counter()
        result = generate_portfolio(
            season, week, slate_id,
            baseline["requested_candidate_count"],
            engine=create_engine("sqlite://"),
            config_builder=lambda _: deepcopy(config), players=players,
            ownership_available=False, max_exposure=1.0,
            enforce_single_te=bool(saved.get("enforce_single_te", False)),
            avoid_dst_opponents=bool(saved.get("avoid_dst_opponents", False)),
            include_control_comparisons=False, candidate_aware_ownership=True,
            solver_backend=args.solver,
            precompute_correlation_terms=True,
        )
        sequential_seconds = perf_counter() - started
    sequential = {signature(lineup) for lineup in result.lineups}
    print(f"Sequential: {len(sequential)} candidates in {sequential_seconds:.2f}s", flush=True)

    tag_players(players, result.config.tag_thresholds)
    started = perf_counter()
    result.lineups, discovery = expand_candidate_discovery(
        result, players,
        enforce_single_te=bool(saved.get("enforce_single_te", False)),
        avoid_dst_opponents=bool(saved.get("avoid_dst_opponents", False)),
        starting_qb_ids=starting_qb_ids,
        max_workers=args.workers, solver_backend=args.solver,
    )
    discovery_seconds = perf_counter() - started
    actual = {signature(lineup) for lineup in result.lineups}
    print(f"Discovery: {len(actual)} candidates in {discovery_seconds:.2f}s", flush=True)

    started = perf_counter()
    rows = pool.to_dict("records")
    source = {str(row["player_id"]): row for row in rows}
    selected, report = analyze_small_field(
        result,
        pool_rows=[{**source[player.player_id], "gpp_player": player}
                   for player in players],
        count=int(saved.get("num_lineups") or 1),
        max_exposure=float(saved.get("max_exposure") or 1),
        ownership_available=False,
        requested_candidate_count=baseline["requested_candidate_count"],
        candidate_aware_ownership=True,
        discovery_diagnostics=discovery,
        enforce_single_te=bool(saved.get("enforce_single_te", False)),
        avoid_dst_opponents=bool(saved.get("avoid_dst_opponents", False)),
        solver_backend=args.solver,
    )
    selection_seconds = perf_counter() - started
    expected_winner = tuple(sorted(baseline["all_candidates"][baseline["selected_ranks"][0] - 1]["player_ids"]))
    actual_winner = signature(selected[0]) if selected else None
    output = {
        "source_run_id": args.run_id,
        "reused_saved_sequential": args.reuse_saved_sequential,
        "solver_backend": args.solver,
        "workers": args.workers,
        "sequential_seconds": sequential_seconds,
        "discovery_seconds": discovery_seconds,
        "selection_and_reporting_seconds": selection_seconds,
        "sequential_count": len(sequential),
        "sequential_matches_saved": sequential == expected_sequential,
        "sequential_only_in_saved": [list(value) for value in sorted(expected_sequential - sequential)],
        "sequential_only_in_shadow": [list(value) for value in sorted(sequential - expected_sequential)],
        "candidate_count": len(actual),
        "candidates_match_saved": actual == expected,
        "only_in_saved": [list(value) for value in sorted(expected - actual)],
        "only_in_shadow": [list(value) for value in sorted(actual - expected)],
        "winner_matches_saved": actual_winner == expected_winner,
        "winner_saved": list(expected_winner),
        "winner_shadow": list(actual_winner) if actual_winner else None,
        "selected_ranks": report["selected_ranks"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({key: value for key, value in output.items()
                      if key not in {"only_in_saved", "only_in_shadow",
                                     "sequential_only_in_saved", "sequential_only_in_shadow"}}, indent=2), flush=True)


if __name__ == "__main__":
    main()
