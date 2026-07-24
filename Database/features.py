"\"\"\"Feature engineering for player-week predictions.\"\"\""

from __future__ import annotations

import logging
from typing import Iterable

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

from .config import get_connection_string
from .operations import delete_from_postgres, ensure_table_columns
from .scoring import compute_dk_scoring


ROLLING_WINDOWS = (3, 5)
EXTENDED_WINDOWS = (3, 5, 8)
SHORT_OPP_WINDOWS = (4, 8)


def _rolling_slope(series: pd.Series) -> float:
    """Compute simple slope of a sequence; returns 0.0 if insufficient data."""
    valid = series.dropna()
    n = len(valid)
    if n < 2:
        return 0.0
    x = np.arange(n)
    try:
        slope, _ = np.polyfit(x, valid.values.astype(float), 1)
        return float(slope)
    except Exception:
        return 0.0


def _safe_div(numer: pd.Series, denom: pd.Series) -> pd.Series:
    if not isinstance(numer, pd.Series):
        numer = pd.Series(numer)
    if not isinstance(denom, pd.Series):
        denom = pd.Series(denom)
    numer_safe = pd.to_numeric(numer, errors="coerce")
    denom_safe = pd.to_numeric(denom, errors="coerce").replace({0: pd.NA})
    result = numer_safe / denom_safe
    return result.astype("Float64")


def _to_numeric(series: pd.Series, default: float = 0.0) -> pd.Series:
    """Coerce to numeric with a fallback fill."""
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _coerce_numeric(df: pd.DataFrame, cols: list[str], default: float = 0.0) -> pd.DataFrame:
    for col in cols:
        if col in df.columns:
            df[col] = _to_numeric(df[col], default=default)
    return df


