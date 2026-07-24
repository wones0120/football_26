"""Shared player master resolver for consistent player IDs across ingests."""

from __future__ import annotations

import uuid
import json
from dataclasses import dataclass, field
from typing import Optional, Dict, Tuple

import pandas as pd
from sqlalchemy import create_engine, inspect, text

from Database.config import get_connection_string
from Database.dst import normalize_team


def _norm_name(name: str) -> str:
    return " ".join(str(name or "").lower().replace("'", " ").split())


def _strip_suffix(name_norm: str) -> str:
    # Trim common suffixes (jr/sr/ii/iii) to avoid duplicate variants
    suffixes = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"}
    parts = name_norm.split()
    if parts and parts[-1] in suffixes:
        return " ".join(parts[:-1])
    return name_norm


def _norm_team(team: str) -> str:
    return normalize_team(team)


@dataclass
class PlayerMasterResolver:
    connection_string: str = get_connection_string()
    _cache: Dict[Tuple[str, str], str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.engine = create_engine(self.connection_string)
        self._ensure_table()

    def _ensure_table(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS player_master (
            player_master_id UUID PRIMARY KEY,
            full_name TEXT NOT NULL,
            normalized_name TEXT,
            name_norm TEXT NOT NULL,
            first_name TEXT,
            last_name TEXT,
            primary_team TEXT,
            position TEXT,
            aliases JSONB DEFAULT '[]',
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        );
        """
        with self.engine.begin() as conn:
            conn.execute(text(ddl))
            inspector = inspect(conn)
            columns = {col["name"] for col in inspector.get_columns("player_master")}
            if "normalized_name" not in columns:
                conn.execute(text("ALTER TABLE player_master ADD COLUMN normalized_name TEXT"))
                columns.add("normalized_name")
            if "name_norm" not in columns:
                conn.execute(text("ALTER TABLE player_master ADD COLUMN name_norm TEXT"))
                columns.add("name_norm")
            if "aliases" not in columns:
                conn.execute(text("ALTER TABLE player_master ADD COLUMN aliases JSONB DEFAULT '[]'"))
                columns.add("aliases")
            if "normalized_name" in columns:
                conn.execute(text("UPDATE player_master SET name_norm = normalized_name WHERE name_norm IS NULL"))
                conn.execute(text("UPDATE player_master SET normalized_name = name_norm WHERE normalized_name IS NULL"))
            conn.execute(text("UPDATE player_master SET aliases = '[]'::jsonb WHERE aliases IS NULL"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_player_master_name_norm ON player_master(name_norm)"))
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS idx_player_master_name_team ON player_master(name_norm, primary_team)")
            )

    def resolve(self, full_name: str, team: Optional[str] = None, position: Optional[str] = None) -> str:
        """Return player_master_id, inserting if missing. Uses cache to avoid repeat lookups per batch."""
        name_norm = _norm_name(full_name)
        base_norm = _strip_suffix(name_norm)
        team_norm = _norm_team(team)
        cache_key = (base_norm, team_norm)
        if cache_key in self._cache:
            return self._cache[cache_key]

        norms = list({name_norm, base_norm})
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    "SELECT player_master_id, name_norm, primary_team, aliases "
                    "FROM player_master "
                    "WHERE name_norm = ANY(:norms) OR aliases ?| :norms"
                ),
                {"norms": norms},
            ).fetchall()

            def _score(r):
                team_match = 0 if team_norm and r.primary_team == team_norm else 1
                return team_match

            best = None
            for r in rows:
                if best is None or _score(r) < _score(best):
                    best = r
            if best:
                self._cache[cache_key] = str(best.player_master_id)
                return self._cache[cache_key]

            # Insert new
            pmid = str(uuid.uuid4())
            parts = full_name.split()
            first_name = parts[0] if parts else ""
            last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
            aliases = norms
            conn.execute(
                text(
                    "INSERT INTO player_master "
                    "(player_master_id, full_name, normalized_name, name_norm, first_name, last_name, "
                    "primary_team, position, aliases, created_at, updated_at) "
                    "VALUES (:id, :full_name, :name_norm, :name_norm, :first_name, :last_name, "
                    ":team, :position, CAST(:aliases AS JSONB), now(), now())"
                ),
                {
                    "id": pmid,
                    "full_name": full_name,
                    "name_norm": base_norm,
                    "first_name": first_name,
                    "last_name": last_name,
                    "team": team_norm,
                    "position": position,
                    "aliases": json.dumps(aliases),
                },
            )
            existing = conn.execute(
                text(
                    "SELECT player_master_id FROM player_master "
                    "WHERE name_norm = :name_norm AND primary_team = :team "
                    "LIMIT 1"
                ),
                {"name_norm": base_norm, "team": team_norm},
            ).fetchone()
            pmid_final = str(existing.player_master_id) if existing else pmid
            self._cache[cache_key] = pmid_final
            return pmid_final

    def attach_to_dataframe(self, df: pd.DataFrame, name_col: str, team_col: Optional[str] = None, pos_col: Optional[str] = None) -> pd.DataFrame:
        if name_col not in df.columns:
            return df
        df = df.copy()
        resolver = self

        def _resolve_row(row):
            name = row.get(name_col, "")
            team = row.get(team_col, "") if team_col else ""
            pos = row.get(pos_col, "") if pos_col else ""
            return resolver.resolve(str(name), team, pos)

        df["player_master_id"] = df.apply(_resolve_row, axis=1)
        return df
