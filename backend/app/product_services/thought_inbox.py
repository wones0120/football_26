"""Persist raw Digital Twin thoughts and extract guarded belief candidates."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Iterable, Mapping

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from Database.config import get_connection_string

from .beliefs import BeliefService
from .predictions import PredictionsService
from .target_schema import validate_target_schema


EXTRACTION_POLICY_ID = "raw_thought_extractor_v1"
THOUGHT_CONTEXTS = {"auto", "general", "slate", "player"}
MAX_CANDIDATES = 12

_DIRECTION_CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("fade", ("fade", "underweight", "overpriced", "overowned", "too high", "downgrade")),
    ("avoid", ("avoid", "stay away", "do not play", "don't play")),
    ("boost", ("boost", "upgrade", "underpriced", "too low", "higher than", "increase")),
    ("prefer", ("prefer", "overweight", "prioritize", "love", "like", "target")),
    ("monitor", ("monitor", "watch", "uncertain", "questionable", "wait for")),
)
_SENTENCE_ABBREVIATIONS = {"dr", "jr", "mr", "mrs", "ms", "sr", "st", "vs"}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _searchable(value: Any) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())


def split_raw_thoughts(raw_text: str, *, limit: int = MAX_CANDIDATES) -> tuple[list[str], bool]:
    """Split free-form notes without losing the original capture."""
    text_value = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [
        re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s*", "", line).strip()
        for line in text_value.split("\n")
        if line.strip()
    ]
    statements: list[str] = []
    for line in lines:
        start = 0
        for match in re.finditer(r"[.!?]\s+(?=[A-Z0-9])", line):
            punctuation_index = match.start()
            previous_word = re.search(r"([A-Za-z]+)\W*$", line[start:punctuation_index])
            if previous_word and previous_word.group(1).lower() in _SENTENCE_ABBREVIATIONS:
                continue
            statement = line[start : punctuation_index + 1].strip()
            if statement:
                statements.append(statement)
            start = match.end()
        remainder = line[start:].strip()
        if remainder:
            statements.append(remainder)

    statements = [statement[:5000] for statement in statements if statement]
    was_truncated = len(statements) > limit
    return statements[:limit], was_truncated


def _infer_direction(statement: str) -> tuple[str, str | None]:
    searchable = _searchable(statement)
    for direction, cues in _DIRECTION_CUES:
        for cue in cues:
            normalized_cue = _searchable(cue)
            if re.search(rf"(?:^|\s){re.escape(normalized_cue)}(?:$|\s)", searchable):
                return direction, cue
    return "neutral", None


def _infer_calibration(statement: str) -> tuple[int, int]:
    searchable = _searchable(statement)
    if any(cue in searchable for cue in ("very confident", "strong conviction", "must play", "lock button")):
        return 4, 70
    if any(cue in searchable for cue in ("small lean", "slight lean", "maybe", "not sure")):
        return 2, 35
    return 3, 50


def _matched_player(statement: str, players: Iterable[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    searchable = f" {_searchable(statement)} "
    matches: list[tuple[int, Mapping[str, Any]]] = []
    for player in players:
        name = _searchable(player.get("player_display_name"))
        if name and f" {name} " in searchable:
            matches.append((len(name), player))
    return max(matches, key=lambda row: row[0])[1] if matches else None


def extract_candidate_beliefs(
    raw_text: str,
    *,
    context_type: str,
    season: int | None = None,
    week: int | None = None,
    slate: str | None = None,
    contest_format: str | None = None,
    objective: str | None = None,
    subject_label: str | None = None,
    subject_id: str | None = None,
    players: Iterable[Mapping[str, Any]] = (),
) -> tuple[list[dict[str, Any]], list[str]]:
    """Extract reviewable candidates; never activate or apply them."""
    statements, was_truncated = split_raw_thoughts(raw_text)
    notices = [
        "Extraction creates draft candidates only. Review each scope, posture, conviction, and confidence before accepting it."
    ]
    if was_truncated:
        notices.append(f"Only the first {MAX_CANDIDATES} candidates were extracted; the full raw capture remains preserved.")

    normalized_slate = _clean_text(slate)
    normalized_subject = _clean_text(subject_label)
    candidates: list[dict[str, Any]] = []
    player_rows = list(players)
    for ordinal, statement in enumerate(statements, start=1):
        matched = _matched_player(statement, player_rows) if context_type == "auto" else None
        if context_type == "player":
            scope_type = "player"
            candidate_subject = normalized_subject
            candidate_subject_id = _clean_text(subject_id)
            extraction_reason = f"Player context selected for {candidate_subject}."
        elif context_type == "general":
            scope_type = "global"
            candidate_subject = None
            candidate_subject_id = None
            extraction_reason = "General context selected; suggested as a durable playbook belief."
        elif matched:
            scope_type = "player"
            candidate_subject = _clean_text(matched.get("player_display_name"))
            candidate_subject_id = _clean_text(matched.get("player_id"))
            extraction_reason = f"Matched projected player {candidate_subject} in the raw text."
        else:
            scope_type = "weekly"
            candidate_subject = None
            candidate_subject_id = None
            extraction_reason = "Current-slate context selected or no projected player name was matched."

        direction, cue = _infer_direction(statement)
        strength, confidence = _infer_calibration(statement)
        if cue:
            extraction_reason = f"{extraction_reason} Posture cue: “{cue}”."
        else:
            extraction_reason = f"{extraction_reason} No posture cue was assumed."

        contextual = scope_type in {"season", "weekly", "game", "player"}
        weekly = scope_type in {"weekly", "game", "player"}
        contest_scoped = scope_type in {"contest_profile", "weekly", "game", "player"}
        candidates.append(
            {
                "ordinal": ordinal,
                "scope_type": scope_type,
                "subject_label": candidate_subject,
                "subject_id": candidate_subject_id,
                "season": season if contextual else None,
                "week": week if weekly else None,
                "slate": normalized_slate.upper() if weekly and normalized_slate else None,
                "contest_format": contest_format if contest_scoped else None,
                "objective": objective if contest_scoped else None,
                "direction": direction,
                "strength": strength,
                "confidence": confidence,
                "thought_text": statement,
                "extraction_reason": extraction_reason,
            }
        )
    return candidates, notices


def _candidate_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["reviewed_payload"] = result.pop("reviewed_payload_json", None) or {}
    result["status"] = result.get("decision") or "pending"
    return result


def _capture_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["notices"] = result.pop("notices_json", None) or []
    result.setdefault("candidates", [])
    return result


class ThoughtInboxService:
    """Persist verbatim notes, immutable extracted drafts, and explicit decisions."""

    def __init__(
        self,
        connection_string: str | None = None,
        engine: Engine | None = None,
        belief_service: BeliefService | None = None,
        predictions_service: PredictionsService | None = None,
    ) -> None:
        self.connection_string = connection_string or (
            str(engine.url) if engine is not None else get_connection_string()
        )
        self.engine = engine or create_engine(self.connection_string)
        self.belief_service = belief_service or BeliefService(connection_string=self.connection_string)
        self.predictions_service = predictions_service or PredictionsService(connection_string=self.connection_string)

    def _ensure_schema(self) -> None:
        validate_target_schema(
            self.engine,
            consumer=type(self).__name__,
            required_tables=(
                "human_belief",
                "raw_thought_capture",
                "raw_thought_candidate",
                "raw_thought_candidate_decision",
            ),
        )

    @staticmethod
    def _normalize_capture(payload: Mapping[str, Any]) -> dict[str, Any]:
        raw_text = _clean_text(payload.get("raw_text"))
        if not raw_text:
            raise ValueError("raw_text is required")
        if len(raw_text) > 20000:
            raise ValueError("raw_text cannot exceed 20,000 characters")

        context_type = str(payload.get("context_type") or "auto").strip().lower()
        if context_type not in THOUGHT_CONTEXTS:
            raise ValueError(f"context_type must be one of: {', '.join(sorted(THOUGHT_CONTEXTS))}")
        subject_label = _clean_text(payload.get("subject_label"))
        if context_type == "player" and not subject_label:
            raise ValueError("player context requires a subject_label")

        season = payload.get("season")
        week = payload.get("week")
        season = int(season) if season is not None else None
        week = int(week) if week is not None else None
        if context_type in {"slate", "player"} and (season is None or week is None):
            raise ValueError(f"{context_type} context requires season and week")
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

        slate = _clean_text(payload.get("slate"))
        return {
            "context_type": context_type,
            "raw_text": raw_text,
            "subject_label": subject_label,
            "subject_id": _clean_text(payload.get("subject_id")),
            "season": season,
            "week": week,
            "slate": slate.upper() if slate else None,
            "contest_format": contest_format,
            "objective": objective,
            "source": _clean_text(payload.get("source")) or "thought_inbox",
        }

    def capture(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        capture = self._normalize_capture(payload)
        player_rows: list[dict[str, Any]] = []
        source_notice: str | None = None
        if capture["context_type"] == "auto" and capture["season"] and capture["week"]:
            try:
                player_rows = self.predictions_service.fetch_predictions(
                    season=capture["season"],
                    week=capture["week"],
                    slate=capture["slate"],
                    limit=1000,
                )
            except Exception:  # noqa: BLE001 - raw capture must survive optional player matching
                source_notice = "Current projections were unavailable, so player names were not auto-matched."

        candidates, notices = extract_candidate_beliefs(
            capture["raw_text"],
            context_type=capture["context_type"],
            season=capture["season"],
            week=capture["week"],
            slate=capture["slate"],
            contest_format=capture["contest_format"],
            objective=capture["objective"],
            subject_label=capture["subject_label"],
            subject_id=capture["subject_id"],
            players=player_rows,
        )
        if source_notice:
            notices.append(source_notice)
        if not candidates:
            raise ValueError("No belief candidates could be extracted from raw_text")

        self._ensure_schema()
        capture_id = f"thought-capture-{uuid.uuid4()}"
        with self.engine.begin() as connection:
            capture_row = connection.execute(
                text(
                    """
                    INSERT INTO target.raw_thought_capture
                        (capture_id, context_type, raw_text, subject_label, subject_id, season,
                         week, slate, contest_format, objective, extraction_policy_id,
                         notices_json, source)
                    VALUES
                        (:capture_id, :context_type, :raw_text, :subject_label, :subject_id,
                         :season, :week, :slate, :contest_format, :objective,
                         :extraction_policy_id, CAST(:notices_json AS JSONB), :source)
                    RETURNING capture_id, context_type, raw_text, subject_label, subject_id,
                              season, week, slate, contest_format, objective,
                              extraction_policy_id, notices_json, source, created_at
                    """
                ),
                {
                    **capture,
                    "capture_id": capture_id,
                    "extraction_policy_id": EXTRACTION_POLICY_ID,
                    "notices_json": json.dumps(notices),
                },
            ).mappings().one()
            candidate_rows = []
            for candidate in candidates:
                candidate_id = f"thought-candidate-{uuid.uuid4()}"
                row = connection.execute(
                    text(
                        """
                        INSERT INTO target.raw_thought_candidate
                            (candidate_id, capture_id, ordinal, scope_type, subject_label,
                             subject_id, season, week, slate, contest_format, objective,
                             direction, strength, confidence, thought_text, extraction_reason)
                        VALUES
                            (:candidate_id, :capture_id, :ordinal, :scope_type, :subject_label,
                             :subject_id, :season, :week, :slate, :contest_format, :objective,
                             :direction, :strength, :confidence, :thought_text, :extraction_reason)
                        RETURNING candidate_id, capture_id, ordinal, scope_type, subject_label,
                                  subject_id, season, week, slate, contest_format, objective,
                                  direction, strength, confidence, thought_text,
                                  extraction_reason, created_at
                        """
                    ),
                    {**candidate, "candidate_id": candidate_id, "capture_id": capture_id},
                ).mappings().one()
                candidate_rows.append(_candidate_payload({**dict(row), "decision": None, "reviewed_payload_json": {}}))

        result = _capture_payload(capture_row)
        result["candidates"] = candidate_rows
        return result

    def _candidate_rows(self, capture_ids: list[str]) -> list[dict[str, Any]]:
        if not capture_ids:
            return []
        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT c.candidate_id, c.capture_id, c.ordinal, c.scope_type,
                           c.subject_label, c.subject_id, c.season, c.week, c.slate,
                           c.contest_format, c.objective, c.direction, c.strength,
                           c.confidence, c.thought_text, c.extraction_reason, c.created_at,
                           d.decision_id, d.decision, d.belief_id, d.belief_version_id,
                           d.reviewed_payload_json, d.created_at AS decided_at
                    FROM target.raw_thought_candidate c
                    LEFT JOIN target.raw_thought_candidate_decision d
                      ON d.candidate_id = c.candidate_id
                    WHERE c.capture_id = ANY(:capture_ids)
                    ORDER BY c.capture_id, c.ordinal
                    """
                ),
                {"capture_ids": capture_ids},
            ).mappings().all()
        return [_candidate_payload(row) for row in rows]

    def list(
        self,
        *,
        season: int | None = None,
        week: int | None = None,
        slate: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        self._ensure_schema()
        conditions: list[str] = []
        params: dict[str, Any] = {"limit": limit}
        if season is not None:
            conditions.append("(season IS NULL OR season = :season)")
            params["season"] = season
        if week is not None:
            conditions.append("(week IS NULL OR week = :week)")
            params["week"] = week
        if slate:
            conditions.append("(slate IS NULL OR UPPER(slate) = UPPER(:slate))")
            params["slate"] = slate
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    f"""
                    SELECT capture_id, context_type, raw_text, subject_label, subject_id,
                           season, week, slate, contest_format, objective,
                           extraction_policy_id, notices_json, source, created_at
                    FROM target.raw_thought_capture
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
        captures = [_capture_payload(row) for row in rows]
        candidates = self._candidate_rows([row["capture_id"] for row in captures])
        by_capture: dict[str, list[dict[str, Any]]] = {}
        for candidate in candidates:
            by_capture.setdefault(candidate["capture_id"], []).append(candidate)
        for capture in captures:
            capture["candidates"] = by_capture.get(capture["capture_id"], [])
        return captures

    def decide(
        self,
        candidate_id: str,
        decision: str,
        belief_payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if decision not in {"accepted", "rejected"}:
            raise ValueError("decision must be accepted or rejected")
        if decision == "accepted" and not belief_payload:
            raise ValueError("belief is required when accepting a candidate")

        self._ensure_schema()
        with self.engine.begin() as connection:
            candidate = connection.execute(
                text(
                    """
                    SELECT c.candidate_id, c.capture_id, c.ordinal, c.scope_type,
                           c.subject_label, c.subject_id, c.season, c.week, c.slate,
                           c.contest_format, c.objective, c.direction, c.strength,
                           c.confidence, c.thought_text, c.extraction_reason, c.created_at,
                           rc.extraction_policy_id,
                           d.decision_id, d.decision
                    FROM target.raw_thought_candidate c
                    JOIN target.raw_thought_capture rc ON rc.capture_id = c.capture_id
                    LEFT JOIN target.raw_thought_candidate_decision d
                      ON d.candidate_id = c.candidate_id
                    WHERE c.candidate_id = :candidate_id
                    FOR UPDATE OF c
                    """
                ),
                {"candidate_id": candidate_id},
            ).mappings().first()
            if not candidate:
                raise ValueError(f"Thought candidate not found: {candidate_id}")
            if candidate.get("decision_id"):
                raise ValueError("This thought candidate already has an immutable decision")

            reviewed_payload: dict[str, Any] = {}
            belief: dict[str, Any] | None = None
            if decision == "accepted":
                reviewed_payload = dict(belief_payload or {})
                metadata = dict(reviewed_payload.get("metadata") or {})
                metadata.update(
                    {
                        "raw_thought_capture_id": candidate["capture_id"],
                        "raw_thought_candidate_id": candidate_id,
                        "extraction_policy_id": candidate["extraction_policy_id"],
                        "impact_guardrail": "not_applied",
                    }
                )
                reviewed_payload["metadata"] = metadata
                reviewed_payload["source"] = "raw_thought_inbox"
                belief = self.belief_service.create_with_connection(connection, reviewed_payload)

            connection.execute(
                text(
                    """
                    INSERT INTO target.raw_thought_candidate_decision
                        (decision_id, candidate_id, decision, belief_id,
                         belief_version_id, reviewed_payload_json)
                    VALUES
                        (:decision_id, :candidate_id, :decision, :belief_id,
                         :belief_version_id, CAST(:reviewed_payload_json AS JSONB))
                    """
                ),
                {
                    "decision_id": f"thought-decision-{uuid.uuid4()}",
                    "candidate_id": candidate_id,
                    "decision": decision,
                    "belief_id": belief["belief_id"] if belief else None,
                    "belief_version_id": belief["belief_version_id"] if belief else None,
                    "reviewed_payload_json": json.dumps(reviewed_payload, default=str, sort_keys=True),
                },
            )

        rows = self._candidate_rows([str(candidate["capture_id"])])
        return next(row for row in rows if row["candidate_id"] == candidate_id)