def _coerce_str(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for col in cols:
        if col in df.columns:
            df[col] = df[col].astype(str).fillna("")
        else:
            df[col] = ""
    return df


# Columns we may reference in feature computation; ensure existence to avoid KeyErrors
FEATURE_INPUT_COLS = [
    "player_id",
    "dk_player_id",
    "season",
    "week",
    "position",
    "position_group",
    "recent_team",
    "opponent_team",
    "player_display_name",
    "dk_total_points",
    "targets",
    "carries",
    "rush_attempts",
    "pass_attempts",
    "attempts",
    "snaps",
    "offense_snaps",
    "offensive_snaps",
    "team_snaps",
    "routes_run",
    "routes",
    "air_yards",
    "airyards",
    "pass_yards",
    "rush_yards",
    "rec_yards",
    "touchdowns",
    "total_tds",
    "rz_touches",
    "big_play",
    "explosive_plays",
    "pass_rate_neutral",
    "pass_rate_trailing",
    "pass_rate_leading",
    "proe_neutral",
    "proe_trailing",
    "proe_leading",
    "no_huddle_rate",
    "two_min_rate",
    "snap_share",
    "target_share",
    "carry_share",
    "route_share",
    "rz_target_share",
    "rz_carry_share",
    "i10_target_share",
    "i10_carry_share",
    "points",
    "points_scored",
    "team_points",
    "team_score",
    "salary",
    "game_info",
    "player_team",
]


def _ensure_feature_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in FEATURE_INPUT_COLS:
        if col not in df.columns:
            df[col] = pd.NA
    return df


def _compute_player_rollups(df: pd.DataFrame) -> pd.DataFrame:
    """Add lagged and rolling features per player."""
    df = df.sort_values(["player_id", "week"]).copy()
    grouped = df.groupby("player_id", group_keys=False)

    df["dk_points_prev"] = grouped["dk_total_points"].shift(1)
    for window in ROLLING_WINDOWS:
        df[f"dk_points_mean_{window}"] = (
            grouped["dk_total_points"].shift(1).rolling(window, min_periods=1).mean()
        )
        df[f"targets_mean_{window}"] = (
            grouped["targets"].shift(1).rolling(window, min_periods=1).mean()
            if "targets" in df.columns
            else None
        )
        df[f"carries_mean_{window}"] = (
            grouped["carries"].shift(1).rolling(window, min_periods=1).mean()
            if "carries" in df.columns
            else None
        )
        df[f"routes_mean_{window}"] = (
            grouped["routes_run"].shift(1).rolling(window, min_periods=1).mean()
            if "routes_run" in df.columns
            else None
        )
        df[f"dk_points_std_{window}"] = (
            grouped["dk_total_points"].shift(1).rolling(window, min_periods=1).std()
            if "dk_total_points" in df.columns
            else None
        )
        df[f"dk_points_max_{window}"] = (
            grouped["dk_total_points"].shift(1).rolling(window, min_periods=1).max()
            if "dk_total_points" in df.columns
            else None
        )
        df[f"snap_share_mean_{window}"] = (
            grouped["snap_share"].shift(1).rolling(window, min_periods=1).mean()
            if "snap_share" in df.columns
            else None
        )
        df[f"target_share_mean_{window}"] = (
            grouped["target_share"].shift(1).rolling(window, min_periods=1).mean()
            if "target_share" in df.columns
            else None
        )
        df[f"carry_share_mean_{window}"] = (
            grouped["carry_share"].shift(1).rolling(window, min_periods=1).mean()
            if "carry_share" in df.columns
            else None
        )
        df[f"route_share_mean_{window}"] = (
            grouped["route_share"].shift(1).rolling(window, min_periods=1).mean()
            if "route_share" in df.columns
            else None
        )
        df[f"rz_target_share_mean_{window}"] = (
            grouped["rz_target_share"].shift(1).rolling(window, min_periods=1).mean()
            if "rz_target_share" in df.columns
            else None
        )
        df[f"rz_carry_share_mean_{window}"] = (
            grouped["rz_carry_share"].shift(1).rolling(window, min_periods=1).mean()
            if "rz_carry_share" in df.columns
            else None
        )
        df[f"i10_target_share_mean_{window}"] = (
            grouped["i10_target_share"].shift(1).rolling(window, min_periods=1).mean()
            if "i10_target_share" in df.columns
            else None
        )
        df[f"i10_carry_share_mean_{window}"] = (
            grouped["i10_carry_share"].shift(1).rolling(window, min_periods=1).mean()
            if "i10_carry_share" in df.columns
            else None
        )
        df[f"air_yards_mean_{window}"] = (
            grouped["air_yards_per_g"].shift(1).rolling(window, min_periods=1).mean()
            if "air_yards_per_g" in df.columns
            else None
        )
        df[f"deep_targets_mean_{window}"] = (
            grouped["deep_targets"].shift(1).rolling(window, min_periods=1).mean()
            if "deep_targets" in df.columns
            else None
        )
        df[f"off_plays_per_g_mean_{window}"] = (
            grouped["off_plays_per_g"].shift(1).rolling(window, min_periods=1).mean()
            if "off_plays_per_g" in df.columns
            else None
        )
        df[f"def_plays_allowed_per_g_mean_{window}"] = (
            grouped["def_plays_allowed_per_g"].shift(1).rolling(window, min_periods=1).mean()
            if "def_plays_allowed_per_g" in df.columns
            else None
        )
        df[f"combined_plays_proj_mean_{window}"] = (
            grouped["combined_plays_proj"].shift(1).rolling(window, min_periods=1).mean()
            if "combined_plays_proj" in df.columns
            else None
        )
        for col in [
            "pass_rate_neutral",
            "pass_rate_trailing",
            "pass_rate_leading",
            "proe_neutral",
            "proe_trailing",
            "proe_leading",
        ]:
            if col in df.columns:
                df[f"{col}_mean_{window}"] = grouped[col].shift(1).rolling(window, min_periods=1).mean()
    return df


def _parse_opponent_from_game_info(game_info: str, player_team: str) -> str:
    if not game_info:
        return ""
    first_token = str(game_info).split()[0] if " " in str(game_info) else str(game_info)
    cleaned = first_token.replace(" ", "").upper()
    if "@" not in cleaned:
        return ""
    left, right = cleaned.split("@", 1)
    team = (player_team or "").upper()
    if team == left:
        return right
    if team == right:
        return left
    return right


def _latest_by_team(df: pd.DataFrame, team_col: str, cols: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[team_col] + cols)
    latest = df.sort_values("week").dropna(subset=[team_col])
    latest = latest.drop_duplicates(team_col, keep="last")
    return latest[[team_col] + [c for c in cols if c in latest.columns]]


def _load_defense_allowance(engine, season: int) -> pd.DataFrame:
    """Return defense vs position rolling means (shifted to avoid leakage)."""
    query = text(
        "SELECT recent_team AS defense_team, position, season, week, dk_total_points "
        "FROM team_weekly_position_defense WHERE season = :season"
    )
    df = pd.read_sql(query, engine, params={"season": season})
    if df.empty:
        return df

    df = df.sort_values(["defense_team", "position", "week"])
    grouped = df.groupby(["defense_team", "position"], group_keys=False)
    for window in ROLLING_WINDOWS:
        df[f"defense_allow_mean_{window}"] = (
            grouped["dk_total_points"].shift(1).rolling(window, min_periods=1).mean()
        )
    cols = ["defense_team", "position", "week"] + [c for c in df.columns if c.startswith("defense_allow")]
    return df[cols]


def _load_game_lines(engine, season: int) -> pd.DataFrame:
    """Return game-level betting context for implied totals/spreads."""
    query = text(
        "SELECT season, week, home_team, away_team, spread_line, total_line "
        "FROM nfl_schedules WHERE season = :season"
    )
    df = pd.read_sql(query, engine, params={"season": season})
    if df.empty:
        return df

    df["home_team"] = df["home_team"].str.upper()
    df["away_team"] = df["away_team"].str.upper()
    df["spread_line"] = df["spread_line"].fillna(0.0)
    df["total_line"] = df["total_line"].fillna(0.0)

    home_team = df[["season", "week", "home_team", "spread_line", "total_line"]].copy()
    home_team = home_team.rename(columns={"home_team": "team"})
    home_team["team_spread"] = home_team["spread_line"]
    home_team["team_implied_total"] = (home_team["total_line"] / 2.0) - (home_team["spread_line"] / 2.0)
    home_team["game_total"] = home_team["total_line"]

    away_team = df[["season", "week", "away_team", "spread_line", "total_line"]].copy()
    away_team = away_team.rename(columns={"away_team": "team"})
    away_team["team_spread"] = -away_team["spread_line"]
    away_team["team_implied_total"] = (away_team["total_line"] / 2.0) + (away_team["spread_line"] / 2.0)
    away_team["game_total"] = away_team["total_line"]

    lines = pd.concat([home_team, away_team], ignore_index=True)
    return lines[["season", "week", "team", "team_spread", "team_implied_total", "game_total"]]


def _add_recent_form_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["player_id", "week"])
    grouped = df.groupby("player_id", group_keys=False)
    df["fp_last_game"] = grouped["dk_total_points"].shift(1)
    for window in EXTENDED_WINDOWS:
        shifted = grouped["dk_total_points"].shift(1)
        df[f"fp_roll_mean_w{window}"] = shifted.rolling(window, min_periods=1).mean()
        df[f"fp_roll_median_w{window}"] = shifted.rolling(window, min_periods=1).median()
        df[f"fp_roll_std_w{window}"] = shifted.rolling(window, min_periods=1).std()
        df[f"fp_roll_p80_w{window}"] = shifted.rolling(window, min_periods=1).quantile(0.8)
        df[f"fp_roll_p20_w{window}"] = shifted.rolling(window, min_periods=1).quantile(0.2)
        df[f"games_played_last_w{window}"] = shifted.rolling(window, min_periods=1).count()
        df[f"trend_fp_w{window}"] = grouped["dk_total_points"].shift(1).rolling(window, min_periods=2).apply(
            _rolling_slope, raw=False
        )

        # Usage and snap share rolling
        pass_att = df["pass_attempts"] if "pass_attempts" in df.columns else df.get("attempts", pd.Series(0, index=df.index))
        rush_att = df.get("carries", df.get("rush_attempts", pd.Series(0, index=df.index)))
        targets = df.get("targets", pd.Series(0, index=df.index))
        position_upper = df.get("position", "").astype(str).str.upper()
        opp_series = pd.Series(0, index=df.index, dtype=float)
        opp_series[position_upper == "QB"] = (pd.Series(pass_att).astype(float) + pd.Series(rush_att).astype(float))[position_upper == "QB"].fillna(0)
        opp_series[position_upper == "RB"] = (pd.Series(rush_att).astype(float) + pd.Series(targets).astype(float))[position_upper == "RB"].fillna(0)
        opp_series[position_upper.isin(["WR", "TE"])] = pd.Series(targets).astype(float)[position_upper.isin(["WR", "TE"])].fillna(0)
        opp_series.name = "opp_usage_tmp"
        df["opp_usage_tmp"] = _to_numeric(opp_series)
        df[f"usage_roll_mean_w{window}"] = grouped["opp_usage_tmp"].shift(1).rolling(window, min_periods=1).mean()

        if "snap_share" in df.columns:
            snap_series = df["snap_share"]
        elif "snaps" in df.columns and "team_snaps" in df.columns:
            snap_series = _safe_div(df["snaps"], df["team_snaps"])
        else:
            snap_series = df.get("snaps", pd.Series(0, index=df.index))
        snap_series.name = "snap_share_tmp"
        df["snap_share_tmp"] = _to_numeric(snap_series)
        df[f"snap_share_roll_mean_w{window}"] = grouped["snap_share_tmp"].shift(1).rolling(window, min_periods=1).mean()

    return df


