"""Immutable model, human, and combined Digital Twin variant bundles."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from Database.config import get_connection_string

from .target_schema import validate_target_schema


VARIANT_POLICY_ID = "digital_twin_variants_v1"
VARIANT_TYPES = ("model_only", "human_only", "combined")
PROJECTION_FIELDS = ("projection_mean", "projection_p10", "projection_p50", "projection_p90")


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _scaled(value: float | None, multiplier: float) -> float | None:
    return None if value is None else round(max(0.0, value * multiplier), 4)


def artifact_hash(artifact: Mapping[str, Any]) -> str:
    """Return a stable digest for a JSON-safe variant artifact."""
    encoded = json.dumps(
        artifact,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _model_player(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "player_id": str(row["player_id"]),
        "player_label": str(row.get("player_label") or row["player_id"]),
        "game_id": str(row["game_id"]) if row.get("game_id") is not None else None,
        "model_run_id": (
            str(row["model_run_id"]) if row.get("model_run_id") is not None else None
        ),
        "projection_mean": _number(row.get("projection_mean", row.get("mean"))),
        "projection_p10": _number(row.get("projection_p10", row.get("p10"))),
        "projection_p50": _number(
            row.get("projection_p50", row.get("median", row.get("mean")))
        ),
        "projection_p90": _number(row.get("projection_p90", row.get("p90"))),
    }


def build_variant_artifacts(
    *,
    projection_run_id: str,
    base_rows: Sequence[Mapping[str, Any]],
    approved_rows: Sequence[Mapping[str, Any]],
    decision_cutoff_at: datetime | str,
) -> dict[str, dict[str, Any]]:
    """Build the three replayable artifacts from exact model and approval inputs."""
    model_players = sorted(
        (_model_player(row) for row in base_rows),
        key=lambda row: (row["player_id"], row.get("game_id") or ""),
    )
    if not model_players:
        raise ValueError("The selected projection run has no player projections in this scope")
    model_ids = {row["player_id"] for row in model_players}
    if len(model_ids) != len(model_players):
        raise ValueError("The selected projection run contains duplicate player projections")

    human_by_player: dict[str, dict[str, Any]] = {}
    for row in approved_rows:
        modifier = _json_value(row.get("approved_modifier_json", row.get("modifier")), {})
        target_player_id = str(row.get("target_player_id") or "").strip()
        modifier_player_id = str(modifier.get("player_id") or "").strip()
        if target_player_id and modifier_player_id and modifier_player_id != target_player_id:
            raise ValueError("Approved modifier player does not match its impact preview target")
        player_id = target_player_id or modifier_player_id
        if not player_id or player_id not in model_ids:
            continue
        multiplier = _number(modifier.get("projection_multiplier"))
        if multiplier is None or multiplier <= 0:
            raise ValueError("Approved projection modifiers require a positive projection_multiplier")
        if modifier.get("modifier_type") != "player_projection_multiplier":
            raise ValueError("Unsupported approved modifier type")
        if modifier.get("policy_id") != "belief_impact_v1":
            raise ValueError("Unsupported approved modifier policy")
        item = human_by_player.setdefault(
            player_id,
            {
                "player_id": player_id,
                "projection_multiplier": 1.0,
                "suggested_exposure_multiplier": 1.0,
                "approved_inputs": [],
            },
        )
        item["projection_multiplier"] = round(item["projection_multiplier"] * multiplier, 8)
        exposure_multiplier = _number(modifier.get("suggested_exposure_multiplier"))
        item["suggested_exposure_multiplier"] = round(
            item["suggested_exposure_multiplier"]
            * (exposure_multiplier if exposure_multiplier is not None else 1.0),
            8,
        )
        item["approved_inputs"].append(
            {
                "decision_id": str(row.get("decision_id") or ""),
                "preview_id": str(row.get("preview_id") or ""),
                "belief_id": str(row.get("belief_id") or ""),
                "belief_version_id": str(row.get("belief_version_id") or ""),
                "policy_id": str(modifier.get("policy_id") or row.get("policy_id") or ""),
                "projection_multiplier": round(multiplier, 8),
            }
        )

    human_players = []
    for player_id in sorted(human_by_player):
        item = human_by_player[player_id]
        item["approved_inputs"] = sorted(
            item["approved_inputs"],
            key=lambda value: (value["decision_id"], value["preview_id"]),
        )
        human_players.append(item)

    model_artifact = {
        "variant_type": "model_only",
        "projection_run_id": projection_run_id,
        "players": model_players,
    }
    human_artifact = {
        "variant_type": "human_only",
        "projection_run_id": projection_run_id,
        "decision_cutoff_at": (
            decision_cutoff_at.isoformat()
            if isinstance(decision_cutoff_at, datetime)
            else str(decision_cutoff_at)
        ),
        "composition_rule": "multiply_each_explicitly_approved_player_modifier",
        "players": human_players,
    }
    combined_artifact = build_combined_artifact(model_artifact, human_artifact)
    return {
        "model_only": model_artifact,
        "human_only": human_artifact,
        "combined": combined_artifact,
    }


def build_combined_artifact(
    model_artifact: Mapping[str, Any], human_artifact: Mapping[str, Any]
) -> dict[str, Any]:
    """Recompute the combined projection snapshot from persisted variant inputs."""
    human_by_player = {
        str(row["player_id"]): row for row in human_artifact.get("players", [])
    }
    combined_players: list[dict[str, Any]] = []
    for model_row in model_artifact.get("players", []):
        player_id = str(model_row["player_id"])
        human_row = human_by_player.get(player_id, {})
        multiplier = _number(human_row.get("projection_multiplier")) or 1.0
        combined_row = dict(model_row)
        for field in PROJECTION_FIELDS:
            combined_row[field] = _scaled(_number(model_row.get(field)), multiplier)
        combined_row.update(
            {
                "projection_multiplier": round(multiplier, 8),
                "suggested_exposure_multiplier": round(
                    _number(human_row.get("suggested_exposure_multiplier")) or 1.0, 8
                ),
                "approved_decision_ids": [
                    value["decision_id"] for value in human_row.get("approved_inputs", [])
                ],
                "approved_preview_ids": [
                    value["preview_id"] for value in human_row.get("approved_inputs", [])
                ],
            }
        )
        combined_players.append(combined_row)
    return {
        "variant_type": "combined",
        "projection_run_id": str(model_artifact["projection_run_id"]),
        "composition_rule": str(human_artifact.get("composition_rule") or ""),
        "players": combined_players,
    }


def compare_artifacts(artifacts: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Return a compact side-by-side comparison of all changed player inputs."""
    model_by_player = {
        str(row["player_id"]): row for row in artifacts["model_only"].get("players", [])
    }
    human_by_player = {
        str(row["player_id"]): row for row in artifacts["human_only"].get("players", [])
    }
    combined_by_player = {
        str(row["player_id"]): row for row in artifacts["combined"].get("players", [])
    }
    rows = []
    for player_id in sorted(human_by_player):
        model = model_by_player[player_id]
        human = human_by_player[player_id]
        combined = combined_by_player[player_id]
        rows.append(
            {
                "player_id": player_id,
                "player_label": model.get("player_label") or player_id,
                "projection_multiplier": human["projection_multiplier"],
                "model_projection_mean": model.get("projection_mean"),
                "combined_projection_mean": combined.get("projection_mean"),
                "projection_mean_delta": (
                    None
                    if model.get("projection_mean") is None
                    or combined.get("projection_mean") is None
                    else round(combined["projection_mean"] - model["projection_mean"], 4)
                ),
                "approved_decision_ids": combined.get("approved_decision_ids", []),
                "approved_preview_ids": combined.get("approved_preview_ids", []),
            }
        )
    return {
        "player_count": len(model_by_player),
        "players_with_human_input": len(human_by_player),
        "players_unchanged": len(model_by_player) - len(human_by_player),
        "changed_players": rows,
    }


