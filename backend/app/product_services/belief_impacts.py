"""Guarded, immutable impact previews for Digital Twin beliefs."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Mapping

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from Database.config import get_connection_string

from .beliefs import BeliefService
from .ownership import OwnershipService
from .predictions import PredictionsService
from .simulations import SimulationService
from .target_schema import validate_target_schema


IMPACT_POLICY_ID = "belief_impact_v1"
DECISIONS = {"approved", "rejected"}


def _normalize_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _scaled(value: float | None, multiplier: float) -> float | None:
    return None if value is None else round(max(0.0, value * multiplier), 4)


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def projection_adjustment_pct(direction: str, strength: int, confidence: int) -> float:
    """Return the bounded, deterministic projection adjustment for policy v1."""
    sign = 1.0 if direction in {"boost", "prefer"} else -1.0 if direction in {"fade", "avoid"} else 0.0
    posture_weight = 1.0 if direction in {"boost", "fade"} else 0.65
    magnitude = 0.12 * (max(1, min(int(strength), 5)) / 5) * (max(0, min(int(confidence), 100)) / 100)
    return round(sign * posture_weight * magnitude, 6)


def build_impact_payload(
    *,
    belief: Mapping[str, Any],
    prediction: Mapping[str, Any],
    ownership: Mapping[str, Any] | None = None,
    exposure_pct: float | None = None,
    baseline_optimal_lineup_probability: float | None = None,
    proposed_optimal_lineup_probability: float | None = None,
) -> dict[str, Any]:
    """Build a transparent before/after proposal without mutating source rows."""
    adjustment_pct = projection_adjustment_pct(
        str(belief["direction"]), int(belief["strength"]), int(belief["confidence"])
    )
    multiplier = 1.0 + adjustment_pct
    projected_ownership = _number((ownership or {}).get("projected_ownership"))
    baseline = {
        "projection_mean": _number(prediction.get("predicted_mean")),
        "projection_p10": _number(prediction.get("predicted_p10")),
        "projection_p50": _number(prediction.get("predicted_p50")),
        "projection_p90": _number(prediction.get("predicted_p90")),
        "field_ownership_pct": projected_ownership,
        "portfolio_exposure_pct": _number(exposure_pct),
        "optimal_lineup_probability": _number(baseline_optimal_lineup_probability),
    }
    proposed = {
        "projection_mean": _scaled(baseline["projection_mean"], multiplier),
        "projection_p10": _scaled(baseline["projection_p10"], multiplier),
        "projection_p50": _scaled(baseline["projection_p50"], multiplier),
        "projection_p90": _scaled(baseline["projection_p90"], multiplier),
        # Ownership is a forecast of field behavior, not a human preference control.
        "field_ownership_pct": projected_ownership,
        "portfolio_exposure_pct": (
            None
            if baseline["portfolio_exposure_pct"] is None
            else round(max(0.0, min(100.0, baseline["portfolio_exposure_pct"] * multiplier)), 4)
        ),
        "optimal_lineup_probability": _number(proposed_optimal_lineup_probability),
    }
    delta = {
        key: None if baseline[key] is None or proposed[key] is None else round(proposed[key] - baseline[key], 4)
        for key in baseline
    }
    notices = [
        "Field ownership is intentionally unchanged; this belief changes your view, not the field forecast.",
        "Approval stores a modifier for DT-703 and never rewrites the base projection.",
    ]
    if baseline["optimal_lineup_probability"] is None:
        notices.append("Optimal-lineup probability is unavailable because no matching DT-502 simulation was found.")
    elif proposed["optimal_lineup_probability"] is None:
        notices.append("The measured baseline optimal-lineup probability is available; rerun the simulation to measure the proposed distribution.")
    else:
        notices.append("Optimal-lineup probability replays the DT-502 run with the same seed and draws after changing only this player's distribution.")
    if baseline["portfolio_exposure_pct"] is None:
        notices.append("Portfolio exposure is unavailable because no matching persisted optimizer portfolio was found.")
    return {
        "adjustment_pct": adjustment_pct,
        "baseline": baseline,
        "proposed": proposed,
        "delta": delta,
        "modifier": {
            "modifier_type": "player_projection_multiplier",
            "policy_id": IMPACT_POLICY_ID,
            "player_id": str(prediction["player_id"]),
            "belief_direction": str(belief["direction"]),
            "belief_strength": int(belief["strength"]),
            "belief_confidence": int(belief["confidence"]),
            "max_absolute_projection_adjustment": 0.12,
            "projection_multiplier": round(multiplier, 6),
            "suggested_exposure_multiplier": round(multiplier, 6),
            "field_ownership_multiplier": 1.0,
            "applies_to": ["projection_mean", "projection_p10", "projection_p50", "projection_p90"],
        },
        "notices": notices,
    }


class BeliefImpactService:
    """Persist previews and one immutable approval or rejection per preview."""

    def __init__(
        self,
        connection_string: str | None = None,
        engine: Engine | None = None,
        belief_service: BeliefService | None = None,
        predictions_service: PredictionsService | None = None,
        ownership_service: OwnershipService | None = None,
        simulation_service: SimulationService | None = None,
    ) -> None:
        self.connection_string = connection_string or (
            str(engine.url) if engine is not None else get_connection_string()
        )
        self.engine = engine or create_engine(self.connection_string)
        self.belief_service = belief_service or BeliefService(connection_string=self.connection_string)
        self.predictions_service = predictions_service or PredictionsService(connection_string=self.connection_string)
        self.ownership_service = ownership_service or OwnershipService(connection_string=self.connection_string)
        self.simulation_service = simulation_service or SimulationService(
            connection_string=self.connection_string
        )

    def _ensure_schema(self) -> None:
        validate_target_schema(
            self.engine,
            consumer=type(self).__name__,
            required_tables=("belief_impact_preview", "belief_impact_decision"),
        )

    @staticmethod
    def _match_player(
        predictions: list[dict[str, Any]], target_player_id: str | None, subject_label: str | None
    ) -> dict[str, Any]:
        if target_player_id:
            matched = [row for row in predictions if str(row.get("player_id")) == str(target_player_id)]
        else:
            name_key = _normalize_name(subject_label)
            matched = [row for row in predictions if _normalize_name(row.get("player_display_name")) == name_key]
        if not matched:
            raise ValueError("Target player was not found in the selected slate projections")
        if len(matched) > 1:
            raise ValueError("Target player is ambiguous; select the exact slate player")
        return matched[0]

    def _fetch_exposure(
        self,
        *,
        season: int,
        week: int,
        slate: str | None,
        contest_format: str | None,
        objective: str | None,
        player_id: str,
    ) -> tuple[float | None, str | None]:
        conditions = ["season = :season", "week = :week", "status = 'completed'"]
        params: dict[str, Any] = {"season": season, "week": week, "player_id": player_id}
        if slate:
            conditions.append("UPPER(COALESCE(slate_id, '')) = UPPER(:slate)")
            params["slate"] = slate
        if contest_format:
            conditions.append("contest_format = :contest_format")
            params["contest_format"] = contest_format
        if objective:
            conditions.append("objective = :objective")
            params["objective"] = objective
        try:
            with self.engine.begin() as connection:
                connection.execute(text("SET LOCAL statement_timeout = '1500ms'"))
                row = connection.execute(
                    text(
                        f"""
                        WITH latest_run AS (
                            SELECT optimizer_run_id
                            FROM target.optimizer_run
                            WHERE {' AND '.join(conditions)}
                            ORDER BY created_at DESC
                            LIMIT 1
                        )
                        SELECT lr.optimizer_run_id,
                               COUNT(l.lineup_id) AS lineup_count,
                               COUNT(l.lineup_id) FILTER (
                                   WHERE EXISTS (
                                       SELECT 1 FROM target.lineup_player lp
                                       WHERE lp.lineup_id = l.lineup_id AND lp.player_id = :player_id
                                   )
                               ) AS player_lineup_count
                        FROM latest_run lr
                        LEFT JOIN target.lineup l ON l.optimizer_run_id = lr.optimizer_run_id
                        GROUP BY lr.optimizer_run_id
                        """
                    ),
                    params,
                ).mappings().first()
        except Exception:  # noqa: BLE001 - exposure is optional preview evidence
            return None, None
        if not row or not int(row.get("lineup_count") or 0):
            return None, str(row["optimizer_run_id"]) if row else None
        return (
            round(100 * int(row.get("player_lineup_count") or 0) / int(row["lineup_count"]), 4),
            str(row["optimizer_run_id"]),
        )

    @staticmethod
    def _row_payload(row: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(row)
        for source, target, default in (
            ("baseline_json", "baseline", {}),
            ("proposed_json", "proposed", {}),
            ("delta_json", "delta", {}),
            ("modifier_json", "modifier", {}),
            ("lineage_json", "lineage", {}),
            ("notices_json", "notices", []),
            ("approved_modifier_json", "approved_modifier", {}),
        ):
            if source in payload:
                payload[target] = _json_value(payload.pop(source), default)
        payload["status"] = payload.pop("decision", None) or "pending"
        return payload

    def create_preview(self, belief_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        self._ensure_schema()
        belief = self.belief_service.get_current(belief_id)
        if belief["status"] != "active" or belief.get("is_expired"):
            raise ValueError("Only a current active belief can create an impact preview")

        season = int(payload.get("season") or belief.get("season") or 0)
        week = int(payload.get("week") or belief.get("week") or 0)
        if not season or not week:
            raise ValueError("Impact previews require a season and week")
        slate = str(payload.get("slate") or belief.get("slate") or "").strip().upper() or None
        contest_format = str(payload.get("contest_format") or belief.get("contest_format") or "").strip().lower() or None
        objective = str(payload.get("objective") or belief.get("objective") or "").strip().lower() or None

        predictions = self.predictions_service.fetch_predictions(
            season=season, week=week, slate=slate, limit=1000
        )
        prediction = self._match_player(
            predictions,
            str(payload.get("target_player_id") or belief.get("subject_id") or "").strip() or None,
            belief.get("subject_label"),
        )
        ownership_rows = self.ownership_service.fetch_projected_ownership(
            season=season, week=week, slate=slate, limit=1000
        )
        ownership = next(
            (row for row in ownership_rows if str(row.get("player_id")) == str(prediction["player_id"])),
            None,
        )
        exposure_pct, optimizer_run_id = self._fetch_exposure(
            season=season,
            week=week,
            slate=slate,
            contest_format=contest_format,
            objective=objective,
            player_id=str(prediction["player_id"]),
        )
        adjustment_pct = projection_adjustment_pct(
            str(belief["direction"]), int(belief["strength"]), int(belief["confidence"])
        )
        try:
            simulation_impact = self.simulation_service.estimate_player_modifier(
                season=season,
                week=week,
                slate=slate or "",
                player_id=str(prediction["player_id"]),
                projection_multiplier=1.0 + adjustment_pct,
                projection_run_id=prediction.get("projection_run_id"),
            )
        except Exception:  # noqa: BLE001 - simulation evidence is optional preview context
            simulation_impact = None
        impact = build_impact_payload(
            belief=belief,
            prediction=prediction,
            ownership=ownership,
            exposure_pct=exposure_pct,
            baseline_optimal_lineup_probability=(simulation_impact or {}).get(
                "baseline_optimal_lineup_probability"
            ),
            proposed_optimal_lineup_probability=(simulation_impact or {}).get(
                "proposed_optimal_lineup_probability"
            ),
        )
        preview_id = f"belief-preview-{uuid.uuid4()}"
        lineage = {
            "belief_version_id": belief["belief_version_id"],
            "projection_run_id": prediction.get("projection_run_id"),
            "projection_data_cutoff_at": (
                str(prediction.get("data_cutoff_at")) if prediction.get("data_cutoff_at") else None
            ),
            "model_run_id": prediction.get("model_run_id"),
            "feature_run_id": prediction.get("feature_run_id"),
            "ownership_run_id": (ownership or {}).get("ownership_run_id"),
            "ownership_data_cutoff_at": (
                str((ownership or {}).get("data_cutoff_at"))
                if (ownership or {}).get("data_cutoff_at")
                else None
            ),
            "optimizer_run_id": optimizer_run_id,
            "simulation_run_id": (simulation_impact or {}).get("simulation_run_id"),
            "simulation_model_id": (simulation_impact or {}).get("simulation_model_id"),
            "simulation_seed": (simulation_impact or {}).get("seed"),
            "simulation_iterations": (simulation_impact or {}).get("num_simulations"),
        }
        params = {
            "preview_id": preview_id,
            "belief_version_id": belief["belief_version_id"],
            "belief_id": belief_id,
            "policy_id": IMPACT_POLICY_ID,
            "season": season,
            "week": week,
            "slate": slate,
            "contest_format": contest_format,
            "objective": objective,
            "target_player_id": str(prediction["player_id"]),
            "target_label": str(prediction.get("player_display_name") or prediction["player_id"]),
            "adjustment_pct": impact["adjustment_pct"],
            "baseline_json": json.dumps(impact["baseline"], sort_keys=True),
            "proposed_json": json.dumps(impact["proposed"], sort_keys=True),
            "delta_json": json.dumps(impact["delta"], sort_keys=True),
            "modifier_json": json.dumps(impact["modifier"], sort_keys=True),
            "lineage_json": json.dumps(lineage, sort_keys=True),
            "notices_json": json.dumps(impact["notices"]),
        }
        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    INSERT INTO target.belief_impact_preview
                        (preview_id, belief_version_id, belief_id, policy_id, season, week, slate,
                         contest_format, objective, target_player_id, target_label, adjustment_pct,
                         baseline_json, proposed_json, delta_json, modifier_json, lineage_json,
                         notices_json)
                    VALUES
                        (:preview_id, :belief_version_id, :belief_id, :policy_id, :season, :week,
                         :slate, :contest_format, :objective, :target_player_id, :target_label,
                         :adjustment_pct, CAST(:baseline_json AS JSONB), CAST(:proposed_json AS JSONB),
                         CAST(:delta_json AS JSONB), CAST(:modifier_json AS JSONB),
                         CAST(:lineage_json AS JSONB), CAST(:notices_json AS JSONB))
                    RETURNING preview_id, belief_version_id, belief_id, policy_id, season, week,
                              slate, contest_format, objective, target_player_id, target_label,
                              adjustment_pct, baseline_json, proposed_json, delta_json,
                              modifier_json, lineage_json, notices_json, created_at
                    """
                ),
                params,
            ).mappings().one()
        return self._row_payload(row)

    def list(
        self,
        *,
        preview_id: str | None = None,
        belief_id: str | None = None,
        season: int | None = None,
        week: int | None = None,
        slate: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        self._ensure_schema()
        conditions: list[str] = []
        params: dict[str, Any] = {"limit": max(1, min(int(limit), 500))}
        if preview_id:
            conditions.append("p.preview_id = :preview_id")
            params["preview_id"] = preview_id
        if belief_id:
            conditions.append("p.belief_id = :belief_id")
            params["belief_id"] = belief_id
        if season is not None:
            conditions.append("p.season = :season")
            params["season"] = int(season)
        if week is not None:
            conditions.append("p.week = :week")
            params["week"] = int(week)
        if slate:
            conditions.append("UPPER(COALESCE(p.slate, '')) = UPPER(:slate)")
            params["slate"] = slate
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    f"""
                    SELECT p.preview_id, p.belief_version_id, p.belief_id, p.policy_id,
                           p.season, p.week, p.slate, p.contest_format, p.objective,
                           p.target_player_id, p.target_label, p.adjustment_pct,
                           p.baseline_json, p.proposed_json, p.delta_json, p.modifier_json,
                           p.lineage_json, p.notices_json, p.created_at,
                           d.decision_id, d.decision, d.note_text,
                           d.approved_modifier_json, d.created_at AS decided_at
                    FROM target.belief_impact_preview p
                    LEFT JOIN target.belief_impact_decision d ON d.preview_id = p.preview_id
                    {where}
                    ORDER BY p.created_at DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
        return [self._row_payload(row) for row in rows]

    def decide(self, preview_id: str, decision: str, note_text: str | None = None) -> dict[str, Any]:
        self._ensure_schema()
        normalized = decision.strip().lower()
        if normalized not in DECISIONS:
            raise ValueError("decision must be approved or rejected")
        previews = self.list(preview_id=preview_id, limit=1)
        preview = next((row for row in previews if row["preview_id"] == preview_id), None)
        if not preview:
            raise ValueError(f"Impact preview not found: {preview_id}")
        if preview["status"] != "pending":
            raise ValueError("This impact preview already has a final decision")
        current_belief = self.belief_service.get_current(str(preview["belief_id"]))
        if current_belief["belief_version_id"] != preview["belief_version_id"]:
            raise ValueError("This preview belongs to an older belief version; create a new preview")
        if current_belief["status"] != "active" or current_belief.get("is_expired"):
            raise ValueError("Only a current active belief preview can receive a decision")
        approved_modifier = preview["modifier"] if normalized == "approved" else {}
        decision_id = f"belief-decision-{uuid.uuid4()}"
        try:
            with self.engine.begin() as connection:
                result = connection.execute(
                    text(
                        """
                        INSERT INTO target.belief_impact_decision
                            (decision_id, preview_id, decision, note_text, approved_modifier_json)
                        SELECT :decision_id, p.preview_id, :decision, :note_text,
                               CAST(:approved_modifier_json AS JSONB)
                        FROM target.belief_impact_preview p
                        WHERE p.preview_id = :preview_id
                          AND p.belief_version_id = (
                              SELECT hb.belief_version_id
                              FROM target.human_belief hb
                              WHERE hb.belief_id = p.belief_id
                              ORDER BY hb.belief_version DESC
                              LIMIT 1
                          )
                          AND EXISTS (
                              SELECT 1
                              FROM target.human_belief hb
                              WHERE hb.belief_version_id = p.belief_version_id
                                AND hb.status = 'active'
                                AND (hb.expires_at IS NULL OR hb.expires_at > now())
                          )
                        """
                    ),
                    {
                        "decision_id": decision_id,
                        "preview_id": preview_id,
                        "decision": normalized,
                        "note_text": str(note_text or "").strip() or None,
                        "approved_modifier_json": json.dumps(approved_modifier, sort_keys=True),
                    },
                )
                if result.rowcount != 1:
                    raise ValueError(
                        "This preview no longer belongs to the current active belief version"
                    )
        except IntegrityError as exc:
            raise ValueError("This impact preview already has a final decision") from exc
        return self.list(preview_id=preview_id, limit=1)[0]
