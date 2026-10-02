#!/usr/bin/env python3
"""Read-only expanded-candidate and portfolio audit from one frozen Classic run."""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.app.db import engine
from backend.app.product_dependencies import get_optimizer_service
from backend.app.product_services.classic_frontier_diagnostic import (
    add_relative_chalk, candidate_ownership, lineup_key, select_portfolio,
)
from backend.app.product_services.classic_small_field import describe_candidate
from backend.app.product_services.gpp_optimizer import (
    LineupTagCaps, ObjectiveWeights, PortfolioTargets, SlateConfig, StackRules,
    TagThresholds, _build_lineup, build_format_specific_terms,
    build_lineup_correlation_terms, tag_players,
)
from backend.app.product_services.rule_library import resolve_strategy_profile


FAMILIES = ((1, 0), (2, 0), (1, 1), (2, 1))
SHADOWS = (("production", 1.0, 1.0), ("context50", .5, 1.0),
           ("correlation50", 1.0, .5), ("both50", .5, .5),
           ("both0", 0.0, 0.0))


def configuration(raw: dict) -> SlateConfig:
    return SlateConfig(
        stack_rules=StackRules(**raw["stack_rules"]),
        tag_thresholds=TagThresholds(**raw["tag_thresholds"]),
        objective_weights=ObjectiveWeights(**raw["objective_weights"]),
        tag_caps=LineupTagCaps(**raw["tag_caps"]),
        salary_cap=raw["salary_cap"], roster_size=raw["roster_size"],
        portfolio_targets=PortfolioTargets(**raw["portfolio_targets"]),
        correlation_bonus=raw["correlation_bonus"],
        uniqueness_overlap=raw["uniqueness_overlap"],
        normalize_objective=raw["normalize_objective"],
        stack_templates=raw["stack_templates"],
    )


def load_frozen(run_id: str) -> dict[str, Any]:
    with engine.connect() as connection:
        run = dict(connection.execute(text(
            "SELECT * FROM target.optimizer_run WHERE optimizer_run_id=:run_id"
        ), {"run_id": run_id}).mappings().one())
        params = run["constraint_config_json"]
        ownership = {str(row["player_id"]): float(row["projected_ownership"])
                     for row in connection.execute(text(
                         "SELECT player_id, projected_ownership FROM target.ownership_projection "
                         "WHERE ownership_run_id=:ownership_run_id"
                     ), {"ownership_run_id": params["ownership_run_id"]}).mappings()}
    runtime = params["strategy_runtime"]
    saved = {str(row["player_id"]): row for row in runtime["player_pool"]["rows"]}
    service = get_optimizer_service()
    pool = service._load_player_pool(  # noqa: SLF001 — diagnostic replay
        int(run["season"]), int(run["week"]), str(run["slate_id"]),
        projection_run_id=str(run["projection_run_id"]),
        ownership_run_id=str(params["ownership_run_id"]),
    )
    if set(pool.player_id.astype(str)) != set(saved):
        raise ValueError("Frozen player IDs differ from replayed projection pool")
    pool = pool[pool.player_id.astype(str).map(lambda player_id: saved[player_id]["included"])].copy()
    for field in ("salary", "projection", "p90"):
        mismatches = sum(abs(float(row[field]) - float(saved[str(row["player_id"])][field])) > 1e-8
                         for row in pool.to_dict("records"))
        if mismatches:
            raise ValueError(f"Frozen {field} differs for {mismatches} players")
    for live_field, saved_field in (("position", "position"),
                                    ("player_team", "team"),
                                    ("opponent_team", "opponent_team")):
        mismatches = sum(str(row[live_field]).upper() != str(saved[str(row["player_id"])][saved_field]).upper()
                         for row in pool.to_dict("records"))
        if mismatches:
            raise ValueError(f"Frozen {live_field} differs for {mismatches} players")
    pool["optimizer_context_adjustment"] = pool.player_id.astype(str).map(
        lambda player_id: saved[player_id]["optimizer_context_adjustment"]
    )
    players = service._gpp_players_from_pool(pool)  # noqa: SLF001 — diagnostic replay
    config = configuration(runtime["config"])
    tag_players(players, config.tag_thresholds)
    return {"run": run, "params": params, "runtime": runtime, "pool": pool,
            "players": players, "config": config, "ownership": ownership,
            "saved": saved}


