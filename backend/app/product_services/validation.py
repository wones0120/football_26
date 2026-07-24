"""Data validation helpers."""

from __future__ import annotations

from typing import Iterable, List, Optional
import uuid

import pandas as pd
from sqlalchemy import create_engine, text

from Database.curated_ingest import _norm_name, _strip_suffix
from Database.config import get_connection_string


def fetch_weekly_row_counts(
    table_name: str,
    seasons: Optional[Iterable[int]] = None,
    connection_string: Optional[str] = None,
) -> List[dict]:
    """
    Return weekly row counts for the given table, filling missing weeks with zero.
    Adds a crude completeness signal: compares each week's rows to the median
    non-zero count for that season and labels as ok/partial/missing.
    Orders results by season asc, week asc.
    """
    conn_str = connection_string or get_connection_string()
    engine = create_engine(conn_str)

    with engine.begin() as connection:
        if seasons:
            season_list = list(seasons)
            base_query = text(
                f"SELECT season, week, COUNT(*) AS rows "
                f"FROM {table_name} "
                "WHERE season = ANY(:seasons) "
                "GROUP BY season, week"
            )
            counts = connection.execute(base_query, {"seasons": season_list}).fetchall()
        else:
            base_query = text(
                f"SELECT season, week, COUNT(*) AS rows "
                f"FROM {table_name} "
                "GROUP BY season, week"
            )
            counts = connection.execute(base_query).fetchall()

    by_season = {}
    for row in counts:
        # Skip rows without a valid week (e.g., future/predictive rows)
        if row.week is None:
            continue
        by_season.setdefault(row.season, {})[int(row.week)] = int(row.rows)

    rows: List[dict] = []
    for season in sorted(by_season.keys()):
        if not by_season[season]:
            continue
        max_week = max(by_season[season].keys())
        non_zero_counts = [c for c in by_season[season].values() if c > 0]
        median_non_zero = (
            int(sorted(non_zero_counts)[len(non_zero_counts) // 2]) if non_zero_counts else 0
        )
        for week in range(1, max_week + 1):
            count = by_season[season].get(week, 0)
            if count == 0:
                status = "missing"
            elif median_non_zero > 0 and count < 0.8 * median_non_zero:
                status = "partial"
            else:
                status = "ok"
            rows.append(
                {
                    "season": int(season),
                    "week": int(week),
                    "rows": count,
                    "expected_rows": median_non_zero if median_non_zero else None,
                    "status": status,
                }
            )
    return rows


def fetch_unmatched_salaries(
    season: int | None = None,
    week: int | None = None,
    slate: str | None = None,
    limit: int = 50,
    connection_string: Optional[str] = None,
) -> List[dict]:
    conn_str = connection_string or get_connection_string()
    engine = create_engine(conn_str)
    filters = []
    params: dict = {}
    if season:
        filters.append("season = :season")
        params["season"] = season
    if week:
        filters.append("week = :week")
        params["week"] = week
    if slate:
        filters.append("slate = :slate")
        params["slate"] = slate
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = text(
        f"SELECT season, week, slate, name, player_team, created_at "
        f"FROM dk_salary_unmatched {where_clause} "
        f"ORDER BY created_at DESC "
        f"LIMIT :limit"
    )
    params["limit"] = limit
    with engine.begin() as conn:
        rows = conn.execute(query, params).mappings().all()
    return [dict(row) for row in rows]


def fetch_unmatched_injuries(
    season: int | None = None,
    week: int | None = None,
    slate: str | None = None,
    limit: int = 50,
    connection_string: Optional[str] = None,
) -> List[dict]:
    if season is None or week is None:
        return []

    conn_str = connection_string or get_connection_string()
    engine = create_engine(conn_str)

    with engine.begin() as conn:
        inj_df = pd.read_sql(
            text(
                "SELECT season, week, slate, player_id, nickname, first_name, last_name, team, opponent, injury_indicator "
                "FROM weekly_injuries WHERE season = :season AND week = :week"
            ),
            conn,
            params={"season": season, "week": week},
        )
        sal_query = "SELECT player_id, name, player_team, slate FROM curated_salaries WHERE season = :season AND week = :week"
        sal_params = {"season": season, "week": week}
        if slate:
            sal_query += " AND slate = :slate"
            sal_params["slate"] = slate
        sal_df = pd.read_sql(text(sal_query), conn, params=sal_params)

    if inj_df.empty:
        return []

    def _normalize_alias(name: str) -> str:
        key = " ".join(name.lower().replace("'", " ").split())
        if "hollywood brown" in key or ("hollywood" in key and "brown" in key):
            return "marquise brown"
        if key == "marquise brown":
            return "marquise brown"
        return key

    def norm_name(nick, first, last):
        parts = []
        if nick:
            parts.append(_normalize_alias(str(nick).lower().strip()))
        full = f"{str(first or '').strip()} {str(last or '').strip()}".strip().lower()
        if full:
            parts.append(_normalize_alias(full))
        return parts[0] if parts else ""

    inj_df["name_norm"] = [
        norm_name(row.nickname, row.first_name, row.last_name) for row in inj_df.itertuples()
    ]
    inj_df["player_id"] = inj_df["player_id"].astype(str)
    inj_df["team_norm"] = inj_df["team"].astype(str).str.upper().str.strip()
    inj_df["slate"] = inj_df.get("slate").fillna("")

    if not sal_df.empty:
        sal_df["player_id"] = sal_df["player_id"].astype(str)
        sal_df["name_norm"] = sal_df["name"].astype(str).str.lower().str.strip().map(_normalize_alias)
        sal_df["team_norm"] = sal_df["player_team"].astype(str).str.upper().str.strip()
        if slate:
            sal_df = sal_df[sal_df["slate"] == slate]
    else:
        sal_df = pd.DataFrame(columns=["player_id", "name_norm", "team_norm", "slate"])

    salary_ids = set(sal_df["player_id"].tolist())
    salary_name_team = {(r.name_norm, r.team_norm) for r in sal_df.itertuples() if r.name_norm}
    salary_names = set(sal_df["name_norm"].tolist())

    def is_matched(row):
        if row.player_id in salary_ids:
            return True
        if (row.name_norm, row.team_norm) in salary_name_team:
            return True
        if row.name_norm in salary_names:
            return True
        return False

    unmatched = inj_df[~inj_df.apply(is_matched, axis=1)].copy()
    unmatched = unmatched.head(limit)
    return [
        {
            "season": int(row.season),
            "week": int(row.week),
            "slate": row.slate or None,
            "name": row.nickname or f"{row.first_name} {row.last_name}",
            "player_team": row.team,
            "opponent": row.opponent,
            "status": row.injury_indicator,
        }
        for row in unmatched.itertuples()
    ]


def process_unmatched_players(
    season: int | None = None,
    week: int | None = None,
    source: str | None = None,
    connection_string: Optional[str] = None,
) -> dict:
    """
    Promote curated_unmatched rows marked add_to_player_master='Y' into player_master.
    """
    conn_str = connection_string or get_connection_string()
    engine = create_engine(conn_str)
    filters = ["add_to_player_master = 'Y'"]
    params: dict = {}
    if season is not None:
        filters.append("season = :season")
        params["season"] = season
    if week is not None:
        filters.append("week = :week")
        params["week"] = week
    if source:
        filters.append("source = :source")
        params["source"] = source
    where_clause = " AND ".join(filters)
    query = text(f"SELECT * FROM curated_unmatched WHERE {where_clause}")
    added = 0
    skipped = 0
    with engine.begin() as conn:
        df = pd.read_sql(query, conn, params=params)
        if df.empty:
            return {"added": 0, "skipped_existing": 0, "processed": 0}
        for _, row in df.iterrows():
            name = (
                row.get("player_display_name")
                or row.get("player_name")
                or row.get("nickname")
                or row.get("name")
                or row.get("First Name")
            )
            if not name or str(name).strip() == "":
                first = row.get("first_name") or row.get("First Name")
                last = row.get("last_name") or row.get("Last Name")
                name = f"{first or ''} {last or ''}".strip()
            if not name:
                skipped += 1
                continue
            team = row.get("recent_team") or row.get("team") or row.get("player_team") or ""
            position = row.get("position") or ""
            name_norm = _strip_suffix(_norm_name(name))
            team_norm = str(team or "").upper()
            existing = conn.execute(
                text(
                    "SELECT player_master_id FROM player_master "
                    "WHERE name_norm = :name_norm AND primary_team = :team LIMIT 1"
                ),
                {"name_norm": name_norm, "team": team_norm},
            ).fetchone()
            if existing:
                skipped += 1
                continue
            pmid = str(uuid.uuid4())
            conn.execute(
                text(
                    "INSERT INTO player_master (player_master_id, full_name, name_norm, first_name, last_name, primary_team, position) "
                    "VALUES (:id, :full_name, :name_norm, :first_name, :last_name, :team, :position)"
                ),
                {
                    "id": pmid,
                    "full_name": name,
                    "name_norm": name_norm,
                    "first_name": str(name).split()[0] if name else "",
                    "last_name": " ".join(str(name).split()[1:]) if name else "",
                    "team": team_norm,
                    "position": position,
                },
            )
            added += 1
    return {"added": added, "skipped_existing": skipped, "processed": len(df)}
