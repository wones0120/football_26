#!/usr/bin/env python3
"""Frozen prelock five-entry portfolio with one CAR/CLE-free offense path."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

import pulp

from backend.app.product_services.classic_frontier_diagnostic import candidate_ownership, lineup_key
from backend.app.product_services.classic_small_field import describe_candidate
from backend.app.product_services.gpp_optimizer import (
    _build_lineup, build_format_specific_terms, build_lineup_correlation_terms,
)
from backend.app.product_services.rule_library import resolve_strategy_profile
from scripts.audit_sunday_main_portfolio_frontier import load_frozen


RUN_ID = "a6d7f5e7-db0f-44ae-87c4-60a826973408"
QUALITY = Path("artifacts/sunday-main-quality-governed-portfolio-2026w3.json")
CORE = Path("artifacts/sunday-main-core-exposure-2026w3.json")
GAME = Path("artifacts/sunday-main-game-environment-2026w3.json")
OUTPUT = Path("artifacts/sunday-main-clean-car-portfolio-2026w3.json")
OFFENSE = {"QB", "RB", "WR", "TE"}


def main() -> None:
    quality = json.loads(QUALITY.read_text())
    core = json.loads(CORE.read_text())
    game = json.loads(GAME.read_text())
    frozen = load_frozen(RUN_ID)
    players, config = frozen["players"], frozen["config"]
    by_id = {player.player_id: player for player in players}
    index_by_id = {player.player_id: i for i, player in enumerate(players)}
    pool_by_id = {str(row["player_id"]): row for row in frozen["pool"].to_dict("records")}
    game_totals = sorted({float(player.game_total) for player in players
                          if player.game_total is not None})
    profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
    correlation_terms = build_lineup_correlation_terms(players, profile=profile)
    format_terms = build_format_specific_terms(players, profile=profile)
    global_mean, global_p90 = quality["global_mean"], quality["global_p90"]
    car_ids = {player.player_id for player in players
               if player.team in {"CAR", "CLE"} and player.position in OFFENSE}
    old_keys = {lineup_key(row) for row in quality["candidates"]}
    candidates = {lineup_key(row): dict(row) for row in quality["candidates"]}
    candidates.update({lineup_key(row): dict(row) for row in game["new_exact_candidates"]})

    def describe(ids: list[str]) -> dict:
        key = tuple(sorted(ids))
        if key not in candidates:
            row = describe_candidate(
                [by_id[player_id] for player_id in ids], all_players=players,
                config=config, pool_by_id=pool_by_id, ownership_available=False,
                candidate_aware_ownership=True, game_totals=game_totals,
            )
            row["rank"] = None
            row["mean_loss_vs_global"] = global_mean - row["mean"]
            row["p90_loss_vs_global"] = global_p90 - row["p90"]
            candidates[key] = row
        row = candidates[key]
        row["ownership"] = candidate_ownership(row, frozen["ownership"])
        return row

    def solve_car_free(gap: float, *, qb_id: str | None = None,
                       previous: list[set[int]] | None = None) -> list[str] | None:
        active_config = replace(config, uniqueness_overlap=8) if previous else config
        indexes = _build_lineup(
            players, active_config, {player_id: 0 for player_id in car_ids},
            previous or [], required_player_ids={qb_id} if qb_id else None,
            minimum_mean=global_mean-gap, minimum_p90=global_p90-gap,
            enforce_single_te=bool(frozen["params"]["enforce_single_te"]),
            avoid_dst_opponents=bool(frozen["params"]["avoid_dst_opponents"]),
            precomputed_correlation_terms=correlation_terms,
            precomputed_format_terms=format_terms,
        )
        return [players[index].player_id for index in indexes] if indexes is not None else None

    grid = []
    for step in range(5):
        gap = 5.0 + step*0.01
        ids = solve_car_free(gap)
        row = describe(ids) if ids else None
        grid.append({"screen_gap": gap, "legal_car_free_lineup": row})
        print(f"joint screen {gap:.2f}: {'CAR-free lineup' if row else 'none'}", flush=True)

    # A CAR/CLE-free entry is necessary for portfolio feasibility. Narrow its
    # exact legal minimax gap far beyond the requested hundredth-point grid.
    low, high = 5.03, 5.04
    best_ids = None
    for _ in range(16):
        mid = (low+high)/2
        ids = solve_car_free(mid)
        if ids is None:
            low = mid
        else:
            high, best_ids = mid, ids
    exact_minimum = describe(best_ids) if best_ids else None
    print(f"CAR-free gap in [{low:.8f}, {high:.8f}]", flush=True)

    qualifying_qbs = {row["qb"]["player_id"] for row in quality["candidates"]
                      if row["mean_loss_vs_global"] <= 5+1e-8
                      and row["p90_loss_vs_global"] <= 5+1e-8}
    family_feasibility = []
    for qb_id in sorted(qualifying_qbs):
        ids = solve_car_free(5.04, qb_id=qb_id)
        row = describe(ids) if ids else None
        family_feasibility.append({"qb_id": qb_id, "qb": by_id[qb_id].name,
                                   "best_car_free_at_5_04": row})
    feasible_families = [row for row in family_feasibility
                         if row["best_car_free_at_5_04"]]

    # Enumerate nearby alternatives in the feasible QB family, so portfolio
    # overlap and non-QB exposure constraints do not rely on a single column.
    for family in feasible_families:
        initial = family["best_car_free_at_5_04"]
        previous = [{index_by_id[player_id] for player_id in initial["player_ids"]}]
        for _ in range(10):
            ids = solve_car_free(5.04, qb_id=family["qb_id"], previous=previous)
            if ids is None:
                break
            previous.append({index_by_id[player_id] for player_id in ids})
            describe(ids)
        family["enumerated_alternatives"] = len(previous)-1

    def summarize(rows: list[dict]) -> dict:
        ordered = sorted(rows, key=lambda row: -row["objective_score"])
        overlap = [[len(set(left["player_ids"]) & set(right["player_ids"]))
                    for right in ordered] for left in ordered]
        count_by_id = Counter(player_id for row in ordered
                              for player_id in row["player_ids"])
        player_exposure = [{"player_id": player_id, "name": by_id[player_id].name,
                            "position": by_id[player_id].position,
                            "team": by_id[player_id].team,
                            "appearances": count, "exposure_pct": 20*count}
                           for player_id, count in count_by_id.most_common()]
        offense_by_game = defaultdict(int)
        offense_piece_counts = defaultdict(Counter)
        for row in ordered:
            games_here = set()
            for player_id in row["player_ids"]:
                player = by_id[player_id]
                if player.position in OFFENSE and player.game_id:
                    games_here.add(player.game_id)
                    offense_piece_counts[player.game_id][player_id] += 1
            for game_id in games_here:
                offense_by_game[game_id] += 1
        game_exposure = []
        for game_id in sorted({player.game_id for player in players if player.game_id}):
            members = [player for player in players if player.game_id == game_id]
            teams = sorted({player.team for player in members})
            if len(teams) != 2:
                continue
            game_exposure.append({
                "game_id": game_id, "game": "-".join(teams),
                "game_total": next((player.game_total for player in members
                                    if player.game_total is not None), None),
                "offense_entries": offense_by_game[game_id],
                "offense_appearances": sum(offense_piece_counts[game_id].values()),
                "offensive_pieces": [
                    {"name": by_id[player_id].name, "appearances": count}
                    for player_id, count in offense_piece_counts[game_id].most_common()
                ],
            })
        return {"status": "optimal", "lineups": ordered,
                "selector_sum": sum(row["objective_score"] for row in ordered),
                "mean_sum": sum(row["mean"] for row in ordered),
                "p90_sum": sum(row["p90"] for row in ordered),
                "minimum_mean": min(row["mean"] for row in ordered),
                "minimum_p90": min(row["p90"] for row in ordered),
                "maximum_joint_gap": max(max(row["mean_loss_vs_global"],
                                             row["p90_loss_vs_global"]) for row in ordered),
                "qb_exposure": [{"name": row["qb"]["name"], "appearances": 1}
                                for row in ordered],
                "player_exposure": player_exposure,
                "game_offensive_exposure": game_exposure,
                "overlap": overlap}

    def select_portfolio(gap: float) -> dict:
        eligible = [row for row in candidates.values()
                    if row["mean_loss_vs_global"] <= gap+1e-8
                    and row["p90_loss_vs_global"] <= gap+1e-8]
        model = pulp.LpProblem("clean_car_portfolio", pulp.LpMaximize)
        selected = pulp.LpVariable.dicts("lineup", range(len(eligible)), cat="Binary")
        model += pulp.lpSum(row["objective_score"]*selected[i]
                            for i, row in enumerate(eligible))
        model += pulp.lpSum(selected.values()) == 5
        qbs = defaultdict(list)
        non_qbs = defaultdict(list)
        car_entries = []
        ids = [set(row["player_ids"]) for row in eligible]
        for index, row in enumerate(eligible):
            qbs[row["qb"]["player_id"]].append(index)
            for player_id in row["player_ids"]:
                if by_id[player_id].position != "QB":
                    non_qbs[player_id].append(index)
            if ids[index] & car_ids:
                car_entries.append(index)
        for indexes in qbs.values():
            model += pulp.lpSum(selected[index] for index in indexes) <= 1
        for indexes in non_qbs.values():
            model += pulp.lpSum(selected[index] for index in indexes) <= 4
        model += pulp.lpSum(selected[index] for index in car_entries) <= 4
        for i in range(len(eligible)):
            for j in range(i+1, len(eligible)):
                if len(ids[i] & ids[j]) > 6:
                    model += selected[i]+selected[j] <= 1
        status = model.solve(pulp.PULP_CBC_CMD(msg=False))
        if status != pulp.LpStatusOptimal:
            return {"status": pulp.LpStatus[status], "eligible_candidate_count": len(eligible)}
        rows = [eligible[i] for i in range(len(eligible)) if pulp.value(selected[i]) > .9]
        return {**summarize(rows), "eligible_candidate_count": len(eligible)}

    portfolio_grid = []
    for step in range(5):
        gap = 5.0+step*0.01
        result = select_portfolio(gap)
        portfolio_grid.append({"screen_gap": gap, "portfolio": result})
        print(f"portfolio at {gap:.2f}: {result['status']}", flush=True)
    first = next((row for row in portfolio_grid if row["portfolio"]["status"] == "optimal"), None)
    exact_feasibility = select_portfolio(max(exact_minimum["mean_loss_vs_global"],
                                             exact_minimum["p90_loss_vs_global"]) + 1e-6)
    a = summarize(core["unrestricted"]["lineups"])
    b = summarize(core["all_non_qb_cap4"]["lineups"])
    if first is None:
        raise RuntimeError("No feasible portfolio by 5.04; extend diagnostic grid")
    c = first["portfolio"]
    no_car = [row for row in c["lineups"] if not set(row["player_ids"]) & car_ids]
    if len(no_car) != 1:
        raise AssertionError("Expected exactly one CAR/CLE-free entry")
    payload = {
        "source_optimizer_run_id": RUN_ID,
        "source_data_cutoff_at": quality["source_data_cutoff_at"],
        "no_current_game_outcomes_used": True,
        "unchanged_quality_maxima": {"mean": global_mean, "p90": global_p90},
        "screen_grid": portfolio_grid,
        "car_free_lineup_grid": grid,
        "car_free_exact_minimum_gap_interval": {"lower": low, "upper": high,
                                                "witness_joint_gap": max(
                                                    exact_minimum["mean_loss_vs_global"],
                                                    exact_minimum["p90_loss_vs_global"]),
                                                "witness": exact_minimum},
        "portfolio_at_witness_gap": exact_feasibility,
        "first_feasible_centipoint_screen": first["screen_gap"],
        "car_free_qb_families_at_5_04": family_feasibility,
        "candidate_count": len(candidates),
        "portfolios": {"A_unrestricted": a, "B_non_qb_max4": b, "C_clean_car": c},
        "C_car_free_entry": no_car[0],
        "C_minus_A": {"selector": c["selector_sum"]-a["selector_sum"],
                      "mean": c["mean_sum"]-a["mean_sum"],
                      "p90": c["p90_sum"]-a["p90_sum"]},
        "C_minus_B": {"selector": c["selector_sum"]-b["selector_sum"],
                      "mean": c["mean_sum"]-b["mean_sum"],
                      "p90": c["p90_sum"]-b["p90_sum"]},
        "new_exact_candidates": [row for key, row in candidates.items()
                                 if key not in old_keys],
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, default=str, allow_nan=False)+"\n")
    print(f"saved {OUTPUT} ({len(candidates)} candidates)", flush=True)


if __name__ == "__main__":
    main()
