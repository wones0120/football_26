"""Pre-lock, immutable approval gate for full Classic skill-player exposure."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .market_snapshots import utc_time


SKILL_POSITIONS = frozenset({"RB", "WR", "TE"})


def required_skill_players(job: Any) -> list[dict]:
    if (job.contest_format != "classic" or job.strategy != "classic_small_field_gpp"
            or len(job.results or []) <= 1):
        return []
    lineups = job.results or []
    counts = Counter(str(player.get("player_id")) for lineup in lineups
                     for player in lineup if player.get("player_id"))
    by_id = {str(player.get("player_id")): player for lineup in lineups for player in lineup}
    return [{"player_id": pid, "player": by_id[pid].get("name") or by_id[pid].get("player_name") or pid,
             "position": str(by_id[pid].get("position") or "").upper(),
             "selected_count": count, "selected_total": len(lineups)}
            for pid, count in sorted(counts.items())
            if count == len(lineups) and str(by_id[pid].get("position") or "").upper() in SKILL_POSITIONS]


def saved_readiness(job: Any) -> dict:
    first = (job.results or [[]])[0]
    report = first[0].get("classic_small_field_report") if first else None
    return report if isinstance(report, dict) else {}


def first_kickoff(job: Any) -> datetime:
    value = (saved_readiness(job).get("prelock_timing") or {}).get("first_saved_kickoff_at")
    if not value:
        raise ValueError("Saved first-kickoff evidence is unavailable")
    return utc_time(value)


def approval_status(job: Any, engine: Engine) -> dict:
    required = required_skill_players(job)
    if not required:
        return {"required": [], "approved": [], "pending": []}
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT player_id, decision, reason, decided_at, requested_cap,
                   resulting_optimizer_run_id
            FROM target.skill_exposure_decision
            WHERE optimizer_run_id = :run_id
        """), {"run_id": job.job_id}).mappings().all()
    decisions = {str(row["player_id"]): dict(row) for row in rows}
    approved = [row for row in required if decisions.get(row["player_id"], {}).get("decision") == "approve"]
    pending = [row for row in required if row["player_id"] not in {item["player_id"] for item in approved}]
    return {"required": required, "approved": approved, "pending": pending,
            "decisions": list(decisions.values())}


def ensure_classic_export_ready(job: Any, engine: Engine) -> dict:
    if job.contest_format != "classic" or job.strategy != "classic_small_field_gpp":
        return {"required": [], "approved": [], "pending": []}
    readiness = saved_readiness(job).get("entry_readiness") or {}
    if readiness.get("status") not in {"ENTRY_READY", "ENTRY_READY_WITH_APPROVAL_REQUIRED"}:
        raise ValueError(f"Classic export blocked: entry readiness is {readiness.get('status') or 'unavailable'}")
    status = approval_status(job, engine)
    if status["pending"]:
        names = ", ".join(row["player"] for row in status["pending"])
        raise ValueError(f"100% skill-player exposure approval required before export: {names}")
    return status


def record_decision(job: Any, engine: Engine, *, player_id: str, decision: str,
                    reason: str, requested_cap: float | None = None,
                    resulting_run_id: str | None = None,
                    now: datetime | None = None) -> dict:
    now = utc_time(now or datetime.now(UTC))
    kickoff = first_kickoff(job)
    if now >= kickoff:
        raise ValueError("Skill exposure decisions must be saved before slate kickoff")
    if not reason.strip():
        raise ValueError("An approval or cap decision requires a saved reason")
    required = {row["player_id"]: row for row in required_skill_players(job)}
    if player_id not in required:
        raise ValueError("Player is not a 100% RB/WR/TE exposure case in this optimizer run")
    if decision == "approve":
        if requested_cap is not None or resulting_run_id is not None:
            raise ValueError("Approval keeps the original exposure and takes no cap")
    elif decision == "cap":
        if (requested_cap is None or not 0 <= requested_cap <= .80
                or resulting_run_id is None or resulting_run_id == job.job_id):
            raise ValueError("Cap requires a new optimizer run and cap between 0 and 80%")
    else:
        raise ValueError("Decision must be approve or cap")
    decision_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{job.job_id}/{player_id}"))
    with engine.begin() as connection:
        existing = connection.execute(text("""
            SELECT decision_id, decision, reason, requested_cap, resulting_optimizer_run_id
            FROM target.skill_exposure_decision
            WHERE optimizer_run_id = :run_id AND player_id = :player_id
        """), {"run_id": job.job_id, "player_id": player_id}).mappings().first()
        if existing:
            if (existing["decision"] != decision or existing["reason"] != reason.strip()
                    or existing["requested_cap"] != requested_cap
                    or existing["resulting_optimizer_run_id"] != resulting_run_id):
                raise ValueError("This run/player already has an immutable exposure decision")
            return dict(existing)
        connection.execute(text("""
            INSERT INTO target.skill_exposure_decision
                (decision_id, optimizer_run_id, player_id, selected_exposure,
                 decision, requested_cap, resulting_optimizer_run_id, reason,
                 decided_at, first_kickoff_at)
            VALUES (:decision_id, :run_id, :player_id, 1.0, :decision,
                    :cap, :resulting_run_id, :reason, :now, :kickoff)
        """), {"decision_id": decision_id, "run_id": job.job_id, "player_id": player_id,
               "decision": decision, "cap": requested_cap,
               "resulting_run_id": resulting_run_id, "reason": reason.strip(),
               "now": now, "kickoff": kickoff})
    return {"decision_id": decision_id, "optimizer_run_id": job.job_id,
            "player_id": player_id, "decision": decision, "reason": reason.strip(),
            "requested_cap": requested_cap, "resulting_optimizer_run_id": resulting_run_id,
            "decided_at": now.isoformat()}