def _add_opportunity_efficiency(df: pd.DataFrame) -> pd.DataFrame:
    # Base opportunity this week
    pass_att = df["pass_attempts"] if "pass_attempts" in df.columns else df.get("attempts", pd.Series(0, index=df.index))
    rush_att = df.get("carries", df.get("rush_attempts", pd.Series(0, index=df.index)))
    targets = df.get("targets", pd.Series(0, index=df.index))
    position_upper = df.get("position", "").astype(str).str.upper()
    opp_total = pd.Series(0, index=df.index, dtype=float)
    opp_total[position_upper == "QB"] = (pass_att + rush_att).fillna(0)[position_upper == "QB"]
    opp_total[position_upper == "RB"] = (rush_att + targets).fillna(0)[position_upper == "RB"]
    opp_total[position_upper.isin(["WR", "TE"])] = targets.fillna(0)[position_upper.isin(["WR", "TE"])]
    df["opp_total"] = opp_total

    # Team opp totals by position within week
    if {"season", "week", "recent_team", "position"}.issubset(df.columns):
        team_pos_totals = (
            df.groupby(["season", "week", "recent_team", "position"])["opp_total"]
            .sum()
            .rename("team_pos_opp_total")
            .reset_index()
        )
        df = df.merge(team_pos_totals, on=["season", "week", "recent_team", "position"], how="left")
        df["opp_share"] = _safe_div(df["opp_total"], df["team_pos_opp_total"])
    else:
        df["team_pos_opp_total"] = pd.NA
        df["opp_share"] = pd.NA

    snaps = df.get("snaps", df.get("offense_snaps", pd.Series(np.nan, index=df.index)))
    df["targets_per_snap"] = _safe_div(targets, snaps)
    df["carries_per_snap"] = _safe_div(rush_att, snaps)
    air_yards = df.get("air_yards", df.get("airyards", pd.Series(np.nan, index=df.index)))
    df["air_yards_per_target"] = _safe_div(air_yards, targets)
    routes = df.get("routes_run", df.get("routes", pd.Series(np.nan, index=df.index)))
    df["yprr"] = _safe_div(df.get("rec_yards", pd.Series(np.nan, index=df.index)), routes)
    df["yards_per_target"] = _safe_div(df.get("rec_yards", pd.Series(np.nan, index=df.index)), targets)
    df["yards_per_carry"] = _safe_div(df.get("rush_yards", pd.Series(np.nan, index=df.index)), rush_att)
    td_col = df.get("touchdowns", df.get("total_tds", pd.Series(np.nan, index=df.index)))
    df["td_rate"] = _safe_div(td_col, df["opp_total"].replace({0: pd.NA}))
    # Coerce roll inputs to numeric to avoid non-numeric aggregation errors
    for col in ["yprr", "yards_per_target", "yards_per_carry", "td_rate", "targets_per_snap", "carries_per_snap", "air_yards_per_target"]:
        df[col] = _to_numeric(df[col], default=np.nan)

    grouped = df.sort_values(["player_id", "week"]).groupby("player_id", group_keys=False)
    for window in EXTENDED_WINDOWS:
        df[f"yards_per_target_roll_w{window}"] = grouped["yards_per_target"].shift(1).rolling(window, min_periods=1).mean()
        df[f"yards_per_carry_roll_w{window}"] = grouped["yards_per_carry"].shift(1).rolling(window, min_periods=1).mean()
        df[f"td_rate_roll_w{window}"] = grouped["td_rate"].shift(1).rolling(window, min_periods=1).mean()

    if "rz_touches" in df.columns:
        team_rz = (
            df.groupby(["season", "week", "recent_team"])["rz_touches"]
            .sum()
            .rename("team_rz_touches")
            .reset_index()
        )
        df = df.merge(team_rz, on=["season", "week", "recent_team"], how="left")
        df["red_zone_share"] = _safe_div(df["rz_touches"], df["team_rz_touches"])
    else:
        df["red_zone_share"] = pd.NA

    if "big_play" in df.columns:
        df["explosive_play_rate"] = _safe_div(df["big_play"], df["opp_total"])
    elif "explosive_plays" in df.columns:
        df["explosive_play_rate"] = _safe_div(df["explosive_plays"], df["opp_total"])
    else:
        df["explosive_play_rate"] = pd.NA
    return df


def _add_matchup_features(df: pd.DataFrame) -> pd.DataFrame:
    if "opponent_team" not in df.columns or "position" not in df.columns:
        return df
    for col in ["dk_total_points", "rec_yards", "rush_yards", "pass_yards"]:
        if col not in df.columns:
            df[col] = pd.NA
    dvp = df[["opponent_team", "position", "week", "dk_total_points", "rec_yards", "rush_yards", "pass_yards"]].copy()
    dvp = dvp.sort_values(["opponent_team", "position", "week"])
    dvp["yards_total"] = dvp[["rec_yards", "rush_yards", "pass_yards"]].sum(axis=1, skipna=True)
    dvp_grouped = dvp.groupby(["opponent_team", "position"], group_keys=False)
    # shift to remove current game leakage
    for window in SHORT_OPP_WINDOWS:
        dvp[f"opp_dvp_fp_allowed_pos_w{window}"] = dvp_grouped["dk_total_points"].shift(1).rolling(window, min_periods=1).mean()
        dvp[f"opp_dvp_yards_allowed_pos_w{window}"] = dvp_grouped["yards_total"].shift(1).rolling(window, min_periods=1).mean()
        dvp[f"opp_dvp_tds_allowed_pos_w{window}"] = dvp_grouped["dk_total_points"].shift(1).rolling(window, min_periods=1).apply(
            lambda s: (s >= 6).sum(), raw=False
        )
    dvp["opp_dvp_fp_allowed_pos_szn"] = dvp_grouped["dk_total_points"].shift(1).expanding().mean()
    dvp = dvp.drop(columns=["dk_total_points", "rec_yards", "rush_yards", "pass_yards", "yards_total"])
    dvp = dvp.drop_duplicates(subset=["opponent_team", "position", "week"], keep="last")
    df = df.merge(dvp, on=["opponent_team", "position", "week"], how="left")
    return df


def _add_game_environment(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["recent_team", "week"])
    grouped = df.groupby("recent_team", group_keys=False)
    points = None
    for cand in ["points", "points_scored", "team_points", "team_score"]:
        if cand in df.columns:
            points = df[cand]
            break
    if points is None:
        points = pd.Series(np.nan, index=df.index, name="points_proxy")
    points.name = points.name or "points_proxy"
    df["points_proxy"] = points
    if "rush_attempts" in df.columns:
        rush_attempts = df["rush_attempts"]
    else:
        rush_attempts = df.get("carries", pd.Series(np.nan, index=df.index))
    pass_attempts = df.get("pass_attempts", df.get("attempts", pd.Series(np.nan, index=df.index)))
    plays = None
    for cand in ["team_snaps", "offense_snaps", "offensive_snaps", "plays"]:
        if cand in df.columns:
            plays = df[cand]
            break
    if plays is None:
        plays = pd.Series(np.nan, index=df.index, name="plays_proxy")
    plays.name = plays.name or "plays_proxy"
    df["plays_proxy"] = plays
    pass_rate_series = _safe_div(pass_attempts, pass_attempts + rush_attempts)
    pass_rate_series = _to_numeric(pass_rate_series, default=0.0)
    df["pass_rate_proxy"] = pass_rate_series
    for window in EXTENDED_WINDOWS:
        pts_series = df["points_proxy"]
        play_series = df["plays_proxy"]
        df[f"team_points_roll_w{window}"] = grouped[pts_series.name].shift(1).rolling(window, min_periods=1).mean()
        df[f"team_pass_rate_roll_w{window}"] = grouped["pass_rate_proxy"].shift(1).rolling(window, min_periods=1).mean()
        df[f"team_plays_roll_w{window}"] = grouped[play_series.name].shift(1).rolling(window, min_periods=1).mean()

    # Opponent defensive points allowed rolling
    if {"opponent_team", "week"}.issubset(df.columns):
        base_pts_col = "points_proxy"
        opp_points = (
            df.groupby(["recent_team", "week"])[base_pts_col]
            .mean()
            .reset_index()
            .rename(columns={"recent_team": "opponent_team", base_pts_col: "opp_points_allowed"})
        )
        df = df.merge(opp_points, on=["opponent_team", "week"], how="left")
        df["opponent_points_allowed_roll_w3"] = df.groupby("opponent_team")["opp_points_allowed"].shift(1).rolling(3, min_periods=1).mean()
        df["opponent_points_allowed_roll_w8"] = df.groupby("opponent_team")["opp_points_allowed"].shift(1).rolling(8, min_periods=1).mean()

    # Stackability proxy
    pace = df.get("combined_plays_proj", pd.Series(0, index=df.index))
    points_roll = df.get("team_points_roll_w3", pd.Series(0, index=df.index))
    z_pace = (pace - pace.mean()) / (pace.std() or 1)
    z_points = (points_roll - points_roll.mean()) / (points_roll.std() or 1)
    df["game_stackability_score"] = z_pace.fillna(0) + z_points.fillna(0)
    return df


