"""Versioned human beliefs for the Digital Twin."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from Database.config import get_connection_string

from .target_schema import validate_target_schema


BELIEF_SCOPES = {"global", "contest_profile", "season", "weekly", "game", "player"}
BELIEF_DIRECTIONS = {"boost", "fade", "prefer", "avoid", "monitor", "neutral"}
BELIEF_STATUSES = {"active", "inactive"}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _normalize_create(payload: Mapping[str, Any]) -> dict[str, Any]:
    scope_type = str(payload.get("scope_type") or "").strip().lower()
    if scope_type not in BELIEF_SCOPES:
        raise ValueError(f"scope_type must be one of: {', '.join(sorted(BELIEF_SCOPES))}")

    thought_text = _clean_text(payload.get("thought_text"))
    if not thought_text:
        raise ValueError("thought_text is required")

    direction = str(payload.get("direction") or "neutral").strip().lower()
    if direction not in BELIEF_DIRECTIONS:
        raise ValueError(f"direction must be one of: {', '.join(sorted(BELIEF_DIRECTIONS))}")

    strength = int(payload.get("strength", 3))
    confidence = int(payload.get("confidence", 50))
    if not 1 <= strength <= 5:
        raise ValueError("strength must be between 1 and 5")
    if not 0 <= confidence <= 100:
        raise ValueError("confidence must be between 0 and 100")

    season = payload.get("season")
    week = payload.get("week")
    season = int(season) if season is not None else None
    week = int(week) if week is not None else None
    if week is not None and not 1 <= week <= 25:
        raise ValueError("week must be between 1 and 25")

    contest_format = _clean_text(payload.get("contest_format"))
    objective = _clean_text(payload.get("objective"))
    contest_format = contest_format.lower() if contest_format else None
    objective = objective.lower() if objective else None
    if contest_format not in {None, "classic", "showdown"}:
        raise ValueError("contest_format must be classic or showdown")
    if objective not in {None, "cash", "gpp"}:
        raise ValueError("objective must be cash or gpp")

    subject_label = _clean_text(payload.get("subject_label"))
    if scope_type == "contest_profile" and not (contest_format or objective):
        raise ValueError("contest_profile beliefs require a contest format or objective")
    if scope_type in {"season", "weekly", "game"} and season is None:
        raise ValueError(f"{scope_type} beliefs require a season")
    if scope_type in {"weekly", "game"} and week is None:
        raise ValueError(f"{scope_type} beliefs require a week")
    if scope_type in {"game", "player"} and not subject_label:
        raise ValueError(f"{scope_type} beliefs require a subject_label")

    status = str(payload.get("status") or "active").strip().lower()
    if status not in BELIEF_STATUSES:
        raise ValueError("status must be active or inactive")

    slate = _clean_text(payload.get("slate"))
    return {
        "scope_type": scope_type,
        "subject_label": subject_label,
        "subject_id": _clean_text(payload.get("subject_id")),
        "season": season,
        "week": week,
        "slate": slate.upper() if slate else None,
        "contest_format": contest_format,
        "objective": objective,
        "direction": direction,
        "strength": strength,
        "confidence": confidence,
        "thought_text": thought_text,
        "evidence_text": _clean_text(payload.get("evidence_text")),
        "expires_at": payload.get("expires_at"),
        "is_retrospective": bool(payload.get("is_retrospective", False)),
        "status": status,
        "source": _clean_text(payload.get("source")) or "manual",
        "metadata_json": dict(payload.get("metadata") or {}),
    }


def _row_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["metadata"] = result.pop("metadata_json", None) or {}
    expires_at = result.get("expires_at")
    now = datetime.now(timezone.utc)
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    result["is_expired"] = bool(expires_at and expires_at <= now)
    return result


class BeliefService:
    """Persist immutable versions of user-authored decision beliefs."""

    def __init__(self, connection_string: str | None = None, engine: Engine | None = None) -> None:
        self.connection_string = connection_string or (
            str(engine.url) if engine is not None else get_connection_string()
        )
        self.engine = engine or create_engine(self.connection_string)

    def _ensure_schema(self) -> None:
        validate_target_schema(
            self.engine,
            consumer=type(self).__name__,
            required_tables=("human_belief",),
        )

    def _insert_version(
        self,
        connection,
        *,
        belief_id: str,
        belief_version: int,
        supersedes_version_id: str | None,
        operation: str,
        belief: Mapping[str, Any],
    ) -> dict[str, Any]:
        belief_version_id = f"belief-version-{uuid.uuid4()}"
        row = connection.execute(
            text(
                """
                INSERT INTO target.human_belief
                    (belief_version_id, belief_id, belief_version, supersedes_version_id,
                     operation, status, scope_type, subject_label, subject_id, season, week,
                     slate, contest_format, objective, direction, strength, confidence,
                     thought_text, evidence_text, expires_at, is_retrospective, source, metadata_json)
                VALUES
                    (:belief_version_id, :belief_id, :belief_version, :supersedes_version_id,
                     :operation, :status, :scope_type, :subject_label, :subject_id, :season, :week,
                     :slate, :contest_format, :objective, :direction, :strength, :confidence,
                     :thought_text, :evidence_text, :expires_at, :is_retrospective, :source,
                     CAST(:metadata_json AS JSONB))
                RETURNING belief_version_id, belief_id, belief_version, supersedes_version_id,
                          operation, status, scope_type, subject_label, subject_id, season, week,
                          slate, contest_format, objective, direction, strength, confidence,
                          thought_text, evidence_text, expires_at, is_retrospective,
                          impact_status, source, metadata_json, created_at
                """
            ),
            {
                **belief,
                "belief_version_id": belief_version_id,
                "belief_id": belief_id,
                "belief_version": belief_version,
                "supersedes_version_id": supersedes_version_id,
                "operation": operation,
                "metadata_json": json.dumps(belief.get("metadata_json") or {}, sort_keys=True),
            },
        ).mappings().one()
        return _row_payload(row)

    def create(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        self._ensure_schema()
        with self.engine.begin() as connection:
            return self.create_with_connection(connection, payload)

    def create_with_connection(self, connection, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Create a belief inside an existing transaction."""
        belief = _normalize_create(payload)
        return self._insert_version(
            connection,
            belief_id=f"belief-{uuid.uuid4()}",
            belief_version=1,
            supersedes_version_id=None,
            operation="created",
            belief=belief,
        )

    def _latest_for_update(self, connection, belief_id: str) -> dict[str, Any]:
        row = connection.execute(
            text(
                """
                SELECT belief_version_id, belief_id, belief_version, status, scope_type,
                       subject_label, subject_id, season, week, slate, contest_format, objective,
                       direction, strength, confidence, thought_text, evidence_text, expires_at,
                       is_retrospective, source, metadata_json
                FROM target.human_belief
                WHERE belief_id = :belief_id
                ORDER BY belief_version DESC
                LIMIT 1
                FOR UPDATE
                """
            ),
            {"belief_id": belief_id},
        ).mappings().first()
        if not row:
            raise ValueError(f"Belief not found: {belief_id}")
        return dict(row)

    def get_current(self, belief_id: str) -> dict[str, Any]:
        """Return the latest immutable version of one logical belief."""
        self._ensure_schema()
        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT belief_version_id, belief_id, belief_version, supersedes_version_id,
                           operation, status, scope_type, subject_label, subject_id, season, week,
                           slate, contest_format, objective, direction, strength, confidence,
                           thought_text, evidence_text, expires_at, is_retrospective,
                           impact_status, source, metadata_json, created_at
                    FROM target.human_belief
                    WHERE belief_id = :belief_id
                    ORDER BY belief_version DESC
                    LIMIT 1
                    """
                ),
                {"belief_id": belief_id},
            ).mappings().first()
        if not row:
            raise ValueError(f"Belief not found: {belief_id}")
        return _row_payload(row)

    def revise(self, belief_id: str, changes: Mapping[str, Any]) -> dict[str, Any]:
        self._ensure_schema()
        allowed = {
            "subject_label", "subject_id", "season", "week", "slate", "contest_format",
            "objective", "direction", "strength", "confidence", "thought_text",
            "evidence_text", "expires_at", "is_retrospective", "source", "metadata", "status",
        }
        unexpected = set(changes) - allowed
        if unexpected:
            raise ValueError(f"Unsupported revision fields: {', '.join(sorted(unexpected))}")
        with self.engine.begin() as connection:
            previous = self._latest_for_update(connection, belief_id)
            merged = {
                "scope_type": previous["scope_type"],
                "subject_label": previous["subject_label"],
                "subject_id": previous["subject_id"],
                "season": previous["season"],
                "week": previous["week"],
                "slate": previous["slate"],
                "contest_format": previous["contest_format"],
                "objective": previous["objective"],
                "direction": previous["direction"],
                "strength": previous["strength"],
                "confidence": previous["confidence"],
                "thought_text": previous["thought_text"],
                "evidence_text": previous["evidence_text"],
                "expires_at": previous["expires_at"],
                "is_retrospective": previous["is_retrospective"],
                "source": previous["source"],
                "metadata": previous["metadata_json"] or {},
                "status": previous["status"],
                **changes,
            }
            belief = _normalize_create(merged)
            old_status = str(previous["status"])
            new_status = str(belief["status"])
            operation = (
                "deactivated" if old_status == "active" and new_status == "inactive"
                else "reactivated" if old_status == "inactive" and new_status == "active"
                else "revised"
            )
            return self._insert_version(
                connection,
                belief_id=belief_id,
                belief_version=int(previous["belief_version"]) + 1,
                supersedes_version_id=str(previous["belief_version_id"]),
                operation=operation,
                belief=belief,
            )

    def set_status(self, belief_id: str, status: str) -> dict[str, Any]:
        normalized = status.strip().lower()
        if normalized not in BELIEF_STATUSES:
            raise ValueError("status must be active or inactive")
        return self.revise(belief_id, {"status": normalized})

    def list(
        self,
        *,
        season: int | None = None,
        week: int | None = None,
        slate: str | None = None,
        include_inactive: bool = True,
        limit: int = 200,
    ) -> dict[str, Any]:
        self._ensure_schema()
        conditions = ["latest_rank = 1"]
        params: dict[str, Any] = {"limit": max(1, min(int(limit), 500))}
        if season is not None:
            conditions.append("(season IS NULL OR season = :season)")
            params["season"] = int(season)
        if week is not None:
            conditions.append("(week IS NULL OR week = :week)")
            params["week"] = int(week)
        if slate:
            conditions.append("(slate IS NULL OR UPPER(slate) = UPPER(:slate))")
            params["slate"] = slate
        if not include_inactive:
            conditions.append("status = 'active'")

        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    f"""
                    WITH versions AS (
                        SELECT belief_version_id, belief_id, belief_version, supersedes_version_id,
                               operation, status, scope_type, subject_label, subject_id, season, week,
                               slate, contest_format, objective, direction, strength, confidence,
                               thought_text, evidence_text, expires_at, is_retrospective,
                               impact_status, source, metadata_json, created_at,
                               ROW_NUMBER() OVER (
                                   PARTITION BY belief_id ORDER BY belief_version DESC
                               ) AS latest_rank
                        FROM target.human_belief
                    )
                    SELECT belief_version_id, belief_id, belief_version, supersedes_version_id,
                           operation, status, scope_type, subject_label, subject_id, season, week,
                           slate, contest_format, objective, direction, strength, confidence,
                           thought_text, evidence_text, expires_at, is_retrospective,
                           impact_status, source, metadata_json, created_at
                    FROM versions
                    WHERE {' AND '.join(conditions)}
                    ORDER BY created_at DESC, belief_id
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()

        beliefs = [_row_payload(row) for row in rows]
        active = sum(row["status"] == "active" and not row["is_expired"] for row in beliefs)
        inactive = sum(row["status"] == "inactive" for row in beliefs)
        expired = sum(row["is_expired"] for row in beliefs)
        scopes: dict[str, int] = {}
        for row in beliefs:
            scopes[row["scope_type"]] = scopes.get(row["scope_type"], 0) + 1
        return {
            "rows": beliefs,
            "summary": {
                "total": len(beliefs),
                "active": active,
                "inactive": inactive,
                "expired": expired,
                "by_scope": scopes,
            },
        }
