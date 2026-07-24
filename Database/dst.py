"""Canonical NFL DST identity and DraftKings scoring helpers."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import inspect, text


DST_POSITIONS = frozenset({"D", "DEF", "DST"})
TEAM_ALIASES = {
    "JAC": "JAX",
    "LA": "LAR",
    "OAK": "LV",
    "SD": "LAC",
    "STL": "LAR",
    "WSH": "WAS",
}
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class DstIdentityRepairResult:
    teams_seen: int = 0
    masters_created: int = 0
    masters_updated: int = 0
    salary_rows_resolved: int = 0


def normalize_team(team: str | None) -> str:
    """Return the modern canonical abbreviation used by salary and target data."""
    value = str(team or "").strip().upper()
    return TEAM_ALIASES.get(value, value)


def team_aliases(team: str | None) -> tuple[str, ...]:
    canonical = normalize_team(team)
    aliases = {canonical}
    aliases.update(alias for alias, target in TEAM_ALIASES.items() if target == canonical)
    return tuple(sorted(aliases))


def is_dst_position(position: str | None) -> bool:
    return str(position or "").strip().upper() in DST_POSITIONS


def deterministic_dst_player_id(team: str) -> str:
    canonical = normalize_team(team)
    if not canonical:
        raise ValueError("DST team is required")
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"dst-{canonical.lower()}"))


def normalize_name(name: str | None) -> str:
    return " ".join(str(name or "").lower().replace("'", " ").split())


def charged_points_allowed(
    opponent_score: float,
    opponent_defensive_touchdowns: float = 0,
    opponent_defensive_safeties: float = 0,
) -> float:
    """Approximate DK-charged points by removing scores made by the opponent DST.

    Downloaded DraftKings results override this reconstruction when available.
    Seven points per defensive touchdown is the best deterministic reconstruction
    available from weekly aggregates because conversion ownership is not present.
    """
    charged = (
        float(opponent_score)
        - 7.0 * float(opponent_defensive_touchdowns)
        - 2.0 * float(opponent_defensive_safeties)
    )
    return max(0.0, charged)


def dk_points_allowed_score(points_allowed: float) -> float:
    value = float(points_allowed)
    if value <= 0:
        return 10.0
    if value <= 6:
        return 7.0
    if value <= 13:
        return 4.0
    if value <= 20:
        return 1.0
    if value <= 27:
        return 0.0
    if value <= 34:
        return -1.0
    return -4.0


def dk_dst_points(
    *,
    sacks: float = 0,
    interceptions: float = 0,
    fumble_recoveries: float = 0,
    safeties: float = 0,
    defensive_touchdowns: float = 0,
    special_teams_touchdowns: float = 0,
    blocked_kicks: float = 0,
    points_allowed: float = 0,
) -> float:
    return float(
        sacks
        + 2 * interceptions
        + 2 * fumble_recoveries
        + 2 * safeties
        + 6 * defensive_touchdowns
        + 6 * special_teams_touchdowns
        + 2 * blocked_kicks
        + dk_points_allowed_score(points_allowed)
    )


def repair_dst_identities(engine, schema: str = "public") -> DstIdentityRepairResult:
    """Attach every DST salary row to one stable franchise-level master identity."""
    if not _IDENTIFIER_RE.match(schema):
        raise ValueError(f"Unsafe schema identifier: {schema!r}")
    quoted_schema = f'"{schema}"'

    with engine.begin() as conn:
        inspector = inspect(conn)
        if not inspector.has_table("curated_salary", schema=schema) or not inspector.has_table(
            "player_master", schema=schema
        ):
            return DstIdentityRepairResult()

        master_columns = {column["name"] for column in inspector.get_columns("player_master", schema=schema)}
        normalized_name_expr = (
            "COALESCE(name_norm, normalized_name, '')"
            if "normalized_name" in master_columns
            else "COALESCE(name_norm, '')"
        )
        salary_rows = conn.execute(
            text(
                f"""
                SELECT DISTINCT trim(player_name) AS player_name, upper(trim(team)) AS team
                FROM {quoted_schema}.curated_salary
                WHERE upper(trim(position)) IN ('D', 'DEF', 'DST')
                  AND NULLIF(trim(team), '') IS NOT NULL
                """
            )
        ).mappings().all()
        master_rows = conn.execute(
            text(
                f"""
                SELECT player_master_id::text AS player_master_id, full_name,
                       {normalized_name_expr} AS name_norm,
                       COALESCE(primary_team, '') AS primary_team,
                       COALESCE(position, '') AS position
                FROM {quoted_schema}.player_master
                """
            )
        ).mappings().all()

        masters_by_name: dict[str, list[dict]] = {}
        masters_by_team: dict[str, list[dict]] = {}
        for row in master_rows:
            row_dict = dict(row)
            masters_by_name.setdefault(normalize_name(row["full_name"] or row["name_norm"]), []).append(row_dict)
            canonical_team = normalize_team(row["primary_team"])
            if canonical_team and is_dst_position(row["position"]):
                masters_by_team.setdefault(canonical_team, []).append(row_dict)

        created = 0
        updated = 0
        resolved = 0
        teams_seen: set[str] = set()
        for salary in salary_rows:
            team = normalize_team(salary["team"])
            name = str(salary["player_name"] or "").strip()
            if not team:
                continue
            teams_seen.add(team)
            name_candidates = masters_by_name.get(normalize_name(name), [])
            team_candidates = masters_by_team.get(team, [])
            candidate = next(
                (row for row in name_candidates if normalize_team(row["primary_team"]) == team),
                name_candidates[0] if len(name_candidates) == 1 else (team_candidates[0] if team_candidates else None),
            )

            if candidate is None:
                player_id = deterministic_dst_player_id(team)
                insert_columns = [
                    "player_master_id",
                    "full_name",
                    "name_norm",
                    "first_name",
                    "last_name",
                    "primary_team",
                    "position",
                    "aliases",
                ]
                values = [
                    ":player_id",
                    ":full_name",
                    ":name_norm",
                    "''",
                    "''",
                    ":team",
                    "'DST'",
                    "CAST(:aliases AS JSONB)",
                ]
                if "normalized_name" in master_columns:
                    insert_columns.append("normalized_name")
                    values.append(":name_norm")
                conn.execute(
                    text(
                        f"INSERT INTO {quoted_schema}.player_master "
                        f"({', '.join(insert_columns)}) VALUES ({', '.join(values)}) "
                        "ON CONFLICT (player_master_id) DO NOTHING"
                    ),
                    {
                        "player_id": player_id,
                        "full_name": name or f"{team} DST",
                        "name_norm": normalize_name(name or f"{team} DST"),
                        "team": team,
                        "aliases": "[]",
                    },
                )
                candidate = {
                    "player_master_id": player_id,
                    "full_name": name,
                    "name_norm": normalize_name(name),
                    "primary_team": team,
                    "position": "DST",
                }
                masters_by_name.setdefault(normalize_name(name), []).append(candidate)
                masters_by_team.setdefault(team, []).append(candidate)
                created += 1
            else:
                player_id = str(candidate["player_master_id"])
                set_clauses = ["primary_team = :team", "position = 'DST'", "updated_at = now()"]
                if "normalized_name" in master_columns:
                    set_clauses.append("normalized_name = COALESCE(normalized_name, name_norm)")
                conn.execute(
                    text(
                        f"UPDATE {quoted_schema}.player_master SET {', '.join(set_clauses)} "
                        "WHERE player_master_id = :player_id"
                    ),
                    {"team": team, "player_id": player_id},
                )
                updated += 1

            result = conn.execute(
                text(
                    f"""
                    UPDATE {quoted_schema}.curated_salary
                    SET player_master_id = :player_id
                    WHERE upper(trim(position)) IN ('D', 'DEF', 'DST')
                      AND upper(trim(team)) = ANY(:team_aliases)
                      AND player_master_id::text IS DISTINCT FROM :player_id
                    """
                ),
                {
                    "player_id": player_id,
                    "team_aliases": list(team_aliases(team)),
                },
            )
            resolved += int(result.rowcount or 0)

    return DstIdentityRepairResult(
        teams_seen=len(teams_seen),
        masters_created=created,
        masters_updated=updated,
        salary_rows_resolved=resolved,
    )
