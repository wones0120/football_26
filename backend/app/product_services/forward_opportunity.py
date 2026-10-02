"""Point-in-time shadow forecasts of NFL opportunities and scoring components.

This module does not alter canonical projections. Every historical evaluation call
filters observations to games before the game being predicted. Missing current
usage and red-zone evidence remains explicit in the output.
"""

from __future__ import annotations

from collections import defaultdict
from math import isfinite
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SKILL = {"RB", "WR", "TE"}
TEAM_FEATURES = ["pass_mean3", "pass_mean8", "rush_mean3", "rush_mean8",
                 "td_mean8", "target_rate8", "rb_carry_rate8",
                 "team_implied_total", "team_spread_line", "game_total_line"]
TEAM_TARGETS = ("pass_attempts", "rush_attempts", "offensive_tds")
STAT_COLUMNS = ("attempts", "completions", "passing_yards", "passing_tds",
                "passing_interceptions", "carries", "rushing_yards", "rushing_tds",
                "targets", "receptions", "receiving_yards", "receiving_tds")


def _float(value: Any) -> float | None:
    try:
        number = float(value)
        return number if isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _positive_float(value: Any) -> float | None:
    number = _float(value)
    return number if number is not None and number > 0 else None


def _period(frame: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(frame["season"]).astype(int) * 100 + pd.to_numeric(frame["week"]).astype(int)


def prepare_weekly_stats(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize native-ID rows; never infer identity from display names."""
    required = {"season", "week", "team", "position", *STAT_COLUMNS}
    missing = sorted(required - set(raw))
    if missing:
        raise ValueError("Weekly stats lack component fields: " + ", ".join(missing))
    frame = raw.copy()
    frame["team"] = frame["team"].fillna("").astype(str).str.upper()
    frame["position"] = frame["position"].fillna("").astype(str).str.upper()
    frame["period"] = _period(frame)
    for field in STAT_COLUMNS:
        frame[field] = pd.to_numeric(frame[field], errors="coerce")
    # A source field that exists but is null is unavailable, not a measured zero.
    return frame


def team_games_from_weekly(stats: pd.DataFrame) -> pd.DataFrame:
    """Observed team volume; plays exclude sacks/kneels and are labeled a proxy."""
    skill = stats.loc[stats["position"].isin({"QB", "RB", "WR", "TE"})].copy()
    skill["qb_attempts"] = skill["attempts"].where(skill["position"].eq("QB"), 0)
    skill["rb_carries"] = skill["carries"].where(skill["position"].eq("RB"), 0)
    skill["skill_targets"] = skill["targets"].where(skill["position"].isin(SKILL), 0)
    grouped = skill.groupby(["season", "week", "period", "team"], as_index=False).agg(
        pass_attempts=("qb_attempts", "sum"), rush_attempts=("carries", "sum"),
        targets=("skill_targets", "sum"), rb_carries=("rb_carries", "sum"),
        pass_tds=("passing_tds", "sum"), rush_tds=("rushing_tds", "sum"),
    )
    grouped["offensive_plays_proxy"] = grouped["pass_attempts"] + grouped["rush_attempts"]
    grouped["offensive_tds"] = grouped["pass_tds"] + grouped["rush_tds"]
    return grouped


def _team_feature_from_games(games: list[dict], context: dict) -> dict:
    """Lagged team inputs from a short chronological game history."""
    recent = games[-8:]
    last3 = games[-3:]
    def mean(rows, key):
        return float(sum(float(row[key]) for row in rows) / len(rows)) if rows else None
    attempts = sum(float(row["pass_attempts"]) for row in recent)
    rushes = sum(float(row["rush_attempts"]) for row in recent)
    return {
        "pass_mean3": mean(last3, "pass_attempts"),
        "pass_mean8": mean(recent, "pass_attempts"),
        "rush_mean3": mean(last3, "rush_attempts"),
        "rush_mean8": mean(recent, "rush_attempts"),
        "td_mean8": mean(recent, "offensive_tds"),
        "target_rate8": sum(float(row["targets"]) for row in recent) / attempts if attempts > 0 else None,
        "rb_carry_rate8": sum(float(row["rb_carries"]) for row in recent) / rushes if rushes > 0 else None,
        "team_implied_total": _positive_float(context.get("team_implied_total")),
        "team_spread_line": _float(context.get("team_spread_line")),
        "game_total_line": _positive_float(context.get("game_total_line")),
        "history_games": len(games),
        "last_observed_period": int(games[-1]["period"]) if games else None,
    }


def _context_by_team(rows: pd.DataFrame) -> pd.DataFrame:
    frame = rows.copy()
    if "recent_team" in frame:
        frame["team"] = frame["recent_team"]
    frame["team"] = frame["team"].fillna("").astype(str).str.upper()
    frame["period"] = _period(frame)
    for field in ("team_implied_total", "team_spread_line", "game_total_line"):
        if field not in frame:
            frame[field] = np.nan
    return frame.sort_values(["period", "team"]).drop_duplicates(["period", "team"], keep="last")


def forecast_team_volumes(
    weekly: pd.DataFrame, contexts: pd.DataFrame, target_context: pd.DataFrame,
    *, period: int,
) -> dict[str, dict]:
    """Ridge forecasts trained on earlier team games with lagged volume features."""
    history = team_games_from_weekly(weekly.loc[weekly["period"] < period])
    if history.empty:
        return {}
    context = _context_by_team(contexts)
    context = context.loc[context["period"] < period]
    rows = []
    markets = {(int(row["period"]), row["team"]): row
               for row in context.to_dict("records")}
    for team, games in history.groupby("team"):
        seen: list[dict] = []
        for game in games.sort_values("period").to_dict("records"):
            if len(seen) >= 3:
                values = _team_feature_from_games(
                    seen, markets.get((int(game["period"]), team), {}))
                rows.append({**values, **{key: game[key] for key in TEAM_TARGETS}})
            seen.append(game)
    training = pd.DataFrame(rows)
    requested = _context_by_team(target_context)
    result = {}
    for team, team_rows in requested.groupby("team"):
        if not team or team_rows.empty:
            continue
        values = _team_feature_from_games(
            history.loc[history["team"].eq(team)].sort_values("period").to_dict("records"),
            team_rows.iloc[0].to_dict())
        if values["history_games"] < 3 or len(training) < 100:
            result[team] = {"status": "unavailable", "reason": "fewer than three team games or 100 training examples",
                            "features": values}
            continue
        columns = [key for key in TEAM_FEATURES if values[key] is not None
                   and key in training and training[key].notna().sum() >= 100]
        if not {"pass_mean3", "rush_mean3"}.issubset(columns):
            result[team] = {"status": "unavailable", "reason": "lagged team volume unavailable",
                            "features": values}
            continue
        fit = training.dropna(subset=columns + list(TEAM_TARGETS))
        if len(fit) < 100:
            result[team] = {"status": "unavailable", "reason": "insufficient complete training context",
                            "features": values}
            continue
        forecast = {}
        for label in TEAM_TARGETS:
            model = make_pipeline(StandardScaler(), Ridge(alpha=30.0))
            model.fit(fit[columns], fit[label])
            raw = float(model.predict(pd.DataFrame([values])[columns])[0])
            low, high = fit[label].quantile([0.01, 0.99])
            forecast[label] = max(0.0, float(np.clip(raw, low, high)))
        forecast["offensive_plays_proxy"] = forecast["pass_attempts"] + forecast["rush_attempts"]
        forecast["targets_per_pass_attempt"] = values["target_rate8"]
        forecast["rb_carries_per_rush_attempt"] = values["rb_carry_rate8"]
        recent = history.loc[history["team"].eq(team)].tail(8)
        total_td = float(recent["offensive_tds"].sum())
        forecast["pass_td_fraction"] = (float(recent["pass_tds"].sum()) / total_td
                                        if total_td > 0 else None)
        forecast.update(status="available", model="standardized ridge from prior team games",
                        features=values, feature_columns=columns,
                        volume_confidence="medium" if values["last_observed_period"] // 100 == period // 100 else "low",
                        touchdown_confidence="low: no red-zone or goal-line evidence")
        result[team] = forecast
    return result


def _player_history(weekly: pd.DataFrame, player_id: str, period: int,
                    team: str | None = None) -> pd.DataFrame:
    selected = weekly["player_master_id"].astype(str).eq(player_id) & weekly["period"].lt(period)
    if team is not None:
        selected &= weekly["team"].eq(team)
    return weekly.loc[selected].sort_values("period")


def _blend_role_share(values: pd.Series) -> dict:
    observed = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if observed.empty:
        return {"forecast": None, "baseline8": None, "recent3": None,
                "last": None, "weights": None, "games": 0}
    baseline = float(observed.tail(8).mean())
    recent = float(observed.tail(3).mean())
    last = float(observed.iloc[-1])
    if len(observed) >= 8:
        weights = {"baseline8": 0.4, "recent3": 0.45, "last": 0.15}
    elif len(observed) >= 3:
        weights = {"baseline8": 0.25, "recent3": 0.6, "last": 0.15}
    else:
        weights = {"baseline8": 0.0, "recent3": 0.85, "last": 0.15}
    forecast = sum(weights[key] * value for key, value in
                   (("baseline8", baseline), ("recent3", recent), ("last", last)))
    return {"forecast": forecast, "baseline8": baseline, "recent3": recent,
            "last": last, "weights": weights, "games": len(observed)}


def forecast_player_opportunities(
    weekly: pd.DataFrame, targets: pd.DataFrame, team_forecasts: dict[str, dict],
    *, period: int,
) -> tuple[list[dict], dict[str, dict]]:
    """Monotonic role-weight allocation with explicit unallocated opportunity."""
    historical = weekly.loc[weekly["period"] < period].copy()
    games = team_games_from_weekly(historical)
    historical = historical.merge(games[["period", "team", "targets", "rb_carries", "rush_attempts", "pass_attempts"]],
                                  on=["period", "team"], suffixes=("", "_team"), how="left")
    historical["target_share_game"] = np.where(historical["targets_team"] > 0,
                                                historical["targets"] / historical["targets_team"], np.nan)
    historical["rb_carry_share_game"] = np.where(
        historical["rb_carries"] > 0,
        historical["carries"] / historical["rb_carries"], np.nan)
    historical["qb_attempt_share_game"] = np.where(
        historical["pass_attempts"] > 0,
        historical["attempts"] / historical["pass_attempts"], np.nan)
    player_histories = {
        (str(player_id), team): group.sort_values("period")
        for (player_id, team), group in historical.loc[historical["player_master_id"].notna()]
            .groupby(["player_master_id", "team"])
    }
    rows = []
    for target in targets.to_dict("records"):
        player_id = str(target.get("player_id") or "")
        team = str(target.get("recent_team") or target.get("team") or "").upper()
        position = str(target.get("position") or "").upper()
        if position not in SKILL | {"QB"} or team not in team_forecasts:
            continue
        team_forecast = team_forecasts[team]
        if team_forecast.get("status") != "available":
            continue
        player_history = player_histories.get((player_id, team))
        if player_history is None:
            player_history = historical.iloc[:0]
        target_share = _blend_role_share(player_history["target_share_game"] if position in SKILL else pd.Series(dtype=float))
        carry_share = _blend_role_share(player_history["rb_carry_share_game"] if position == "RB" else pd.Series(dtype=float))
        qb_share = _blend_role_share(player_history["qb_attempt_share_game"] if position == "QB" else pd.Series(dtype=float))
        importance = _float(target.get("offensive_role_importance"))
        completeness = _float(target.get("offensive_role_completeness")) or 0.0
        role_factor = 1.0 + 0.3 * (importance or 0.0) * completeness
        supplied_availability = _float(target.get("pregame_availability_probability"))
        availability = float(np.clip(supplied_availability, 0, 1)) if supplied_availability is not None else 1.0
        snap_trend = _float(target.get("snap_share_trend"))
        snap_factor = 1.0 + 0.2 * float(np.clip(snap_trend, -0.2, 0.2)) if snap_trend is not None else 1.0
        explicit_target_share = _float(target.get("pregame_effective_target_share"))
        explicit_carry_share = _float(target.get("pregame_effective_carry_share"))
        target_weight = (explicit_target_share if explicit_target_share is not None else target_share["forecast"])
        carry_weight = (explicit_carry_share if explicit_carry_share is not None else carry_share["forecast"])
        target_weight = max(0.0, target_weight * role_factor * snap_factor * availability) if target_weight is not None else None
        carry_weight = max(0.0, carry_weight * role_factor * snap_factor * availability) if carry_weight is not None else None
        qb_rush = _blend_role_share(
            player_history["carries"] / player_history["rush_attempts"].replace(0, np.nan)
            if position == "QB" and not player_history.empty else pd.Series(dtype=float)
        )
        other_rush = _blend_role_share(
            player_history["carries"] / player_history["rush_attempts"].replace(0, np.nan)
            if position in {"WR", "TE"} and not player_history.empty else pd.Series(dtype=float)
        )
        rows.append({"player_id": player_id, "team": team, "position": position,
                     "name": target.get("player_display_name") or target.get("name"),
                     "role_importance": importance, "role_completeness": completeness,
                     "role_factor": role_factor, "snap_trend_factor": snap_factor,
                     "target_share_blend": target_share, "carry_share_blend": carry_share,
                     "qb_attempt_share_blend": qb_share,
                     "qb_rush_share_blend": qb_rush,
                     "other_rush_share_blend": other_rush,
                     "explicit_target_share": explicit_target_share,
                     "explicit_carry_share": explicit_carry_share,
                     "target_weight": target_weight, "carry_weight": carry_weight,
                     "last_opportunity_period": int(player_history.iloc[-1]["period"]) if not player_history.empty else None,
                     "opportunity_confidence": ("medium" if len(player_history) >= 3
                        and int(player_history.iloc[-1]["period"]) // 100 == period // 100 else "low"),
                     "expected_targets": None, "expected_carries": None,
                     "expected_qb_attempts": None,
                     "availability": availability,
                     "availability_evidence": ("explicit pregame probability" if supplied_availability is not None
                                               else "unavailable; forecast conditional on active participation"),
                     "source": "lagged player usage blended with learned team-volume forecast",
                     "context_adjustment": "explicit pregame share" if explicit_target_share is not None or explicit_carry_share is not None else "none",
                     "team_implied_total": _float(target.get("team_implied_total")),
                     "salary": _float(target.get("salary")),
                     "direct_mean": _float(target.get("predicted_mean")),
                     "direct_p90": _float(target.get("predicted_p90"))})
    reconciliation = {}
    by_team: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_team[row["team"]].append(row)
    for team, members in by_team.items():
        forecast = team_forecasts[team]
        target_budget = (forecast["pass_attempts"] * forecast["targets_per_pass_attempt"]
                         if forecast["targets_per_pass_attempt"] is not None else None)
        rb_budget = (forecast["rush_attempts"] * forecast["rb_carries_per_rush_attempt"]
                     if forecast["rb_carries_per_rush_attempt"] is not None else None)
        forecast["target_budget"] = target_budget
        forecast["rb_carry_budget"] = rb_budget
        for weight_key, budget, output in (("target_weight", target_budget, "expected_targets"),
                                           ("carry_weight", rb_budget, "expected_carries")):
            weights = [row[weight_key] or 0.0 for row in members]
            total_weight = sum(weights)
            for row in members:
                row[output] = (budget * (row[weight_key] or 0.0) / max(1.0, total_weight)
                               if budget is not None and row[weight_key] is not None else None)
        qb_weights = [row["qb_attempt_share_blend"]["forecast"] or 0.0 for row in members if row["position"] == "QB"]
        qb_total = sum(qb_weights)
        for row in members:
            if row["position"] == "QB" and row["qb_attempt_share_blend"]["forecast"] is not None:
                row["expected_qb_attempts"] = (forecast["pass_attempts"] * row["qb_attempt_share_blend"]["forecast"]
                                               * row["availability"] / max(1.0, qb_total))
                qb_rush_share = row["qb_rush_share_blend"]["forecast"]
                row["expected_carries"] = (forecast["rush_attempts"] * qb_rush_share * row["availability"]
                                           if qb_rush_share is not None else None)
            if row["position"] in {"WR", "TE"}:
                other_share = row["other_rush_share_blend"]["forecast"]
                row["expected_carries"] = (forecast["rush_attempts"] * other_share * row["availability"]
                                           if other_share is not None else None)
        rb_allocated = sum(row["expected_carries"] or 0.0 for row in members if row["position"] == "RB")
        non_rb = [row for row in members if row["position"] in {"QB", "WR", "TE"}]
        non_rb_total = sum(row["expected_carries"] or 0.0 for row in non_rb)
        remaining_rush = max(0.0, forecast["rush_attempts"] - rb_allocated)
        if non_rb_total > remaining_rush:
            for row in non_rb:
                if row["expected_carries"] is not None:
                    row["expected_carries"] *= remaining_rush / non_rb_total
        allocated_targets = sum(row["expected_targets"] or 0.0 for row in members)
        allocated_rb_carries = sum(row["expected_carries"] or 0.0 for row in members if row["position"] == "RB")
        allocated_qb_carries = sum(row["expected_carries"] or 0.0 for row in members if row["position"] == "QB")
        allocated_other_carries = sum(row["expected_carries"] or 0.0 for row in members if row["position"] in {"WR", "TE"})
        unallocated_rush = max(0.0, forecast["rush_attempts"] - rb_allocated - allocated_qb_carries - allocated_other_carries)
        reconciliation[team] = {"expected_pass_attempts": forecast["pass_attempts"],
                                "expected_rush_attempts": forecast["rush_attempts"],
                                "expected_offensive_plays_proxy": forecast["offensive_plays_proxy"],
                                "target_budget": target_budget, "allocated_targets": allocated_targets,
                                "unallocated_targets": max(0.0, target_budget - allocated_targets) if target_budget is not None else None,
                                "rb_carry_budget": rb_budget, "allocated_rb_carries": allocated_rb_carries,
                                "unallocated_rb_carries": max(0.0, rb_budget - allocated_rb_carries) if rb_budget is not None else None,
                                "other_rush_budget": forecast["rush_attempts"] - rb_budget if rb_budget is not None else None,
                                "allocated_qb_carries": allocated_qb_carries,
                                "allocated_wr_te_carries": allocated_other_carries,
                                "unallocated_rush_attempts": unallocated_rush,
                                "team_offensive_tds": forecast["offensive_tds"],
                                "touchdown_confidence": forecast["touchdown_confidence"],
                                "volume_confidence": forecast["volume_confidence"],
                                "last_observed_period": forecast["features"]["last_observed_period"]}
    return rows, reconciliation


def _rates(weekly: pd.DataFrame, position: str, player_id: str, period: int,
           player_groups=None, position_groups=None, peer_rates=None) -> dict | None:
    prior = weekly.loc[weekly["period"] < period] if player_groups is None else None
    player = (_player_history(prior, player_id, period).tail(8) if player_groups is None
              else player_groups.get(player_id, weekly.iloc[:0]).tail(8))
    peer = (prior.loc[prior["position"].eq(position)] if position_groups is None
            else position_groups.get(position, weekly.iloc[:0]))
    if player.empty or peer.empty:
        return None
    def ratio(numerator: str, denominator: str, default: float = 0.0) -> float:
        if peer_rates is not None:
            global_rate = peer_rates.get((position, numerator, denominator), default)
        else:
            global_denominator = float(peer[denominator].sum())
            global_rate = float(peer[numerator].sum() / global_denominator) if global_denominator > 0 else default
        player_denominator = float(player[denominator].sum())
        player_numerator = float(player[numerator].sum())
        return (player_numerator + 20 * global_rate) / (player_denominator + 20)
    return {"rush_yards_per_carry": ratio("rushing_yards", "carries"),
            "catch_rate": float(np.clip(ratio("receptions", "targets"), 0, 1)),
            "receive_yards_per_target": ratio("receiving_yards", "targets"),
            "pass_yards_per_attempt": ratio("passing_yards", "attempts"),
            "pass_completion_rate": float(np.clip(ratio("completions", "attempts"), 0, 1)),
            "interception_rate": float(np.clip(ratio("passing_interceptions", "attempts"), 0, 1)),
            "games": len(player)}


def project_components(weekly: pd.DataFrame, opportunities: list[dict], teams: dict[str, dict], *, period: int) -> list[dict]:
    """Build DraftKings component means with low-confidence team-level TD allocation."""
    by_team: dict[str, list[dict]] = defaultdict(list)
    for row in opportunities:
        by_team[row["team"]].append(row)
    prior = weekly.loc[weekly["period"] < period]
    player_groups = {str(key): group for key, group in
                     prior.loc[prior["player_master_id"].notna()].groupby("player_master_id")}
    position_groups = {str(key): group for key, group in prior.groupby("position")}
    rate_pairs = (("rushing_yards", "carries"), ("receptions", "targets"),
                  ("receiving_yards", "targets"), ("passing_yards", "attempts"),
                  ("completions", "attempts"), ("passing_interceptions", "attempts"))
    peer_rates = {}
    for position, peers in position_groups.items():
        for numerator, denominator in rate_pairs:
            count = float(peers[denominator].sum())
            peer_rates[(position, numerator, denominator)] = (
                float(peers[numerator].sum()) / count if count > 0 else 0.0)
    output = []
    for row in opportunities:
        rates = _rates(weekly, row["position"], row["player_id"], period,
                       player_groups, position_groups, peer_rates)
        if rates is None:
            output.append({**row, "component_status": "unavailable", "reason": "no prior canonical player efficiency"})
            continue
        team = teams[row["team"]]
        pass_fraction = team.get("pass_td_fraction")
        if pass_fraction is None:
            output.append({**row, "component_status": "unavailable", "reason": "team touchdown split unavailable"})
            continue
        team_pass_tds = team["offensive_tds"] * pass_fraction
        team_rush_tds = team["offensive_tds"] * (1 - pass_fraction)
        members = by_team[row["team"]]
        target_total = max(team.get("target_budget") or 0.0,
                           sum(item["expected_targets"] or 0 for item in members))
        rush_total = team["rush_attempts"]
        targets = row["expected_targets"] or 0.0
        carries = row["expected_carries"] or 0.0
        target_td_share = targets / target_total if target_total > 0 else 0.0
        carry_td_share = carries / rush_total if rush_total > 0 else 0.0
        receiving_tds = team_pass_tds * target_td_share if row["position"] in SKILL else 0.0
        rushing_tds = team_rush_tds * carry_td_share if row["position"] in {"RB", "QB", "WR", "TE"} else 0.0
        passing_tds = team_pass_tds * ((row["expected_qb_attempts"] or 0) / team["pass_attempts"])
        passing_yards = (row["expected_qb_attempts"] or 0) * rates["pass_yards_per_attempt"]
        interceptions = (row["expected_qb_attempts"] or 0) * rates["interception_rate"]
        receptions = targets * rates["catch_rate"]
        receiving_yards = targets * rates["receive_yards_per_target"]
        rushing_yards = carries * rates["rush_yards_per_carry"]
        # Component means omit nonlinear 100/300-yard bonuses and rare 2PT/fumble events;
        # the direct-model residual in the hybrid can absorb their expectation.
        points = (passing_yards * 0.04 + passing_tds * 4 - interceptions
                  + rushing_yards * 0.1 + rushing_tds * 6
                  + receptions + receiving_yards * 0.1 + receiving_tds * 6)
        direct = row.get("direct_mean")
        output.append({**row, "component_status": "available", "efficiency": rates,
                       "components": {"expected_pass_attempts": row["expected_qb_attempts"],
                                      "completions": (row["expected_qb_attempts"] or 0) * rates["pass_completion_rate"],
                                      "passing_yards": passing_yards, "passing_tds": passing_tds,
                                      "interceptions": interceptions, "carries": row["expected_carries"],
                                      "rushing_yards": rushing_yards, "rushing_tds": rushing_tds,
                                      "targets": row["expected_targets"], "receptions": receptions,
                                      "receiving_yards": receiving_yards, "receiving_tds": receiving_tds},
                       "component_mean": max(0.0, points),
                       "hybrid_mean": 0.5 * max(0.0, points) + 0.5 * direct if direct is not None else None,
                       "hybrid_weight": 0.5, "touchdown_source": "team TD forecast and opportunity shares; no red-zone evidence",
                       "touchdown_confidence": "low"})
    return output


def opportunity_sanity(opportunities: list[dict], reconciliation: dict[str, dict]) -> list[dict]:
    """Flag workload mismatches without changing the forecast or lineup rules."""
    flags: list[dict] = []
    for team, budget in reconciliation.items():
        if budget["allocated_targets"] > (budget["target_budget"] or 0) + 1e-6:
            flags.append({"team": team, "code": "targets_exceed_budget"})
        used_rush = (budget["allocated_rb_carries"] + budget["allocated_qb_carries"]
                     + budget["allocated_wr_te_carries"])
        if used_rush > budget["expected_rush_attempts"] + 1e-6:
            flags.append({"team": team, "code": "rushes_exceed_budget"})
        members = [row for row in opportunities if row["team"] == team]
        for position, field, role_threshold, workload_threshold, code in (
            ("RB", "expected_carries", 0.6, 0.2, "central_rb_low_carries"),
            ("WR", "expected_targets", 0.6, 0.15, "primary_wr_low_targets"),
        ):
            peers = [row for row in members if row["position"] == position
                     and row["role_importance"] is not None and row[field] is not None]
            if not peers:
                continue
            available = (budget["rb_carry_budget"] if position == "RB"
                         else budget["target_budget"])
            if not available:
                continue
            highest = max(peers, key=lambda row: row["role_importance"])
            if highest["role_importance"] >= role_threshold and highest[field] < available * workload_threshold:
                flags.append({"team": team, "player_id": highest["player_id"], "code": code,
                              "role_importance": highest["role_importance"],
                              "expected_opportunities": highest[field],
                              "team_budget": available,
                              "note": "Check recent usage, health, and teammates; this is diagnostic only"})
            for peer in peers:
                if (peer["player_id"] != highest["player_id"]
                    and peer["role_importance"] + 0.2 < highest["role_importance"]
                    and peer[field] > highest[field] * 1.5):
                    flags.append({"team": team, "player_id": peer["player_id"],
                                  "comparison_player_id": highest["player_id"],
                                  "code": "secondary_exceeds_centerpiece",
                                  "expected_opportunities": peer[field],
                                  "centerpiece_expected_opportunities": highest[field],
                                  "note": "Compare measured shares and pregame role evidence"})
    return flags