def _add_salary_value_features(df: pd.DataFrame) -> pd.DataFrame:
    if "salary" not in df.columns:
        df["salary_k"] = pd.NA
        return df
    df["salary_k"] = _safe_div(df["salary"], 1000.0)
    df["value_fp_per_k"] = _safe_div(df["dk_total_points"], df["salary_k"])
    grouped = df.sort_values(["player_id", "week"]).groupby("player_id", group_keys=False)
    for window in EXTENDED_WINDOWS:
        df[f"value_fp_per_k_roll_w{window}"] = grouped["value_fp_per_k"].shift(1).rolling(window, min_periods=1).mean()
        df[f"ceiling_per_k_w{window}"] = grouped["dk_total_points"].shift(1).rolling(window, min_periods=1).quantile(0.8) / df["salary_k"]
        df[f"floor_per_k_w{window}"] = grouped["dk_total_points"].shift(1).rolling(window, min_periods=1).quantile(0.2) / df["salary_k"]
    # Slate rank/percentile by position
    if {"week", "season", "position"}.issubset(df.columns):
        df["salary_rank_pos_slate"] = df.groupby(["season", "week", "position"])["salary"].rank(method="dense", ascending=False)
        df["salary_percentile_pos_slate"] = df.groupby(["season", "week", "position"])["salary"].rank(pct=True)
    # Boom/bust proxies
    boom_thresh = 4.0
    bust_thresh = 2.0
    df["boom_rate"] = grouped["dk_total_points"].apply(
        lambda s: (s.shift(1) >= boom_thresh * df.loc[s.index, "salary_k"])
        .rolling(EXTENDED_WINDOWS[-1], min_periods=1)
        .mean()
    ).reset_index(level=0, drop=True)
    df["bust_rate"] = grouped["dk_total_points"].apply(
        lambda s: (s.shift(1) <= bust_thresh * df.loc[s.index, "salary_k"])
        .rolling(EXTENDED_WINDOWS[-1], min_periods=1)
        .mean()
    ).reset_index(level=0, drop=True)
    return df


def _add_correlation_features(df: pd.DataFrame) -> pd.DataFrame:
    df["game_id"] = df.apply(
        lambda r: f"{r.get('season','')}-{r.get('week','')}-{r.get('recent_team','')}-{r.get('opponent_team','')}",
        axis=1,
    )
    df["team_id"] = df.get("recent_team", "")
    df["opp_id"] = df.get("opponent_team", "")
    # Partner scores for pass catchers
    target_share = df.get("target_share", pd.Series(0, index=df.index))
    air_share = df.get("air_yards_share", pd.Series(0, index=df.index))
    snap_share = df.get("snap_share", pd.Series(0, index=df.index))
    df["qb_stack_partner_score"] = target_share.fillna(0) + air_share.fillna(0) + snap_share.fillna(0)
    # Bringback: opponent top partner score among WR/TE
    if {"season", "week", "opponent_team", "position"}.issubset(df.columns):
        opp_scores = (
            df[df["position"].isin(["WR", "TE"])]
            .groupby(["season", "week", "recent_team"])["qb_stack_partner_score"]
            .max()
            .rename("bringback_score")
            .reset_index()
        )
        df = df.merge(
            opp_scores.rename(columns={"recent_team": "opponent_team"}),
            on=["season", "week", "opponent_team"],
            how="left",
        )
    else:
        df["bringback_score"] = pd.NA

    df["rb_def_synergy_tag"] = df["position"].astype(str).str.upper().isin(["RB", "DST"]).astype(int)
    pace = df.get("combined_plays_proj", pd.Series(0, index=df.index))
    pace_median = pace.median() or 0
    df["pace_match_tag"] = ((pace >= pace_median) & (df.groupby("game_id")["combined_plays_proj"].transform("max") >= pace_median)).astype(int)

    # Concentration index: sum of top-2 target_share within team-week
    if {"season", "week", "recent_team", "target_share"}.issubset(df.columns):
        conc = (
            df.groupby(["season", "week", "recent_team"])["target_share"]
            .apply(lambda s: s.fillna(0).sort_values(ascending=False).head(2).sum())
            .rename("concentration_index_team")
            .reset_index()
        )
        df = df.merge(conc, on=["season", "week", "recent_team"], how="left")
    else:
        df["concentration_index_team"] = pd.NA

    df["primary_receiver_flag"] = ((df.get("target_share", 0).fillna(0) >= 0.25) | (df.get("snap_share", 0).fillna(0) >= 0.8)).astype(int)
    df["workhorse_rb_flag"] = (
        (df["position"].astype(str).str.upper() == "RB")
        & ((df.get("carry_share", 0).fillna(0) >= 0.6) | (df.get("snap_share", 0).fillna(0) >= 0.7))
    ).astype(int)
    return df


def _add_availability_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["player_id", "week"])
    grouped = df.groupby("player_id", group_keys=False)
    df["did_play_last_week"] = (~grouped["week"].shift(1).isna()).astype(int)
    df["weeks_since_last_game"] = (grouped["week"].diff().fillna(0) - 1).clip(lower=0)
    snaps = df.get("snaps", df.get("offense_snaps", pd.Series(np.nan, index=df.index)))
    snap_col = snaps.name if hasattr(snaps, "name") and snaps.name else "snaps_proxy"
    df[snap_col] = snaps
    df["snap_change_wow"] = df[snap_col] - grouped[snap_col].shift(1)
    df["snap_drop_flag"] = (_safe_div(df["snap_change_wow"], grouped[snap_col].shift(1)).fillna(0) <= -0.3).astype(int)
    if "opp_total" in df.columns:
        df["usage_change_wow"] = df["opp_total"] - grouped["opp_total"].shift(1)
    else:
        df["usage_change_wow"] = pd.NA
    df["returning_flag"] = ((df["weeks_since_last_game"] >= 2) & (df["did_play_last_week"] == 1)).astype(int)
    snap_share_series = df.get("snap_share", pd.Series(np.nan, index=df.index))
    df["snap_share"] = _to_numeric(snap_share_series, default=np.nan)
    for window in EXTENDED_WINDOWS:
        df[f"role_stability_roll_w{window}"] = grouped["snap_share"].shift(1).rolling(window, min_periods=1).std()
    return df


