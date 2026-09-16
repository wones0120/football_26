"""Targeted, replayable LEARN-002 questions from Digital Twin variants."""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from typing import Any, Mapping

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from Database.config import get_connection_string

from .target_schema import validate_target_schema


QUESTION_POLICY_ID = "agent_question_voi_v1"
QUESTION_POLICY = {
    "policy_id": QUESTION_POLICY_ID,
    "max_questions": 5,
    "disagreement_min_multiplier_delta": 0.04,
    "disagreement_min_score": 25.0,
    "uncertainty_min_mean": 8.0,
    "uncertainty_min_width": 12.0,
    "uncertainty_min_score": 40.0,
    "uncertainty_answer_multiplier": 0.04,
}
ANSWERS_BY_TRIGGER = {
    "model_human_disagreement": {"support_model", "support_human", "no_change"},
    "high_value_uncertainty": {"lean_upside", "lean_downside", "no_change"},
}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _modifier(player_id: str, multiplier: float, source: str) -> dict[str, Any]:
    if multiplier == 1.0:
        return {}
    return {
        "modifier_type": "player_projection_multiplier",
        "policy_id": QUESTION_POLICY_ID,
        "player_id": player_id,
        "projection_multiplier": round(multiplier, 8),
        "suggested_exposure_multiplier": round(multiplier, 8),
        "field_ownership_multiplier": 1.0,
        "source": source,
        "status": "recorded_not_applied",
    }


def build_agent_questions(
    *,
    variant_set: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
    max_questions: int | None = None,
) -> list[dict[str, Any]]:
    """Apply the versioned VOI policy to one immutable DT-703 bundle."""
    model_rows = {
        str(row["player_id"]): dict(row)
        for row in artifacts.get("model_only", {}).get("players", [])
    }
    human_rows = {
        str(row["player_id"]): dict(row)
        for row in artifacts.get("human_only", {}).get("players", [])
    }
    candidates: list[dict[str, Any]] = []

    for player_id, human in human_rows.items():
        model = model_rows.get(player_id)
        if not model:
            continue
        multiplier = _number(human.get("projection_multiplier"))
        mean = _number(model.get("projection_mean"))
        p10 = _number(model.get("projection_p10"))
        p90 = _number(model.get("projection_p90"))
        if multiplier is None or mean is None:
            continue
        multiplier_delta = abs(multiplier - 1.0)
        if multiplier_delta < QUESTION_POLICY["disagreement_min_multiplier_delta"]:
            continue
        delta = round(mean * (multiplier - 1.0), 4)
        width = max(0.0, p90 - p10) if p10 is not None and p90 is not None else 0.0
        score = round(min(100.0, abs(delta) * 12.0 + width), 2)
        if score < QUESTION_POLICY["disagreement_min_score"]:
            continue
        label = str(model.get("player_label") or player_id)
        direction = "raise" if multiplier > 1 else "lower"
        context = {
            "model_projection_mean": mean,
            "human_projection_mean": round(mean * multiplier, 4),
            "projection_p10": p10,
            "projection_p90": p90,
            "projection_multiplier": multiplier,
            "approved_inputs": human.get("approved_inputs", []),
            "answer_modifiers": {
                "support_model": {},
                "support_human": _modifier(player_id, multiplier, "support_human"),
                "no_change": {},
            },
        }
        candidates.append({
            "trigger_type": "model_human_disagreement",
            "priority": 5 if score >= 60 else 4,
            "value_of_information_score": score,
            "subject_player_id": player_id,
            "subject_label": label,
            "question_text": (
                f"Your approved view would {direction} {label} from {mean:.2f} to "
                f"{mean * multiplier:.2f} points. Which view should guide this slate?"
            ),
            "context": context,
        })

    for player_id, model in model_rows.items():
        if player_id in human_rows:
            continue
        mean = _number(model.get("projection_mean"))
        p10 = _number(model.get("projection_p10"))
        p90 = _number(model.get("projection_p90"))
        if mean is None or p10 is None or p90 is None:
            continue
        width = max(0.0, p90 - p10)
        if mean < QUESTION_POLICY["uncertainty_min_mean"] or width < QUESTION_POLICY["uncertainty_min_width"]:
            continue
        score = round(min(100.0, width * 2.0 + mean), 2)
        if score < QUESTION_POLICY["uncertainty_min_score"]:
            continue
        label = str(model.get("player_label") or player_id)
        answer_delta = float(QUESTION_POLICY["uncertainty_answer_multiplier"])
        context = {
            "model_projection_mean": mean,
            "projection_p10": p10,
            "projection_p90": p90,
            "uncertainty_width": round(width, 4),
            "answer_modifiers": {
                "lean_upside": _modifier(player_id, 1.0 + answer_delta, "lean_upside"),
                "lean_downside": _modifier(player_id, 1.0 - answer_delta, "lean_downside"),
                "no_change": {},
            },
        }
        candidates.append({
            "trigger_type": "high_value_uncertainty",
            "priority": 4 if score >= 60 else 3,
            "value_of_information_score": score,
            "subject_player_id": player_id,
            "subject_label": label,
            "question_text": (
                f"{label} has a wide {p10:.2f}–{p90:.2f} point range around a "
                f"{mean:.2f} mean. Do you have a strong slate-specific lean?"
            ),
            "context": context,
        })

    candidates.sort(
        key=lambda row: (
            -int(row["priority"]),
            -float(row["value_of_information_score"]),
            row["trigger_type"],
            row["subject_player_id"],
        )
    )
    limit = max(1, min(int(max_questions or QUESTION_POLICY["max_questions"]), 10))
    results = []
    for row in candidates[:limit]:
        evidence = {
            "policy": QUESTION_POLICY,
            "variant_set_id": str(variant_set["variant_set_id"]),
            "projection_run_id": str(variant_set["projection_run_id"]),
            "trigger_type": row["trigger_type"],
            "subject_player_id": row["subject_player_id"],
            "context": row["context"],
        }
        evidence_hash = _hash(evidence)
        results.append({
            **row,
            "question_id": "agent-question-" + str(uuid.uuid5(uuid.NAMESPACE_URL, evidence_hash)),
            "policy_id": QUESTION_POLICY_ID,
            "variant_set_id": str(variant_set["variant_set_id"]),
            "season": int(variant_set["season"]),
            "week": int(variant_set["week"]),
            "slate": str(variant_set["slate"]).upper(),
            "evidence_hash": evidence_hash,
        })
    return results


