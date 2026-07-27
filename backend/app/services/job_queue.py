"""Database-backed queue primitives shared by the API and worker process."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..job_schemas import OperationalJobResponse
from ..models import OperationalJob


BENCHMARK_JOB = "benchmark_suite"
PROJECTION_JOB = "projection_build"
RESEARCH_SIMULATION_JOB = "research_simulation"
SLATE_SIMULATION_JOB = "slate_simulation"
ULTIMATE_LINEUP_JOB = "ultimate_lineup"
WEEKLY_RUN_JOB = "weekly_run"
SUPPORTED_JOB_TYPES = frozenset(
    {
        BENCHMARK_JOB,
        PROJECTION_JOB,
        RESEARCH_SIMULATION_JOB,
        SLATE_SIMULATION_JOB,
        ULTIMATE_LINEUP_JOB,
        WEEKLY_RUN_JOB,
    }
)


class JobConflictError(ValueError):
    pass


class JobStateError(ValueError):
    pass


class PermanentJobError(RuntimeError):
    """An execution failure that cannot become valid through worker retry."""


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _request_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _assert_same_request(job: OperationalJob, request_hash: str) -> None:
    if job.request_hash != request_hash:
        raise JobConflictError(
            "Idempotency key is already associated with a different "
            f"{job.job_type} request."
        )


def enqueue_job(
    session: Session,
    *,
    job_type: str,
    idempotency_key: str,
    request_payload: dict[str, Any],
    run_id: str | None = None,
    checkpoint: dict[str, Any] | None = None,
    max_attempts: int = 3,
    commit: bool = True,
) -> tuple[OperationalJob, bool]:
    if job_type not in SUPPORTED_JOB_TYPES:
        raise ValueError(f"Unsupported operational job type: {job_type}")
    normalized_key = idempotency_key.strip()
    if not normalized_key:
        raise ValueError("idempotency_key must not be blank")
    if len(normalized_key) > 255:
        raise ValueError("idempotency_key must be at most 255 characters")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    request_hash = _request_hash(request_payload)
    existing = session.scalar(
        select(OperationalJob).where(
            OperationalJob.job_type == job_type,
            OperationalJob.idempotency_key == normalized_key,
        )
    )
    if existing is not None:
        _assert_same_request(existing, request_hash)
        return existing, False

    timestamp = _utcnow_naive()
    job = OperationalJob(
        job_id=str(uuid4()),
        job_type=job_type,
        idempotency_key=normalized_key,
        request_hash=request_hash,
        request_json=request_payload,
        status="queued",
        stage="queued",
        progress_current=0,
        progress_total=1,
        progress_message="Waiting for an operational worker.",
        run_id=run_id,
        checkpoint_json=checkpoint,
        attempt_count=0,
        max_attempts=max_attempts,
        available_at=timestamp,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(job)
    try:
        if commit:
            session.commit()
        else:
            session.flush()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(OperationalJob).where(
                OperationalJob.job_type == job_type,
                OperationalJob.idempotency_key == normalized_key,
            )
        )
        if existing is None:
            raise
        _assert_same_request(existing, request_hash)
        return existing, False
    session.refresh(job)
    return job, True


def get_job(session: Session, job_id: str) -> OperationalJob | None:
    return session.get(OperationalJob, job_id)


def list_jobs(
    session: Session,
    *,
    status: str | None = None,
    job_type: str | None = None,
    limit: int = 50,
) -> list[OperationalJob]:
    query = select(OperationalJob)
    if status is not None:
        query = query.where(OperationalJob.status == status)
    if job_type is not None:
        query = query.where(OperationalJob.job_type == job_type)
    return list(
        session.scalars(
            query.order_by(OperationalJob.created_at.desc()).limit(limit)
        )
    )


def job_response(job: OperationalJob) -> OperationalJobResponse:
    total = max(1, int(job.progress_total))
    percent = min(
        100.0,
        max(0.0, (float(job.progress_current) / total) * 100.0),
    )
    if job.status == "completed":
        percent = 100.0
    return OperationalJobResponse(
        job_id=job.job_id,
        job_type=job.job_type,
        idempotency_key=job.idempotency_key,
        status=job.status,
        stage=job.stage,
        progress_current=job.progress_current,
        progress_total=total,
        progress_percent=percent,
        progress_message=job.progress_message,
        run_id=job.run_id,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        error_message=job.error_message,
        result=job.result_json,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


def _eligible_jobs(timestamp: datetime):
    return or_(
        and_(
            OperationalJob.status == "queued",
            OperationalJob.available_at <= timestamp,
            OperationalJob.attempt_count < OperationalJob.max_attempts,
        ),
        and_(
            OperationalJob.status == "running",
            OperationalJob.lease_expires_at.is_not(None),
            OperationalJob.lease_expires_at < timestamp,
            OperationalJob.attempt_count < OperationalJob.max_attempts,
        ),
    )


def claim_next_job(
    session: Session,
    *,
    worker_id: str,
    lease_seconds: int = 300,
) -> OperationalJob | None:
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be at least 1")
    timestamp = _utcnow_naive()
    session.execute(
        update(OperationalJob)
        .where(
            OperationalJob.status == "running",
            OperationalJob.lease_expires_at.is_not(None),
            OperationalJob.lease_expires_at < timestamp,
            OperationalJob.attempt_count >= OperationalJob.max_attempts,
        )
        .values(
            status="failed",
            stage="failed",
            progress_message="Worker lease expired after the final allowed attempt.",
            error_message="Worker lease expired before the job reached a terminal state.",
            locked_by=None,
            lease_expires_at=None,
            completed_at=timestamp,
            updated_at=timestamp,
        )
    )
    session.commit()
    query = (
        select(OperationalJob)
        .where(_eligible_jobs(timestamp))
        .order_by(OperationalJob.available_at, OperationalJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = session.scalar(query)
    if job is None:
        return None

    job.status = "running"
    job.stage = "starting"
    job.progress_message = "Claimed by operational worker."
    job.attempt_count += 1
    job.locked_by = worker_id
    job.lease_expires_at = timestamp + timedelta(seconds=lease_seconds)
    job.started_at = job.started_at or timestamp
    job.completed_at = None
    job.updated_at = timestamp
    session.commit()
    session.refresh(job)
    return job


def heartbeat_job(
    session: Session,
    *,
    job_id: str,
    worker_id: str,
    lease_seconds: int,
) -> bool:
    timestamp = _utcnow_naive()
    result = session.execute(
        update(OperationalJob)
        .where(
            OperationalJob.job_id == job_id,
            OperationalJob.status == "running",
            OperationalJob.locked_by == worker_id,
        )
        .values(
            lease_expires_at=timestamp + timedelta(seconds=lease_seconds),
            updated_at=timestamp,
        )
    )
    session.commit()
    return result.rowcount == 1


def update_job_progress(
    session: Session,
    *,
    job_id: str,
    worker_id: str,
    stage: str,
    current: int,
    total: int,
    message: str,
    lease_seconds: int = 300,
    run_id: str | None = None,
    checkpoint: dict[str, Any] | None = None,
) -> bool:
    timestamp = _utcnow_naive()
    values: dict[str, Any] = {
        "stage": stage,
        "progress_current": max(0, int(current)),
        "progress_total": max(1, int(total)),
        "progress_message": message,
        "lease_expires_at": timestamp + timedelta(seconds=lease_seconds),
        "updated_at": timestamp,
    }
    if run_id is not None:
        values["run_id"] = run_id
    if checkpoint is not None:
        values["checkpoint_json"] = checkpoint
    result = session.execute(
        update(OperationalJob)
        .where(
            OperationalJob.job_id == job_id,
            OperationalJob.status == "running",
            OperationalJob.locked_by == worker_id,
        )
        .values(**values)
    )
    session.commit()
    return result.rowcount == 1


def complete_job(
    session: Session,
    *,
    job_id: str,
    worker_id: str,
    result_payload: dict[str, Any],
    run_id: str | None = None,
) -> bool:
    timestamp = _utcnow_naive()
    values: dict[str, Any] = {
        "status": "completed",
        "stage": "completed",
        "progress_current": 1,
        "progress_total": 1,
        "progress_message": "Operational job completed.",
        "result_json": result_payload,
        "error_message": None,
        "locked_by": None,
        "lease_expires_at": None,
        "completed_at": timestamp,
        "updated_at": timestamp,
    }
    if run_id is not None:
        values["run_id"] = run_id
    result = session.execute(
        update(OperationalJob)
        .where(
            OperationalJob.job_id == job_id,
            OperationalJob.status == "running",
            OperationalJob.locked_by == worker_id,
        )
        .values(**values)
    )
    session.commit()
    return result.rowcount == 1


def fail_job(
    session: Session,
    *,
    job_id: str,
    worker_id: str,
    error_message: str,
    permanent: bool = False,
    retry_delay_seconds: int = 5,
) -> bool:
    job = session.get(OperationalJob, job_id)
    if (
        job is None
        or job.status != "running"
        or job.locked_by != worker_id
    ):
        return False

    timestamp = _utcnow_naive()
    should_retry = not permanent and job.attempt_count < job.max_attempts
    job.status = "queued" if should_retry else "failed"
    job.stage = "retry_wait" if should_retry else "failed"
    job.progress_message = (
        "Worker attempt failed; waiting to retry."
        if should_retry
        else "Operational job failed."
    )
    job.error_message = error_message[:8000]
    job.available_at = timestamp + timedelta(seconds=max(0, retry_delay_seconds))
    job.locked_by = None
    job.lease_expires_at = None
    job.completed_at = None if should_retry else timestamp
    job.updated_at = timestamp
    session.commit()
    return True


def retry_job(session: Session, job_id: str) -> OperationalJob:
    job = session.get(OperationalJob, job_id)
    if job is None:
        raise LookupError("Operational job not found.")
    if job.status != "failed":
        raise JobStateError("Only failed operational jobs can be retried.")

    timestamp = _utcnow_naive()
    job.status = "queued"
    job.stage = "queued"
    job.progress_current = 0
    job.progress_total = 1
    job.progress_message = "Manual retry queued; saved run/checkpoint data will be reused."
    job.result_json = None
    job.error_message = None
    job.available_at = timestamp
    job.locked_by = None
    job.lease_expires_at = None
    job.completed_at = None
    job.max_attempts = max(job.max_attempts, job.attempt_count + 1)
    job.updated_at = timestamp
    session.commit()
    session.refresh(job)
    return job