def verify_variant_artifacts(
    artifacts: Mapping[str, Mapping[str, Any]], stored_hashes: Mapping[str, str]
) -> dict[str, Any]:
    """Verify stored JSON integrity and deterministic combined recomposition."""
    stored_artifact_hashes: dict[str, str] = {}
    checks: dict[str, bool] = {}
    for variant_type in VARIANT_TYPES:
        try:
            stored_artifact_hashes[variant_type] = artifact_hash(artifacts[variant_type])
        except (KeyError, TypeError, ValueError):
            stored_artifact_hashes[variant_type] = ""
        checks[variant_type] = (
            bool(stored_artifact_hashes[variant_type])
            and stored_artifact_hashes[variant_type] == stored_hashes.get(variant_type)
        )

    recomputed_combined: dict[str, Any] | None = None
    recomputed_hashes = {
        "model_only": stored_artifact_hashes["model_only"],
        "human_only": stored_artifact_hashes["human_only"],
        "combined": "",
    }
    try:
        recomputed_combined = build_combined_artifact(
            artifacts["model_only"], artifacts["human_only"]
        )
        recomputed_hashes["combined"] = artifact_hash(recomputed_combined)
    except (KeyError, TypeError, ValueError):
        checks["combined"] = False
    else:
        checks["combined"] = checks["combined"] and (
            recomputed_hashes["combined"] == stored_hashes.get("combined")
        )
    return {
        "checks": checks,
        "stored_artifact_hashes": stored_artifact_hashes,
        "recomputed_hashes": recomputed_hashes,
        "recomputed_combined": recomputed_combined,
    }