def build_player_features(
    season: int,
    weeks: Iterable[int] | None = None,
    future_week: int | None = None,
    connection_string: str | None = None,
) -> int:
    """
    Build lightweight predictive features and persist to predictive_features.

    Returns number of rows written.
    """
    conn_str = connection_string or get_connection_string()
    engine = create_engine(conn_str)
    with engine.begin() as connection:
        df = pd.read_sql(
            text(
                "SELECT * FROM curated_weekly_stats WHERE season = :season"
            ),
            connection,
            params={"season": season},
        )

    if df.empty:
        logging.warning("No curated weekly stats available to build features (season=%s weeks=%s)", season, weeks)
        return 0

    # Select source weeks
    if future_week is not None:
        source_df = df[df["week"] < future_week]
        if source_df.empty:
            logging.warning(
                "No historical data found before future_week=%s (season=%s); falling back to all available weeks.",
                future_week,
                season,
            )
            source_df = df
    elif weeks:
        source_df = df[df["week"].isin(weeks)]
    else:
        source_df = df
    if source_df.empty:
        logging.warning("No historical data available for feature build (season=%s, future_week=%s, weeks=%s)", season, future_week, weeks)
        return 0

    # Compute DK scoring directly on curated stats
    scored_df = compute_dk_scoring(source_df)

    base_cols = [
        "player_master_id",
        "player_id",
        "dk_player_id",
        "player_display_name",
        "position",
        "position_group",
        "recent_team",
        "opponent_team",
        "season",
        "week",
        "dk_total_points",
        "targets",
        "carries",
    ]
    for col in base_cols:
        if col not in scored_df.columns:
            scored_df[col] = None
    # Canonicalize identifier to player_master_id where present; keep DK/salary id separately
    if "player_master_id" not in scored_df.columns:
        scored_df["player_master_id"] = None
    if "player_id" not in scored_df.columns:
        scored_df["player_id"] = None
    scored_df["dk_player_id"] = scored_df.get("dk_player_id", scored_df.get("player_id", None))
    scored_df["player_master_id"] = scored_df["player_master_id"].where(scored_df["player_master_id"].notna(), None)

    # Prefer master id, then explicit player_id, then any internal id if present. Avoid fillna(None) which raises.
    player_id_series = scored_df["player_master_id"].combine_first(scored_df["player_id"])
    if "internal_player_id" in scored_df.columns:
        player_id_series = player_id_series.combine_first(scored_df["internal_player_id"])
    scored_df["player_id"] = player_id_series.astype(str)
    # Shares: compute team totals per week/team and derive per-player share metrics
    def _first_existing(cols):
        return next((c for c in cols if c in df.columns), None)

    snap_col = _first_existing(["offense_snaps", "offensive_snaps", "player_snaps", "snaps"])
    target_col = "targets" if "targets" in df.columns else None
    carry_col = "carries" if "carries" in df.columns else None
    route_col = _first_existing(["routes_run", "routes"])
    pass_att_col = _first_existing(["attempts", "pass_attempts"])
    dropbacks_col = "dropbacks" if "dropbacks" in df.columns else None
    air_yards_col = _first_existing(["air_yards", "airyards"])
    deep_tgt_col = _first_existing(["deep_targets", "deep_tgts"])
    no_huddle_col = _first_existing(["no_huddle_rate", "no_huddle_pct"])
    hurry_col = _first_existing(["two_min_rate", "hurry_up_rate", "two_min_pct"])
    pr_neutral_col = _first_existing(["pass_rate_neutral", "pr_neutral"])
    pr_trailing_col = _first_existing(["pass_rate_trailing", "pr_trailing"])
    pr_leading_col = _first_existing(["pass_rate_leading", "pr_leading"])
    proe_neutral_col = _first_existing(["proe_neutral", "pass_roe_neutral"])
    proe_trailing_col = _first_existing(["proe_trailing", "pass_roe_trailing"])
    proe_leading_col = _first_existing(["proe_leading", "pass_roe_leading"])
    rz_tgt_col = _first_existing(["rz_targets", "redzone_targets", "targets_redzone"])
    rz_carry_col = _first_existing(["rz_carries", "redzone_carries", "carries_redzone"])
    i10_tgt_col = _first_existing(["i10_targets", "inside10_targets"])
    i10_carry_col = _first_existing(["i10_carries", "inside10_carries"])

    share_cols = {}
    group_cols = ["recent_team", "week"]
    team_aggs = {}
    if snap_col:
        team_aggs["team_snaps"] = (snap_col, "sum")
        share_cols["snap_share"] = ("team_snaps", snap_col)
    if target_col:
        team_aggs["team_targets"] = (target_col, "sum")
        share_cols["target_share"] = ("team_targets", target_col)
    if carry_col:
        team_aggs["team_carries"] = (carry_col, "sum")
        share_cols["carry_share"] = ("team_carries", carry_col)
    if route_col:
        team_aggs["team_routes"] = (route_col, "sum")
    if dropbacks_col:
        team_aggs["team_dropbacks"] = (dropbacks_col, "sum")
    elif pass_att_col:
        team_aggs["team_dropbacks"] = (pass_att_col, "sum")
    if air_yards_col:
        team_aggs["team_air_yards"] = (air_yards_col, "sum")
    if deep_tgt_col:
        team_aggs["team_deep_targets"] = (deep_tgt_col, "sum")

    if rz_tgt_col:
        team_aggs["team_rz_targets"] = (rz_tgt_col, "sum")
        share_cols["rz_target_share"] = ("team_rz_targets", rz_tgt_col)
    if rz_carry_col:
        team_aggs["team_rz_carries"] = (rz_carry_col, "sum")
        share_cols["rz_carry_share"] = ("team_rz_carries", rz_carry_col)
    if i10_tgt_col:
        team_aggs["team_i10_targets"] = (i10_tgt_col, "sum")
        share_cols["i10_target_share"] = ("team_i10_targets", i10_tgt_col)
    if i10_carry_col:
        team_aggs["team_i10_carries"] = (i10_carry_col, "sum")
        share_cols["i10_carry_share"] = ("team_i10_carries", i10_carry_col)

    if route_col:
        share_cols["route_share"] = (
            "team_dropbacks" if "team_dropbacks" in team_aggs else "team_routes",
            route_col,
        )
    if air_yards_col:
        share_cols["air_yards_share"] = ("team_air_yards", air_yards_col)
    if deep_tgt_col:
        share_cols["deep_target_share"] = ("team_deep_targets", deep_tgt_col)

    features_df = scored_df.copy()
    features_df = _ensure_feature_columns(features_df)
    # Coerce likely numeric columns to numeric to avoid aggregation errors
    numeric_cols = [
        "dk_total_points",
        "targets",
        "carries",
        "rush_attempts",
        "pass_attempts",
        "attempts",
        "snaps",
        "offense_snaps",
        "offensive_snaps",
        "team_snaps",
        "routes_run",
        "routes",
        "air_yards",
        "airyards",
        "pass_yards",
        "rush_yards",
        "rec_yards",
        "touchdowns",
        "total_tds",
        "rz_touches",
        "big_play",
        "explosive_plays",
        "snap_share",
        "target_share",
        "carry_share",
        "route_share",
        "rz_target_share",
        "rz_carry_share",
        "i10_target_share",
        "i10_carry_share",
        "pass_rate_neutral",
        "pass_rate_trailing",
        "pass_rate_leading",
        "proe_neutral",
        "proe_trailing",
        "proe_leading",
        "no_huddle_rate",
        "two_min_rate",
        "points",
        "points_scored",
        "team_points",
        "team_score",
        "salary",
    ]
    features_df = _coerce_numeric(features_df, numeric_cols, default=0.0)
    # Ensure key identifiers are strings to avoid merge dtype mismatches
    features_df = _coerce_str(features_df, ["recent_team", "opponent_team", "player_id", "player_master_id", "dk_player_id"])
    # Ensure team identifiers exist before downstream grouping/merges
    if "recent_team" not in features_df.columns or features_df["recent_team"].isna().all():
        features_df["recent_team"] = features_df.get("team", "")
    if "opponent_team" not in features_df.columns:
        features_df["opponent_team"] = ""
    if "week" not in features_df.columns:
        features_df["week"] = None
    if team_aggs:
        team_totals = (
            features_df.groupby(group_cols, dropna=False)
            .agg(**{name: pd.NamedAgg(column=col, aggfunc="sum") for name, (col, _) in team_aggs.items()})
            .reset_index()
        )
        if not all(col in team_totals.columns for col in group_cols):
            raise ValueError("Grouping failed: missing recent_team/week in team totals.")
        features_df = features_df.merge(team_totals, on=group_cols, how="left")

        for share_name, (team_col, player_col) in share_cols.items():
            if player_col in features_df.columns and team_col in features_df.columns:
                denom = features_df[team_col].replace({0: pd.NA})
                features_df[share_name] = features_df[player_col] / denom
            else:
                features_df[share_name] = None
        # Fill NaN shares with 0 for stability
        for share_name in share_cols.keys():
            features_df[share_name] = features_df[share_name].fillna(0.0)
    else:
        for share_name in [
            "snap_share",
            "target_share",
            "carry_share",
            "route_share",
            "rz_target_share",
            "rz_carry_share",
            "i10_target_share",
            "i10_carry_share",
            "air_yards_share",
            "deep_target_share",
        ]:
            features_df[share_name] = 0.0

    # Per-game air yards and aDOT when available
    if air_yards_col and target_col:
        features_df["air_yards_per_g"] = features_df[air_yards_col]
        denom = features_df[target_col].replace({0: pd.NA})
        features_df["adot"] = (features_df[air_yards_col] / denom).fillna(0.0)
    else:
        features_df["air_yards_per_g"] = 0.0
        features_df["adot"] = 0.0

    if deep_tgt_col:
        features_df["deep_targets"] = features_df[deep_tgt_col]
        features_df["deep_target_rate"] = (
            features_df[deep_tgt_col] / features_df[target_col].replace({0: pd.NA}) if target_col else 0.0
        )
        features_df["deep_target_rate"] = features_df["deep_target_rate"].fillna(0.0)
    else:
        features_df["deep_targets"] = 0.0
        features_df["deep_target_rate"] = 0.0

    # Pace/context: no-huddle and hurry-up proxies
    if no_huddle_col:
        features_df["no_huddle_rate"] = features_df[no_huddle_col].fillna(0.0)
    else:
        features_df["no_huddle_rate"] = 0.0
    if hurry_col:
        features_df["two_min_rate"] = features_df[hurry_col].fillna(0.0)
    else:
        features_df["two_min_rate"] = 0.0

    # Team-level pace aggregates (season-to-date and last 3), offense and defense
    if "team_snaps" in features_df.columns:
        play_log = features_df[
            [
                "recent_team",
                "opponent_team",
                "week",
                "team_snaps",
                "pass_rate_neutral",
                "pass_rate_trailing",
                "pass_rate_leading",
                "proe_neutral",
                "proe_trailing",
                "proe_leading",
            ]
        ].copy()
        # Offensive pace per team
        play_log = play_log.sort_values(["recent_team", "week"])
        play_log["off_cum_snaps"] = play_log.groupby("recent_team")["team_snaps"].shift().cumsum()
        play_log["off_games"] = play_log.groupby("recent_team").cumcount()
        play_log["off_plays_per_g"] = play_log["off_cum_snaps"] / play_log["off_games"].replace({0: pd.NA})
        play_log["off_plays_per_g"] = pd.to_numeric(play_log["off_plays_per_g"], errors="coerce").ffill().fillna(0.0)
        play_log["off_plays_per_g_l3"] = (
            play_log.groupby("recent_team")["team_snaps"].shift().rolling(3, min_periods=1).mean().reset_index(level=0, drop=True)
        ).fillna(0.0).infer_objects(copy=False)

        # Offensive pass rates by script
        for col in ["pass_rate_neutral", "pass_rate_trailing", "pass_rate_leading", "proe_neutral", "proe_trailing", "proe_leading"]:
            if col in play_log.columns:
                play_log[col] = play_log[col].ffill().fillna(0.0).infer_objects(copy=False)

        # Defensive pace allowed (opponent plays)
        play_log = play_log.sort_values(["opponent_team", "week"])
        play_log["def_cum_snaps"] = play_log.groupby("opponent_team")["team_snaps"].shift().cumsum()
        play_log["def_games"] = play_log.groupby("opponent_team").cumcount()
        play_log["def_plays_allowed_per_g"] = play_log["def_cum_snaps"] / play_log["def_games"].replace({0: pd.NA})
        play_log["def_plays_allowed_per_g"] = pd.to_numeric(play_log["def_plays_allowed_per_g"], errors="coerce").ffill().fillna(0.0)
        play_log["def_plays_allowed_per_g_l3"] = (
            play_log.groupby("opponent_team")["team_snaps"].shift().rolling(3, min_periods=1).mean().reset_index(level=0, drop=True)
        ).fillna(0.0).infer_objects(copy=False)

        pace_cols = play_log[
            [
                "recent_team",
                "opponent_team",
                "week",
                "off_plays_per_g",
                "off_plays_per_g_l3",
                "def_plays_allowed_per_g",
                "def_plays_allowed_per_g_l3",
                "pass_rate_neutral",
                "pass_rate_trailing",
                "pass_rate_leading",
                "proe_neutral",
                "proe_trailing",
                "proe_leading",
            ]
        ]
        features_df = features_df.merge(
            pace_cols,
            on=["recent_team", "opponent_team", "week"],
            how="left",
        )
        # Combined plays projection: average of offense plays/g and opponent plays allowed/g
        features_df["combined_plays_proj"] = (
            features_df["off_plays_per_g"].fillna(0.0) + features_df["def_plays_allowed_per_g"].fillna(0.0)
        ) / 2.0
    else:
        features_df["off_plays_per_g"] = 0.0
        features_df["off_plays_per_g_l3"] = 0.0
        features_df["def_plays_allowed_per_g"] = 0.0
        features_df["def_plays_allowed_per_g_l3"] = 0.0
        features_df["combined_plays_proj"] = 0.0
        for col in ["pass_rate_neutral", "pass_rate_trailing", "pass_rate_leading", "proe_neutral", "proe_trailing", "proe_leading"]:
            features_df[col] = 0.0

    # Ensure base columns still present
    for col in base_cols:
        if col not in features_df.columns:
            features_df[col] = None
    # Ensure share/context columns exist even if upstream data missing
    for col in [
        "snap_share",
        "target_share",
        "carry_share",
        "route_share",
        "rz_target_share",
        "rz_carry_share",
        "i10_target_share",
        "i10_carry_share",
        "air_yards_share",
        "deep_target_share",
        "no_huddle_rate",
        "two_min_rate",
        "pass_rate_neutral",
        "pass_rate_trailing",
        "pass_rate_leading",
        "proe_neutral",
        "proe_trailing",
        "proe_leading",
    ]:
        if col not in features_df.columns:
            features_df[col] = 0.0

    features = _compute_player_rollups(features_df[base_cols + [col for col in features_df.columns if col not in base_cols]])

    # Extended feature chunks
    features = _add_recent_form_features(features)
    features = _add_opportunity_efficiency(features)
    features = _add_matchup_features(features)
    features = _add_game_environment(features)
    features = _add_salary_value_features(features)
    features = _add_correlation_features(features)
    features = _add_availability_features(features)

    # Boom/bust rates: fraction of games meeting a DK threshold
    if "dk_total_points" in features.columns:
        def _threshold(pos: str) -> float:
            pos = (pos or "").upper()
            if pos == "QB":
                return 30.0
            if pos in ("WR", "RB"):
                return 25.0
            return 20.0

        features["dk_points_25plus_rate"] = 0.0
        for pid, group in features.groupby("player_id"):
            pos = group["position"].iloc[0] if "position" in group.columns else ""
            thresh = _threshold(pos)
            total_games = len(group)
            if total_games == 0:
                continue
            hits = (group["dk_total_points"] >= thresh).sum()
            rate = float(hits) / float(total_games)
            features.loc[group.index, "dk_points_25plus_rate"] = rate

    # Attach opponent strength (defense vs position)
    defense_df = _load_defense_allowance(engine, season)
    if not defense_df.empty:
        # position-specific allowance
        features = features.merge(
            defense_df,
            how="left",
            left_on=["opponent_team", "position", "week"],
            right_on=["defense_team", "position", "week"],
        )
        features = features.drop(columns=["defense_team"], errors="ignore")
        # run/pass funnel indicators using RB vs pass-catcher allowance (5-week mean)
        funnel = defense_df.pivot_table(
            index=["defense_team", "week"],
            columns="position",
            values="defense_allow_mean_5",
            aggfunc="first",
        ).reset_index()
        league_rb = funnel.get("RB", pd.Series(dtype=float)).mean()
        wrte = funnel.get("WR", pd.Series(dtype=float)).fillna(0) + funnel.get("TE", pd.Series(dtype=float)).fillna(0)
        funnel["run_funnel"] = (funnel.get("RB", pd.Series(dtype=float)).fillna(0) - wrte) / max(1.0, league_rb if pd.notna(league_rb) else 1.0)
        funnel["pass_funnel"] = (wrte - funnel.get("RB", pd.Series(dtype=float)).fillna(0)) / max(1.0, league_rb if pd.notna(league_rb) else 1.0)
        funnel = funnel.rename(columns={"defense_team": "opponent_team"})
        features = features.merge(
            funnel[["opponent_team", "week", "run_funnel", "pass_funnel"]],
            how="left",
            on=["opponent_team", "week"],
        )

    # Label for training
    features = features.rename(columns={"dk_total_points": "label_dk_total_points"})

    # Attach betting context: implied totals/spreads
    lines_df = _load_game_lines(engine, season)
    if not lines_df.empty:
        features = features.merge(
            lines_df,
            how="left",
            left_on=["recent_team", "season", "week"],
            right_on=["team", "season", "week"],
        ).drop(columns=["team"], errors="ignore")

    # Rename opponent allowance for clarity
    if "defense_allow_mean_3" in features.columns:
        features = features.rename(columns={"defense_allow_mean_3": "opp_pts_allowed_pos_3"})
    if "defense_allow_mean_5" in features.columns:
        features = features.rename(columns={"defense_allow_mean_5": "opp_pts_allowed_pos_5"})

    future_rows_count = 0
    # Future-week scaffolding: build target_week rows using historical rollups + schedule/context
    if future_week is not None:
        # Ensure curated_salaries has normalized columns and backfill them for this week
        normalize_cols = pd.DataFrame(
            {
                "player_display_name": pd.Series(dtype=str),
                "position": pd.Series(dtype=str),
                "roster_position": pd.Series(dtype=str),
                "player_team": pd.Series(dtype=str),
                "dk_player_id": pd.Series(dtype=str),
            }
        )
        ensure_table_columns(engine, "curated_salaries", normalize_cols)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE curated_salaries "
                    "SET player_display_name = COALESCE(player_display_name, \"Name\"::text), "
                    "    position = COALESCE(position, \"Position\"::text), "
                    "    roster_position = COALESCE(roster_position, \"Roster Position\"::text), "
                    "    player_team = COALESCE(player_team, \"TeamAbbrev\"::text), "
                    "    dk_player_id = COALESCE(dk_player_id, \"ID\"::text) "
                    "WHERE season = :season AND week = :week"
                ),
                {"season": season, "week": future_week},
            )
            salary_df = pd.read_sql(
                text(
                    "SELECT * FROM curated_salaries WHERE season = :season AND week = :week"
                ),
                conn,
                params={"season": season, "week": future_week},
            )
        if salary_df.empty:
            raise ValueError(f"No salaries found for future week {future_week} (season {season}).")

        if "player_master_id" not in salary_df.columns:
            raise ValueError(
                f"curated_salaries missing player_master_id for season={season} week={future_week}; "
                f"columns={list(salary_df.columns)}"
            )
        if salary_df["player_master_id"].isna().all():
            raise ValueError(
                f"curated_salaries player_master_id empty for season={season} week={future_week}; "
                "run salary curation to populate player_master_id."
            )

        # Preserve provider/DK id separately for slate mapping
        dk_col = next((c for c in ["dk_player_id", "ID", "player_id", "id"] if c in salary_df.columns), None)
        if dk_col is None:
            raise ValueError(
                f"curated_salaries missing a DK/player id column (dk_player_id/ID/player_id) for season={season} week={future_week}; "
                f"columns={list(salary_df.columns)}"
            )
        salary_df["dk_player_id"] = salary_df[dk_col].astype(str)

        # Canonical matching id is player_master_id; fallback to internal id then DK id
        salary_df["feature_match_id"] = salary_df["player_master_id"]
        if "internal_player_id" in salary_df.columns:
            salary_df["feature_match_id"] = salary_df["feature_match_id"].where(
                salary_df["feature_match_id"].notna(), salary_df["internal_player_id"]
            )
        salary_df["feature_match_id"] = salary_df["feature_match_id"].where(
            salary_df["feature_match_id"].notna(), salary_df["dk_player_id"]
        )
        salary_df["feature_match_id"] = salary_df["feature_match_id"].astype(str)
        salary_df = salary_df.drop_duplicates("dk_player_id")
        # Normalize salary columns
        for col in ["player_team", "position", "roster_position", "game_info", "name", "player_name", "player_display_name", "TeamAbbrev"]:
            if col not in salary_df.columns:
                salary_df[col] = ""
        salary_df["recent_team"] = salary_df["player_team"].where(salary_df["player_team"] != "", salary_df["TeamAbbrev"])
        salary_df["opponent_team"] = salary_df.apply(
            lambda row: _parse_opponent_from_game_info(row.get("game_info", ""), row.get("recent_team", "")),
            axis=1,
        )
        salary_df["player_display_name"] = salary_df["name"].where(salary_df["name"] != "", salary_df["player_display_name"])
        salary_df["player_display_name"] = salary_df["player_display_name"].where(salary_df["player_display_name"] != "", salary_df["player_name"])
        salary_df["player_display_name"] = salary_df["player_display_name"].where(salary_df["player_display_name"] != "", salary_df["dk_player_id"])
        salary_df["position"] = salary_df["position"].where(salary_df["position"] != "", salary_df["roster_position"])
        salary_df["season"] = season
        salary_df["week"] = future_week
        salary_df["label_dk_total_points"] = pd.NA

        latest_player = (
            features.sort_values("week")
            .drop_duplicates("player_id", keep="last")
        )
        cols_to_drop = {"season", "week", "label_dk_total_points"}
        latest_player = latest_player.drop(columns=[c for c in cols_to_drop if c in latest_player.columns], errors="ignore")

        future_rows = salary_df.merge(
            latest_player,
            left_on="feature_match_id",
            right_on="player_id",
            how="left",
            suffixes=("", "_hist"),
        )
        # Use player_master_id as canonical player_id; retain DK id for slate mapping
        future_rows["player_id"] = (
            future_rows.get("player_master_id").fillna(future_rows["feature_match_id"]).astype(str)
            if "player_master_id" in future_rows.columns
            else future_rows["feature_match_id"].astype(str)
        )
        future_rows["dk_player_id"] = future_rows.get("dk_player_id", future_rows.get("feature_match_id"))
        # Prefer salary values for overlapping columns
        for col in ["player_display_name", "position", "recent_team", "opponent_team", "player_master_id"]:
            x_col = f"{col}_x"
            y_col = f"{col}_y"
            if x_col in future_rows.columns:
                future_rows[col] = future_rows[x_col]
            elif y_col in future_rows.columns:
                future_rows[col] = future_rows[y_col]
            future_rows = future_rows.drop(columns=[c for c in (x_col, y_col) if c in future_rows.columns], errors="ignore")
        # Ensure names/positions are populated from salary mapping (use DK id as the lookup key)
        if "name" in salary_df.columns:
            name_map = dict(zip(salary_df["dk_player_id"].astype(str), salary_df["name"]))
            future_rows["player_display_name"] = future_rows["dk_player_id"].astype(str).map(name_map).fillna(future_rows.get("player_display_name", ""))
        if "position" in salary_df.columns:
            pos_map = dict(zip(salary_df["dk_player_id"].astype(str), salary_df["position"]))
            future_rows["position"] = future_rows["dk_player_id"].astype(str).map(pos_map).fillna(future_rows.get("position", ""))
        if "recent_team" not in future_rows.columns:
            future_rows["recent_team"] = salary_df.get("player_team", None)
        if "opponent_team" not in future_rows.columns:
            future_rows["opponent_team"] = salary_df.get("opponent_team", None)
        if "week" not in future_rows.columns:
            future_rows["week"] = future_week

        # Team/offense context
        team_ctx_cols = [
            "off_plays_per_g",
            "off_plays_per_g_l3",
            "pass_rate_neutral",
            "pass_rate_trailing",
            "pass_rate_leading",
            "proe_neutral",
            "proe_trailing",
            "proe_leading",
        ]
        team_ctx = _latest_by_team(features, "recent_team", team_ctx_cols)
        if not team_ctx.empty:
            future_rows = future_rows.merge(team_ctx, on="recent_team", how="left", suffixes=("", "_teamctx"))

        # Defense/pace allowed context (by opponent)
        def_ctx_cols = ["def_plays_allowed_per_g", "def_plays_allowed_per_g_l3"]
        def_ctx = _latest_by_team(features, "recent_team", def_ctx_cols)
        if not def_ctx.empty:
            def_ctx = def_ctx.rename(columns={"recent_team": "opponent_team"})
            future_rows = future_rows.merge(def_ctx, on="opponent_team", how="left", suffixes=("", "_oppctx"))

        # Betting lines for target week
        if not lines_df.empty:
            lines_future = lines_df[lines_df["week"] == future_week]
            if not lines_future.empty:
                future_rows = future_rows.merge(
                    lines_future[["team", "team_spread", "team_implied_total", "game_total"]],
                    left_on="recent_team",
                    right_on="team",
                    how="left",
                ).drop(columns=["team"], errors="ignore")

        # Combined plays projection for future rows
        future_rows["combined_plays_proj"] = (
            future_rows.get("off_plays_per_g", 0).fillna(0) + future_rows.get("def_plays_allowed_per_g", 0).fillna(0)
        ) / 2.0

        # Ensure all columns from historical features exist
        for col in features.columns:
            if col not in future_rows.columns:
                default_val = 0.0 if pd.api.types.is_numeric_dtype(features[col]) else ""
                if col == "label_dk_total_points":
                    default_val = pd.NA
                future_rows[col] = default_val
        future_rows = future_rows[features.columns]
        # Drop all-NA columns before concatenation to avoid future dtype warnings
        future_rows = future_rows.dropna(axis=1, how="all")
        future_rows_count = len(future_rows)
        if future_rows_count == 0:
            raise ValueError(f"Future-week feature build produced zero rows for week {future_week}.")
        features = pd.concat([features, future_rows], ignore_index=True)

    # Keep all historical weeks (including week 1) and future rows
    features = features.drop_duplicates(subset=["player_id", "season", "week"])

    # Decide which rows to persist
    rows_to_write = features if future_week is None else future_rows if future_rows_count > 0 else pd.DataFrame()
    if rows_to_write.empty:
        logging.warning("No rows to write for build (season=%s weeks=%s future_week=%s)", season, weeks, future_week)
        return 0

    # Persist (gracefully handle first-time table creation)
    try:
        if future_week is not None:
            delete_from_postgres(conn_str, "predictive_features", season=season, week=future_week)
        elif weeks:
            delete_from_postgres(conn_str, "predictive_features", season=season, week=weeks)
        else:
            delete_from_postgres(conn_str, "predictive_features", season=season, week=None)
    except Exception as exc:  # noqa: BLE001 - table may not exist yet
        logging.info("predictive_features table not found; will create on first write (%s)", exc)

    ensure_table_columns(engine, "predictive_features", rows_to_write)
    with engine.begin() as connection:
        rows_to_write.to_sql(
            "predictive_features",
            connection,
            if_exists="append",
            index=False,
        )
        # Ensure future-week rows remain unlabeled
        if future_week is not None:
            connection.execute(
                text(
                    "UPDATE predictive_features "
                    "SET label_dk_total_points = NULL "
                    "WHERE season = :season AND week = :week"
                ),
                {"season": season, "week": future_week},
            )
            # Refresh display_name/position/team from salaries for the target week
            connection.execute(
                text(
                    "UPDATE predictive_features pf "
                    "SET player_display_name = COALESCE(ds.player_display_name, ds.\"Name\", pf.player_display_name), "
                    "    position = COALESCE(ds.position, ds.\"Roster Position\", ds.\"Position\", pf.position), "
                    "    recent_team = COALESCE(ds.player_team, ds.\"TeamAbbrev\", pf.recent_team), "
                    "    dk_player_id = COALESCE(pf.dk_player_id, ds.dk_player_id, ds.\"ID\"::text) "
                    "FROM curated_salaries ds "
                    "WHERE pf.season = ds.season "
                    "  AND pf.week = ds.week "
                    "  AND pf.season = :season "
                    "  AND pf.week = :week "
                    "  AND COALESCE(pf.player_master_id::text, pf.dk_player_id::text) = "
                    "      COALESCE(ds.player_master_id::text, ds.\"ID\"::text)"
                ),
                {"season": season, "week": future_week},
            )
    logging.info(
        "Inserted %s predictive features rows (season=%s weeks=%s future_week=%s future_rows=%s)",
        len(rows_to_write),
        season,
        weeks,
        future_week,
        future_rows_count,
    )
    return len(rows_to_write)
