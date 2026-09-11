"""Data validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional
import uuid

import pandas as pd
from sqlalchemy import bindparam, create_engine, inspect, text

from Database.curated_ingest import _norm_name, _strip_suffix
from Database.config import get_connection_string


@dataclass(frozen=True)
class _ValidationTable:
    name: str
    schema: str | None = "public"
    slate_column: str | None = None


# Coverage is intentionally restricted to known relations. Besides preventing a
# query-string value from becoming a SQL identifier, the aliases keep older UI
# names working while the product migrates to the canonical public/target model.
_VALIDATION_TABLES: dict[str, tuple[_ValidationTable, ...]] = {
    "nfl_weekly_data_with_scores": (
        _ValidationTable("nfl_weekly_data_with_scores"),
        _ValidationTable("fact_player_game_actual", "target"),
    ),
    "raw_weekly_stats": (
        _ValidationTable("raw_weekly_stats"),
        _ValidationTable("raw_nfl_weekly_stat"),
    ),
    "raw_weekly_rosters": (
        _ValidationTable("raw_weekly_rosters"),
        _ValidationTable("raw_nfl_weekly_roster"),
    ),
    "raw_injuries": (
        _ValidationTable("raw_injuries"),
        _ValidationTable("raw_injury_row", slate_column="slate"),
    ),
    "curated_weekly_stats": (
        _ValidationTable("curated_weekly_stats"),
        _ValidationTable("fact_player_game_actual", "target"),
    ),
    "curated_weekly_rosters": (
        _ValidationTable("curated_weekly_rosters"),
        _ValidationTable("curated_player_game_participation"),
    ),
    "curated_injuries": (
        _ValidationTable("curated_injuries", slate_column="slate"),
        _ValidationTable("curated_injury", slate_column="slate"),
    ),
    "curated_salaries": (
        _ValidationTable("curated_salaries", slate_column="slate"),
        _ValidationTable("curated_salary", slate_column="slate"),
        _ValidationTable("snapshot_salary", "target", "slate"),
    ),
    "predictive_features": (
        _ValidationTable("predictive_features", slate_column="slate"),
        _ValidationTable("player_game_feature_matrix", slate_column="slate"),
        _ValidationTable("feature_player_game", "target"),
    ),
    "player_expected_points": (
        _ValidationTable("player_expected_points", slate_column="slate"),
        _ValidationTable("player_projection", "target", "slate_id"),
    ),
    "weekly_injuries": (
        _ValidationTable("weekly_injuries", slate_column="slate"),
        _ValidationTable("curated_injury", slate_column="slate"),
    ),
    "fact_player_game_actual": (_ValidationTable("fact_player_game_actual", "target"),),
    "curated_salary": (_ValidationTable("curated_salary", slate_column="slate"),),
    "player_game_feature_matrix": (
        _ValidationTable("player_game_feature_matrix", slate_column="slate"),
    ),
    "player_projection": (_ValidationTable("player_projection", "target", "slate_id"),),
}


def _resolve_validation_table(connection, table_name: str) -> _ValidationTable | None:
    candidates = _VALIDATION_TABLES.get(table_name)
    if candidates is None:
        raise ValueError(f"Unsupported validation table: {table_name}")

    inspector = inspect(connection)
    for candidate in candidates:
        # SQLite has no public schema; omitting it keeps service tests portable.
        schema = candidate.schema if connection.dialect.name != "sqlite" else None
        if inspector.has_table(candidate.name, schema=schema):
            return _ValidationTable(candidate.name, schema, candidate.slate_column)
    return None


def _missing_week(seasons: list[int], week: int | None) -> List[dict]:
    if len(seasons) != 1 or week is None:
        return []
    return [
        {
            "season": int(seasons[0]),
            "week": int(week),
            "rows": 0,
            "expected_rows": None,
            "status": "missing",
        }
    ]


def fetch_weekly_row_counts(
    table_name: str,
    seasons: Optional[Iterable[int]] = None,
    week: int | None = None,
    slate: str | None = None,
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

    season_list = [int(season) for season in seasons] if seasons else []
    with engine.begin() as connection:
        table = _resolve_validation_table(connection, table_name)
        if table is None:
            return _missing_week(season_list, week)

        relation = f'"{table.schema}"."{table.name}"' if table.schema else f'"{table.name}"'
        filters: list[str] = []
        params: dict[str, object] = {}
        if season_list:
            filters.append("season IN :seasons")
            params["seasons"] = season_list
        if week is not None:
            filters.append("week = :week")
            params["week"] = int(week)
        if slate and table.slate_column:
            filters.append(f'UPPER("{table.slate_column}") = UPPER(:slate)')
            params["slate"] = slate

        where_clause = f" WHERE {' AND '.join(filters)}" if filters else ""
        base_query = text(
            f"SELECT season, week, COUNT(*) AS rows FROM {relation}"
            f"{where_clause} GROUP BY season, week"
        )
        if season_list:
            base_query = base_query.bindparams(bindparam("seasons", expanding=True))
        counts = connection.execute(base_query, params).fetchall()

    if season_list and week is not None and not counts:
        return _missing_week(season_list, week)

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
        min_week = week if week is not None else 1
        max_week = week if week is not None else max(by_season[season].keys())
        non_zero_counts = [c for c in by_season[season].values() if c > 0]
        median_non_zero = (
            int(sorted(non_zero_counts)[len(non_zero_counts) // 2]) if non_zero_counts else 0
        )
        for week_number in range(min_week, max_week + 1):
            count = by_season[season].get(week_number, 0)
            if count == 0:
                status = "missing"
            elif median_non_zero > 0 and count < 0.8 * median_non_zero:
                status = "partial"
            else:
                status = "ok"
            rows.append(
                {
                    "season": int(season),
                    "week": int(week_number),
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
