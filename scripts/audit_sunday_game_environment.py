#!/usr/bin/env python3
"""Frozen prelock game-environment and high-total construction diagnostic."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pulp
from sqlalchemy import text

from backend.app.db import engine
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
OUTPUT = Path("artifacts/sunday-main-game-environment-2026w3.json")
OFFENSE = {"QB", "RB", "WR", "TE"}
PASS_CATCHER = {"WR", "TE"}
GAMES = {"BAL-DAL": {"BAL", "DAL"}, "LAC-BUF": {"LAC", "BUF"},
         "CAR-CLE": {"CAR", "CLE"}}


def main() -> None:
    saved = json.loads(QUALITY.read_text())
    core = json.loads(CORE.read_text())
    frozen = load_frozen(RUN_ID)
    players, config = frozen["players"], frozen["config"]
    by_id = {player.player_id: player for player in players}
    source = {str(row["player_id"]): row for row in frozen["pool"].to_dict("records")}
    game_totals = sorted({float(player.game_total) for player in players
                          if player.game_total is not None})
    profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
    terms = build_lineup_correlation_terms(players, profile=profile)
    formats = build_format_specific_terms(players, profile=profile)
    global_mean, global_p90 = saved["global_mean"], saved["global_p90"]
    old_rows = saved["candidates"]
    old_keys = {lineup_key(row): row for row in old_rows}
    candidates = {lineup_key(row): dict(row) for row in old_rows}
    candidates.update({lineup_key(row): dict(row) for row in core["new_exact_candidates"]})
    qb_players = [player for player in players if player.position == "QB"]
    ids_by_game = {name: {player.player_id for player in players
                          if player.team in teams and player.position in OFFENSE}
                   for name, teams in GAMES.items()}
    car_ids = ids_by_game["CAR-CLE"]
    core_ids = {name: next(player.player_id for player in players if player.name == name)
                for name in ("Jalen Coker", "Denzel Boston")}

    def score(ids: list[str]) -> dict:
        key = tuple(sorted(ids))
        if key not in candidates:
            row = describe_candidate(
                [by_id[player_id] for player_id in ids], all_players=players,
                config=config, pool_by_id=source, ownership_available=False,
                candidate_aware_ownership=True, game_totals=game_totals,
            )
            row["rank"] = None
            row["mean_loss_vs_global"] = global_mean - row["mean"]
            row["p90_loss_vs_global"] = global_p90 - row["p90"]
            candidates[key] = row
        row = candidates[key]
        row["ownership"] = candidate_ownership(row, frozen["ownership"])
        return row

    def solve(*, gap: float | None, game: str | None = None, count: int = 0,
              qb_id: str | None = None, omit: set[str] | None = None) -> list[str] | None:
        indexes = _build_lineup(
            players, config, {player_id: 0 for player_id in (omit or ())}, [],
            required_player_ids={qb_id} if qb_id else None,
            minimum_player_groups=[(ids_by_game[game], count)] if game and count else None,
            minimum_mean=global_mean-gap if gap is not None else None,
            minimum_p90=global_p90-gap if gap is not None else None,
            enforce_single_te=bool(frozen["params"]["enforce_single_te"]),
            avoid_dst_opponents=bool(frozen["params"]["avoid_dst_opponents"]),
            precomputed_correlation_terms=terms,
            precomputed_format_terms=formats,
        )
        return [players[index].player_id for index in indexes] if indexes is not None else None

    def best_for(request: dict, gap: float | None) -> dict | None:
        game = request.get("game")
        if request.get("stack"):
            qbs = [player for player in qb_players if player.team in GAMES[game]]
            results = [solve(gap=gap, qb_id=qb.player_id, omit=request.get("omit"))
                       for qb in qbs]
            rows = [score(ids) for ids in results if ids]
            return max(rows, key=lambda row: row["objective_score"], default=None)
        ids = solve(gap=gap, game=game, count=request.get("count", 0),
                    omit=request.get("omit"))
        return score(ids) if ids else None

    requests = {
        "A_BAL_DAL_QB_stack": {"game": "BAL-DAL", "stack": True},
        "B_BAL_DAL_offense_2": {"game": "BAL-DAL", "count": 2},
        "C_BAL_DAL_offense_3": {"game": "BAL-DAL", "count": 3},
        "D_LAC_BUF_QB_stack": {"game": "LAC-BUF", "stack": True},
        "E_LAC_BUF_offense_2": {"game": "LAC-BUF", "count": 2},
        "F_LAC_BUF_offense_3": {"game": "LAC-BUF", "count": 3},
        "no_Coker": {"omit": {core_ids["Jalen Coker"]}},
        "no_Boston": {"omit": {core_ids["Denzel Boston"]}},
        "neither_Coker_nor_Boston": {"omit": set(core_ids.values())},
        "no_CAR_CLE_offense": {"omit": car_ids},
    }
    counterfactuals = {}
    for label, request in requests.items():
        at_five = best_for(request, 5.0)
        unrestricted = best_for(request, None)
        closest = None
        threshold = None
        if at_five is None and unrestricted is not None:
            low = 5.0
            high = max(5.01, unrestricted["mean_loss_vs_global"],
                       unrestricted["p90_loss_vs_global"]) + 0.1
            for _ in range(11):
                mid = (low + high) / 2
                row = best_for(request, mid)
                if row is None:
                    low = mid
                else:
                    high, closest = mid, row
            threshold = {"lower": low, "upper": high}
        counterfactuals[label] = {"at_joint_5": at_five, "best_unconstrained": unrestricted,
                                  "closest_if_5_infeasible": closest,
                                  "minimum_joint_gap_interval": threshold}
        print(f"{label}: {'feasible' if at_five else 'infeasible'} at 5", flush=True)

    # Preserve the saved universe, then add exact QB stacks and CAR-free choices
    # under progressively wider *diagnostic* screens. No scoring weight changes.
    gap_grid = (5.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 15.0)
    target_qbs = [player for player in qb_players
                  if player.team in GAMES["BAL-DAL"] | GAMES["LAC-BUF"]]
    quality_qb_ids = {row["qb"]["player_id"] for row in old_rows
                      if row["mean_loss_vs_global"] <= 5 + 1e-9
                      and row["p90_loss_vs_global"] <= 5 + 1e-9}
    car_free_qbs = [player for player in qb_players
                    if player.player_id in quality_qb_ids or player in target_qbs]
    portfolio_requests = []
    for gap in gap_grid:
        for qb in target_qbs:
            portfolio_requests.append((gap, qb.player_id, frozenset()))
            portfolio_requests.append((gap, qb.player_id, frozenset(car_ids)))
        for qb in car_free_qbs:
            if qb not in target_qbs:
                portfolio_requests.append((gap, qb.player_id, frozenset(car_ids)))

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(solve, gap=gap, qb_id=qb_id, omit=set(omit)):
                   (gap, qb_id, omit) for gap, qb_id, omit in portfolio_requests}
        for index, future in enumerate(as_completed(futures), 1):
            ids = future.result()
            if ids:
                score(ids)
            if index % 25 == 0 or index == len(futures):
                print(f"portfolio discovery {index}/{len(futures)}", flush=True)

    # Market and portfolio exposure from the actual frozen five.
    games: dict[str, dict] = {}
    by_game = defaultdict(list)
    for player in players:
        if player.game_id:
            by_game[player.game_id].append(player)
    baseline = core["unrestricted"]
    for game_id, members in by_game.items():
        teams = sorted({player.team for player in members if player.team})
        if len(teams) != 2:
            continue
        team_lines = {}
        for team in teams:
            team_player = next((player for player in members if player.team == team
                                and player.team_total is not None), None)
            team_lines[team] = {"implied_total": team_player.team_total if team_player else None,
                                "spread": team_player.spread if team_player else None}
        appeared = offense_entries = multi_offense = stack_entries = dst_only = offense_appearances = 0
        piece_counts = Counter()
        for row in baseline["lineups"]:
            present = [by_id[player_id] for player_id in row["player_ids"]
                       if by_id[player_id].game_id == game_id]
            offense = [player for player in present if player.position in OFFENSE]
            if present:
                appeared += 1
            if offense:
                offense_entries += 1
            if len(offense) >= 2:
                multi_offense += 1
            if present and not offense:
                dst_only += 1
            offense_appearances += len(offense)
            for player in offense:
                piece_counts[player.player_id] += 1
            qbs = [player for player in offense if player.position == "QB"]
            if any(any(catcher.team == qb.team and catcher.position in PASS_CATCHER
                       for catcher in offense) for qb in qbs):
                stack_entries += 1
        piece_rows = [{"name": by_id[player_id].name, "team": by_id[player_id].team,
                       "position": by_id[player_id].position, "appearances": count,
                       "projected_ownership": by_id[player_id].ownership}
                      for player_id, count in piece_counts.most_common()]
        games["-".join(teams)] = {
            "game_id": game_id, "teams": teams, "game_total": next(
                (player.game_total for player in members if player.game_total is not None), None),
            "team_lines": team_lines, "any_entries": appeared,
            "offense_entries": offense_entries, "multi_offense_entries": multi_offense,
            "qb_stack_entries": stack_entries, "dst_only_entries": dst_only,
            "offense_appearances": offense_appearances,
            "offense_ownership_sum_across_appearances": (
                sum(by_id[player_id].ownership * count for player_id, count in piece_counts.items())
                if all(by_id[player_id].ownership is not None for player_id in piece_counts) else None),
            "offensive_pieces": piece_rows,
        }

    def flags(row: dict) -> tuple[bool, bool, bool]:
        qb_team = row["qb"]["team"]
        stack = row["stack"]["partner_count"] >= 1
        ids = set(row["player_ids"])
        return (stack and qb_team in GAMES["BAL-DAL"],
                stack and qb_team in GAMES["LAC-BUF"],
                bool(ids & car_ids))

    def portfolio(gap: float, *, cap_car: bool) -> dict:
        eligible = [row for row in candidates.values()
                    if row["mean_loss_vs_global"] <= gap + 1e-8
                    and row["p90_loss_vs_global"] <= gap + 1e-8]
        model = pulp.LpProblem("game_environment_portfolio", pulp.LpMaximize)
        selected = pulp.LpVariable.dicts("lineup", range(len(eligible)), cat="Binary")
        model += pulp.lpSum(row["objective_score"] * selected[i]
                            for i, row in enumerate(eligible))
        model += pulp.lpSum(selected.values()) == 5
        by_qb = defaultdict(list)
        sets = [set(row["player_ids"]) for row in eligible]
        row_flags = [flags(row) for row in eligible]
        for index, row in enumerate(eligible):
            by_qb[row["qb"]["player_id"]].append(index)
        for indexes in by_qb.values():
            model += pulp.lpSum(selected[i] for i in indexes) <= 1
        model += pulp.lpSum(selected[i] for i, state in enumerate(row_flags) if state[0]) >= 1
        model += pulp.lpSum(selected[i] for i, state in enumerate(row_flags) if state[1]) >= 1
        if cap_car:
            model += pulp.lpSum(selected[i] for i, state in enumerate(row_flags) if state[2]) <= 4
        for i in range(len(eligible)):
            for j in range(i + 1, len(eligible)):
                if len(sets[i] & sets[j]) > 6:
                    model += selected[i] + selected[j] <= 1
        status = model.solve(pulp.PULP_CBC_CMD(msg=False))
        if status != pulp.LpStatusOptimal:
            return {"status": pulp.LpStatus[status], "lineups": [],
                    "eligible_candidate_count": len(eligible)}
        rows = sorted((eligible[i] for i in range(len(eligible)) if pulp.value(selected[i]) > .9),
                      key=lambda row: -row["objective_score"])
        return {"status": "optimal", "lineups": rows,
                "eligible_candidate_count": len(eligible),
                "selector_sum": sum(row["objective_score"] for row in rows),
                "mean_sum": sum(row["mean"] for row in rows),
                "p90_sum": sum(row["p90"] for row in rows),
                "max_joint_gap": max(max(row["mean_loss_vs_global"],
                                         row["p90_loss_vs_global"]) for row in rows),
                "car_offense_entries": sum(flags(row)[2] for row in rows),
                "overlap": [[len(set(left["player_ids"]) & set(right["player_ids"]))
                             for right in rows] for left in rows]}

    candidate_gaps = sorted({5.0, *(max(row["mean_loss_vs_global"],
                                      row["p90_loss_vs_global"]) for row in candidates.values()
                                      if max(row["mean_loss_vs_global"],
                                             row["p90_loss_vs_global"]) >= 5)})
    portfolio_results = {}
    for label, cap_car in (("C_cap_CAR_CLE_4", True), ("D_no_CAR_CLE_cap", False)):
        at_five = portfolio(5.0, cap_car=cap_car)
        first = None
        if at_five["status"] == "optimal":
            first = {"screen_gap": 5.0, "result": at_five}
        else:
            # Monotone feasibility allows binary search over the exact candidate gaps.
            low, high = 0, len(candidate_gaps) - 1
            if portfolio(candidate_gaps[high] + 1e-6, cap_car=cap_car)["status"] == "optimal":
                while low < high:
                    mid = (low + high) // 2
                    if portfolio(candidate_gaps[mid] + 1e-6, cap_car=cap_car)["status"] == "optimal":
                        high = mid
                    else:
                        low = mid + 1
                gap = candidate_gaps[low] + 1e-6
                first = {"screen_gap": gap, "result": portfolio(gap, cap_car=cap_car)}
        portfolio_results[label] = {"at_joint_5": at_five, "first_feasible": first,
                                    "at_10": portfolio(10.0, cap_car=cap_car),
                                    "at_12": portfolio(12.0, cap_car=cap_car)}
        print(f"{label}: first {first['screen_gap'] if first else None}", flush=True)

    opportunity = {}
    for name, player_id in core_ids.items():
        player = by_id[player_id]
        raw = source[player_id]
        saved_player = frozen["saved"][player_id]
        individual_rules = []
        for row in baseline["lineups"]:
            individual_rules.append({
                "lineup_rank": row["rank"],
                "rules": [rule for rule in row["correlation_rules"]
                          if player_id in {piece.get("player_id") for piece in rule.get("players", [])}],
            })
        opportunity[name] = {
            "player_id": player_id, "team": player.team, "salary": player.salary,
            "mean": player.projection, "p90": player.ceiling,
            "value_per_1000": player.projection/(player.salary/1000),
            "ownership": player.ownership, "game_total": player.game_total,
            "team_total": player.team_total, "spread": player.spread,
            "context_adjustment_points": player.optimizer_context_adjustment,
            "context_reason_codes": saved_player.get("optimizer_context_reason_codes"),
            "projected_targets": raw.get("projected_targets"),
            "target_share_mean_3": raw.get("target_share_mean_3"),
            "role_class": raw.get("offensive_role_class"),
            "correlation_rules_by_baseline_lineup": individual_rules,
        }

    high_total_player_values = {}
    for game in ("BAL-DAL", "LAC-BUF", "CAR-CLE"):
        members = [player for player in players if player.team in GAMES[game]
                   and player.position in OFFENSE]
        high_total_player_values[game] = [
            {"name": player.name, "team": player.team, "position": player.position,
             "salary": player.salary, "mean": player.projection, "p90": player.ceiling,
             "value_per_1000": player.projection / (player.salary/1000),
             "ownership": player.ownership}
            for player in sorted(members, key=lambda player: -player.projection)[:12]
        ]

    with engine.connect() as connection:
        lineage = dict(connection.execute(text(
            "SELECT m.model_run_id, m.model_id, m.data_cutoff_at, m.params_json "
            "FROM target.player_projection p "
            "JOIN target.model_run m ON m.model_run_id=p.model_run_id "
            "WHERE p.projection_run_id=:projection_run_id LIMIT 1"
        ), {"projection_run_id": str(frozen["run"]["projection_run_id"])}).mappings().one())
    projection_model_lineage = {
        "projection_run_id": str(frozen["run"]["projection_run_id"]),
        "model_run_id": str(lineage["model_run_id"]),
        "model_id": lineage["model_id"],
        "data_cutoff_at": str(lineage["data_cutoff_at"]),
        "feature_columns": lineage["params_json"].get("feature_columns"),
    }
    for portfolio_row in (core["unrestricted"], core["all_non_qb_cap4"]):
        for row in portfolio_row["lineups"]:
            row["ownership"] = candidate_ownership(row, frozen["ownership"])

    payload = {
        "source_optimizer_run_id": RUN_ID,
        "source_data_cutoff_at": saved["source_data_cutoff_at"],
        "no_current_game_outcomes_used": True,
        "quality_maxima": {"mean": global_mean, "p90": global_p90},
        "unchanged_weights": vars(config.objective_weights),
        "game_exposure": games,
        "high_total_player_values": high_total_player_values,
        "projection_model_lineage": projection_model_lineage,
        "counterfactuals": counterfactuals,
        "opportunity": opportunity,
        "portfolio_discovery": {"saved_candidates": len(old_rows),
                                "core_new_candidates": len(core["new_exact_candidates"]),
                                "additional_requests": len(portfolio_requests),
                                "total_candidates": len(candidates)},
        "portfolios": {"A_unrestricted": baseline,
                       "B_non_QB_cap4": core["all_non_qb_cap4"],
                       **portfolio_results},
        "new_exact_candidates": [row for key, row in candidates.items() if key not in old_keys],
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, default=str, allow_nan=False) + "\n")
    print(f"saved {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
