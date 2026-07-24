"""DraftKings scoring transformations for weekly data."""

from __future__ import annotations

import logging
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from .config import get_connection_string
from .operations import ensure_table_columns


DK_SCORING_HELP = """DraftKings NFL scoring reference:
- Passing: 0.04 pts per yard, 4 per TD, -1 per INT, +3 bonus at 300+ yards.
- Rushing: 0.1 pts per yard, 6 per TD, +3 bonus at 100+ yards.
- Receiving: 1 per reception, 0.1 per yard, 6 per TD, +3 bonus at 100+ yards.
- Two-point conversions: 2 points (passing, rushing, receiving).
- Fumbles lost: -1 each.
"""


def _safe_get(df: pd.DataFrame, cols: Sequence[str]) -> pd.Series:
    present = [col for col in cols if col in df.columns]
    if not present:
        return pd.Series(0, index=df.index, dtype="float64")
    return df[present].fillna(0).sum(axis=1)


def compute_dk_scoring(df: pd.DataFrame) -> pd.DataFrame:
    """Return a dataframe with DK scoring columns and dk_total_points."""
    if df.empty:
        return df

    df = df.copy()
    # Drop internal surrogate keys so we don't collide with PK on re-insert
    if "id" in df.columns:
        df = df.drop(columns=["id"])
    if "team" not in df.columns and "recent_team" in df.columns:
        df["team"] = df["recent_team"]
    # Base stats (fill NaNs to avoid propagation)
    for col in [
        "passing_yards",
        "passing_tds",
        "interceptions",
        "rushing_yards",
        "rushing_tds",
        "receptions",
        "receiving_yards",
        "receiving_tds",
        "passing_2pt_conversions",
        "rushing_2pt_conversions",
        "receiving_2pt_conversions",
    ]:
        if col in df.columns:
            df[col] = df[col].fillna(0)

    df["dk_pass_yds_points"] = df.get("passing_yards", 0) * 0.04
    df["dk_pass_td_points"] = df.get("passing_tds", 0) * 4
    df["dk_int_points"] = df.get("interceptions", 0) * -1

    df["dk_rush_yds_points"] = df.get("rushing_yards", 0) * 0.1
    df["dk_rush_td_points"] = df.get("rushing_tds", 0) * 6

    df["dk_rec_points"] = df.get("receptions", 0) * 1
    df["dk_rec_yds_points"] = df.get("receiving_yards", 0) * 0.1
    df["dk_rec_td_points"] = df.get("receiving_tds", 0) * 6

    fumbles_lost = _safe_get(
        df,
        ["rushing_fumbles_lost", "receiving_fumbles_lost", "sack_fumbles_lost", "fumbles_lost"],
    )
    df["dk_fum_lost_points"] = fumbles_lost * -1

    df["dk_pass_300_bonus"] = np.where(df.get("passing_yards", 0) >= 300, 3, 0)
    df["dk_rush_100_bonus"] = np.where(df.get("rushing_yards", 0) >= 100, 3, 0)
    df["dk_rec_100_bonus"] = np.where(df.get("receiving_yards", 0) >= 100, 3, 0)

    df["dk_rush_2pt_points"] = df.get("rushing_2pt_conversions", 0) * 2
    df["dk_rec_2pt_points"] = df.get("receiving_2pt_conversions", 0) * 2
    df["dk_pass_2pt_points"] = df.get("passing_2pt_conversions", 0) * 2

    score_columns = [
        "dk_pass_yds_points",
        "dk_pass_td_points",
        "dk_int_points",
        "dk_rush_yds_points",
        "dk_rush_td_points",
        "dk_rec_points",
        "dk_rec_yds_points",
        "dk_rec_td_points",
        "dk_fum_lost_points",
        "dk_pass_300_bonus",
        "dk_rush_100_bonus",
        "dk_rec_100_bonus",
        "dk_rush_2pt_points",
        "dk_rec_2pt_points",
        "dk_pass_2pt_points",
    ]
    df["dk_total_points"] = df[score_columns].sum(axis=1)

    # Optional salary -> value metric if salary is present
    if "dk_salary" in df.columns:
        df["salary_points_ratio"] = df["dk_total_points"] / df["dk_salary"]

    return df


def build_weekly_scores(
    season: int,
    weeks: Iterable[int] | None = None,
    connection_string: str | None = None,
) -> int:
    """
    Populate nfl_weekly_data_with_scores for the given season/weeks.

    Returns the number of rows written.
    """
    conn_str = connection_string or get_connection_string()
    engine = create_engine(conn_str)
    with engine.begin() as connection:
        if weeks:
            logging.info("Reading weekly data for scoring (season=%s, weeks=%s)", season, weeks)
            df = pd.read_sql(
                text("SELECT * FROM nfl_weekly_data WHERE season = :season AND week = ANY(:weeks)"),
                connection,
                params={"season": season, "weeks": list(weeks)},
            )
        else:
            logging.info("Reading weekly data for scoring (season=%s, full season recompute)", season)
            df = pd.read_sql(
                text("SELECT * FROM nfl_weekly_data WHERE season = :season"),
                connection,
                params={"season": season},
            )

    if df.empty:
        logging.warning("No weekly data found for scoring (season=%s weeks=%s)", season, weeks)
        return 0
    # Ensure team columns are strings to avoid dtype issues
    for col in ["recent_team", "team", "opponent_team"]:
        if col in df.columns:
            df[col] = df[col].astype(str)

    scored = compute_dk_scoring(df)
    scored = scored.drop_duplicates(subset=["player_id", "season", "week"])

    # Minimal processing: keep raw ids/names only; skip player_master attachment here

    with engine.begin() as connection:
        if weeks:
            delete_sql = "DELETE FROM nfl_weekly_data_with_scores WHERE season = :season AND week = ANY(:weeks)"
            connection.execute(text(delete_sql), {"season": season, "weeks": list(weeks)})
        else:
            delete_sql = "DELETE FROM nfl_weekly_data_with_scores WHERE season = :season"
            connection.execute(text(delete_sql), {"season": season})
        ensure_table_columns(engine, "nfl_weekly_data_with_scores", scored)
        scored.to_sql(
            "nfl_weekly_data_with_scores",
            connection,
            if_exists="append",
            index=False,
        )
    logging.info("Inserted %s scored weekly rows for season=%s", len(scored), season)
    return len(scored)