def discover(frozen: dict[str, Any], workers: int) -> dict[str, Any]:
    players, config = frozen["players"], frozen["config"]
    source = {str(row["player_id"]): row for row in frozen["pool"].to_dict("records")}
    game_totals = sorted({float(player.game_total) for player in players
                          if player.game_total is not None})
    profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
    terms = build_lineup_correlation_terms(players, profile=profile)
    formats = build_format_specific_terms(players, profile=profile)
    by_id = {player.player_id: player for player in players}
    old = frozen["runtime"]["classic_small_field"]["all_candidates"]
    for saved_row in old:
        replayed = describe_candidate(
            [by_id[player_id] for player_id in saved_row["player_ids"]],
            all_players=players, config=config, pool_by_id=source,
            ownership_available=False, game_totals=game_totals,
        )
        if abs(replayed["objective_score"] - saved_row["objective_score"]) > 1e-9:
            raise ValueError("Saved candidate objective did not replay exactly")
    old_keys = {lineup_key(row) for row in old}
    universe = {lineup_key(row): {**row, "sources": ["saved_sequential_120"]} for row in old}
    requests: list[tuple[str, str | None, tuple[int, int] | None, str | None]] = [
        ("global_highest_mean", None, None, "mean"),
        ("global_highest_p90", None, None, "p90"),
        ("global_highest_production_selector", None, None, None),
    ]
    # Eligibility is saved by the source run; current QB evidence may have moved.
    starters = [player for player in players if player.position == "QB"]
    for qb in starters:
        requests.append((f"qb_family:{qb.name}", qb.player_id, None, None))
        for family in FAMILIES:
            label = f"qb_construction:{qb.name}:QB+{family[0]}"
            if family[1]:
                label += "+bring-back"
            requests.append((label, qb.player_id, family, None))

    def solve(request: tuple[str, str | None, tuple[int, int] | None, str | None]):
        label, qb_id, family, quality = request
        active_config = config
        active_players = players
        if quality:
            weights = ObjectiveWeights(projection=float(quality == "mean"),
                                       ceiling=float(quality == "p90"),
                                       leverage=0.0, correlation=0.0)
            active_config = replace(config, objective_weights=weights, correlation_bonus=0.0)
            active_players = [replace(player, optimizer_context_adjustment=0.0)
                              for player in players]
        rules = (replace(config.stack_rules, min_pass_catchers=family[0],
                         min_bring_backs=family[1]) if family else None)
        indexes = _build_lineup(
            active_players, active_config, None, [],
            enforce_single_te=bool(frozen["params"]["enforce_single_te"]),
            avoid_dst_opponents=bool(frozen["params"]["avoid_dst_opponents"]),
            stack_rules=rules, required_player_ids={qb_id} if qb_id else None,
            exact_pass_catchers=family[0] if family else None,
            exact_bring_backs=family[1] if family else None,
            precomputed_correlation_terms=terms,
            precomputed_format_terms=formats,
        )
        return label, ([players[i].player_id for i in indexes] if indexes is not None else None)

    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(solve, request) for request in requests]
        for index, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)
            if index % 10 == 0 or index == len(requests):
                print(f"discovery {index}/{len(requests)}", flush=True)
    injected = []
    for label, ids in sorted(results):
        if ids is None:
            injected.append({"source": label, "status": "infeasible"})
            continue
        key = tuple(sorted(ids))
        if key not in universe:
            lineup = [by_id[player_id] for player_id in ids]
            row = describe_candidate(lineup, all_players=players, config=config,
                                     pool_by_id=source, ownership_available=False,
                                     game_totals=game_totals)
            universe[key] = {**row, "sources": []}
        universe[key]["sources"].append(label)
        injected.append({"source": label, "status": "legal",
                         "player_ids": list(key), "absent_from_old_120": key not in old_keys})
    rows = sorted(universe.values(), key=lambda row: (-float(row["objective_score"]),
                                                      -float(row["mean"]), lineup_key(row)))
    for rank, row in enumerate(rows, 1):
        row["production_rank"] = rank
        row["ownership"] = candidate_ownership(row, frozen["ownership"])
        if row["ownership"]["status"] == "available":
            row["ownership"]["chalk_tag_count"] = sum(
                "chalk" in by_id[player_id].tags for player_id in row["player_ids"]
            )
            row["ownership"]["standard_caps_pass"] = (
                row["ownership"]["chalk_tag_count"] <= 5
                and row["ownership"]["ownership_sum"] <= 160.0
            )
        else:
            row["ownership"]["chalk_tag_count"] = None
            row["ownership"]["standard_caps_pass"] = None
    add_relative_chalk(rows)
    ranks = {lineup_key(row): i for i, row in enumerate(rows, 1)}
    global_mean = next(row for row in rows if "global_highest_mean" in row["sources"])
    global_p90 = next(row for row in rows if "global_highest_p90" in row["sources"])
    for row in rows:
        row["mean_loss_vs_global"] = global_mean["mean"] - row["mean"]
        row["p90_loss_vs_global"] = global_p90["p90"] - row["p90"]
    for item in injected:
        if item["status"] == "legal":
            row = rows[ranks[tuple(item["player_ids"])] - 1]
            item.update({"production_rank": row["production_rank"],
                         "mean_loss_vs_global": row["mean_loss_vs_global"],
                         "p90_loss_vs_global": row["p90_loss_vs_global"]})
    return {"candidates": rows, "injections": injected,
            "starting_qbs": [{"player_id": qb.player_id, "name": qb.name, "team": qb.team}
                             for qb in starters],
            "old_candidate_count": len(old), "total_candidate_count": len(rows),
            "saved_candidate_scores_replayed": len(old),
            "frozen_player_inputs": [{
                "player_id": player.player_id, "name": player.name,
                "team": player.team, "opponent": player.opponent,
                "position": player.position, "salary": player.salary,
                "mean": player.projection, "p90": player.ceiling,
                "context_adjustment": player.optimizer_context_adjustment,
                "game_id": player.game_id, "game_total": player.game_total,
                "team_spread": player.spread, "team_total": player.team_total,
                "market_context_point_in_time_safe": player.market_context_point_in_time_safe,
                "ownership": frozen["ownership"].get(player.player_id),
                "ownership_observed": player.player_id in frozen["ownership"],
            } for player in players],
            "global_mean": global_mean["mean"], "global_p90": global_p90["p90"]}


