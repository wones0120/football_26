"""Slate-oriented helper services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd

from Database.config import get_connection_string
from Database.operations import delete_from_postgres, insert_into_postgres, ensure_table_columns
from .player_master import PlayerMasterResolver
from .player_master import PlayerMasterResolver


@dataclass
class SlateLoadResult:
    resource: str
    season: int
    week: int
    slate: str
    rows_written: int
    message: str
    completed_at: datetime


class SlateDataService:
    """Slate-oriented helper services."""

    def load_salaries(self, season: int, week: int, slate: str, source: str | None) -> SlateLoadResult:
        path = self._find_salary_file(season, week, slate)
        if path is None:
            return SlateLoadResult(
                resource="salaries",
                season=season,
                week=week,
                slate=slate,
                rows_written=0,
                message=f"Could not find salary file matching DKSalaries_{season}_{week}_{slate}.csv",
                completed_at=datetime.utcnow(),
            )

        df = pd.read_csv(path)
        rename_map = {
            "Position": "position",
            "Name": "name",
            "Name + ID": "name_and_id",
            "ID": "player_id",
            "Roster Position": "roster_position",
            "Salary": "salary",
            "Game Info": "game_info",
            "TeamAbbrev": "player_team",
            "AvgPointsPerGame": "average_points_per_game",
            "Slate": "slate",
        }
        df = df.rename(columns=rename_map)
        numeric_cols = ["salary", "player_id", "week", "season"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["season"] = season
        df["week"] = week
        df["slate"] = slate

        # Attach player_master_id via shared resolver (cached per batch)
        pm_resolver = PlayerMasterResolver()
        df = pm_resolver.attach_to_dataframe(
            df,
            name_col="name" if "name" in df.columns else "player_name",
            team_col="player_team" if "player_team" in df.columns else "team" if "team" in df.columns else None,
            pos_col="position" if "position" in df.columns else None,
        )

        # Attach player_master_id for stable joins
        pm_resolver = PlayerMasterResolver()
        df = pm_resolver.attach_to_dataframe(
            df,
            name_col="name" if "name" in df.columns else "player_name",
            team_col="player_team" if "player_team" in df.columns else "team" if "team" in df.columns else None,
            pos_col="position" if "position" in df.columns else None,
        )

        # Attempt to normalize player_id to internal IDs and retain original as dk_player_id
        try:
            mapped_df, unmatched = self._map_salary_ids(df, season, week)
            df = mapped_df
            if unmatched:
                import logging
                logging.warning("Unmatched salary rows (top 5 shown): %s", unmatched[:5])
                if unmatched:
                    df_unmatched = pd.DataFrame(unmatched, columns=["name", "player_team"])
                    df_unmatched["season"] = season
                    df_unmatched["week"] = week
                    df_unmatched["slate"] = slate
                    df_unmatched["created_at"] = datetime.utcnow()
                    conn = get_connection_string()
                    from sqlalchemy import create_engine
                    engine = create_engine(conn)
                    from Database.operations import ensure_table_columns
                    ensure_table_columns(engine, "dk_salary_unmatched", df_unmatched)
                    df_unmatched.to_sql("dk_salary_unmatched", engine, if_exists="append", index=False)
        except Exception as exc:  # noqa: BLE001
            import logging
            logging.warning("Failed to map salary IDs; keeping originals (%s)", exc)

        conn = get_connection_string()
        from sqlalchemy import create_engine
        engine = create_engine(conn)
        ensure_table_columns(engine, "dk_salaries", df)
        delete_from_postgres(connection_string=conn, table_name="dk_salaries", season=season, week=week, slate=slate)
        success = insert_into_postgres(
            df=df, connection_string=conn, table_name="dk_salaries", season=season, week=week, slate=slate
        )
        rows = len(df) if success else 0
        return SlateLoadResult(
            resource="salaries",
            season=season,
            week=week,
            slate=slate,
            rows_written=rows,
            message=f"Inserted {rows} rows from {path.name}" if success else f"Failed to insert data from {path.name}",
            completed_at=datetime.utcnow(),
        )

    def load_injuries(self, season: int, week: int, slate: str, source: str | None) -> SlateLoadResult:
        path = self._find_injury_file(season, week, slate)
        if path is None:
            return SlateLoadResult(
                resource="injuries",
                season=season,
                week=week,
                slate=slate,
                rows_written=0,
                message=f"Could not find injury file matching *{season}*{week}* (e.g., FanDuel_injuries_{season}_{week}.csv)",
                completed_at=datetime.utcnow(),
            )

        df = pd.read_csv(path)
        # Normalize column names (case-insensitive keys)
        rename_map = {
            "id": "player_id",
            "player id": "player_id",
            "first name": "first_name",
            "nickname": "nickname",
            "last name": "last_name",
            "position": "position",
            "fppg": "fppg",
            "played": "played",
            "salary": "salary",
            "game": "game_info",
            "team": "team",
            "opponent": "opponent",
            "injury indicator": "injury_indicator",
            "injury details": "injury_details",
            "tier": "tier",
            "roster position": "roster_position",
        }
        lower_cols = {c.lower(): c for c in df.columns}
        for key, new_name in rename_map.items():
            if key in lower_cols:
                df = df.rename(columns={lower_cols[key]: new_name})
        # Drop unnamed/index columns
        df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
        # Build player_name if missing and try to backfill player_id from salaries for the same slate
        if "player_name" not in df.columns:
            if {"first_name", "last_name"}.issubset(df.columns):
                df["player_name"] = (df["first_name"].astype(str) + " " + df["last_name"].astype(str)).str.strip()
            elif "nickname" in df.columns:
                df["player_name"] = df["nickname"].astype(str)
            elif "name" in df.columns:
                df["player_name"] = df["name"].astype(str)
        if "player_name" in df.columns:
            df["player_name"] = df["player_name"].astype(str)
        if "player_id" not in df.columns:
            df["player_id"] = ""
        df["player_id"] = df["player_id"].astype(str).str.strip()

        def _norm(val: str) -> str:
            return " ".join(str(val or "").lower().replace("'", " ").split())

        df["name_norm"] = df.get("player_name", df.get("name", "")).apply(_norm)
        team_col = "team" if "team" in df.columns else "player_team" if "player_team" in df.columns else None
        df["team_norm"] = df[team_col].astype(str).str.upper() if team_col else ""
        missing_mask = df["player_id"].isna() | (df["player_id"] == "")

        if missing_mask.any():
            from sqlalchemy import create_engine, text
            engine = create_engine(get_connection_string())
            with engine.begin() as conn:
                sal_df = pd.read_sql(
                    text(
                        "SELECT player_id, name, player_team FROM dk_salaries "
                        "WHERE season = :season AND week = :week AND slate = :slate"
                    ),
                    conn,
                    params={"season": season, "week": week, "slate": slate},
                )
            if not sal_df.empty:
                sal_df["player_id"] = sal_df["player_id"].astype(str)
                sal_df["name_norm"] = sal_df["name"].apply(_norm)
                sal_df["team_norm"] = sal_df["player_team"].astype(str).str.upper()
                name_map = dict(zip(sal_df["name_norm"], sal_df["player_id"]))
                df.loc[missing_mask, "player_id"] = df.loc[missing_mask, "name_norm"].map(name_map)
                combo_map = dict(zip(zip(sal_df["name_norm"], sal_df["team_norm"]), sal_df["player_id"]))
                still_missing = df["player_id"].isna() | (df["player_id"] == "")
                df.loc[still_missing, "player_id"] = df.loc[still_missing].apply(
                    lambda r: combo_map.get((r["name_norm"], r.get("team_norm", ""))), axis=1
                )

        # Attach player_master_id
        pm_resolver = PlayerMasterResolver()
        pm_name_col = "player_name" if "player_name" in df.columns else "nickname" if "nickname" in df.columns else None
        if not pm_name_col and "name" in df.columns:
            pm_name_col = "name"
        pm_team_col = "team" if "team" in df.columns else None
        pm_pos_col = "position" if "position" in df.columns else None
        if pm_name_col:
            df = pm_resolver.attach_to_dataframe(df, name_col=pm_name_col, team_col=pm_team_col, pos_col=pm_pos_col)

        # Capture unmatched rows, then drop them
        missing_mask = df["player_id"].isna() | (df["player_id"] == "")
        if missing_mask.any():
            unmatched_df = df.loc[missing_mask, :].copy()
            unmatched_df["season"] = season
            unmatched_df["week"] = week
            unmatched_df["slate"] = slate
            unmatched_df["name"] = unmatched_df.get("player_name", unmatched_df.get("nickname", ""))
            unmatched_df["player_team"] = unmatched_df.get("team", "")
            unmatched_df["opponent"] = unmatched_df.get("opponent", "")
            unmatched_df["created_at"] = datetime.utcnow()
            unmatched_df = unmatched_df[["season", "week", "slate", "name", "player_team", "opponent", "created_at"]]
            conn = get_connection_string()
            from sqlalchemy import create_engine
            engine = create_engine(conn)
            ensure_table_columns(engine, "weekly_injury_unmatched", unmatched_df)
            unmatched_df.to_sql("weekly_injury_unmatched", engine, if_exists="append", index=False)
        before = len(df)
        df = df[~missing_mask]
        dropped = before - len(df)
        if dropped:
            import logging
            logging.warning("Dropped %s injury rows missing player_id", dropped)

        # Attach player_master_id via shared resolver (cached per batch)
        pm_resolver = PlayerMasterResolver()
        pm_name_col = "player_name" if "player_name" in df.columns else "nickname" if "nickname" in df.columns else None
        if not pm_name_col and "name" in df.columns:
            pm_name_col = "name"
        pm_team_col = "team" if "team" in df.columns else None
        pm_pos_col = "position" if "position" in df.columns else None
        if pm_name_col:
            df = pm_resolver.attach_to_dataframe(df, name_col=pm_name_col, team_col=pm_team_col, pos_col=pm_pos_col)
        # Fill text fields to satisfy NOT NULL constraints
        text_fill = [
            "position",
            "first_name",
            "nickname",
            "last_name",
            "game_info",
            "team",
            "opponent",
            "injury_indicator",
            "injury_details",
            "tier",
            "roster_position",
            "slate",
        ]
        for col in text_fill:
            if col in df.columns:
                df[col] = df[col].fillna("")
        numeric_fill = ["fppg", "played", "salary"]
        for col in numeric_fill:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        df["season"] = season
        df["week"] = week
        df["slate"] = slate

        # Coerce numeric fields where present
        for col in ["salary", "fppg"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Ensure schema has slate column (and any others) before writing
        from Database.operations import ensure_table_columns  # local import to avoid cycle
        from sqlalchemy import create_engine
        engine = create_engine(get_connection_string())
        ensure_table_columns(engine, "weekly_injuries", df)

        conn = get_connection_string()
        delete_from_postgres(
            connection_string=conn,
            table_name="weekly_injuries",
            season=season,
            week=week,
            slate=slate,
        )
        success = insert_into_postgres(
            df=df,
            connection_string=conn,
            table_name="weekly_injuries",
            season=season,
            week=week,
            slate=slate,
        )
        rows = len(df) if success else 0
        return SlateLoadResult(
            resource="injuries",
            season=season,
            week=week,
            slate=slate,
            rows_written=rows,
            message=f"Inserted {rows} rows from {path.name}" if success else f"Failed to insert data from {path.name}",
            completed_at=datetime.utcnow(),
        )

    def _find_salary_file(self, season: int, week: int, slate: str) -> Path | None:
        roots = [Path.cwd(), Path.home() / "Downloads"]
        target_tokens = [str(season), str(week), self._normalize_token(slate)]

        for root in roots:
            if not root.exists():
                continue
            candidates = list(root.rglob("DKSalaries*.csv"))
            for path in candidates:
                name_norm = self._normalize_token(path.name)
                if all(token in name_norm for token in target_tokens):
                    return path

            # Fallback: loose matching on season/week only
            for path in candidates:
                name_norm = self._normalize_token(path.name)
                if str(season) in name_norm and str(week) in name_norm:
                    return path
        return None

    def _find_injury_file(self, season: int, week: int, slate: str | None = None) -> Path | None:
        roots = [Path.cwd(), Path.home() / "Downloads"]
        target_tokens = [str(season), str(week), "injur"]
        if slate:
            target_tokens.append(self._normalize_token(slate))
        for root in roots:
            if not root.exists():
                continue
            candidates = list(root.rglob("*.csv"))
            for path in candidates:
                name_norm = self._normalize_token(path.name)
                if all(token in name_norm for token in target_tokens):
                    return path
        return None

    @staticmethod
    def _normalize_token(text: str) -> str:
        key = "".join(ch for ch in text.lower() if ch.isalnum())
        if "hollywoodbrown" in key or ("hollywood" in key and "brown" in key):
            return "marquisebrown"
        return key

    def _map_salary_ids(self, df: pd.DataFrame, season: int, week: int) -> tuple[pd.DataFrame, list[tuple[str, str]]]:
        """Map salary IDs to internal player_ids via name/team; retain original as dk_player_id."""
        from sqlalchemy import create_engine, text
        engine = create_engine(get_connection_string())
        salaries = df.copy()
        salaries["dk_player_id"] = salaries["player_id"]
        def _alias(name: str) -> str:
            key = " ".join(name.lower().replace("'", " ").split())
            if "hollywood brown" in key or ("hollywood" in key and "brown" in key):
                return "marquise brown"
            return key

        salaries["name_norm"] = salaries["name"].astype(str).str.lower().str.strip().map(_alias)

        # Build reference maps
        rosters = pd.read_sql(
            text(
                "SELECT player_id, player_name, team, week "
                "FROM nfl_weekly_rosters "
                "WHERE season = :season AND player_id IS NOT NULL AND team IS NOT NULL"
            ),
            engine,
            params={"season": season},
        )
        name_team_map: dict[tuple[str, str], str] = {}
        name_map: dict[str, str] = {}
        if not rosters.empty:
            rosters = rosters.sort_values("week")
            rosters["name_norm"] = rosters["player_name"].str.lower().str.strip().map(_alias)
            # Latest per player_id
            latest = rosters.drop_duplicates("player_id", keep="last")
            for _, row in latest.iterrows():
                pid = str(row["player_id"])
                nn = row["name_norm"]
                team = row["team"]
                name_team_map[(nn, team)] = pid
                name_map[nn] = pid

        weekly = pd.read_sql(
            text(
                "SELECT player_id, player_name FROM nfl_weekly_data_with_scores "
                "WHERE season = :season"
            ),
            engine,
            params={"season": season},
        )
        if not weekly.empty:
            weekly["name_norm"] = weekly["player_name"].str.lower().str.strip().map(_alias)
            # Latest per player_id
            weekly_latest = weekly.drop_duplicates("player_id", keep="last")
            for _, row in weekly_latest.iterrows():
                pid = str(row["player_id"])
                nn = row["name_norm"]
                name_map.setdefault(nn, pid)

        resolved = []
        unmatched_rows: list[tuple[str, str]] = []
        for _, row in salaries.iterrows():
            name_norm = row["name_norm"]
            team = row["player_team"]
            resolved_id = None
            if (name_norm, team) in name_team_map:
                resolved_id = name_team_map[(name_norm, team)]
            elif name_norm in name_map:
                resolved_id = name_map[name_norm]
            if resolved_id:
                row["internal_player_id"] = resolved_id
            else:
                unmatched_rows.append((row["name"], team))
                row["internal_player_id"] = row["dk_player_id"]
            resolved.append(row)

        resolved_df = pd.DataFrame(resolved).drop(columns=["name_norm"])
        return resolved_df, unmatched_rows
