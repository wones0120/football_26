"""Append-only human/AI decisions, separated from production lineup tables."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import json
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .ai_showdown_packet import _date, digest
from .showdown_selection_review import POLICY, reject_outcomes, review_comparison
from .target_schema import validate_target_schema

DECISION_CONTRACT = "showdown_selection_decision_v1"
TABLES = ("showdown_selection_review", "showdown_selection_decision", "showdown_selection_outcome")


class Rejection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str
    reason: str = Field(min_length=1, max_length=4000)


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=128)
    previous_decision_id: str | None = None
    review_hash: str
    status: Literal["PROPOSED", "SELECTED", "USER_APPROVED"]
    proposed_candidate_ids: list[str] = Field(min_length=2, max_length=2)
    explicitly_considered_ids: list[str] = Field(default_factory=list, max_length=10000)
    other_displayed_candidate_ids: list[str] = Field(default_factory=list, max_length=10000)
    alternative_candidate_ids_considered: list[str] = Field(default_factory=list, max_length=10000)
    rejected_candidates: list[Rejection] = Field(default_factory=list, max_length=10000)
    reasoning: str = Field(min_length=1, max_length=12000)
    football_theses: list[str] = Field(min_length=2, max_length=2)
    complementarity_reason: str = Field(min_length=1, max_length=8000)
    accepted_high_overlap_exception: str | None = Field(default=None, max_length=4000)
    reviewer_type: Literal["HUMAN", "AI_ASSISTED", "AI"] = "HUMAN"
    reviewer_identity: str | None = Field(default=None, max_length=200)
    model_name: str | None = Field(default=None, max_length=200)


class EntryReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contest_id: str
    entry_id: str


class ExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=128)
    previous_decision_id: str
    learning_report_id: str
    entries: list[EntryReference] = Field(min_length=2, max_length=2)


def review_hash(review: dict) -> str:
    return digest(review)


def verify_record(record: dict) -> None:
    if digest({k: v for k, v in record.items() if k != "record_hash"}) != record.get("record_hash"):
        raise ValueError("Immutable decision record hash mismatch")


def make_decision(review: dict, request: DecisionRequest, *, now: datetime,
                  previous: dict | None = None) -> dict:
    """Pure contract validation; production passes a server-owned clock only."""
    reject_outcomes(review)
    if request.review_hash != review_hash(review):
        raise ValueError("Review hash mismatch; reopen this exact frozen run")
    identity = review["run_identity"]
    cutoff, created, kickoff = (_date(identity[k]) for k in ("evidence_cutoff", "created_at", "kickoff_at"))
    if (now.tzinfo is None or not all((cutoff, created, kickoff)) or not cutoff <= created <= now < kickoff
            or identity["timing_status"] != "prelock_saved_run"):
        raise ValueError("New selection decisions require a valid live prelock run and a server timestamp before kickoff")
    if (review["data_readiness"].get("status") != "READY" or review["data_readiness"].get("incomplete_evidence")
            or review["data_readiness"].get("non_production_override")
            or identity["frozen_source_hash_basis"] != "generation_snapshot"):
        raise ValueError("Live decisions require complete frozen generation evidence")
    if request.previous_decision_id != (previous["decision_id"] if previous else None):
        raise ValueError("Stale decision revision; reload the decision history")
    if previous:
        verify_record(previous)
        if previous["run_identity"]["optimizer_run_id"] != identity["optimizer_run_id"]:
            raise ValueError("Previous decision belongs to another frozen run")
        if previous["status"] == "ENTERED_CONFIRMED":
            raise ValueError("Confirmed execution cannot be revised into a prelock selection")
    ids = request.proposed_candidate_ids
    comparison = review_comparison(review, ids)
    eligible = {c["candidate_id"]: c for c in review["candidates"]}
    collections = [request.explicitly_considered_ids, request.other_displayed_candidate_ids,
                   request.alternative_candidate_ids_considered, [r.candidate_id for r in request.rejected_candidates]]
    for values in collections:
        if len(set(values)) != len(values) or not set(values) <= eligible.keys():
            raise ValueError("Attention/consideration/rejection IDs must be unique and belong to this eligible universe")
    considered = set(request.explicitly_considered_ids)
    if not set(ids + request.alternative_candidate_ids_considered + [r.candidate_id for r in request.rejected_candidates]) <= considered:
        raise ValueError("Proposed, alternative-considered and rejected candidates must be explicitly marked considered")
    if set(ids) & {r.candidate_id for r in request.rejected_candidates}:
        raise ValueError("A proposed candidate cannot also be rejected in the same revision")
    if any(not value.strip() for value in [request.reasoning, request.complementarity_reason, *request.football_theses,
                                          *(r.reason for r in request.rejected_candidates)]):
        raise ValueError("Written reasoning, two football theses and rejection reasons cannot be blank")
    if (request.status != "PROPOSED" and comparison["proposed_pair"]["shared_player_count"] >= 5
            and not (request.accepted_high_overlap_exception or "").strip()):
        raise ValueError("Record why the concentrated player core is deliberately accepted")
    if request.status == "USER_APPROVED" and (not previous or previous["status"] not in {"SELECTED", "USER_APPROVED"}
                                              or previous["proposed_candidate_ids"] != ids):
        raise ValueError("User approval requires an existing SELECTED revision with the same ordered pair")
    attention = review["attention_shortlist"]
    record = {"contract_id": DECISION_CONTRACT, "protocol": POLICY, "decision_id": str(uuid4()),
              "revision": previous["revision"] + 1 if previous else 1,
              "previous_decision_id": request.previous_decision_id, "decision_timestamp": now.isoformat(),
              "timestamp_basis": "server_clock", "selection_frozen_at": now.isoformat(),
              "run_identity": deepcopy(identity), "review_hash": request.review_hash,
              "status": request.status, "proposed_candidate_ids": ids,
              "attention": {"finalists_automatically_surfaced": attention["finalist_candidate_ids"],
                            "ceiling_outsiders_automatically_surfaced": attention["ceiling_outsider_candidate_ids"],
                            "other_displayed_candidate_ids": request.other_displayed_candidate_ids,
                            "explicitly_considered_ids": request.explicitly_considered_ids},
              "rosters": [{"candidate_id": cid, "captain_player_id": eligible[cid]["construction"]["captain_player_id"],
                           "physical_player_ids": sorted(p["player_id"] for p in eligible[cid]["players"]),
                           "players": [{k: p[k] for k in ("player_id", "name", "slot", "team", "position")} for p in eligible[cid]["players"]]}
                          for cid in ids],
              "alternative_candidate_ids_considered": request.alternative_candidate_ids_considered,
              "rejected_candidates": [r.model_dump() for r in request.rejected_candidates],
              "reasoning": request.reasoning.strip(), "football_theses": [t.strip() for t in request.football_theses],
              "complementarity_reason": request.complementarity_reason.strip(),
              "accepted_high_overlap_exception": request.accepted_high_overlap_exception,
              "reviewer": {"type": request.reviewer_type, "identity": request.reviewer_identity,
                           "model_name": request.model_name, "identity_basis": "self_reported"},
              "user_approval_status": "USER_APPROVED" if request.status == "USER_APPROVED" else "NOT_APPROVED",
              **comparison, "execution": None,
              "research_tracking": {**review["counts"], "explicitly_considered": len(considered),
                                    "attention_coverage_fraction": len(considered) / len(eligible),
                                    "outsider_selected": bool(set(ids) - set(attention["finalist_candidate_ids"])),
                                    "ceiling_outsider_selected": bool(set(ids) & set(attention["ceiling_outsider_candidate_ids"])),
                                    "chosen_pair": ids if request.status != "PROPOSED" else None}}
    record["record_hash"] = digest(record)
    return record


def make_execution(previous: dict, review: dict, request: ExecutionRequest, report: dict, *, now: datetime) -> dict:
    """Confirm evidence from the existing canonical contest-result/learning workflow."""
    from .optimizer_effectiveness import candidate_signature
    verify_record(previous)
    if previous["decision_id"] != request.previous_decision_id or previous["status"] not in {"USER_APPROVED", "ENTERED_CONFIRMED"}:
        raise ValueError("Entry confirmation must link the latest USER_APPROVED decision")
    identity = previous["run_identity"]
    if now.tzinfo is None or now < _date(identity["kickoff_at"]):
        raise ValueError("Imported contest-result confirmation is available after kickoff only")
    if (report.get("report_id") != request.learning_report_id or
            any(report.get(k) != identity[k] for k in ("season", "week", "slate"))):
        raise ValueError("Learning report belongs to another slate")
    by_key = {(str(e["contest_id"]), str(e["entry_id"])): e for e in report.get("entries", [])}
    refs = [(r.contest_id, r.entry_id) for r in request.entries]
    if len(set(refs)) != 2:
        raise ValueError("Two distinct actual entry references are required")
    by_signature = {candidate_signature(c, "showdown"): c["candidate_id"] for c in review["candidates"]}
    entries = []
    for key in refs:
        e = by_key.get(key)
        signature = candidate_signature(e or {}, "showdown")
        if not e or not e.get("identity_complete") or signature is None:
            raise ValueError("Actual entry is missing or has unresolved canonical roster identity")
        entries.append({"contest_id": key[0], "entry_id": key[1], "candidate_id": by_signature.get(signature),
                        "submitted_roster": [{"player_id": pid, "slot": "CPT" if cpt else "FLEX"} for pid, cpt in signature]})
    record = deepcopy(previous)
    record.pop("record_hash")
    record.update(decision_id=str(uuid4()), previous_decision_id=previous["decision_id"], revision=previous["revision"] + 1,
                  status="ENTERED_CONFIRMED", decision_timestamp=now.isoformat(),
                  execution={"learning_report_id": report["report_id"], "learning_evidence_hash": report["evidence_hash"],
                             "entry_user": report.get("entry_user"), "basis": "imported_canonical_contest_result",
                             "confirmed_at": now.isoformat(), "entries": entries,
                             "matches_approved_pair": sorted(e["candidate_id"] or "UNKNOWN" for e in entries) == sorted(previous["proposed_candidate_ids"])})
    record["record_hash"] = digest(record)
    return record


class SelectionDecisionStore:
    def __init__(self, engine: Engine):
        self.engine = engine

    def ensure_schema(self):
        validate_target_schema(self.engine, consumer="Showdown selection research", required_tables=("showdown_selection_review", "showdown_selection_decision", "showdown_selection_outcome"))

    def history(self, run_id: str) -> list[dict]:
        self.ensure_schema()
        with self.engine.connect() as c:
            rows = c.execute(text("SELECT record_json FROM target.showdown_selection_decision WHERE optimizer_run_id=:run ORDER BY revision"), {"run": run_id}).scalars().all()
        for row in rows:
            verify_record(row)
        return rows

    def _append(self, run_id, request, build, review=None):
        self.ensure_schema()
        request_hash = digest(request.model_dump())
        with self.engine.begin() as c:
            # One chain per optimizer run; retries are idempotent even after lock.
            c.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:run, 0))"), {"run": run_id})
            existing = c.execute(text("SELECT request_hash, record_json FROM target.showdown_selection_decision WHERE optimizer_run_id=:run AND idempotency_key=:key"), {"run": run_id, "key": request.idempotency_key}).mappings().first()
            if existing:
                if existing["request_hash"] != request_hash:
                    raise ValueError("Idempotency key was already used for a different decision")
                verify_record(existing["record_json"])
                return existing["record_json"]
            previous = c.execute(text("SELECT record_json FROM target.showdown_selection_decision WHERE optimizer_run_id=:run ORDER BY revision DESC LIMIT 1"), {"run": run_id}).scalar()
            if request.previous_decision_id != (previous["decision_id"] if previous else None):
                raise ValueError("Stale decision revision; reload the decision history")
            if review is None:
                if not previous:
                    raise ValueError("A prelock decision is required before execution confirmation")
                review = c.execute(text("SELECT review_json FROM target.showdown_selection_review WHERE review_hash=:hash"), {"hash": previous["review_hash"]}).scalar_one()
            if previous:
                verify_record(previous)
            if previous and previous["review_hash"] != review_hash(review):
                raise ValueError("Packet/review changed; the existing immutable run review cannot be replaced")
            now = c.execute(text("SELECT clock_timestamp()")).scalar_one()
            record = build(review, previous, now, c)
            if record["run_identity"]["optimizer_run_id"] != run_id:
                raise ValueError("Decision belongs to another optimizer run")
            c.execute(text("""INSERT INTO target.showdown_selection_review (review_hash, optimizer_run_id, review_json)
                VALUES (:hash, :run, CAST(:review AS JSONB)) ON CONFLICT (review_hash) DO NOTHING"""),
                      {"hash": review_hash(review), "run": run_id, "review": json.dumps(review)})
            c.execute(text("""INSERT INTO target.showdown_selection_decision
                (decision_id, optimizer_run_id, review_hash, revision, previous_decision_id, idempotency_key,
                 request_hash, status, decided_at, kickoff_at, record_json)
                VALUES (:id, :run, :review, :revision, :previous, :key, :request, :status, :now, :kickoff, CAST(:record AS JSONB))"""),
                      {"id": record["decision_id"], "run": run_id, "review": record["review_hash"], "revision": record["revision"],
                       "previous": record["previous_decision_id"], "key": request.idempotency_key, "request": request_hash,
                       "status": record["status"], "now": now, "kickoff": _date(record["run_identity"]["kickoff_at"]),
                       "record": json.dumps(record)})
        return record

    def append_decision(self, review: dict, request: DecisionRequest) -> dict:
        return self._append(review["run_identity"]["optimizer_run_id"], request,
                            lambda r, prev, now, c: make_decision(r, request, previous=prev, now=now), review=review)

    def append_execution(self, run_id: str, request: ExecutionRequest) -> dict:
        def build(review, previous, now, c):
            if (previous["status"] not in {"USER_APPROVED", "ENTERED_CONFIRMED"}
                    or now < _date(previous["run_identity"]["kickoff_at"])):
                raise ValueError("User approval and postkickoff time are required before reading imported entry outcomes")
            report = c.execute(text("SELECT report_json FROM target.slate_learning_report WHERE report_id=:id"), {"id": request.learning_report_id}).scalar()
            if not report:
                raise ValueError("Imported learning report not found")
            return make_execution(previous, review, request, report, now=now)
        return self._append(run_id, request, build)

    def frozen_review(self, hash_value: str) -> dict:
        with self.engine.connect() as c:
            review = c.execute(text("SELECT review_json FROM target.showdown_selection_review WHERE review_hash=:hash"), {"hash": hash_value}).scalar_one()
        if review_hash(review) != hash_value:
            raise ValueError("Frozen review hash mismatch")
        return review
