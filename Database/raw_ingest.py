"""Raw ingest helpers for weekly stats, salaries, and injuries."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

import pandas as pd
from sqlalchemy import create_engine, text

from .config import get_connection_string
from .operations import ensure_table_columns
from .data_sources import NFLDataSource, NFLDataset


def _ensure_table(engine, table_name: str, df: pd.DataFrame):
    ensure_table_columns(engine, table_name, df)


def load_raw_weekly_stats(season: int, weeks: Iterable[int] | None = None, connection_string: str | None = None) -> int:
    """Fetch weekly stats from the source API and store as raw_weekly_stats for given season/weeks."""
    conn_str = connection_string or get_connection_string()
    engine = create_engine(conn_str)
    ds = NFLDataSource()
    df = ds.fetch(NFLDataset.WEEKLY_STATS, season)
    if weeks:
        df = df[df["week"].isin(list(weeks))]
    if df.empty:
        logging.warning("No weekly data found for raw ingest (season=%s weeks=%s)", season, weeks)
        return 0
    df["season"] = season
    _ensure_table(engine, "raw_weekly_stats", df)
    with engine.begin() as conn:
        if weeks:
            conn.execute(text("DELETE FROM raw_weekly_stats WHERE season = :season AND week = ANY(:weeks)"),
                         {"season": season, "weeks": list(weeks)})
        else:
            conn.execute(text("DELETE FROM raw_weekly_stats WHERE season = :season"), {"season": season})
        df.to_sql("raw_weekly_stats", conn, if_exists="append", index=False)
    logging.info("Inserted %s rows into raw_weekly_stats (season=%s weeks=%s)", len(df), season, weeks)
    return len(df)


def load_raw_schedules(season: int, connection_string: str | None = None) -> int:
    """Fetch schedules from the source API and store as raw_schedules for a season."""
    conn_str = connection_string or get_connection_string()
    engine = create_engine(conn_str)
    ds = NFLDataSource()
    df = ds.fetch(NFLDataset.SCHEDULES, season)
    if df.empty:
        logging.warning("No schedules found for raw ingest (season=%s)", season)
        return 0
    df["season"] = season
    _ensure_table(engine, "raw_schedules", df)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM raw_schedules WHERE season = :season"), {"season": season})
        df.to_sql("raw_schedules", conn, if_exists="append", index=False)
    logging.info("Inserted %s rows into raw_schedules (season=%s)", len(df), season)
    return len(df)


def load_raw_weekly_rosters(season: int, weeks: Iterable[int] | None = None, connection_string: str | None = None) -> int:
    """Fetch weekly rosters from the source API and store as raw_weekly_rosters for given season/weeks."""
    conn_str = connection_string or get_connection_string()
    engine = create_engine(conn_str)
    ds = NFLDataSource()
    df = ds.fetch(NFLDataset.WEEKLY_ROSTERS, season)
    if weeks and "week" in df.columns:
        df = df[df["week"].isin(list(weeks))]
    if df.empty:
        logging.warning("No weekly rosters found for raw ingest (season=%s weeks=%s)", season, weeks)
        return 0
    df["season"] = season
    _ensure_table(engine, "raw_weekly_rosters", df)
    with engine.begin() as conn:
        if weeks:
            conn.execute(text("DELETE FROM raw_weekly_rosters WHERE season = :season AND week = ANY(:weeks)"),
                         {"season": season, "weeks": list(weeks)})
        else:
            conn.execute(text("DELETE FROM raw_weekly_rosters WHERE season = :season"), {"season": season})
        df.to_sql("raw_weekly_rosters", conn, if_exists="append", index=False)
    logging.info("Inserted %s rows into raw_weekly_rosters (season=%s weeks=%s)", len(df), season, weeks)
    return len(df)


def load_raw_salaries(file_path: Path, season: int, week: int, slate: str, connection_string: str | None = None) -> int:
    """Load a salary CSV as raw_salaries."""
    conn_str = connection_string or get_connection_string()
    engine = create_engine(conn_str)
    # Use python engine to tolerate stray commas/quotes; skip bad lines rather than failing the whole ingest.
    df = pd.read_csv(file_path, engine="python", on_bad_lines="skip")
    bad_line_count = 0
    if hasattr(df, "errors"):
        bad_line_count = len(getattr(df, "errors", []))
    df["season"] = season
    df["week"] = week
    df["slate"] = slate
    _ensure_table(engine, "raw_salaries", df)
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM raw_salaries WHERE season = :season AND week = :week AND slate = :slate"),
            {"season": season, "week": week, "slate": slate},
        )
        df.to_sql("raw_salaries", conn, if_exists="append", index=False)
    if bad_line_count:
        logging.warning("Skipped %s bad lines while reading salaries CSV %s", bad_line_count, file_path)
    logging.info("Inserted %s rows into raw_salaries for %s/%s/%s", len(df), season, week, slate)
    return len(df)


def load_raw_injuries(file_path: Path, season: int, week: int, slate: str, connection_string: str | None = None) -> int:
    """Load an injury CSV as raw_injuries."""
    conn_str = connection_string or get_connection_string()
    engine = create_engine(conn_str)
    df = pd.read_csv(file_path)
    df["season"] = season
    df["week"] = week
    df["slate"] = slate
    _ensure_table(engine, "raw_injuries", df)
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM raw_injuries WHERE season = :season AND week = :week AND slate = :slate"),
            {"season": season, "week": week, "slate": slate},
        )
        df.to_sql("raw_injuries", conn, if_exists="append", index=False)
    logging.info("Inserted %s rows into raw_injuries for %s/%s/%s", len(df), season, week, slate)
    return len(df)