class DigitalTwinVariantService:
    """Persist and replay immutable Digital Twin comparison bundles."""

    def __init__(
        self,
        connection_string: str | None = None,
        engine: Engine | None = None,
    ) -> None:
        self.connection_string = connection_string or (
            str(engine.url) if engine is not None else get_connection_string()
        )
        self.engine = engine or create_engine(self.connection_string)

    def _ensure_schema(self) -> None:
        validate_target_schema(
            self.engine,
            consumer=type(self).__name__,
            required_tables=("digital_twin_variant_set", "digital_twin_variant"),
        )

    def _resolve_projection_run(
        self,
        *,
        season: int,
        week: int,
        slate: str,
        projection_run_id: str | None,
    ) -> tuple[str, datetime | None]:
        conditions = ["season = :season", "week = :week"]
        params: dict[str, Any] = {"season": season, "week": week, "slate": slate}
        if projection_run_id:
            conditions.append("projection_run_id = :projection_run_id")
            params["projection_run_id"] = projection_run_id
        else:
            conditions.append(
                "projection_run_id = COALESCE(("
                "SELECT active.projection_run_id FROM target.active_projection_run active "
                "WHERE active.season = :season AND active.week = :week "
                "AND (UPPER(active.slate_id) = UPPER(:slate) OR active.slate_id = 'DEFAULT') "
                "ORDER BY CASE WHEN UPPER(active.slate_id) = UPPER(:slate) "
                "THEN 0 ELSE 1 END, active.selected_at DESC LIMIT 1"
                "), projection_run_id)"
            )
        conditions.append(
            "(UPPER(slate_id) = UPPER(:slate) OR "
            "(slate_id IS NULL AND EXISTS ("
            "SELECT 1 FROM target.snapshot_salary s "
            "WHERE s.season = player_projection.season "
            "AND s.week = player_projection.week "
            "AND s.player_id = player_projection.player_id "
            "AND UPPER(COALESCE(s.slate, s.slate_id)) = UPPER(:slate)"
            ")))"
        )
        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    f"""
                    SELECT projection_run_id, MAX(data_cutoff_at) AS data_cutoff_at,
                           MAX(created_at) AS latest_created_at
                    FROM target.player_projection
                    WHERE {' AND '.join(conditions)}
                    GROUP BY projection_run_id
                    ORDER BY latest_created_at DESC
                    LIMIT 1
                    """
                ),
                params,
            ).mappings().first()
        if not row:
            if projection_run_id:
                raise ValueError(f"Projection run not found in this slate: {projection_run_id}")
            raise ValueError("No persisted projection run was found for this slate")
        return str(row["projection_run_id"]), row.get("data_cutoff_at")

    def _load_base_rows(
        self,
        *,
        season: int,
        week: int,
        slate: str,
        projection_run_id: str,
    ) -> list[dict[str, Any]]:
        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT p.player_id,
                           COALESCE(NULLIF(d.full_name, ''), p.player_id) AS player_label,
                           p.game_id, p.model_run_id,
                           p.mean AS projection_mean, p.p10 AS projection_p10,
                           COALESCE(p.median, p.mean) AS projection_p50,
                           p.p90 AS projection_p90
                    FROM target.player_projection p
                    LEFT JOIN target.dim_player d ON d.player_id = p.player_id
                    WHERE p.projection_run_id = :projection_run_id
                      AND p.season = :season AND p.week = :week
                      AND (
                          UPPER(p.slate_id) = UPPER(:slate)
                          OR (
                              p.slate_id IS NULL
                              AND EXISTS (
                                  SELECT 1
                                  FROM target.snapshot_salary s
                                  WHERE s.season = p.season
                                    AND s.week = p.week
                                    AND s.player_id = p.player_id
                                    AND UPPER(COALESCE(s.slate, s.slate_id)) = UPPER(:slate)
                              )
                          )
                      )
                    ORDER BY p.player_id, p.game_id
                    """
                ),
                {
                    "projection_run_id": projection_run_id,
                    "season": season,
                    "week": week,
                    "slate": slate,
                },
            ).mappings().all()
        return [dict(row) for row in rows]

    def _load_approved_rows(
        self,
        *,
        season: int,
        week: int,
        slate: str,
        contest_format: str | None,
        objective: str | None,
        projection_run_id: str,
        decision_cutoff_at: datetime,
    ) -> list[dict[str, Any]]:
        conditions = [
            "p.season = :season",
            "p.week = :week",
            "(p.slate IS NULL OR UPPER(p.slate) = UPPER(:slate))",
            "d.decision = 'approved'",
            "d.created_at <= :decision_cutoff_at",
            "p.lineage_json ->> 'projection_run_id' = :projection_run_id",
        ]
        params: dict[str, Any] = {
            "season": season,
            "week": week,
            "slate": slate,
            "projection_run_id": projection_run_id,
            "decision_cutoff_at": decision_cutoff_at,
        }
        if contest_format:
            conditions.append("(p.contest_format IS NULL OR p.contest_format = :contest_format)")
            params["contest_format"] = contest_format
        if objective:
            conditions.append("(p.objective IS NULL OR p.objective = :objective)")
            params["objective"] = objective
        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    f"""
                    SELECT DISTINCT ON (p.belief_version_id)
                           d.decision_id, p.preview_id, p.belief_id, p.belief_version_id,
                           p.policy_id, p.target_player_id, d.approved_modifier_json,
                           d.created_at AS decided_at
                    FROM target.belief_impact_preview p
                    JOIN target.belief_impact_decision d ON d.preview_id = p.preview_id
                    WHERE {' AND '.join(conditions)}
                    ORDER BY p.belief_version_id, d.created_at DESC, d.decision_id DESC
                    """
                ),
                params,
            ).mappings().all()
        return [dict(row) for row in rows]

    @staticmethod
    def _row_payload(row: Mapping[str, Any], variants: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        artifacts: dict[str, dict[str, Any]] = {}
        hashes: dict[str, str] = {}
        variant_ids: dict[str, str] = {}
        for variant in variants:
            variant_type = str(variant["variant_type"])
            artifacts[variant_type] = _json_value(variant.get("artifact_json"), {})
            hashes[variant_type] = str(variant["artifact_hash"])
            variant_ids[variant_type] = str(variant["variant_id"])
        payload = dict(row)
        payload["artifacts"] = artifacts
        payload["artifact_hashes"] = hashes
        payload["variant_ids"] = variant_ids
        payload["comparison"] = compare_artifacts(artifacts) if len(artifacts) == 3 else {}
        return payload

    def create(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        self._ensure_schema()
        season = int(payload["season"])
        week = int(payload["week"])
        slate = str(payload["slate"]).strip().upper()
        contest_format = str(payload.get("contest_format") or "").strip().lower() or None
        objective = str(payload.get("objective") or "").strip().lower() or None
        decision_cutoff_at = payload.get("decision_cutoff_at") or datetime.now(timezone.utc)
        if not isinstance(decision_cutoff_at, datetime):
            decision_cutoff_at = datetime.fromisoformat(str(decision_cutoff_at).replace("Z", "+00:00"))
        if decision_cutoff_at.tzinfo is None:
            decision_cutoff_at = decision_cutoff_at.replace(tzinfo=timezone.utc)

        projection_run_id, projection_cutoff = self._resolve_projection_run(
            season=season,
            week=week,
            slate=slate,
            projection_run_id=str(payload.get("projection_run_id") or "").strip() or None,
        )
        base_rows = self._load_base_rows(
            season=season,
            week=week,
            slate=slate,
            projection_run_id=projection_run_id,
        )
        approved_rows = self._load_approved_rows(
            season=season,
            week=week,
            slate=slate,
            contest_format=contest_format,
            objective=objective,
            projection_run_id=projection_run_id,
            decision_cutoff_at=decision_cutoff_at,
        )
        artifacts = build_variant_artifacts(
            projection_run_id=projection_run_id,
            base_rows=base_rows,
            approved_rows=approved_rows,
            decision_cutoff_at=decision_cutoff_at,
        )
        variant_set_id = f"digital-twin-variants-{uuid.uuid4()}"
        created_at = datetime.now(timezone.utc)
        with self.engine.begin() as connection:
            set_row = connection.execute(
                text(
                    """
                    INSERT INTO target.digital_twin_variant_set
                        (variant_set_id, policy_id, season, week, slate, contest_format,
                         objective, projection_run_id, projection_data_cutoff_at,
                         decision_cutoff_at, status, created_at)
                    VALUES
                        (:variant_set_id, :policy_id, :season, :week, :slate, :contest_format,
                         :objective, :projection_run_id, :projection_data_cutoff_at,
                         :decision_cutoff_at, 'completed', :created_at)
                    RETURNING *
                    """
                ),
                {
                    "variant_set_id": variant_set_id,
                    "policy_id": VARIANT_POLICY_ID,
                    "season": season,
                    "week": week,
                    "slate": slate,
                    "contest_format": contest_format,
                    "objective": objective,
                    "projection_run_id": projection_run_id,
                    "projection_data_cutoff_at": projection_cutoff,
                    "decision_cutoff_at": decision_cutoff_at,
                    "created_at": created_at,
                },
            ).mappings().one()
            variant_rows = []
            for variant_type in VARIANT_TYPES:
                artifact = artifacts[variant_type]
                variant_rows.append(
                    connection.execute(
                        text(
                            """
                            INSERT INTO target.digital_twin_variant
                                (variant_id, variant_set_id, variant_type, artifact_json,
                                 artifact_hash, created_at)
                            VALUES
                                (:variant_id, :variant_set_id, :variant_type,
                                 CAST(:artifact_json AS JSONB), :artifact_hash, :created_at)
                            RETURNING *
                            """
                        ),
                        {
                            "variant_id": f"digital-twin-variant-{uuid.uuid4()}",
                            "variant_set_id": variant_set_id,
                            "variant_type": variant_type,
                            "artifact_json": json.dumps(artifact, sort_keys=True, allow_nan=False),
                            "artifact_hash": artifact_hash(artifact),
                            "created_at": created_at,
                        },
                    ).mappings().one()
                )
        return self._row_payload(set_row, variant_rows)

    def list(
        self,
        *,
        variant_set_id: str | None = None,
        season: int | None = None,
        week: int | None = None,
        slate: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        self._ensure_schema()
        conditions: list[str] = []
        params: dict[str, Any] = {"limit": max(1, min(int(limit), 200))}
        if variant_set_id:
            conditions.append("s.variant_set_id = :variant_set_id")
            params["variant_set_id"] = variant_set_id
        if season is not None:
            conditions.append("s.season = :season")
            params["season"] = int(season)
        if week is not None:
            conditions.append("s.week = :week")
            params["week"] = int(week)
        if slate:
            conditions.append("UPPER(s.slate) = UPPER(:slate)")
            params["slate"] = slate
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.engine.begin() as connection:
            sets = connection.execute(
                text(
                    f"""
                    SELECT s.*
                    FROM target.digital_twin_variant_set s
                    {where}
                    ORDER BY s.created_at DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
            rows = []
            for set_row in sets:
                variants = connection.execute(
                    text(
                        """
                        SELECT variant_id, variant_set_id, variant_type, artifact_json,
                               artifact_hash, created_at
                        FROM target.digital_twin_variant
                        WHERE variant_set_id = :variant_set_id
                        ORDER BY variant_type
                        """
                    ),
                    {"variant_set_id": set_row["variant_set_id"]},
                ).mappings().all()
                rows.append(self._row_payload(set_row, variants))
        return rows

    def replay(self, variant_set_id: str) -> dict[str, Any]:
        rows = self.list(variant_set_id=variant_set_id, limit=1)
        if not rows:
            raise ValueError(f"Digital Twin variant set not found: {variant_set_id}")
        row = rows[0]
        artifacts = row["artifacts"]
        stored_hashes = row["artifact_hashes"]
        verification = verify_variant_artifacts(artifacts, stored_hashes)
        checks = verification["checks"]
        recomputed_combined = verification["recomputed_combined"]
        return {
            "variant_set_id": variant_set_id,
            "policy_id": row["policy_id"],
            "status": "verified" if all(checks.values()) else "mismatch",
            "checks": checks,
            "stored_hashes": stored_hashes,
            "recomputed_hashes": verification["recomputed_hashes"],
            "comparison": (
                compare_artifacts(
                    {
                        "model_only": artifacts["model_only"],
                        "human_only": artifacts["human_only"],
                        "combined": recomputed_combined,
                    }
                )
                if recomputed_combined is not None and all(checks.values())
                else {}
            ),
        }
