"""Append-only, cutoff-safe pregame player context for projections."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine

from Database.config import get_connection_string
from .salary_eligibility import is_salary_status_eligible, normalize_salary_status


ROLE_LABELS = {
    "STARTER",
    "BACKUP",
    "LEAD",
    "COMMITTEE",
    "PRIMARY",
    "SECONDARY",
    "ROTATION",
}


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _position(value: object) -> str:
    normalized = str(value or "").strip().upper()
    return "DST" if normalized in {"D", "DEF", "D/ST"} else normalized


def load_current_pregame_context(
    connection: Connection,
    *,
    season: int,
    week: int,
    slate: str,
    cutoff: datetime,
) -> list[dict[str, Any]]:
    """Return the newest visible evidence row per canonical player."""
    rows = connection.execute(
        text(
            """
            SELECT DISTINCT ON (context.player_master_id)
                context.pregame_player_context_id,
                context.context_run_id,
                context.player_master_id,
                context.player_name,
                context.team,
                context.position,
                context.availability_probability,
                context.start_probability,
                context.carry_share,
                context.target_share,
                context.expected_snaps,
                context.expected_routes,
                context.expected_carries,
                context.expected_targets,
                context.red_zone_share,
                context.goal_line_share,
                context.role_label,
                context.injury_status,
                context.evidence_json,
                run.source,
                run.source_uri,
                run.observed_at,
                run.received_at
            FROM public.pregame_player_context context
            JOIN public.pregame_context_run run
              ON run.context_run_id = context.context_run_id
            WHERE run.season = :season
              AND run.week = :week
              AND UPPER(run.slate) = UPPER(:slate)
              AND run.status = 'completed'
              AND run.observed_at <= :cutoff
              AND run.received_at <= :cutoff
            ORDER BY context.player_master_id,
                     run.observed_at DESC,
                     run.received_at DESC,
                     context.pregame_player_context_id DESC
            """
        ),
        {
            "season": season,
            "week": week,
            "slate": slate,
            "cutoff": _utc(cutoff),
        },
    ).mappings()
    return [dict(row) for row in rows]


def _filter_salary_player_pool(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return current projection-eligible players from one-row-per-player salaries."""
    salary_eligible = [
        dict(row) for row in rows if is_salary_status_eligible(row.get("player_status"))
    ]
    has_roster_evidence = any(
        row.get("roster_status") is not None
        for row in salary_eligible
        if _position(row.get("position")) != "DST"
    )
    filtered: list[dict[str, Any]] = []
    for row in salary_eligible:
        position = _position(row.get("position"))
        roster_status = str(row.get("roster_status") or "").strip().upper() or None
        if has_roster_evidence and position != "DST" and roster_status != "ACT":
            continue
        filtered.append(
            {
                "player_id": str(row["player_id"]),
                "player_display_name": str(
                    row.get("player_display_name") or row["player_id"]
                ),
                "team": str(row.get("team") or "").strip().upper(),
                "position": position,
                "player_status": normalize_salary_status(row.get("player_status")) or None,
                "roster_status": roster_status,
            }
        )
    return sorted(
        filtered,
        key=lambda row: (
            row["team"],
            row["position"],
            row["player_display_name"],
            row["player_id"],
        ),
    )