def analyze(frozen: dict[str, Any], discovered: dict[str, Any]) -> dict[str, Any]:
    rows = discovered["candidates"]
    players, config = frozen["players"], frozen["config"]
    by_id = {player.player_id: player for player in players}
    source = {str(row["player_id"]): row for row in frozen["pool"].to_dict("records")}
    game_totals = sorted({float(player.game_total) for player in players
                          if player.game_total is not None})
    base_context = {player.player_id: player.optimizer_context_adjustment for player in players}
    for name, context_factor, correlation_factor in SHADOWS:
        for player in players:
            player.optimizer_context_adjustment = base_context[player.player_id] * context_factor
        active_config = replace(config, correlation_bonus=config.correlation_bonus * correlation_factor)
        for row in rows:
            lineup = [by_id[player_id] for player_id in row["player_ids"]]
            scored = describe_candidate(lineup, all_players=players, config=active_config,
                                        pool_by_id=source, ownership_available=False,
                                        game_totals=game_totals)
            row.setdefault("shadow_scores", {})[name] = scored["objective_score"]
            row.setdefault("shadow_components", {})[name] = scored["components"]
        order = sorted(rows, key=lambda row: (-row["shadow_scores"][name],
                                               -row["mean"], lineup_key(row)))
        for rank, row in enumerate(order, 1):
            row.setdefault("shadow_ranks", {})[name] = rank
    for player in players:
        player.optimizer_context_adjustment = base_context[player.player_id]
    frontier = {}
    for name, context_factor, correlation_factor in SHADOWS[:4]:
        winner = min(rows, key=lambda row: row["shadow_ranks"][name])
        frontier[name] = winner["production_rank"]
    for gap in (3, 5, 7):
        eligible = [row for row in rows if row["mean_loss_vs_global"] <= gap + 1e-9]
        winner = max(eligible, key=lambda row: (row["objective_score"], row["mean"]))
        frontier[f"quality_within_{gap}_mean"] = winner["production_rank"]
    ownership_top_a = [row["production_rank"] for row in rows[:20]]
    owner_config = replace(
        config,
        objective_weights=ObjectiveWeights(projection=.35, ceiling=.45,
                                           leverage=.05, correlation=.15),
        tag_caps=LineupTagCaps(max_chalk=5, min_leverage=0, max_punts=2,
                              max_total_ownership=160.0),
    )
    for row in rows:
        row["candidate_aware_selector_score"] = None
        row["candidate_aware_rank"] = None
        if row["ownership"]["status"] != "available":
            row["ownership"]["chalk_tag_count"] = None
            row["ownership"]["standard_caps_pass"] = None
            continue
        row["ownership"]["chalk_tag_count"] = sum(
            "chalk" in by_id[player_id].tags for player_id in row["player_ids"]
        )
        row["ownership"]["standard_caps_pass"] = (
            row["ownership"]["chalk_tag_count"] <= 5
            and row["ownership"]["ownership_sum"] <= 160.0
        )
        lineup = [by_id[player_id] for player_id in row["player_ids"]]
        scored = describe_candidate(lineup, all_players=players, config=owner_config,
                                    pool_by_id=source, ownership_available=True,
                                    game_totals=game_totals)
        row["candidate_aware_selector_score"] = scored["objective_score"]
    complete_for_b = sorted(
        (row for row in rows if row["ownership"]["status"] == "available"
         and row["ownership"]["standard_caps_pass"]),
        key=lambda row: (-row["candidate_aware_selector_score"], -row["mean"], lineup_key(row)),
    )
    for rank, row in enumerate(complete_for_b, 1):
        row["candidate_aware_rank"] = rank
    ownership_top_b = [row["production_rank"] for row in complete_for_b[:20]]
    portfolios = {}
    robustness_keys = [name for name, _, _ in SHADOWS]
    worst_ranks = [max(row["shadow_ranks"][name] for name in robustness_keys)
                   for row in rows]
    # An integer worst-rank improvement dominates the tiny selector tie break.
    robust_values = [-float(rank) + 1e-4 * float(row["objective_score"])
                     for rank, row in zip(worst_ranks, rows)]
    robust_portfolios = {}
    for overlap in (6, 7):
        branch = {}
        robust_branch = {}
        for count in range(1, 6):
            selected = select_portfolio(rows, count, max_overlap=overlap,
                                        max_same_qb=2 if count >= 3 else None,
                                        min_distinct_qbs=min(count, 3),
                                        distinct_primary_paths=True)
            branch[str(count)] = selected
            robust_branch[str(count)] = select_portfolio(
                rows, count, max_overlap=overlap,
                max_same_qb=2 if count >= 3 else None,
                min_distinct_qbs=min(count, 3),
                distinct_primary_paths=True,
                objective_values=robust_values,
            )
            print(f"portfolio overlap {overlap} count {count}: {selected['status']}", flush=True)
        portfolios[str(overlap)] = branch
        robust_portfolios[str(overlap)] = robust_branch
    for overlap in (6, 7):
        portfolios[str(overlap)]["5_unconstrained_qb"] = select_portfolio(
            rows, 5, max_overlap=overlap)
    return {"discovery": {key: value for key, value in discovered.items() if key != "candidates"},
            "candidates": rows, "frontier_winner_ranks": frontier,
            "ownership_top20_all_or_nothing": ownership_top_a,
            "ownership_top20_candidate_aware": ownership_top_b,
            "ownership_candidate_aware_policy": {
                "weights": {"mean": .35, "p90": .45, "leverage": .05,
                            "correlation": .15},
                "chalk_cap": 5, "ownership_sum_cap": 160.0,
                "leverage_unavailable_reason": "frozen pool has no optimal-lineup probabilities",
                "incomplete_candidate_treatment": "ownership score and rank unavailable; candidate remains in discovery universe",
                "cap_rejected_complete_candidates": sum(
                    row["ownership"]["standard_caps_pass"] is False for row in rows
                ),
            },
            "portfolio_frontier": portfolios,
            "robust_worst_rank_portfolio_frontier": robust_portfolios,
            "ownership_coverage": {"eligible": len(players),
                                   "covered": sum(p.player_id in frozen["ownership"] for p in players),
                                   "complete_candidates": sum(row["ownership"]["status"] == "available" for row in rows),
                                   "missing_candidates": sum(row["ownership"]["status"] != "available" for row in rows),
                                   "leverage_available_candidates": sum(row["ownership"]["leverage_sum"] is not None for row in rows)}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("output", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--from-discovery", type=Path)
    args = parser.parse_args()
    frozen = load_frozen(args.run_id)
    discovered = (json.loads(args.from_discovery.read_text()) if args.from_discovery
                  else discover(frozen, args.workers))
    if args.discover_only:
        payload = discovered
    else:
        payload = analyze(frozen, discovered)
    payload["source_optimizer_run_id"] = args.run_id
    payload["projection_run_id"] = str(frozen["run"]["projection_run_id"])
    payload["ownership_run_id"] = frozen["params"]["ownership_run_id"]
    payload["source_data_cutoff_at"] = str(frozen["run"]["data_cutoff_at"])
    payload["source_run_created_at"] = str(frozen["run"]["created_at"])
    args.output.write_text(json.dumps(payload, indent=2, default=str, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output),
                      "candidate_count": len(payload["candidates"])}, indent=2), flush=True)


if __name__ == "__main__":
    main()
