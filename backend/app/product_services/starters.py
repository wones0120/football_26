"""Derive starting QBs per team from rosters and injuries."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import pandas as pd
from sqlalchemy import create_engine, text

from Database.config import get_connection_string
from Database.operations import ensure_table_columns, delete_from_postgres


@dataclass
class StarterLoadResult:
    season: int
    week: int
    slate: str
    rows_written: int
    message: str
    completed_at: datetime


class StartingQBService:
    def __init__(self, connection_string: Optional[str] = None) -> None:
        self.connection_string = connection_string or get_connection_string()
        self.engine = create_engine(self.connection_string)

    def derive_starters(self, season: int, week: int, slate: str) -> StarterLoadResult:
        rosters = self._load_rosters(season, week)
        injuries = self._load_injuries(season, week)
        schedule = self._load_schedule(season, week)

        if rosters.empty:
            return StarterLoadResult(
                season=season,
                week=week,
                slate=slate,
                rows_written=0,
                message="No rosters found for week.",
                completed_at=datetime.utcnow(),
            )

        starters = self._select_qbs(rosters, injuries, schedule)
        if starters.empty:
            return StarterLoadResult(
                season=season,
                week=week,
                slate=slate,
                rows_written=0,
                message="No starting QBs derived.",
                completed_at=datetime.utcnow(),
            )

        starters["season"] = season
        starters["week"] = week
        starters["slate"] = slate
        starters["source"] = "derived"

        try:
            delete_from_postgres(
                connection_string=self.connection_string,
                table_name="starting_qbs",
                season=season,
                week=week,
                slate=slate,
            )
        except Exception as exc:  # noqa: BLE001
            logging.info("starting_qbs not present yet, will create on write (%s)", exc)

        starters.to_sql("starting_qbs", self.engine, if_exists="append", index=False)

        return StarterLoadResult(
            season=season,
            week=week,
            slate=slate,
            rows_written=len(starters),
            message=f"Inserted {len(starters)} starting QBs",
            completed_at=datetime.utcnow(),
        )

    def _load_rosters(self, season: int, week: int) -> pd.DataFrame:
        query = text(
            "SELECT player_id, player_name, full_name, team, position, depth_chart_position "
            "FROM nfl_weekly_rosters WHERE season = :season AND week = :week"
        )
        with self.engine.begin() as conn:
            df = pd.read_sql(query, conn, params={"season": season, "week": week})
        if df.empty:
            return df
        # Normalize display name
        if "player_name" in df.columns:
            df["player_display_name"] = df["player_name"]
        if "full_name" in df.columns:
            df["player_display_name"] = df["player_display_name"].fillna(df["full_name"])
        return df

    def _load_injuries(self, season: int, week: int) -> pd.DataFrame:
        query = text(
            "SELECT player_id, injury_indicator FROM weekly_injuries "
            "WHERE season = :season AND week = :week"
        )
        with self.engine.begin() as conn:
            return pd.read_sql(query, conn, params={"season": season, "week": week})

    def _load_schedule(self, season: int, week: int) -> pd.DataFrame:
        query = text(
            "SELECT home_team, away_team FROM nfl_schedules WHERE season = :season AND week = :week"
        )
        with self.engine.begin() as conn:
            return pd.read_sql(query, conn, params={"season": season, "week": week})

    def _select_qbs(self, rosters: pd.DataFrame, injuries: pd.DataFrame, schedule: pd.DataFrame) -> pd.DataFrame:
        qbs = rosters[rosters["position"] == "QB"].copy()
        # Prefer depth_chart_position == 'QB1' or first QB per team if not labeled
        if "depth_chart_position" in qbs.columns:
            qbs["is_starter"] = qbs["depth_chart_position"].fillna("").str.upper().eq("QB1")
        else:
            qbs["is_starter"] = False

        if injuries is not None and not injuries.empty:
            inj_map = injuries.set_index("player_id")["injury_indicator"].str.upper().to_dict()
            qbs["injury_indicator"] = qbs["player_id"].map(inj_map)
            qbs["is_out"] = qbs["injury_indicator"].isin(["O", "OUT", "IR"])
        else:
            qbs["is_out"] = False

        starters = []
        for team in qbs["team"].dropna().unique():
            team_qbs = qbs[qbs["team"] == team].copy()
            team_qbs = team_qbs[~team_qbs["is_out"]]
            if team_qbs.empty:
                logging.warning("No healthy QB found for team %s", team)
                continue
            starter = team_qbs[team_qbs["is_starter"]].head(1)
            if starter.empty:
                starter = team_qbs.head(1)
            starters.append(starter)

        if not starters:
            return pd.DataFrame()

        starters_df = pd.concat(starters)
        if "player_display_name" in starters_df.columns:
            starters_df["player_name"] = starters_df["player_display_name"]
        # Drop duplicate columns if present
        starters_df = starters_df.loc[:, ~starters_df.columns.duplicated()]

        # Attach opponent from schedule if available
        if schedule is not None and not schedule.empty:
            opp_map = {}
            for _, row in schedule.iterrows():
                opp_map[row.home_team] = row.away_team
                opp_map[row.away_team] = row.home_team
            starters_df["opponent"] = starters_df["team"].map(opp_map)

        starters_df["status"] = "active"
        starters_df = starters_df[
            ["player_id", "player_name", "team", "opponent", "status"]
        ].drop_duplicates()
        return starters_df