class PregameContextService:
    """Validate and persist sourced player context without name-based joins."""

    def __init__(
        self,
        connection_string: str | None = None,
        engine: Engine | None = None,
    ) -> None:
        self.connection_string = connection_string or (
            str(engine.url) if engine is not None else get_connection_string()
        )
        self.engine = engine or create_engine(self.connection_string)

    def _require_schema(self) -> None:
        db_inspector = inspect(self.engine)
        required = {"pregame_context_run", "pregame_player_context"}
        missing = sorted(
            table
            for table in required
            if not db_inspector.has_table(table, schema="public")
        )
        if missing:
            raise ValueError(
                "Pregame context schema is unavailable; apply migration 0026. "
                f"Missing: {', '.join(missing)}"
            )

    @staticmethod
    def _normalize_players(
        players: Sequence[Mapping[str, Any]],
        salary_by_player: Mapping[str, Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, player in enumerate(players, start=1):
            player_id = str(player.get("player_id") or "").strip()
            if not player_id:
                raise ValueError(f"players[{index}] requires canonical player_id")
            if player_id in seen:
                raise ValueError(f"players contains duplicate player_id {player_id}")
            seen.add(player_id)
            salary = salary_by_player.get(player_id)
            if salary is None:
                raise ValueError(
                    f"players[{index}] player_id {player_id} is not in the selected salary slate"
                )
            expected_team = str(salary.get("team") or "").strip().upper()
            expected_position = _position(salary.get("position"))
            supplied_team = str(player.get("team") or expected_team).strip().upper()
            supplied_position = _position(player.get("position") or expected_position)
            if supplied_team != expected_team or supplied_position != expected_position:
                raise ValueError(
                    f"players[{index}] team/position does not match canonical salary identity "
                    f"({expected_team} {expected_position})"
                )
            role_label = str(player.get("role_label") or "").strip().upper() or None
            if role_label and role_label not in ROLE_LABELS:
                raise ValueError(
                    f"players[{index}] role_label must be one of {', '.join(sorted(ROLE_LABELS))}"
                )
            values = {
                key: player.get(key)
                for key in (
                    "availability_probability",
                    "start_probability",
                    "carry_share",
                    "target_share",
                    "expected_snaps",
                    "expected_routes",
                    "expected_carries",
                    "expected_targets",
                    "red_zone_share",
                    "goal_line_share",
                )
            }
            if not any(value is not None for value in values.values()) and not any(
                (role_label, player.get("injury_status"))
            ):
                raise ValueError(f"players[{index}] contains no pregame context signal")
            normalized.append(
                {
                    "player_master_id": player_id,
                    "player_name": str(salary.get("player_name") or player_id),
                    "team": expected_team,
                    "position": expected_position,
                    **values,
                    "role_label": role_label,
                    "injury_status": (
                        str(player.get("injury_status") or "").strip().upper() or None
                    ),
                    "evidence_json": dict(player.get("evidence") or {}),
                }
            )
        return sorted(normalized, key=lambda row: row["player_master_id"])

    @staticmethod
    def _validate_probability_sums(players: Sequence[Mapping[str, Any]]) -> None:
        for field, allowed_positions in (
            ("carry_share", {"RB"}),
            ("target_share", {"RB", "WR", "TE"}),
        ):
            by_team: dict[str, float] = {}
            for player in players:
                if player["position"] not in allowed_positions or player[field] is None:
                    continue
                by_team[player["team"]] = by_team.get(player["team"], 0.0) + float(
                    player[field]
                )
            over = {team: total for team, total in by_team.items() if total > 1.000001}
            if over:
                details = ", ".join(f"{team}={total:.3f}" for team, total in sorted(over.items()))
                raise ValueError(f"Explicit {field} exceeds 1.0: {details}")

    def create_run(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        self._require_schema()
        season = int(payload["season"])
        week = int(payload["week"])
        slate = str(payload["slate"]).strip().upper()
        source = str(payload["source"]).strip()
        if not slate:
            raise ValueError("slate cannot be blank")
        if not source:
            raise ValueError("source cannot be blank")
        observed_at = _utc(payload["observed_at"])
        received_at = datetime.now(UTC)
        if observed_at > received_at:
            raise ValueError("observed_at cannot be in the future")
        with self.engine.begin() as connection:
            salary_rows = connection.execute(
                text(
                    """
                    SELECT DISTINCT ON (player_master_id)
                        player_master_id, player_name, team, position
                    FROM public.curated_salary
                    WHERE season = :season
                      AND week = :week
                      AND UPPER(slate) = UPPER(:slate)
                      AND source_system = 'draftkings'
                      AND player_master_id IS NOT NULL
                    ORDER BY player_master_id,
                        CASE WHEN UPPER(COALESCE(roster_position, '')) = 'FLEX' THEN 0 ELSE 1 END,
                        created_at DESC,
                        curated_salary_id DESC
                    """
                ),
                {"season": season, "week": week, "slate": slate},
            ).mappings()
            salary_by_player = {
                str(row["player_master_id"]): dict(row) for row in salary_rows
            }
            players = self._normalize_players(
                list(payload.get("players") or []), salary_by_player
            )
            if not players:
                raise ValueError("Pregame context requires at least one player")
            self._validate_probability_sums(players)
            canonical_payload = {
                "season": season,
                "week": week,
                "slate": slate,
                "source": source,
                "source_uri": str(payload.get("source_uri") or "").strip() or None,
                "observed_at": observed_at.isoformat(),
                "notes": str(payload.get("notes") or "").strip() or None,
                "players": players,
            }
            content_hash = hashlib.sha256(
                json.dumps(canonical_payload, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
            existing = connection.execute(
                text(
                    "SELECT context_run_id FROM public.pregame_context_run "
                    "WHERE content_hash = :content_hash"
                ),
                {"content_hash": content_hash},
            ).scalar_one_or_none()
            if existing:
                return self.get_run(str(existing), connection=connection)

            context_run_id = str(uuid.uuid4())
            connection.execute(
                text(
                    """
                    INSERT INTO public.pregame_context_run
                        (context_run_id, season, week, slate, source, source_uri,
                         observed_at, received_at, notes, content_hash, status)
                    VALUES
                        (:context_run_id, :season, :week, :slate, :source, :source_uri,
                         :observed_at, :received_at, :notes, :content_hash, 'completed')
                    """
                ),
                {
                    "context_run_id": context_run_id,
                    "season": season,
                    "week": week,
                    "slate": slate,
                    "source": source,
                    "source_uri": canonical_payload["source_uri"],
                    "observed_at": observed_at,
                    "received_at": received_at,
                    "notes": canonical_payload["notes"],
                    "content_hash": content_hash,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO public.pregame_player_context
                        (context_run_id, player_master_id, player_name, team, position,
                         availability_probability, start_probability, carry_share,
                         target_share, expected_snaps, expected_routes,
                         expected_carries, expected_targets, red_zone_share,
                         goal_line_share, role_label, injury_status, evidence_json)
                    VALUES
                        (:context_run_id, :player_master_id, :player_name, :team, :position,
                         :availability_probability, :start_probability, :carry_share,
                         :target_share, :expected_snaps, :expected_routes,
                         :expected_carries, :expected_targets, :red_zone_share,
                         :goal_line_share, :role_label, :injury_status,
                         CAST(:evidence_json AS JSONB))
                    """
                ),
                [
                    {
                        **player,
                        "context_run_id": context_run_id,
                        "evidence_json": json.dumps(player["evidence_json"], sort_keys=True),
                    }
                    for player in players
                ],
            )
            return self.get_run(context_run_id, connection=connection)

    def get_run(
        self,
        context_run_id: str,
        *,
        connection: Connection | None = None,
    ) -> dict[str, Any]:
        self._require_schema()

        def load(active_connection: Connection) -> dict[str, Any]:
            run = active_connection.execute(
                text(
                    "SELECT * FROM public.pregame_context_run "
                    "WHERE context_run_id = :context_run_id"
                ),
                {"context_run_id": context_run_id},
            ).mappings().first()
            if run is None:
                raise ValueError(f"Pregame context run not found: {context_run_id}")
            rows = active_connection.execute(
                text(
                    """
                    SELECT player_master_id AS player_id, player_name, team, position,
                           availability_probability, start_probability, carry_share,
                           target_share, expected_snaps, expected_routes,
                           expected_carries, expected_targets, red_zone_share,
                           goal_line_share, role_label, injury_status,
                           evidence_json AS evidence
                    FROM public.pregame_player_context
                    WHERE context_run_id = :context_run_id
                    ORDER BY team, position, player_name, player_master_id
                    """
                ),
                {"context_run_id": context_run_id},
            ).mappings()
            return {**dict(run), "players": [dict(row) for row in rows]}

        if connection is not None:
            return load(connection)
        with self.engine.connect() as active_connection:
            return load(active_connection)

    def current(
        self,
        *,
        season: int,
        week: int,
        slate: str,
        cutoff: datetime | None = None,
    ) -> dict[str, Any]:
        self._require_schema()
        effective_cutoff = _utc(cutoff or datetime.now(UTC))
        db_inspector = inspect(self.engine)
        has_roster_participation = db_inspector.has_table(
            "curated_player_game_participation", schema="public"
        )
        roster_join = (
            """
            LEFT JOIN LATERAL (
                SELECT participation.roster_status
                FROM public.curated_player_game_participation participation
                WHERE participation.season = salary.season
                  AND participation.week = salary.week
                  AND participation.player_master_id = salary.player_master_id
                  AND UPPER(participation.team) = UPPER(salary.team)
                  AND participation.created_at <= :cutoff
                ORDER BY participation.created_at DESC,
                         participation.curated_player_game_participation_id DESC
                LIMIT 1
            ) roster ON TRUE
            """
            if has_roster_participation
            else ""
        )
        roster_status_select = (
            "roster.roster_status" if has_roster_participation else "NULL::TEXT"
        )
        with self.engine.connect() as connection:
            rows = load_current_pregame_context(
                connection,
                season=season,
                week=week,
                slate=slate,
                cutoff=effective_cutoff,
            )
            salary_rows = connection.execute(
                text(
                    f"""
                    SELECT DISTINCT ON (salary.player_master_id)
                        salary.player_master_id AS player_id,
                        salary.player_name AS player_display_name,
                        salary.team,
                        salary.position,
                        salary.player_status,
                        {roster_status_select} AS roster_status
                    FROM public.curated_salary salary
                    {roster_join}
                    WHERE salary.season = :season
                      AND salary.week = :week
                      AND UPPER(salary.slate) = UPPER(:slate)
                      AND salary.source_system = 'draftkings'
                      AND salary.player_master_id IS NOT NULL
                      AND salary.created_at <= :cutoff
                      AND UPPER(COALESCE(salary.position, ''))
                          IN ('QB', 'RB', 'WR', 'TE', 'K', 'D', 'DEF', 'DST')
                    ORDER BY salary.player_master_id,
                        CASE WHEN UPPER(COALESCE(salary.roster_position, '')) = 'FLEX'
                            THEN 0 ELSE 1 END,
                        salary.created_at DESC,
                        salary.curated_salary_id DESC
                    """
                ),
                {
                    "season": season,
                    "week": week,
                    "slate": slate,
                    "cutoff": effective_cutoff,
                },
            ).mappings()
            player_pool = _filter_salary_player_pool(list(salary_rows))
        return {
            "season": season,
            "week": week,
            "slate": slate.upper(),
            "cutoff": effective_cutoff,
            "context_run_ids": sorted({str(row["context_run_id"]) for row in rows}),
            "rows": rows,
            "player_pool": player_pool,
        }
