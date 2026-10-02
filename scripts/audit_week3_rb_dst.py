#!/usr/bin/env python3
"""Frozen Week 3 RB projection and same-team RB/DST diagnostic audit."""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

from backend.app.db import engine
from backend.app.product_services.classic_small_field import describe_candidate
from backend.app.product_services.gpp_optimizer import (
    _build_lineup, build_format_specific_terms, build_lineup_correlation_terms,
)
from backend.app.product_services.rule_library import resolve_strategy_profile
from scripts.audit_sunday_main_portfolio_frontier import load_frozen


RUN_ID = "a6d7f5e7-db0f-44ae-87c4-60a826973408"
PORTFOLIO = Path("artifacts/sunday-main-clean-car-portfolio-2026w3.json")
QUALITY = Path("artifacts/sunday-main-quality-governed-portfolio-2026w3.json")
OUTPUT = Path("artifacts/week3-rb-dst-audit.json")


def clean_json(value):
    if isinstance(value, dict):
        return {str(key): clean_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(item) for item in value]
    if isinstance(value, (float, np.floating)) and not math.isfinite(value):
        return None
    if value is pd.NA:
        return None
    return value


def spread_bucket(value: float) -> str:
    if value <= -6:
        return "favorite >=6"
    if value <= -2:
        return "favorite 2–5.5"
    if value < 2:
        return "near pick'em"
    if value < 6:
        return "underdog 2–5.5"
    return "underdog >=6"


def role_class(carries: float | None, targets: float | None,
               snap: float | None = None, target_share: float | None = None) -> str:
    carries = carries or 0.0
    targets = targets or 0.0
    if targets >= 4 or (target_share or 0) >= 0.12:
        return "receiving-heavy"
    if carries >= 14 and (snap is None or snap >= 0.55):
        return "workhorse rushing"
    return "committee/other"


def correlation_summary(frame: pd.DataFrame) -> dict:
    n = len(frame)
    if n < 3 or frame.rb_points.std() == 0 or frame.dst_points.std() == 0:
        return {"n": n, "pearson_r": None, "ci95": None}
    r = float(frame.rb_points.corr(frame.dst_points))
    # Resample games rather than players because multiple backs share a DST.
    groups = [group.index.to_numpy() for _, group in frame.reset_index(drop=True).groupby(
        ["season", "week", "game_id"], sort=False)]
    rb_points = frame.rb_points.to_numpy(dtype=float)
    dst_points = frame.dst_points.to_numpy(dtype=float)
    rng = np.random.default_rng(260926)
    estimates = []
    for _ in range(500):
        sampled = rng.integers(0, len(groups), len(groups))
        positions = np.concatenate([groups[i] for i in sampled])
        if rb_points[positions].std() > 0 and dst_points[positions].std() > 0:
            estimates.append(float(np.corrcoef(rb_points[positions], dst_points[positions])[0, 1]))
    return {"n": n, "games": len(groups), "pearson_r": r,
            "ci95": [float(np.quantile(estimates, .025)),
                     float(np.quantile(estimates, .975))] if estimates else None,
            "mean_rb_points": float(frame.rb_points.mean()),
            "mean_dst_points": float(frame.dst_points.mean())}


