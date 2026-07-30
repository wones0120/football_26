"""Champion/challenger evaluation with approved promotion and rollback."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from typing import Any, Iterable, Mapping

from sqlalchemy import create_engine, text

from Database.config import get_connection_string
from .target_schema import validate_target_schema


MODEL_EVALUATION_CONTRACT_ID = "model_challenger_evaluation_v1"
MODEL_PROMOTION_CONTRACT_ID = "model_promotion_decision_v1"
WINDOW_NAMES = ("training", "validation", "test")
GATE_DIRECTIONS = frozenset({"minimize", "maximize"})


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _json_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [dict(item) for item in parsed if isinstance(item, Mapping)]
        return []
    return []


def _week_index(value: Mapping[str, Any]) -> int:
    season = int(value.get("season") or 0)
    week = int(value.get("week") or 0)
    if season < 2000 or week < 1 or week > 25:
        raise ValueError("Every model evaluation boundary requires season>=2000 and week 1-25.")
    return season * 100 + week


def _sha256_hash(value: str, *, label: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{label} must be a 64-character SHA-256 hash.")
    return normalized


def normalize_data_window(data_window: Mapping[str, Any]) -> dict[str, Any]:
    """Validate ordered, non-overlapping training/validation/test weeks."""
    normalized: dict[str, Any] = {}
    indexes: dict[str, tuple[int, int]] = {}
    for name in WINDOW_NAMES:
        window = data_window.get(name)
        if not isinstance(window, Mapping):
            raise ValueError(f"Model evaluation data_window.{name} is required.")
        start = window.get("start")
        end = window.get("end")
        if not isinstance(start, Mapping) or not isinstance(end, Mapping):
            raise ValueError(f"Model evaluation data_window.{name} requires start and end.")
        start_index = _week_index(start)
        end_index = _week_index(end)
        if start_index > end_index:
            raise ValueError(f"Model evaluation {name} window starts after it ends.")
        normalized[name] = {
            "start": {"season": int(start["season"]), "week": int(start["week"])},
            "end": {"season": int(end["season"]), "week": int(end["week"])},
        }
        indexes[name] = (start_index, end_index)
    if indexes["training"][1] >= indexes["validation"][0]:
        raise ValueError("Training must end before validation starts.")
    if indexes["validation"][1] >= indexes["test"][0]:
        raise ValueError("Validation must end before test starts.")
    return normalized


def evaluate_metric_gates(gates: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Evaluate comparable champion/challenger metrics under declared gates."""
    gate_rows = [dict(gate) for gate in gates]
    if not gate_rows:
        raise ValueError("At least one champion/challenger metric gate is required.")
    if not any(float(gate.get("required_improvement") or 0.0) > 0 for gate in gate_rows):
        raise ValueError("At least one metric gate must require a strict positive improvement.")

    results: list[dict[str, Any]] = []
    seen_metrics: set[str] = set()
    for gate in gate_rows:
        metric = str(gate.get("metric") or "").strip()
        direction = str(gate.get("direction") or "").strip().lower()
        if not metric:
            raise ValueError("Every metric gate requires a metric name.")
        if metric in seen_metrics:
            raise ValueError(f"Duplicate metric gate: {metric}")
        seen_metrics.add(metric)
        if direction not in GATE_DIRECTIONS:
            raise ValueError(f"Metric gate {metric} has unsupported direction {direction!r}.")
        champion_value = float(gate.get("champion_value"))
        challenger_value = float(gate.get("challenger_value"))
        required_improvement = float(gate.get("required_improvement") or 0.0)
        metric_values = (champion_value, challenger_value, required_improvement)
        if not all(math.isfinite(value) for value in metric_values):
            raise ValueError(f"Metric gate {metric} contains a non-finite value.")
        improvement = (
            champion_value - challenger_value
            if direction == "minimize"
            else challenger_value - champion_value
        )
        passed = improvement >= required_improvement
        results.append(
            {
                "metric": metric,
                "direction": direction,
                "champion_value": champion_value,
                "challenger_value": challenger_value,
                "required_improvement": required_improvement,
                "observed_improvement": improvement,
                "passed": passed,
            }
        )
    return results