class AgentQuestionService:
    """Persist LEARN-002 questions, answers, and inert proposed modifiers."""

    def __init__(self, connection_string: str | None = None, engine: Engine | None = None) -> None:
        self.connection_string = connection_string or (
            str(engine.url) if engine is not None else get_connection_string()
        )
        self.engine = engine or create_engine(self.connection_string)

    def _ensure_schema(self) -> None:
        validate_target_schema(
            self.engine,
            consumer=type(self).__name__,
            required_tables=(
                "agent_question", "agent_question_answer",
                "digital_twin_variant_set", "digital_twin_variant",
            ),
        )

    @staticmethod
    def _payload(row: Mapping[str, Any]) -> dict[str, Any]:
        value = dict(row)
        value["context"] = value.pop("context_json", {}) or {}
        value["resulting_modifier"] = value.pop("resulting_modifier_json", {}) or {}
        value["status"] = "answered" if value.get("answer_id") else "pending"
        return value

    def _variant_bundle(
        self, connection, *, season: int, week: int, slate: str, variant_set_id: str | None
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        params = {"season": season, "week": week, "slate": slate.upper()}
        condition = "season=:season AND week=:week AND upper(slate)=:slate"
        if variant_set_id:
            condition += " AND variant_set_id=:variant_set_id"
            params["variant_set_id"] = variant_set_id
        variant_set = connection.execute(text(f"""
            SELECT variant_set_id, season, week, slate, projection_run_id, created_at
            FROM target.digital_twin_variant_set
            WHERE {condition}
            ORDER BY created_at DESC LIMIT 1
        """), params).mappings().first()
        if not variant_set:
            raise ValueError("No DT-703 variant bundle exists for this slate; freeze the three variants first")
        rows = connection.execute(text("""
            SELECT variant_type, artifact_json
            FROM target.digital_twin_variant
            WHERE variant_set_id=:variant_set_id
        """), {"variant_set_id": variant_set["variant_set_id"]}).mappings().all()
        artifacts = {str(row["variant_type"]): dict(row["artifact_json"]) for row in rows}
        if "model_only" not in artifacts or "human_only" not in artifacts:
            raise ValueError("The selected DT-703 variant bundle is incomplete")
        return dict(variant_set), artifacts

    def generate(
        self, *, season: int, week: int, slate: str, variant_set_id: str | None = None
    ) -> dict[str, Any]:
        self._ensure_schema()
        with self.engine.begin() as connection:
            variant_set, artifacts = self._variant_bundle(
                connection, season=season, week=week, slate=slate, variant_set_id=variant_set_id
            )
            questions = build_agent_questions(variant_set=variant_set, artifacts=artifacts)
            for question in questions:
                connection.execute(text("""
                    INSERT INTO target.agent_question
                        (question_id, policy_id, variant_set_id, season, week, slate,
                         trigger_type, priority, value_of_information_score,
                         subject_player_id, subject_label, question_text, context_json, evidence_hash)
                    VALUES
                        (:question_id, :policy_id, :variant_set_id, :season, :week, :slate,
                         :trigger_type, :priority, :value_of_information_score,
                         :subject_player_id, :subject_label, :question_text,
                         CAST(:context_json AS JSONB), :evidence_hash)
                    ON CONFLICT (evidence_hash) DO NOTHING
                """), {**question, "context_json": json.dumps(question["context"], sort_keys=True)})
        return self.list(season=season, week=week, slate=slate, variant_set_id=variant_set["variant_set_id"])

    def list(
        self, *, season: int, week: int, slate: str, variant_set_id: str | None = None
    ) -> dict[str, Any]:
        self._ensure_schema()
        params: dict[str, Any] = {"season": season, "week": week, "slate": slate.upper()}
        variant_filter = ""
        if variant_set_id:
            variant_filter = " AND q.variant_set_id=:variant_set_id"
            params["variant_set_id"] = variant_set_id
        else:
            variant_filter = """
                AND q.variant_set_id = (
                    SELECT latest.variant_set_id
                    FROM target.digital_twin_variant_set latest
                    WHERE latest.season=:season AND latest.week=:week
                      AND upper(latest.slate)=:slate
                    ORDER BY latest.created_at DESC LIMIT 1
                )
            """
        with self.engine.begin() as connection:
            rows = connection.execute(text(f"""
                SELECT q.question_id, q.policy_id, q.variant_set_id, q.season, q.week, q.slate,
                       q.trigger_type, q.priority, q.value_of_information_score,
                       q.subject_player_id, q.subject_label, q.question_text, q.context_json,
                       q.evidence_hash, q.created_at, a.answer_id, a.answer, a.answer_text,
                       a.resulting_modifier_json, a.created_at AS answered_at
                FROM target.agent_question q
                LEFT JOIN target.agent_question_answer a USING (question_id)
                WHERE q.season=:season AND q.week=:week AND upper(q.slate)=:slate {variant_filter}
                ORDER BY q.created_at DESC, q.value_of_information_score DESC, q.question_id
            """), params).mappings().all()
        payload = [self._payload(row) for row in rows]
        return {
            "policy_id": QUESTION_POLICY_ID,
            "policy": QUESTION_POLICY,
            "rows": payload,
            "summary": {
                "total": len(payload),
                "pending": sum(row["status"] == "pending" for row in payload),
                "answered": sum(row["status"] == "answered" for row in payload),
            },
        }

    def answer(self, question_id: str, answer: str, answer_text: str | None = None) -> dict[str, Any]:
        self._ensure_schema()
        normalized = answer.strip().lower()
        with self.engine.begin() as connection:
            question = connection.execute(text("""
                SELECT question_id, trigger_type, context_json
                FROM target.agent_question WHERE question_id=:question_id
            """), {"question_id": question_id}).mappings().first()
            if not question:
                raise ValueError(f"Agent question not found: {question_id}")
            if normalized not in ANSWERS_BY_TRIGGER[str(question["trigger_type"])]:
                allowed = ", ".join(sorted(ANSWERS_BY_TRIGGER[str(question["trigger_type"])]))
                raise ValueError(f"Answer must be one of: {allowed}")
            context = dict(question["context_json"] or {})
            resulting_modifier = dict(context.get("answer_modifiers", {}).get(normalized, {}))
            try:
                connection.execute(text("""
                    INSERT INTO target.agent_question_answer
                        (answer_id, question_id, answer, answer_text, resulting_modifier_json)
                    VALUES (:answer_id, :question_id, :answer, :answer_text,
                            CAST(:resulting_modifier_json AS JSONB))
                """), {
                    "answer_id": f"agent-answer-{uuid.uuid4()}",
                    "question_id": question_id,
                    "answer": normalized,
                    "answer_text": str(answer_text or "").strip() or None,
                    "resulting_modifier_json": json.dumps(resulting_modifier, sort_keys=True),
                })
            except IntegrityError as exc:
                raise ValueError("This agent question already has a recorded answer") from exc
            row = connection.execute(text("""
                SELECT q.question_id, q.policy_id, q.variant_set_id, q.season, q.week, q.slate,
                       q.trigger_type, q.priority, q.value_of_information_score,
                       q.subject_player_id, q.subject_label, q.question_text, q.context_json,
                       q.evidence_hash, q.created_at, a.answer_id, a.answer, a.answer_text,
                       a.resulting_modifier_json, a.created_at AS answered_at
                FROM target.agent_question q JOIN target.agent_question_answer a USING (question_id)
                WHERE q.question_id=:question_id
            """), {"question_id": question_id}).mappings().one()
        return self._payload(row)