def historical_relationship() -> dict:
    with engine.connect() as connection:
        actual = pd.read_sql(text("""
            SELECT season, week, game_id, player_id, team_id, position, dk_points,
                   carries, targets, snap_share
            FROM target.fact_player_game_actual
            WHERE position IN ('RB','DST') AND season BETWEEN 2023 AND 2025
              AND week <= 18
        """), connection)
        market = pd.read_sql(text("""
            SELECT season, week, game_id, player_master_id AS player_id,
                   team, game_total_line, team_spread_line, team_implied_total,
                   player_game_feature_matrix_id
            FROM public.player_game_feature_matrix
            WHERE position='RB' AND player_master_id IS NOT NULL
              AND season IN (2024,2025) AND week <= 18
              AND game_total_line IS NOT NULL AND team_spread_line IS NOT NULL
        """), connection)
        workload = pd.read_sql(text("""
            SELECT DISTINCT ON (raw.season, raw.week, alias.player_master_id)
                   raw.season, raw.week, alias.player_master_id AS player_id,
                   NULLIF(raw.raw_row_json ->> 'carries', '')::DOUBLE PRECISION AS carries,
                   NULLIF(raw.raw_row_json ->> 'targets', '')::DOUBLE PRECISION AS targets
            FROM public.raw_nfl_weekly_stat raw
            JOIN public.player_alias alias
              ON alias.source_system='nflreadpy' AND alias.source_key=raw.player_id
            WHERE raw.position='RB' AND raw.season BETWEEN 2023 AND 2025
              AND raw.week <= 18
            ORDER BY raw.season, raw.week, alias.player_master_id,
                     raw.created_at DESC, raw.raw_nfl_weekly_stat_id DESC
        """), connection)
    market = market.sort_values("player_game_feature_matrix_id").drop_duplicates(
        ["season", "week", "game_id", "player_id"], keep="last")
    rb = actual.loc[actual.position.eq("RB")].drop(columns=[
        "carries", "targets", "snap_share"]).merge(
            workload, on=["season", "week", "player_id"], how="left").sort_values(
        ["player_id", "season", "week", "game_id"]).copy()
    for field in ("carries", "targets"):
        rb[f"prior3_{field}"] = rb.groupby("player_id")[field].transform(
            lambda col: col.shift(1).rolling(3, min_periods=3).mean())
    rb["prior_games"] = rb.groupby("player_id").cumcount()
    dst = actual.loc[actual.position.eq("DST"),
                     ["season", "week", "game_id", "team_id", "dk_points"]].rename(
                         columns={"dk_points": "dst_points"})
    joined = market.merge(rb, on=["season", "week", "game_id", "player_id"],
                          how="inner").merge(
        dst, left_on=["season", "week", "game_id", "team"],
        right_on=["season", "week", "game_id", "team_id"], how="inner")
    joined = joined.loc[joined.prior_games.ge(3)
                        & (joined.prior3_carries.fillna(0)+joined.prior3_targets.fillna(0)).ge(3)].copy()
    joined["rb_points"] = joined.dk_points.astype(float)
    joined["spread_bucket"] = joined.team_spread_line.map(spread_bucket)
    joined["role"] = [role_class(c, t) for c,t in zip(
        joined.prior3_carries, joined.prior3_targets)]
    joined["receiving_involved"] = joined.prior3_targets.ge(3)
    return {
        "method": "2024–25 DK RB and same-team DST actuals; pregame market snapshot; prior-three-game RB usage only; game-cluster bootstrap 95% CI",
        "source_rows": {"rb_actual_2023_25": int(len(rb)),
                        "native_workload_rows": int(len(workload)),
                        "market_with_canonical_id": int(len(market)),
                        "paired_eligible": int(len(joined))},
        "overall": correlation_summary(joined),
        "by_spread": {name: correlation_summary(group)
                      for name, group in joined.groupby("spread_bucket")},
        "by_role": {name: correlation_summary(group)
                    for name, group in joined.groupby("role")},
        "by_spread_and_role": {f"{spread}|{role}": correlation_summary(group)
                               for (spread, role), group in joined.groupby(["spread_bucket", "role"])},
        "large_underdog_receiving": correlation_summary(joined.loc[
            joined.spread_bucket.eq("underdog >=6") & joined.receiving_involved]),
        "large_underdog_low_receiving": correlation_summary(joined.loc[
            joined.spread_bucket.eq("underdog >=6") & ~joined.receiving_involved]),
        "season_check": {str(season): correlation_summary(group)
                         for season, group in joined.groupby("season")},
    }


