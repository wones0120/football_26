#!/usr/bin/env python3
"""Frozen prelock exposure and core-exclusion feasibility audit."""

from __future__ import annotations

import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from itertools import combinations
from pathlib import Path

import pulp

from backend.app.product_services.classic_frontier_diagnostic import lineup_key
from backend.app.product_services.classic_small_field import describe_candidate
from backend.app.product_services.gpp_optimizer import (
    _build_lineup, build_format_specific_terms, build_lineup_correlation_terms,
)
from backend.app.product_services.rule_library import resolve_strategy_profile
from scripts.audit_sunday_main_portfolio_frontier import load_frozen


RUN_ID = "a6d7f5e7-db0f-44ae-87c4-60a826973408"
SOURCE = Path("artifacts/sunday-main-quality-governed-portfolio-2026w3.json")
OUTPUT = Path("artifacts/sunday-main-core-exposure-2026w3.json")
CORE_NAMES = ("Derrick Henry", "Jalen Coker", "Denzel Boston")


def main() -> None:
    source = json.loads(SOURCE.read_text())
    frozen = load_frozen(RUN_ID)
    players = frozen["players"]
    by_name = {player.name: player for player in players}
    profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
    terms = build_lineup_correlation_terms(players, profile=profile)
    formats = build_format_specific_terms(players, profile=profile)
    global_mean, global_p90 = source["global_mean"], source["global_p90"]
    selected = [source["candidates"][rank - 1] for rank in source["portfolios"]["5"]["5"]["ranks"]]
    counts = Counter(player["player_id"] for row in selected for player in row["roster"])
    pool_by_id = {str(row["player_id"]): row for row in frozen["pool"].to_dict("records")}
    exposure = []
    for player_id, count in counts.most_common():
        if count < 3:
            continue
        player = next(player for player in players if player.player_id == player_id)
        raw = pool_by_id[player_id]
        exposure.append({
            "player_id": player_id, "name": player.name, "position": player.position,
            "appearances": count, "exposure_pct": 20 * count,
            "salary": player.salary, "mean": player.projection, "p90": player.ceiling,
            "ownership": player.ownership, "value_per_k": player.projection / (player.salary / 1000),
            "role_class": raw.get("offensive_role_class"),
            "role_label": raw.get("pregame_role_label"),
            "team": player.team, "opponent_team": raw.get("opponent_team"),
            "value_rank": None,
        })
    skill = sorted((player for player in players if player.position not in {"QB", "DST"}),
                   key=lambda player: -player.projection / (player.salary / 1000))
    value_rank = {player.player_id: rank for rank, player in enumerate(skill, 1)}
    for row in exposure:
        row["value_rank"] = value_rank.get(row["player_id"])

    core_ids = {name: by_name[name].player_id for name in CORE_NAMES}
    qualifying_qbs = sorted({row["qb"]["player_id"] for row in source["candidates"]
                             if row["mean_loss_vs_global"] <= 5 + 1e-9
                             and row["p90_loss_vs_global"] <= 5 + 1e-9})

    def solve_excluding(names: tuple[str, ...], qb_id: str | None = None,
                        excluded_lineups: list[set[int]] | None = None):
        config = (replace(frozen["config"], uniqueness_overlap=8)
                  if excluded_lineups else frozen["config"])
        indexes = _build_lineup(
            players, config, {core_ids[name]: 0 for name in names},
            excluded_lineups or [],
            required_player_ids={qb_id} if qb_id else None,
            enforce_single_te=bool(frozen["params"]["enforce_single_te"]),
            avoid_dst_opponents=bool(frozen["params"]["avoid_dst_opponents"]),
            minimum_mean=global_mean - 5, minimum_p90=global_p90 - 5,
            precomputed_correlation_terms=terms,
            precomputed_format_terms=formats,
        )
        return [players[index].player_id for index in indexes] if indexes else None

    requests = [(names, qb_id) for size in range(1, 4)
                for names in combinations(CORE_NAMES, size) for qb_id in qualifying_qbs]
    discovered: dict[tuple[str, ...], dict] = {lineup_key(row): dict(row)
                                               for row in source["candidates"]}
    exclusion_feasibility = {name: None for name in CORE_NAMES}
    request_results = []
    game_totals = sorted({float(player.game_total) for player in players
                          if player.game_total is not None})
    by_id = {player.player_id: player for player in players}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(solve_excluding, names, qb_id): (names, qb_id)
                   for names, qb_id in requests}
        for future in as_completed(futures):
            names, qb_id = futures[future]
            ids = future.result()
            request_results.append({"excluded": list(names), "qb_id": qb_id,
                                    "qb_name": by_id[qb_id].name, "feasible": ids is not None,
                                    "player_ids": ids})
            if ids is not None:
                key = tuple(sorted(ids))
                if key not in discovered:
                    row = describe_candidate(
                        [by_id[player_id] for player_id in ids], all_players=players,
                        config=frozen["config"], pool_by_id=pool_by_id,
                        ownership_available=False, candidate_aware_ownership=True,
                        game_totals=game_totals,
                    )
                    row["mean_loss_vs_global"] = global_mean - row["mean"]
                    row["p90_loss_vs_global"] = global_p90 - row["p90"]
                    row["rank"] = None
                    discovered[key] = row
                discovered[key].setdefault("core_exclusion_sources", []).append(
                    {"excluded": list(names), "qb_id": qb_id})
                if len(names) == 1:
                    previous = exclusion_feasibility[names[0]]
                    if previous is None or discovered[key]["objective_score"] > discovered[tuple(sorted(previous))]["objective_score"]:
                        exclusion_feasibility[names[0]] = ids
            if len(futures) <= 10 or sum(item.done() for item in futures) % 10 == 0:
                print(f"core exclusion solves {sum(item.done() for item in futures)}/{len(futures)}", flush=True)

    index_by_id = {player.player_id: index for index, player in enumerate(players)}

    def alternate_rows(result: dict) -> list[tuple[str, ...]]:
        names = tuple(result["excluded"])
        qb_id = result["qb_id"]
        previous = [set(index_by_id[player_id] for player_id in result["player_ids"])]
        alternatives = []
        for _ in range(5):
            ids = solve_excluding(names, qb_id, previous)
            if ids is None:
                break
            previous.append(set(index_by_id[player_id] for player_id in ids))
            alternatives.append(tuple(sorted(ids)))
        return alternatives

    feasible_requests = [row for row in request_results if row["feasible"]]
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(alternate_rows, row): row for row in feasible_requests}
        for future in as_completed(futures):
            request = futures[future]
            for ids in future.result():
                if ids not in discovered:
                    row = describe_candidate(
                        [by_id[player_id] for player_id in ids], all_players=players,
                        config=frozen["config"], pool_by_id=pool_by_id,
                        ownership_available=False, candidate_aware_ownership=True,
                        game_totals=game_totals,
                    )
                    row["mean_loss_vs_global"] = global_mean - row["mean"]
                    row["p90_loss_vs_global"] = global_p90 - row["p90"]
                    row["rank"] = None
                    discovered[ids] = row
                discovered[ids].setdefault("core_exclusion_sources", []).append(
                    {"excluded": request["excluded"], "qb_id": request["qb_id"],
                     "alternate": True})
            print(f"alternate solves for {request['qb_name']} excluding {request['excluded']}: "
                  f"{len(future.result())}", flush=True)

    eligible = [row for row in discovered.values()
                if row["mean_loss_vs_global"] <= 5 + 1e-9
                and row["p90_loss_vs_global"] <= 5 + 1e-9]

    def portfolio(caps: dict[str, int]) -> dict:
        model = pulp.LpProblem("core_exposure_portfolio", pulp.LpMaximize)
        selected_vars = pulp.LpVariable.dicts("lineup", range(len(eligible)), cat="Binary")
        model += pulp.lpSum(row["objective_score"] * selected_vars[i]
                            for i, row in enumerate(eligible))
        model += pulp.lpSum(selected_vars.values()) == 5
        for qb_id in qualifying_qbs:
            model += pulp.lpSum(selected_vars[i] for i, row in enumerate(eligible)
                                if row["qb"]["player_id"] == qb_id) <= 1
        for player_id, cap in caps.items():
            model += pulp.lpSum(selected_vars[i] for i, row in enumerate(eligible)
                                if player_id in row["player_ids"]) <= cap
        player_sets = [set(row["player_ids"]) for row in eligible]
        for i in range(len(eligible)):
            for j in range(i + 1, len(eligible)):
                if len(player_sets[i] & player_sets[j]) > 6:
                    model += selected_vars[i] + selected_vars[j] <= 1
        status = model.solve(pulp.PULP_CBC_CMD(msg=False))
        if status != pulp.LpStatusOptimal:
            return {"status": pulp.LpStatus[status], "lineups": []}
        rows = sorted((eligible[i] for i in range(len(eligible))
                       if pulp.value(selected_vars[i]) > .9),
                      key=lambda row: -row["objective_score"])
        return {
            "status": "optimal", "lineups": rows,
            "ranks": [row["rank"] for row in rows],
            "selector_sum": sum(row["objective_score"] for row in rows),
            "mean_sum": sum(row["mean"] for row in rows),
            "p90_sum": sum(row["p90"] for row in rows),
            "minimum_mean": min(row["mean"] for row in rows),
            "minimum_p90": min(row["p90"] for row in rows),
            "overlap": [[len(set(a["player_ids"]) & set(b["player_ids"]))
                         for b in rows] for a in rows],
            "exposure": [
                {"player_id": player_id, "name": by_id[player_id].name,
                 "position": by_id[player_id].position, "appearances": count}
                for player_id, count in Counter(player_id for row in rows
                                                for player_id in row["player_ids"]).most_common()
            ],
        }

    baseline = portfolio({})
    independent = {name: {str(cap): portfolio({core_ids[name]: cap})
                          for cap in (4, 3)} for name in CORE_NAMES}
    non_qb_ids = {player.player_id: 4 for player in players if player.position != "QB"}
    all_non_qb_cap4 = portfolio(non_qb_ids)
    payload = {
        "source_optimizer_run_id": RUN_ID,
        "source_data_cutoff_at": source["source_data_cutoff_at"],
        "no_current_game_outcomes_used": True,
        "quality_screen": {"maximum_mean_loss": 5, "maximum_p90_loss": 5},
        "baseline_ranks": source["portfolios"]["5"]["5"]["ranks"],
        "baseline_selector_sum": source["portfolios"]["5"]["5"]["score_sum"],
        "exposure": exposure,
        "value_rank_basis": {"metric": "projected mean per $1,000 salary",
                             "population": "frozen included non-QB/non-DST players",
                             "player_count": len(skill)},
        "global_best_excluding_core_under_joint_screen": exclusion_feasibility,
        "core_exclusion_request_results": sorted(request_results,
                                                  key=lambda row: (len(row["excluded"]),
                                                                   row["excluded"], row["qb_name"])),
        "new_exact_candidates": [row for row in discovered.values() if row["rank"] is None],
        "discovery": {"base_candidate_count": len(source["candidates"]),
                      "eligible_base_count": sum(row["mean_loss_vs_global"] <= 5 + 1e-9
                                                 and row["p90_loss_vs_global"] <= 5 + 1e-9
                                                 for row in source["candidates"]),
                      "core_exclusion_requests": len(requests),
                      "alternate_solves_per_feasible_request": 5,
                      "feasible_core_exclusion_requests": len(feasible_requests),
                      "candidate_count": len(discovered),
                      "eligible_candidate_count": len(eligible)},
        "unrestricted": baseline,
        "independent_caps": independent,
        "all_non_qb_cap4": all_non_qb_cap4,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, default=str, allow_nan=False) + "\n")
    print(f"saved {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
