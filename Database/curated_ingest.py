"""Curated ingest helpers: raw -> curated tables with player_master_id stamping."""

from __future__ import annotations

import logging
import uuid
import json
from typing import Iterable, Optional, Dict, Tuple

import pandas as pd
from sqlalchemy import create_engine, text

from .config import get_connection_string
from .dst import deterministic_dst_player_id, is_dst_position, normalize_team
from .operations import ensure_table_columns
from .raw_ingest import (
    _ensure_table,
)


def _norm_name(name: str) -> str:
    return " ".join(str(name or "").lower().replace("'", " ").split())


def _strip_suffix(name_norm: str) -> str:
    suffixes = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"}
    parts = name_norm.split()
    if parts and parts[-1] in suffixes:
        return " ".join(parts[:-1])
    return name_norm


def _norm_team(team: str) -> str:
    return normalize_team(team)


def ensure_player_master(engine) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS player_master (
        player_master_id UUID PRIMARY KEY,
        full_name TEXT NOT NULL,
        name_norm TEXT NOT NULL,
        first_name TEXT,
        last_name TEXT,
        primary_team TEXT,
        position TEXT,
        aliases JSONB DEFAULT '[]',
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_player_master_name_norm ON player_master(name_norm);
    CREATE INDEX IF NOT EXISTS idx_player_master_name_team ON player_master(name_norm, primary_team);
    """
    with engine.begin() as conn:
        conn.execute(text(ddl))


def _extract_name(row: pd.Series) -> str:
    """Pick the best available name field."""
    for col in [
        "player_name",
        "player",
        "display_name",
        "player_display_name",
        "name",
        "full_name",
        "nickname",
    ]:
        if col in row and pd.notna(row.get(col)) and str(row.get(col)).strip():
            return str(row.get(col)).strip()
    return ""


class PlayerResolver:
    """Cached resolver using roster lookups first, then player_master; inserts allowed on bootstrap only."""

    def __init__(self, engine):
        self.engine = engine
        self.cache: Dict[Tuple[str, str], str] = {}
        ensure_player_master(engine)
        with engine.begin() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM player_master")).scalar()
        self.bootstrap_allowed = count == 0
        # Build a roster-based name map (full name + team) for the current season if available
        self.roster_lookup: Dict[Tuple[str, str], Dict[str, str]] = {}

    def _ensure_roster_lookup(self, season: int):
        if self.roster_lookup:
            return
        try:
            with self.engine.begin() as conn:
                df = pd.read_sql(
                    text("SELECT * FROM raw_weekly_rosters WHERE season = :season"),
                    conn,
                    params={"season": season},
                )
            if df.empty:
                return
            for _, row in df.iterrows():
                nm = _extract_name(row)
                name_norm = _strip_suffix(_norm_name(nm))
                team_norm = _norm_team(row.get("team", ""))
                self.roster_lookup[(name_norm, team_norm)] = {
                    "full_name": nm,
                    "position": row.get("position", ""),
                }
        except Exception:
            return

    def resolve(self, full_name: str, team: Optional[str], position: Optional[str], season: Optional[int] = None) -> Optional[str]:
        name_norm = _strip_suffix(_norm_name(full_name))
        team_norm = _norm_team(team)
        if not name_norm:  # skip empty/invalid names
            return None
        key = (name_norm, team_norm)
        if key in self.cache:
            return self.cache[key]

        # Attempt roster lookup if season provided
        if season:
            self._ensure_roster_lookup(season)
            if key in self.roster_lookup:
                roster_name = self.roster_lookup[key]["full_name"]
                roster_pos = self.roster_lookup[key]["position"]
                name_norm = _strip_suffix(_norm_name(roster_name))
                position = roster_pos or position
                key = (name_norm, team_norm)

        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT player_master_id FROM player_master "
                    "WHERE name_norm = :name_norm AND primary_team = :team LIMIT 1"
                ),
                {"name_norm": name_norm, "team": team_norm},
            ).fetchone()
            if not row:
                row = conn.execute(
                    text(
                        "SELECT player_master_id FROM player_master "
                        "WHERE name_norm = :name_norm LIMIT 1"
                    ),
                    {"name_norm": name_norm},
                ).fetchone()
            if row:
                pmid = str(row.player_master_id)
                self.cache[key] = pmid
                return pmid
            if self.bootstrap_allowed:
                pmid = str(uuid.uuid4())
                parts = full_name.split()
                first_name = parts[0] if parts else ""
                last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
                aliases_json = json.dumps([name_norm])
                conn.execute(
                    text(
                        "INSERT INTO player_master (player_master_id, full_name, name_norm, first_name, last_name, primary_team, position, aliases) "
                        "VALUES (:id, :full_name, :name_norm, :first_name, :last_name, :team, :position, CAST(:aliases AS JSONB))"
                    ),
                    {
                        "id": pmid,
                        "full_name": full_name,
                        "name_norm": name_norm,
                        "first_name": first_name,
                        "last_name": last_name,
                        "team": team_norm,
                        "position": position,
                        "aliases": aliases_json,
                    },
                )
                self.cache[key] = pmid
                return pmid
        return None


def _ensure_unmatched_table(engine, df: pd.DataFrame) -> None:
    """Ensure curated_unmatched has expected columns including add_to_player_master."""
    df_with_flag = df.copy()
    if "add_to_player_master" not in df_with_flag.columns:
        df_with_flag["add_to_player_master"] = pd.Series(dtype=object)
    ensure_table_columns(engine, "curated_unmatched", df_with_flag)
    # Ensure a primary key exists for easy editing
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE curated_unmatched
                ADD COLUMN IF NOT EXISTS id BIGSERIAL;
                """
            )
        )
        # Backfill any NULL ids
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'curated_unmatched' AND column_name = 'id') THEN
                        UPDATE curated_unmatched
                        SET id = nextval(pg_get_serial_sequence('curated_unmatched','id'))
                        WHERE id IS NULL;
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint WHERE conname = 'curated_unmatched_pkey'
                        ) THEN
                            ALTER TABLE curated_unmatched ADD CONSTRAINT curated_unmatched_pkey PRIMARY KEY (id);
                        END IF;
                    END IF;
                END$$;
                """
            )
        )


def curate_weekly_stats(season: int, weeks: Iterable[int] | None = None, connection_string: str | None = None) -> int:
    """Transform raw_weekly_stats -> curated_weekly_stats with player_master_id."""
    conn_str = connection_string or get_connection_string()
    engine = create_engine(conn_str)
    pos_filter = {"WR", "RB", "QB", "TE"}
    with engine.begin() as conn:
        if weeks:
            raw = pd.read_sql(
                text("SELECT * FROM raw_weekly_stats WHERE season = :season AND week = ANY(:weeks)"),
                conn,
                params={"season": season, "weeks": list(weeks)},
            )
        else:
            raw = pd.read_sql(
                text("SELECT * FROM raw_weekly_stats WHERE season = :season"),
                conn,
                params={"season": season},
            )
    if raw.empty:
        logging.warning("No raw_weekly_stats found for season=%s weeks=%s", season, weeks)
        return 0
    # Drop rows without a player_display_name
    if "player_display_name" in raw.columns:
        raw = raw[raw["player_display_name"].fillna("").astype(str).str.strip() != ""]
    if raw.empty:
        logging.warning("All raw_weekly_stats rows missing player_display_name (season=%s weeks=%s)", season, weeks)
        return 0
    # Build direct full_name lookup map for exact display name matches
    with engine.begin() as conn:
        pm_df = pd.read_sql(text("SELECT player_master_id, full_name FROM player_master"), conn)
    name_map = {}
    if not pm_df.empty:
        pm_df["full_lower"] = pm_df["full_name"].astype(str).str.strip().str.lower()
        name_map = dict(zip(pm_df["full_lower"], pm_df["player_master_id"]))
    resolver = PlayerResolver(engine)
    raw["player_master_id"] = raw.apply(
        lambda r: name_map.get(str(r.get("player_display_name") or "").strip().lower())
        or resolver.resolve(
            _extract_name(r),
            r.get("recent_team") or r.get("team"),
            r.get("position"),
            season=season,
        ),
        axis=1,
    )
    matched = raw[raw["player_master_id"].notna()].copy()
    unmatched = raw[raw["player_master_id"].isna()].copy()

    # Write unmatched to curated_unmatched (replace existing for this season/week)
    _ensure_unmatched_table(engine, raw.head(0))
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM curated_unmatched"))
        if not unmatched.empty:
            unmatched["source"] = "weekly_stats"
            unmatched["add_to_player_master"] = unmatched.get("add_to_player_master", "")
            pos_series = unmatched["position"] if "position" in unmatched.columns else unmatched.get("position_group")
            if pos_series is None or isinstance(pos_series, str):
                pos_series = pd.Series("", index=unmatched.index)
            filtered = unmatched[pos_series.astype(str).str.upper().isin(pos_filter)]
            if not filtered.empty:
                filtered.to_sql("curated_unmatched", conn, if_exists="append", index=False)

    if matched.empty:
        return 0

    curated = matched.copy()
    curated["team_norm"] = curated.get("recent_team", curated.get("team", "")).astype(str).str.upper()
    _ensure_table(engine, "curated_weekly_stats", curated)
    with engine.begin() as conn:
        if weeks:
            conn.execute(text("DELETE FROM curated_weekly_stats WHERE season = :season AND week = ANY(:weeks)"),
                         {"season": season, "weeks": list(weeks)})
        else:
            conn.execute(text("DELETE FROM curated_weekly_stats WHERE season = :season"), {"season": season})
        curated.to_sql("curated_weekly_stats", conn, if_exists="append", index=False)
    logging.info("Inserted %s rows into curated_weekly_stats (season=%s weeks=%s)", len(curated), season, weeks)
    return len(curated)


def curate_salaries(season: int, week: int, slate: str, connection_string: str | None = None) -> int:
    """Transform raw_salaries -> curated_salaries with player_master_id."""
    conn_str = connection_string or get_connection_string()
    engine = create_engine(conn_str)
    pos_filter = {"WR", "RB", "QB", "TE"}
    with engine.begin() as conn:
        raw = pd.read_sql(
            text("SELECT * FROM raw_salaries WHERE season = :season AND week = :week AND slate = :slate"),
            conn,
            params={"season": season, "week": week, "slate": slate},
        )
    if raw.empty:
        logging.warning("No raw_salaries found for season=%s week=%s slate=%s", season, week, slate)
        return 0
    if "player_id" not in raw.columns and "ID" in raw.columns:
        raw["player_id"] = raw["ID"]
    # Drop rows without a name
    raw = raw[raw.apply(lambda r: bool(str(r.get("Name") or r.get("name") or "").strip()), axis=1)]
    if raw.empty:
        logging.warning("All raw_salaries rows missing Name (season=%s week=%s slate=%s)", season, week, slate)
        return 0

    # Build a deterministic map from player_master using full_name and name_norm
    with engine.begin() as conn:
        pm_df = pd.read_sql(
            text("SELECT player_master_id, full_name, name_norm FROM player_master"),
            conn,
        )
    name_to_id = {}
    norm_to_id = {}
    if not pm_df.empty:
        pm_df["full_lower"] = pm_df["full_name"].astype(str).str.strip().str.lower()
        pm_df["norm"] = pm_df["name_norm"].astype(str)
        name_to_id = dict(zip(pm_df["full_lower"], pm_df["player_master_id"]))
        norm_to_id = dict(zip(pm_df["norm"], pm_df["player_master_id"]))

    def _resolve_salary_row(row: pd.Series) -> Optional[str]:
        raw_name = str(row.get("Name") or row.get("name") or "").strip()
        if not raw_name:
            return None
        full_key = raw_name.lower()
        if full_key in name_to_id:
            return name_to_id[full_key]
        norm_key = _strip_suffix(_norm_name(raw_name))
        return norm_to_id.get(norm_key)

    raw["player_master_id"] = raw.apply(_resolve_salary_row, axis=1)
    matched = raw[raw["player_master_id"].notna()].copy()
    unmatched = raw[raw["player_master_id"].isna()].copy()

    # Write unmatched to curated_unmatched (replace existing for this season/week/slate)
    _ensure_unmatched_table(engine, raw.head(0))
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM curated_unmatched WHERE source = :source AND season = :season AND week = :week AND slate = :slate"),
            {"source": "salaries", "season": season, "week": week, "slate": slate},
        )
        if not unmatched.empty:
            unmatched["source"] = "salaries"
            unmatched["slate"] = slate
            if "add_to_player_master" not in unmatched.columns:
                unmatched["add_to_player_master"] = ""
            pos_series = unmatched["position"] if "position" in unmatched.columns else unmatched.get("position_group")
            if pos_series is None or isinstance(pos_series, str):
                pos_series = pd.Series("", index=unmatched.index)
            filtered = unmatched[pos_series.astype(str).str.upper().isin(pos_filter)]
            if not filtered.empty:
                filtered.to_sql("curated_unmatched", conn, if_exists="append", index=False)

    def _is_dst(df: pd.DataFrame) -> pd.Series:
        dst_mask = pd.Series([False] * len(df), index=df.index)
        for col in ["Position", "Roster Position", "position", "roster_position"]:
            if col in df.columns:
                dst_mask = dst_mask | df[col].map(is_dst_position)
        return dst_mask

    dst_unmatched = unmatched[_is_dst(unmatched)] if not unmatched.empty else pd.DataFrame()
    if not dst_unmatched.empty:
        def _dst_master_id(row: pd.Series) -> str | None:
            team = _norm_team(row.get("TeamAbbrev") or row.get("team") or row.get("player_team"))
            name = str(row.get("Name") or row.get("name") or row.get("player_display_name") or "").strip()
            key = team or name
            if not key:
                return None
            return deterministic_dst_player_id(key)

        existing_pm_ids = set(pm_df["player_master_id"].astype(str)) if not pm_df.empty else set()
        new_pm_rows = []
        for idx, row in dst_unmatched.iterrows():
            pmid = row.get("player_master_id")
            if pd.isna(pmid) or not pmid:
                pmid = _dst_master_id(row)
                dst_unmatched.at[idx, "player_master_id"] = pmid
            if pmid and pmid not in existing_pm_ids:
                full_name = str(row.get("Name") or row.get("name") or "DST").strip()
                team = _norm_team(row.get("TeamAbbrev") or row.get("team") or row.get("player_team"))
                new_pm_rows.append(
                    {
                        "player_master_id": pmid,
                        "full_name": full_name,
                        "name_norm": _norm_name(full_name),
                        "first_name": "",
                        "last_name": "",
                        "primary_team": team,
                        "position": "DST",
                        "aliases": "[]",
                    }
                )
                existing_pm_ids.add(pmid)
        if new_pm_rows:
            pm_insert = pd.DataFrame(new_pm_rows)
            with engine.begin() as conn:
                ensure_table_columns(engine, "player_master", pm_insert)
                pm_insert.to_sql("player_master", conn, if_exists="append", index=False)
        curated = pd.concat([matched, dst_unmatched], ignore_index=True)
    else:
        curated = matched.copy()

    if curated.empty:
        return 0

    curated = curated.copy()
    curated["team_norm"] = curated.get("TeamAbbrev", curated.get("player_team", curated.get("team", ""))).astype(str).str.upper()
    # Normalize common fields for downstream consumers
    def _series(name: str, fallback: str = ""):
        if name in curated.columns:
            return curated[name]
        if fallback and fallback in curated.columns:
            return curated[fallback]
        return pd.Series([""] * len(curated), index=curated.index)

    curated["dk_player_id"] = _series("ID", fallback="player_id").astype(str)
    curated["player_display_name"] = _series("Name", fallback="player_name").astype(str)
    curated["position"] = _series("Position", fallback="position").astype(str)
    curated["roster_position"] = _series("Roster Position", fallback="roster_position").astype(str)
    curated["player_team"] = _series("TeamAbbrev", fallback="team").astype(str)

    _ensure_table(engine, "curated_salaries", curated)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM curated_salaries WHERE season = :season AND week = :week AND slate = :slate"),
                     {"season": season, "week": week, "slate": slate})
        curated.to_sql("curated_salaries", conn, if_exists="append", index=False)
    logging.info("Inserted %s rows into curated_salaries (season=%s week=%s slate=%s)", len(curated), season, week, slate)
    return len(curated)


def curate_injuries(season: int, week: int, slate: str, connection_string: str | None = None) -> int:
    """Transform raw_injuries -> curated_injuries with player_master_id."""
    conn_str = connection_string or get_connection_string()
    engine = create_engine(conn_str)
    with engine.begin() as conn:
        raw = pd.read_sql(
            text("SELECT * FROM raw_injuries WHERE season = :season AND week = :week AND slate = :slate"),
            conn,
            params={"season": season, "week": week, "slate": slate},
        )
    if raw.empty:
        logging.warning("No raw_injuries found for season=%s week=%s slate=%s", season, week, slate)
        return 0
    curated = raw.copy()
    # Drop rows with no usable name fields or unusable nickname to avoid spurious unmatched entries
    def _nickname(row: pd.Series) -> str:
        nick_val = row.get("Nickname", row.get("nickname", ""))
        if pd.isna(nick_val):
            return ""
        return str(nick_val or "").strip()

    def _has_any_name(row: pd.Series) -> bool:
        for col in ["Nickname", "nickname", "First Name", "first_name", "Last Name", "last_name"]:
            if col in row and pd.notna(row.get(col)) and str(row.get(col)).strip():
                return True
        return False

    _team_tokens = {
        # Abbreviations
        "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
        "DET", "GB", "HOU", "IND", "JAX", "KC", "LA", "LAC", "LAR", "LV", "MIA",
        "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN",
        "WAS",
        # Common full names (city + mascot and mascot-only variants)
        "ARIZONA CARDINALS", "CARDINALS",
        "ATLANTA FALCONS", "FALCONS",
        "BALTIMORE RAVENS", "RAVENS",
        "BUFFALO BILLS", "BILLS",
        "CAROLINA PANTHERS", "PANTHERS",
        "CHICAGO BEARS", "BEARS",
        "CINCINNATI BENGALS", "BENGALS",
        "CLEVELAND BROWNS", "BROWNS",
        "DALLAS COWBOYS", "COWBOYS",
        "DENVER BRONCOS", "BRONCOS",
        "DETROIT LIONS", "LIONS",
        "GREEN BAY PACKERS", "PACKERS",
        "HOUSTON TEXANS", "TEXANS",
        "INDIANAPOLIS COLTS", "COLTS",
        "JACKSONVILLE JAGUARS", "JAGUARS",
        "KANSAS CITY CHIEFS", "CHIEFS",
        "LAS VEGAS RAIDERS", "RAIDERS",
        "LOS ANGELES CHARGERS", "CHARGERS",
        "LOS ANGELES RAMS", "RAMS",
        "MIAMI DOLPHINS", "DOLPHINS",
        "MINNESOTA VIKINGS", "VIKINGS",
        "NEW ENGLAND PATRIOTS", "PATRIOTS",
        "NEW ORLEANS SAINTS", "SAINTS",
        "NEW YORK GIANTS", "GIANTS",
        "NEW YORK JETS", "JETS",
        "PHILADELPHIA EAGLES", "EAGLES",
        "PITTSBURGH STEELERS", "STEELERS",
        "SAN FRANCISCO 49ERS", "FORTY NINERS", "49ERS",
        "SEATTLE SEAHAWKS", "SEAHAWKS",
        "TAMPA BAY BUCCANEERS", "BUCCANEERS",
        "TENNESSEE TITANS", "TITANS",
        "WASHINGTON COMMANDERS", "COMMANDERS", "WASHINGTON",
    }

    def _nickname_is_team(row: pd.Series) -> bool:
        nickname_upper = _nickname(row).upper()
        if not nickname_upper:
            return False
        team_val = str(row.get("team", "")).strip().upper()
        opponent_val = str(row.get("opponent", "")).strip().upper()
        return nickname_upper in _team_tokens or nickname_upper == team_val or nickname_upper == opponent_val

    nick_series = curated.apply(_nickname, axis=1)
    before = len(curated)
    # must have some name, must have a non-null nickname, and nickname cannot be a team token
    curated = curated[
        curated.apply(_has_any_name, axis=1)
        & (nick_series != "")
        & (~curated.apply(_nickname_is_team, axis=1))
    ]
    dropped = before - len(curated)
    if dropped:
        logging.info("Skipped %s injury rows with missing nickname/first/last or team-like nickname", dropped)
    # Build deterministic maps from player_master using full_name and name_norm
    with engine.begin() as conn:
        pm_df = pd.read_sql(
            text("SELECT player_master_id, full_name, name_norm FROM player_master"),
            conn,
        )
    name_to_id = {}
    norm_to_id = {}
    if not pm_df.empty:
        pm_df["full_lower"] = pm_df["full_name"].astype(str).str.strip().str.lower()
        pm_df["norm"] = pm_df["name_norm"].astype(str)
        name_to_id = dict(zip(pm_df["full_lower"], pm_df["player_master_id"]))
        norm_to_id = dict(zip(pm_df["norm"], pm_df["player_master_id"]))

    def _col(df: pd.DataFrame, *names: str, default: str = "") -> pd.Series:
        for name in names:
            if name in df.columns:
                return df[name]
        return pd.Series([default] * len(df))

    def _format_injury_unmatched(df: pd.DataFrame) -> pd.DataFrame:
        formatted = pd.DataFrame(
            {
                "season": _col(df, "season"),
                "week": _col(df, "week"),
                "slate": _col(df, "slate"),
                "source": pd.Series(["injuries"] * len(df)),
                "nickname": _col(df, "nickname", "Nickname"),
                "first_name": _col(df, "first_name", "First Name"),
                "last_name": _col(df, "last_name", "Last Name"),
                "team": _col(df, "team"),
                "opponent": _col(df, "opponent"),
                "injury_indicator": _col(df, "injury_indicator", "Injury Indicator"),
                "injury_details": _col(df, "injury_details", "Injury Details"),
            }
        )
        formatted["season"] = pd.to_numeric(formatted["season"], errors="coerce").astype("Int64")
        formatted["week"] = pd.to_numeric(formatted["week"], errors="coerce").astype("Int64")
        return formatted

    def _resolve_injury_row(row: pd.Series) -> Optional[str]:
        # Prefer nickname; fallback to First + Last
        nickname = str(row.get("Nickname") or row.get("nickname") or "").strip()
        first = str(row.get("First Name") or row.get("first_name") or "").strip()
        last = str(row.get("Last Name") or row.get("last_name") or "").strip()
        raw_name = nickname if nickname else f"{first} {last}".strip()
        if not raw_name:
            return None
        full_key = raw_name.lower()
        if full_key in name_to_id:
            return name_to_id[full_key]
        norm_key = _strip_suffix(_norm_name(raw_name))
        return norm_to_id.get(norm_key)

    curated["player_master_id"] = curated.apply(_resolve_injury_row, axis=1)
    # Clear prior unmatched for this key and write any new unmatched
    unmatched = curated[curated["player_master_id"].isna()].copy()
    injury_unmatched = _format_injury_unmatched(unmatched)
    _ensure_table(engine, "curated_injuries_unmatched", injury_unmatched.head(0))
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM curated_injuries_unmatched WHERE season = :season AND week = :week AND slate = :slate"),
            {"season": season, "week": week, "slate": slate},
        )
        if not injury_unmatched.empty:
            injury_unmatched.to_sql("curated_injuries_unmatched", conn, if_exists="append", index=False)
    if not unmatched.empty:
        logging.warning(
            "Unmatched injury rows (%s) for season=%s week=%s slate=%s; writing matched rows only",
            len(unmatched),
            season,
            week,
            slate,
        )
    curated = curated[curated["player_master_id"].notna()].copy()
    if curated.empty:
        logging.warning("No matched injury rows to write for season=%s week=%s slate=%s", season, week, slate)
        return 0
    curated["team_norm"] = _col(curated, "team", "TeamAbbrev").astype(str).str.upper()
    _ensure_table(engine, "curated_injuries", curated)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM curated_injuries WHERE season = :season AND week = :week AND slate = :slate"),
                     {"season": season, "week": week, "slate": slate})
        curated.to_sql("curated_injuries", conn, if_exists="append", index=False)

    # Also write to weekly_injuries for downstream consumers (optimizer/projections)
    rename_map = {
        "Position": "position",
        "First Name": "first_name",
        "Nickname": "nickname",
        "Last Name": "last_name",
        "FPPG": "fppg",
        "Played": "played",
        "Salary": "salary",
        "Game": "game_info",
        "Team": "team",
        "Opponent": "opponent",
        "Injury Indicator": "injury_indicator",
        "Injury Details": "injury_details",
        "Tier": "tier",
        "Roster Position": "roster_position",
        "Id": "Id",
    }
    weekly_df = curated.rename(columns=rename_map).copy()
    # Ensure required fields exist
    for col in ["position", "first_name", "nickname", "last_name", "fppg", "played", "salary", "game_info", "team", "opponent", "injury_indicator", "injury_details", "tier", "roster_position"]:
        if col not in weekly_df.columns:
            weekly_df[col] = None
    weekly_df["season"] = season
    weekly_df["week"] = week
    weekly_df["slate"] = slate
    weekly_df["player_id"] = weekly_df.get("player_id", weekly_df["Id"] if "Id" in weekly_df.columns else "").astype(str)
    weekly_df["injury_indicator"] = weekly_df["injury_indicator"].fillna("")
    weekly_df["injury_details"] = weekly_df["injury_details"].fillna("")
    weekly_df["name_norm"] = weekly_df.apply(
        lambda r: _norm_name(f"{str(r.get('first_name', '')).strip()} {str(r.get('last_name', '')).strip()}") or _norm_name(str(r.get("nickname", ""))),
        axis=1,
    )
    weekly_df["team_norm"] = weekly_df["team"].astype(str).str.upper()
    # Align optional id column
    if "Id" in weekly_df.columns and "id" not in weekly_df.columns:
        weekly_df["id"] = weekly_df["Id"]
    _ensure_table(engine, "weekly_injuries", weekly_df.head(0))
    with engine.begin() as conn:
        # Allocate ids beyond current max to avoid PK collisions across slates
        try:
            max_id = conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM weekly_injuries")).scalar_one()
        except Exception:
            max_id = 0
        weekly_df["id"] = pd.Series(range(max_id + 1, max_id + 1 + len(weekly_df)), index=weekly_df.index, dtype="Int64")
        conn.execute(text("DELETE FROM weekly_injuries WHERE season = :season AND week = :week AND slate = :slate"),
                     {"season": season, "week": week, "slate": slate})
        weekly_df.to_sql("weekly_injuries", conn, if_exists="append", index=False)
    logging.info("Inserted %s rows into curated_injuries (season=%s week=%s slate=%s)", len(curated), season, week, slate)
    return len(curated)


def curate_rosters(season: int, weeks: Iterable[int] | None = None, connection_string: str | None = None) -> int:
    """Transform raw_weekly_rosters -> curated_rosters with player_master_id."""
    conn_str = connection_string or get_connection_string()
    engine = create_engine(conn_str)
    with engine.begin() as conn:
        if weeks:
            raw = pd.read_sql(
                text("SELECT * FROM raw_weekly_rosters WHERE season = :season AND week = ANY(:weeks)"),
                conn,
                params={"season": season, "weeks": list(weeks)},
            )
        else:
            raw = pd.read_sql(
                text("SELECT * FROM raw_weekly_rosters WHERE season = :season"),
                conn,
                params={"season": season},
            )
    if raw.empty:
        logging.warning("No raw_weekly_rosters found for season=%s weeks=%s", season, weeks)
        return 0
    resolver = PlayerResolver(engine)
    curated = raw.copy()
    # Drop rows without any usable name before attempting resolution or writing unmatched
    name_series = curated.apply(_extract_name, axis=1)
    before = len(curated)
    curated = curated[name_series.fillna("").astype(str).str.strip() != ""]
    dropped = before - len(curated)
    if dropped:
        logging.info("Skipped %s roster rows missing player_display_name/display_name", dropped)

    def _col(df: pd.DataFrame, *names: str, default: str = "") -> pd.Series:
        for name in names:
            if name in df.columns:
                return df[name]
        return pd.Series([default] * len(df))

    def _format_roster_unmatched(df: pd.DataFrame) -> pd.DataFrame:
        formatted = pd.DataFrame(
            {
                "season": _col(df, "season"),
                "week": _col(df, "week"),
                "source": pd.Series(["rosters"] * len(df)),
                "player_id": _col(df, "player_id"),
                "player_name": _col(df, "player_name"),
                "player_display_name": _col(df, "player_display_name", "display_name"),
                "team": _col(df, "team"),
                "position": _col(df, "position"),
                "position_group": _col(df, "position_group"),
                "headshot_url": _col(df, "headshot_url"),
            }
        )
        formatted["season"] = pd.to_numeric(formatted["season"], errors="coerce").astype("Int64")
        formatted["week"] = pd.to_numeric(formatted["week"], errors="coerce").astype("Int64")
        # Keep only rows with a season/week and some name present
        name_mask = (
            formatted["player_display_name"].fillna("").astype(str).str.strip() != ""
        ) | (formatted["player_name"].fillna("").astype(str).str.strip() != "")
        formatted = formatted[
            formatted["season"].notna() & formatted["week"].notna() & name_mask
        ]
        return formatted

    curated["player_master_id"] = curated.apply(
        lambda r: resolver.resolve(
            _extract_name(r),
            r.get("team"),
            r.get("position"),
            season=season,
        ),
        axis=1,
    )
    matched = curated[curated["player_master_id"].notna()].copy()
    unmatched = curated[curated["player_master_id"].isna()].copy()
    formatted_unmatched = _format_roster_unmatched(unmatched)
    _ensure_table(engine, "curated_rosters_unmatched", formatted_unmatched.head(0))
    with engine.begin() as conn:
        if weeks:
            conn.execute(
                text("DELETE FROM curated_rosters_unmatched WHERE season = :season AND week = ANY(:weeks)"),
                {"season": season, "weeks": list(weeks)},
            )
        else:
            conn.execute(
                text("DELETE FROM curated_rosters_unmatched WHERE season = :season"),
                {"season": season},
            )
        if not formatted_unmatched.empty:
            formatted_unmatched.to_sql("curated_rosters_unmatched", conn, if_exists="append", index=False)
    if not unmatched.empty:
        logging.warning("Unmatched players in rosters: %s (season=%s weeks=%s)", len(unmatched), season, weeks)
    if matched.empty:
        return 0
    matched["team_norm"] = matched.get("team", "").astype(str).str.upper()
    _ensure_table(engine, "curated_weekly_rosters", matched)
    with engine.begin() as conn:
        if weeks:
            conn.execute(text("DELETE FROM curated_weekly_rosters WHERE season = :season AND week = ANY(:weeks)"),
                         {"season": season, "weeks": list(weeks)})
        else:
            conn.execute(text("DELETE FROM curated_weekly_rosters WHERE season = :season"), {"season": season})
        matched.to_sql("curated_weekly_rosters", conn, if_exists="append", index=False)
    logging.info("Inserted %s rows into curated_weekly_rosters (season=%s weeks=%s)", len(matched), season, weeks)
    return len(matched)