def main() -> None:
    frozen = load_frozen(RUN_ID)
    source = {str(row["player_id"]): row for row in frozen["pool"].to_dict("records")}
    players = frozen["players"]
    by_id = {player.player_id: player for player in players}
    rbs = []
    for player in players:
        if player.position != "RB":
            continue
        row = source[player.player_id]
        snap, carries, targets = (row.get(key) for key in (
            "snap_share_mean_3", "carries_mean_3", "targets_mean_3"))
        share = row.get("target_share_mean_3")
        role_grid = row.get("role_counterfactual_grid")
        strength_terms = []
        if share is not None:
            strength_terms.append(min(1, max(0, float(share)/.28)))
        if targets is not None:
            strength_terms.append(min(1, max(0, float(targets)/8)))
        if row.get("pregame_expected_routes") is not None:
            strength_terms.append(min(1, max(0, float(row["pregame_expected_routes"])/32)))
        rbs.append({
            "player_id": player.player_id, "name": player.name, "team": player.team,
            "salary": player.salary, "mean": player.projection, "p90": player.ceiling,
            "role_class": row.get("offensive_role_class"),
            "workload_class": role_class(carries, targets, snap, share),
            "snap_share_mean_3": snap, "carries_mean_3": carries,
            "targets_mean_3": targets, "target_share_mean_3": share,
            "receiving_role_strength": max(strength_terms, default=None),
            "team_implied_total": row.get("team_implied_total"),
            "spread": row.get("team_spread_line"), "game_total": row.get("game_total_line"),
            "home_away": None,
            "recent_trend": {key: row.get(key) for key in (
                "snap_share_last", "snap_share_prior3", "snap_share_trend",
                "rush_share_last", "rush_share_prior3", "rush_share_trend",
                "target_share_last", "target_share_prior3", "target_share_trend")},
            "role_counterfactual_grid": role_grid,
        })
    # The frozen game key begins with AWAY@HOME, followed by kickoff text.
    for rb in rbs:
        game_id = str(by_id[rb["player_id"]].game_id or "").split(" ", 1)[0]
        teams = game_id.split("@")
        rb["home_away"] = "home" if len(teams) == 2 and teams[1] == rb["team"] else (
            "away" if len(teams) == 2 and teams[0] == rb["team"] else "unavailable")
    rbs.sort(key=lambda row: -row["mean"])
    material = [row for row in rbs if row["mean"] >= 9 or row["salary"] >= 6000
                or (row["carries_mean_3"] or 0) >= 10
                or (row["targets_mean_3"] or 0) >= 3]

    with engine.connect() as connection:
        model = dict(connection.execute(text("""
            SELECT registry.model_version, registry.model_name, registry.artifact_uri,
                   run.model_run_id, run.params_json -> 'feature_columns' AS feature_columns
            FROM target.player_projection projection
            JOIN target.model_run run USING (model_run_id)
            JOIN target.model_registry registry USING (model_id)
            WHERE projection.projection_run_id=:projection_run_id LIMIT 1
        """), {"projection_run_id": str(frozen["run"]["projection_run_id"])}).mappings().one())
    for rb in rbs:
        rb["model_version"] = model["model_version"]
    portfolio = json.loads(PORTFOLIO.read_text())
    quality = json.loads(QUALITY.read_text())
    universe = {tuple(sorted(row["player_ids"])): row
                for row in quality["candidates"] + portfolio["new_exact_candidates"]}
    same_team = []
    for row in universe.values():
        dst = next(p for p in row["roster"] if p["position"] == "DST")
        for member in row["roster"]:
            if member["position"] != "RB" or member["team"] != dst["team"]:
                continue
            player = by_id[member["player_id"]]
            evidence = source[player.player_id]
            rule = [rule for rule in row["correlation_rules"]
                    if rule.get("reason_code") == "same_team_running_back_dst"
                    and {p.get("player_id") for p in rule.get("players", [])} >=
                    {player.player_id, dst["player_id"]}]
            same_team.append({"rb": player.name, "dst": dst["name"],
                "rank": row.get("rank"), "player_ids": row["player_ids"],
                "spread": player.spread, "bucket": spread_bucket(float(player.spread)),
                "team_total": player.team_total,
                "opponent_total": (player.game_total-player.team_total
                                   if player.game_total and player.team_total else None),
                "rushing_role": evidence.get("carries_mean_3"),
                "receiving_role": evidence.get("targets_mean_3"),
                "role": role_class(evidence.get("carries_mean_3"),
                                   evidence.get("targets_mean_3"),
                                   evidence.get("snap_share_mean_3"),
                                   evidence.get("target_share_mean_3")),
                "correlation_bonus": sum(float(r.get("objective_contribution") or 0) for r in rule),
                "correlation_rules": rule, "mean": row["mean"], "p90": row["p90"],
                "selector": row["objective_score"], "favorite": player.spread < 0})

    current = portfolio["C_car_free_entry"]
    c_rows = portfolio["portfolios"]["C_clean_car"]["lineups"]
    other_lineups = [row for row in c_rows
                     if row["qb"]["name"] != current["qb"]["name"]]
    index_by_id = {player.player_id: i for i, player in enumerate(players)}
    previous = [{index_by_id[pid] for pid in row["player_ids"]} for row in other_lineups]
    base_bans = {player.player_id for player in players
                 if player.team in {"CAR", "CLE"} and player.position in {"QB", "RB", "WR", "TE"}}
    exposure = Counter(pid for row in other_lineups for pid in row["player_ids"])
    base_bans |= {pid for pid,count in exposure.items()
                  if count >= 4 and by_id[pid].position != "QB"}
    profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
    correlation_terms = build_lineup_correlation_terms(players, profile=profile)
    format_terms = build_format_specific_terms(players, profile=profile)
    game_totals = sorted({float(p.game_total) for p in players if p.game_total is not None})
    shough_id = current["qb"]["player_id"]
    configs = {
        "A_current": set(),
        "B_no_achane": {p.player_id for p in players if p.name == "De'Von Achane"},
        "C_no_dolphins_dst": {p.player_id for p in players if p.team == "MIA" and p.position == "DST"},
        "D_no_mia_offense": {p.player_id for p in players if p.team == "MIA" and p.position in {"QB","RB","WR","TE"}},
        "E_no_mia_players": {p.player_id for p in players if p.team == "MIA"},
    }
    alternatives = {}
    for label, extra_bans in configs.items():
        if label == "A_current":
            alternatives[label] = {"status": "current", "lineup": current,
                                   "minimum_joint_gap": max(current["mean_loss_vs_global"],
                                                            current["p90_loss_vs_global"])}
            continue
        bans = base_bans | extra_bans
        def solve(gap: float | None) -> dict | None:
            indexes = _build_lineup(
                players, replace(frozen["config"], uniqueness_overlap=6),
                {pid: 0 for pid in bans}, previous,
                required_player_ids={shough_id},
                minimum_mean=(quality["global_mean"]-gap if gap is not None else None),
                minimum_p90=(quality["global_p90"]-gap if gap is not None else None),
                enforce_single_te=bool(frozen["params"]["enforce_single_te"]),
                avoid_dst_opponents=bool(frozen["params"]["avoid_dst_opponents"]),
                precomputed_correlation_terms=correlation_terms,
                precomputed_format_terms=format_terms,
            )
            return (describe_candidate([players[i] for i in indexes],
                all_players=players, config=frozen["config"], pool_by_id=source,
                ownership_available=False, candidate_aware_ownership=True,
                game_totals=game_totals) if indexes is not None else None)
        screen = solve(5.04)
        unrestricted = screen or solve(None)
        closest = screen
        if closest is None and unrestricted is not None:
            lower = 5.04
            upper = max(quality["global_mean"]-unrestricted["mean"],
                        quality["global_p90"]-unrestricted["p90"]) + 0.01
            for _ in range(12):
                middle = (lower+upper)/2
                attempt = solve(middle)
                if attempt is None:
                    lower = middle
                else:
                    upper, closest = middle, attempt
        alternatives[label] = {"status": "feasible_at_5_04" if screen else
                               "infeasible_at_5_04", "lineup": closest,
                               "minimum_joint_gap": (max(quality["global_mean"]-closest["mean"],
                                                        quality["global_p90"]-closest["p90"])
                                                     if closest else None),
                               "unrestricted_selector_lineup": unrestricted,
                               "selector_delta_vs_current": (closest["objective_score"]-current["objective_score"]
                                                             if closest else None),
                               "mean_delta_vs_current": (closest["mean"]-current["mean"]
                                                         if closest else None),
                               "p90_delta_vs_current": (closest["p90"]-current["p90"]
                                                       if closest else None)}
        print(label, alternatives[label]["status"], flush=True)

    payload = {"source_optimizer_run_id": RUN_ID,
               "source_projection_run_id": str(frozen["run"]["projection_run_id"]),
               "source_data_cutoff_at": str(frozen["run"]["data_cutoff_at"]),
               "model": model, "rb_material_count": len(material),
               "rb_all": rbs, "rb_material": material,
               "espn_week3_benchmark": {"status": "unavailable",
                   "reason": "No saved Week 3 ESPN projection/value capture found in project artifacts; Week 2 capture is a different slate and is not compared."},
               "saved_walk_forward_rb_role_calibration": {
                   key: value for key, value in (
                       next((row.get("historical_role_calibration") for row in source.values()
                             if isinstance(row.get("historical_role_calibration"), dict)), {})
                       .get("by_position_and_role_class", {})
                   ).items() if key.startswith("RB|")
               },
               "candidate_universe_count": len(universe),
               "same_team_rb_dst": same_team,
               "same_team_rb_dst_counts": dict(Counter(row["bucket"] for row in same_team)),
               "historical": historical_relationship(),
               "achane_alternatives": alternatives,
               "no_week3_outcomes_used": True,
               "production_weights_unchanged": True}
    OUTPUT.write_text(json.dumps(clean_json(payload), indent=2, default=str,
                                 allow_nan=False)+"\n")
    print(f"saved {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