class ModelGovernanceService:
    """Persist evaluations and atomically apply approved active-run changes."""

    def __init__(self, connection_string: str | None = None) -> None:
        self.connection_string = connection_string or get_connection_string()
        self.engine = create_engine(self.connection_string)

    def _ensure_schema(self) -> None:
        validate_target_schema(
            self.engine,
            consumer=type(self).__name__,
            required_tables=(
                "feature_generation_run",
                "model_run",
                "projection_run",
                "active_projection_run",
                "model_challenger_evaluation",
                "model_promotion_decision",
            ),
        )

    @staticmethod
    def _projection_run(connection, projection_run_id: str) -> Mapping[str, Any] | None:
        return connection.execute(
            text(
                """
                SELECT pr.projection_run_id, pr.model_run_id, pr.season, pr.week,
                       pr.slate_id, pr.row_count, pr.data_cutoff_at, pr.status,
                       pr.created_at, mr.model_id, mr.feature_run_id, mr.params_json,
                       feature.feature_set_hash
                FROM target.projection_run pr
                JOIN target.model_run mr ON mr.model_run_id = pr.model_run_id
                LEFT JOIN target.feature_generation_run feature
                  ON feature.feature_run_id = mr.feature_run_id
                WHERE pr.projection_run_id = :projection_run_id
                """
            ),
            {"projection_run_id": projection_run_id},
        ).mappings().first()

    @staticmethod
    def _evaluation(connection, evaluation_id: str) -> Mapping[str, Any] | None:
        return connection.execute(
            text(
                """
                SELECT *
                FROM target.model_challenger_evaluation
                WHERE evaluation_id = :evaluation_id
                """
            ),
            {"evaluation_id": evaluation_id},
        ).mappings().first()

    @staticmethod
    def _decision(connection, decision_id: str) -> Mapping[str, Any] | None:
        return connection.execute(
            text(
                """
                SELECT *
                FROM target.model_promotion_decision
                WHERE decision_id = :decision_id
                """
            ),
            {"decision_id": decision_id},
        ).mappings().first()

    @staticmethod
    def _evaluation_payload(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "evaluation_id": str(row["evaluation_id"]),
            "contract_id": MODEL_EVALUATION_CONTRACT_ID,
            "season": int(row["season"]),
            "week": int(row["week"]),
            "slate_id": str(row["slate_id"]),
            "champion_projection_run_id": str(row["champion_projection_run_id"]),
            "challenger_projection_run_id": str(row["challenger_projection_run_id"]),
            "data_window": _json_object(row.get("data_window_json")),
            "champion_feature_set_hash": str(row["champion_feature_set_hash"]),
            "challenger_feature_set_hash": str(row["challenger_feature_set_hash"]),
            "champion_code_hash": str(row["champion_code_hash"]),
            "challenger_code_hash": str(row["challenger_code_hash"]),
            "gates": _json_list(row.get("gate_policy_json")),
            "gate_results": _json_list(row.get("gate_results_json")),
            "status": str(row["status"]),
            "evaluation_hash": str(row["evaluation_hash"]),
            "evaluated_by": str(row["evaluated_by"]),
            "evidence_uri": str(row["evidence_uri"]),
            "notes": row.get("notes"),
            "created_at": row["created_at"],
        }

    @staticmethod
    def _decision_payload(row: Mapping[str, Any], *, active: bool = False) -> dict[str, Any]:
        decision_id = str(row["decision_id"])
        action = str(row["action"])
        return {
            "decision_id": decision_id,
            "contract_id": MODEL_PROMOTION_CONTRACT_ID,
            "evaluation_id": str(row["evaluation_id"]),
            "action": action,
            "approved_by": str(row["approved_by"]),
            "approval_reason": str(row["approval_reason"]),
            "previous_projection_run_id": str(row["previous_projection_run_id"]),
            "selected_projection_run_id": str(row["selected_projection_run_id"]),
            "rollback_of_decision_id": row.get("rollback_of_decision_id"),
            "decision_hash": str(row["decision_hash"]),
            "selection_reason": f"model_{action}:{decision_id}",
            "active": active,
            "created_at": row["created_at"],
        }

    def create_evaluation(
        self,
        *,
        champion_projection_run_id: str,
        challenger_projection_run_id: str,
        data_window: Mapping[str, Any],
        champion_code_hash: str,
        challenger_code_hash: str,
        gates: Iterable[Mapping[str, Any]],
        evaluated_by: str,
        evidence_uri: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_schema()
        if champion_projection_run_id == challenger_projection_run_id:
            raise ValueError("Champion and challenger projection runs must differ.")
        normalized_window = normalize_data_window(data_window)
        gate_results = evaluate_metric_gates(gates)
        normalized_gates = [
            {
                "metric": row["metric"],
                "direction": row["direction"],
                "champion_value": row["champion_value"],
                "challenger_value": row["challenger_value"],
                "required_improvement": row["required_improvement"],
            }
            for row in gate_results
        ]
        normalized_evaluator = evaluated_by.strip()
        normalized_evidence = evidence_uri.strip()
        if not normalized_evaluator or not normalized_evidence:
            raise ValueError("evaluated_by and evidence_uri are required.")

        with self.engine.begin() as connection:
            champion = self._projection_run(connection, champion_projection_run_id)
            challenger = self._projection_run(connection, challenger_projection_run_id)
            if not champion or str(champion.get("status")) != "completed":
                raise ValueError("Champion projection run must exist and be completed.")
            if not challenger or str(challenger.get("status")) != "completed":
                raise ValueError("Challenger projection run must exist and be completed.")
            champion_scope = (
                int(champion["season"]),
                int(champion["week"]),
                str(champion["slate_id"]).upper(),
            )
            challenger_scope = (
                int(challenger["season"]),
                int(challenger["week"]),
                str(challenger["slate_id"]).upper(),
            )
            if champion_scope != challenger_scope:
                raise ValueError("Champion and challenger projection runs must share one scope.")
            champion_feature_hash = str(champion.get("feature_set_hash") or "").strip()
            challenger_feature_hash = str(challenger.get("feature_set_hash") or "").strip()
            if not champion_feature_hash or not challenger_feature_hash:
                raise ValueError("Both projection runs require persisted feature-set hashes.")
            declared_code_hashes = {
                "champion": _sha256_hash(champion_code_hash, label="champion_code_hash"),
                "challenger": _sha256_hash(challenger_code_hash, label="challenger_code_hash"),
            }
            for label, run in (("champion", champion), ("challenger", challenger)):
                persisted_code_hash = str(
                    _json_object(run.get("params_json")).get("code_hash") or ""
                ).lower()
                if persisted_code_hash and persisted_code_hash != declared_code_hashes[label]:
                    raise ValueError(
                        f"Declared {label} code hash does not match persisted model lineage."
                    )

            evaluation_core = {
                "contract_id": MODEL_EVALUATION_CONTRACT_ID,
                "season": champion_scope[0],
                "week": champion_scope[1],
                "slate_id": champion_scope[2],
                "champion_projection_run_id": champion_projection_run_id,
                "challenger_projection_run_id": challenger_projection_run_id,
                "data_window": normalized_window,
                "champion_feature_set_hash": champion_feature_hash,
                "challenger_feature_set_hash": challenger_feature_hash,
                "champion_code_hash": declared_code_hashes["champion"],
                "challenger_code_hash": declared_code_hashes["challenger"],
                "gates": normalized_gates,
                "gate_results": gate_results,
                "status": "passed" if all(row["passed"] for row in gate_results) else "blocked",
                "evaluated_by": normalized_evaluator,
                "evidence_uri": normalized_evidence,
                "notes": notes,
            }
            evaluation_hash = hashlib.sha256(
                json.dumps(evaluation_core, sort_keys=True, default=str).encode()
            ).hexdigest()
            evaluation_id = f"model-evaluation:{evaluation_hash[:24]}"
            existing = connection.execute(
                text(
                    """
                    SELECT * FROM target.model_challenger_evaluation
                    WHERE evaluation_hash = :evaluation_hash
                    """
                ),
                {"evaluation_hash": evaluation_hash},
            ).mappings().first()
            if existing:
                return self._evaluation_payload(existing)

            active_run_id = connection.execute(
                text(
                    """
                    SELECT projection_run_id
                    FROM target.active_projection_run
                    WHERE season = :season AND week = :week
                      AND UPPER(slate_id) = UPPER(:slate_id)
                    """
                ),
                {
                    "season": champion_scope[0],
                    "week": champion_scope[1],
                    "slate_id": champion_scope[2],
                },
            ).scalar()
            if str(active_run_id or "") != champion_projection_run_id:
                raise ValueError(
                    "The declared champion is not the active projection run for this scope."
                )

            created = connection.execute(
                text(
                    """
                    INSERT INTO target.model_challenger_evaluation
                        (evaluation_id, season, week, slate_id,
                         champion_projection_run_id, challenger_projection_run_id,
                         data_window_json, champion_feature_set_hash,
                         challenger_feature_set_hash, champion_code_hash,
                         challenger_code_hash, gate_policy_json, gate_results_json,
                         status, evaluation_hash, evaluated_by, evidence_uri, notes)
                    VALUES
                        (:evaluation_id, :season, :week, :slate_id,
                         :champion_projection_run_id, :challenger_projection_run_id,
                         CAST(:data_window_json AS JSONB), :champion_feature_set_hash,
                         :challenger_feature_set_hash, :champion_code_hash,
                         :challenger_code_hash, CAST(:gate_policy_json AS JSONB),
                         CAST(:gate_results_json AS JSONB), :status, :evaluation_hash,
                         :evaluated_by, :evidence_uri, :notes)
                    RETURNING *
                    """
                ),
                {
                    "evaluation_id": evaluation_id,
                    "season": champion_scope[0],
                    "week": champion_scope[1],
                    "slate_id": champion_scope[2],
                    "champion_projection_run_id": champion_projection_run_id,
                    "challenger_projection_run_id": challenger_projection_run_id,
                    "data_window_json": json.dumps(normalized_window, sort_keys=True),
                    "champion_feature_set_hash": champion_feature_hash,
                    "challenger_feature_set_hash": challenger_feature_hash,
                    "champion_code_hash": declared_code_hashes["champion"],
                    "challenger_code_hash": declared_code_hashes["challenger"],
                    "gate_policy_json": json.dumps(normalized_gates, sort_keys=True),
                    "gate_results_json": json.dumps(gate_results, sort_keys=True),
                    "status": evaluation_core["status"],
                    "evaluation_hash": evaluation_hash,
                    "evaluated_by": normalized_evaluator,
                    "evidence_uri": normalized_evidence,
                    "notes": notes,
                },
            ).mappings().one()
        return self._evaluation_payload(created)

    def get_evaluation(self, evaluation_id: str) -> dict[str, Any] | None:
        self._ensure_schema()
        with self.engine.connect() as connection:
            row = self._evaluation(connection, evaluation_id)
        return self._evaluation_payload(row) if row else None

    def _insert_decision(
        self,
        connection,
        *,
        evaluation_id: str,
        action: str,
        approved_by: str,
        approval_reason: str,
        previous_projection_run_id: str,
        selected_projection_run_id: str,
        rollback_of_decision_id: str | None,
    ) -> Mapping[str, Any]:
        decision_core = {
            "contract_id": MODEL_PROMOTION_CONTRACT_ID,
            "evaluation_id": evaluation_id,
            "action": action,
            "approved_by": approved_by,
            "approval_reason": approval_reason,
            "previous_projection_run_id": previous_projection_run_id,
            "selected_projection_run_id": selected_projection_run_id,
            "rollback_of_decision_id": rollback_of_decision_id,
        }
        decision_hash = hashlib.sha256(
            json.dumps(decision_core, sort_keys=True).encode()
        ).hexdigest()
        existing = connection.execute(
            text(
                """
                SELECT * FROM target.model_promotion_decision
                WHERE decision_hash = :decision_hash
                """
            ),
            {"decision_hash": decision_hash},
        ).mappings().first()
        if existing:
            return existing
        same_action = connection.execute(
            text(
                """
                SELECT * FROM target.model_promotion_decision
                WHERE evaluation_id = :evaluation_id AND action = :action
                """
            ),
            {"evaluation_id": evaluation_id, "action": action},
        ).mappings().first()
        if same_action:
            raise ValueError(
                f"Evaluation {evaluation_id} already has a different {action} decision."
            )
        decision_id = f"model-decision:{decision_hash[:24]}"
        return connection.execute(
            text(
                """
                INSERT INTO target.model_promotion_decision
                    (decision_id, evaluation_id, action, approved_by, approval_reason,
                     previous_projection_run_id, selected_projection_run_id,
                     rollback_of_decision_id, decision_hash)
                VALUES
                    (:decision_id, :evaluation_id, :action, :approved_by, :approval_reason,
                     :previous_projection_run_id, :selected_projection_run_id,
                     :rollback_of_decision_id, :decision_hash)
                RETURNING *
                """
            ),
            {"decision_id": decision_id, "decision_hash": decision_hash, **decision_core},
        ).mappings().one()

    @staticmethod
    def _active_pointer(connection, evaluation: Mapping[str, Any]) -> str | None:
        value = connection.execute(
            text(
                """
                SELECT projection_run_id
                FROM target.active_projection_run
                WHERE season = :season AND week = :week
                  AND UPPER(slate_id) = UPPER(:slate_id)
                FOR UPDATE
                """
            ),
            {
                "season": evaluation["season"],
                "week": evaluation["week"],
                "slate_id": evaluation["slate_id"],
            },
        ).scalar()
        return str(value) if value else None

    @staticmethod
    def _move_pointer(
        connection,
        *,
        evaluation: Mapping[str, Any],
        previous_projection_run_id: str,
        selected_projection_run_id: str,
        selection_reason: str,
    ) -> None:
        updated = connection.execute(
            text(
                """
                UPDATE target.active_projection_run
                SET projection_run_id = :selected_projection_run_id,
                    selection_reason = :selection_reason,
                    selected_at = now()
                WHERE season = :season AND week = :week
                  AND UPPER(slate_id) = UPPER(:slate_id)
                  AND projection_run_id = :previous_projection_run_id
                """
            ),
            {
                "season": evaluation["season"],
                "week": evaluation["week"],
                "slate_id": evaluation["slate_id"],
                "previous_projection_run_id": previous_projection_run_id,
                "selected_projection_run_id": selected_projection_run_id,
                "selection_reason": selection_reason,
            },
        )
        if int(updated.rowcount or 0) != 1:
            raise ValueError(
                "The active projection pointer changed concurrently; retry after review."
            )

    def promote(
        self,
        evaluation_id: str,
        *,
        approved_by: str,
        approval_reason: str,
    ) -> dict[str, Any]:
        self._ensure_schema()
        approver = approved_by.strip()
        reason = approval_reason.strip()
        if not approver or not reason:
            raise ValueError("approved_by and approval_reason are required.")
        with self.engine.begin() as connection:
            evaluation = self._evaluation(connection, evaluation_id)
            if not evaluation:
                raise ValueError(f"Model evaluation not found: {evaluation_id}")
            if str(evaluation["status"]) != "passed":
                raise ValueError("A blocked model evaluation cannot be promoted.")
            previous_run_id = str(evaluation["champion_projection_run_id"])
            selected_run_id = str(evaluation["challenger_projection_run_id"])
            existing = connection.execute(
                text(
                    """
                    SELECT * FROM target.model_promotion_decision
                    WHERE evaluation_id = :evaluation_id AND action = 'promotion'
                    """
                ),
                {"evaluation_id": evaluation_id},
            ).mappings().first()
            if existing:
                if (
                    str(existing["approved_by"]) == approver
                    and str(existing["approval_reason"]) == reason
                ):
                    active = self._active_pointer(connection, evaluation) == selected_run_id
                    return self._decision_payload(existing, active=active)
                raise ValueError(f"Evaluation {evaluation_id} already has a promotion decision.")
            if self._active_pointer(connection, evaluation) != previous_run_id:
                raise ValueError("Promotion requires the evaluated champion to remain active.")
            decision = self._insert_decision(
                connection,
                evaluation_id=evaluation_id,
                action="promotion",
                approved_by=approver,
                approval_reason=reason,
                previous_projection_run_id=previous_run_id,
                selected_projection_run_id=selected_run_id,
                rollback_of_decision_id=None,
            )
            self._move_pointer(
                connection,
                evaluation=evaluation,
                previous_projection_run_id=previous_run_id,
                selected_projection_run_id=selected_run_id,
                selection_reason=f"model_promotion:{decision['decision_id']}",
            )
        return self._decision_payload(decision, active=True)

    def rollback(
        self,
        promotion_decision_id: str,
        *,
        approved_by: str,
        approval_reason: str,
    ) -> dict[str, Any]:
        self._ensure_schema()
        approver = approved_by.strip()
        reason = approval_reason.strip()
        if not approver or not reason:
            raise ValueError("approved_by and approval_reason are required.")
        with self.engine.begin() as connection:
            promotion = self._decision(connection, promotion_decision_id)
            if not promotion or str(promotion.get("action")) != "promotion":
                raise ValueError(f"Promotion decision not found: {promotion_decision_id}")
            evaluation_id = str(promotion["evaluation_id"])
            evaluation = self._evaluation(connection, evaluation_id)
            if not evaluation:
                raise ValueError(f"Model evaluation not found: {evaluation_id}")
            existing = connection.execute(
                text(
                    """
                    SELECT * FROM target.model_promotion_decision
                    WHERE rollback_of_decision_id = :promotion_decision_id
                    """
                ),
                {"promotion_decision_id": promotion_decision_id},
            ).mappings().first()
            if existing:
                if (
                    str(existing["approved_by"]) == approver
                    and str(existing["approval_reason"]) == reason
                ):
                    selected_run_id = str(existing["selected_projection_run_id"])
                    active = self._active_pointer(connection, evaluation) == selected_run_id
                    return self._decision_payload(existing, active=active)
                raise ValueError(f"Promotion {promotion_decision_id} was already rolled back.")
            previous_run_id = str(promotion["selected_projection_run_id"])
            selected_run_id = str(promotion["previous_projection_run_id"])
            if self._active_pointer(connection, evaluation) != previous_run_id:
                raise ValueError("Rollback requires the promoted challenger to remain active.")
            decision = self._insert_decision(
                connection,
                evaluation_id=evaluation_id,
                action="rollback",
                approved_by=approver,
                approval_reason=reason,
                previous_projection_run_id=previous_run_id,
                selected_projection_run_id=selected_run_id,
                rollback_of_decision_id=promotion_decision_id,
            )
            self._move_pointer(
                connection,
                evaluation=evaluation,
                previous_projection_run_id=previous_run_id,
                selected_projection_run_id=selected_run_id,
                selection_reason=f"model_rollback:{decision['decision_id']}",
            )
        return self._decision_payload(decision, active=True)

    def get_decision(self, decision_id: str) -> dict[str, Any] | None:
        self._ensure_schema()
        with self.engine.connect() as connection:
            row = self._decision(connection, decision_id)
            if not row:
                return None
            evaluation = self._evaluation(connection, str(row["evaluation_id"]))
            active = bool(
                evaluation
                and self._active_pointer(connection, evaluation)
                == str(row["selected_projection_run_id"])
            )
        return self._decision_payload(row, active=active)
