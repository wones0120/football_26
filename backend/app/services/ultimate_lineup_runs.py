from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import UltimateLineupRun
from ..schemas import (
    UltimateLineupRequest,
    UltimateLineupResponse,
    UltimateLineupRunResponse,
)
from .candidate_checkpoint import CandidateCheckpointStore
from .lineup_learning import LineupLearningService


SessionFactory = Callable[[], Session]


class UltimateLineupRunConflictError(ValueError):
    pass


class UltimateLineupRunStateError(ValueError):
    pass


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _request_payload(request: UltimateLineupRequest) -> dict:
    return request.model_dump(mode="json")


def _request_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _assert_idempotent_request(
    run: UltimateLineupRun,
    *,
    request_hash: str,
) -> None:
    if run.request_hash != request_hash:
        raise UltimateLineupRunConflictError(
            "Idempotency key is already associated with a different "
            "ultimate-lineup request."
        )


def create_ultimate_lineup_run(
    session: Session,
    *,
    idempotency_key: str,
    request: UltimateLineupRequest,
) -> tuple[UltimateLineupRun, bool]:
    payload = _request_payload(request)
    request_hash = _request_hash(payload)
    existing = session.scalar(
        select(UltimateLineupRun).where(
            UltimateLineupRun.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        _assert_idempotent_request(existing, request_hash=request_hash)
        return existing, False

    timestamp = _utcnow_naive()
    run = UltimateLineupRun(
        ultimate_lineup_run_id=str(uuid4()),
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        source_system=request.source_system,
        season=request.season,
        week=request.week,
        slate=request.slate,
        request_json=payload,
        status="queued",
        stage="queued",
        progress_current=0,
        progress_total=1,
        progress_message="Waiting for an ultimate-lineup worker.",
        attempt_count=0,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(run)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(
            select(UltimateLineupRun).where(
                UltimateLineupRun.idempotency_key == idempotency_key
            )
        )
        if existing is None:
            raise
        _assert_idempotent_request(existing, request_hash=request_hash)
        return existing, False
    session.refresh(run)
    return run, True


def get_ultimate_lineup_run(
    session: Session,
    ultimate_lineup_run_id: str,
) -> UltimateLineupRun | None:
    return session.get(UltimateLineupRun, ultimate_lineup_run_id)


def retry_ultimate_lineup_run(
    session: Session,
    ultimate_lineup_run_id: str,
) -> UltimateLineupRun:
    run = session.get(UltimateLineupRun, ultimate_lineup_run_id)
    if run is None:
        raise LookupError("Ultimate-lineup run not found.")
    if run.status != "failed":
        raise UltimateLineupRunStateError(
            "Only failed ultimate-lineup runs can be retried."
        )

    timestamp = _utcnow_naive()
    run.status = "queued"
    run.stage = "queued"
    run.progress_current = 0
    run.progress_total = 1
    run.progress_message = "Retry queued; saved candidate progress will be reused when compatible."
    run.result_json = None
    run.error_message = None
    run.started_at = None
    run.completed_at = None
    run.updated_at = timestamp
    session.commit()
    session.refresh(run)
    return run


def ultimate_lineup_run_response(
    run: UltimateLineupRun,
) -> UltimateLineupRunResponse:
    progress_total = max(1, int(run.progress_total))
    progress_percent = min(
        100.0,
        max(0.0, (float(run.progress_current) / progress_total) * 100.0),
    )
    if run.status == "completed":
        progress_percent = 100.0
    result = (
        UltimateLineupResponse.model_validate(run.result_json)
        if run.result_json is not None
        else None
    )
    return UltimateLineupRunResponse(
        ultimate_lineup_run_id=run.ultimate_lineup_run_id,
        idempotency_key=run.idempotency_key,
        source_system=run.source_system,
        season=run.season,
        week=run.week,
        slate=run.slate,
        status=run.status,
        stage=run.stage,
        progress_current=run.progress_current,
        progress_total=progress_total,
        progress_percent=progress_percent,
        progress_message=run.progress_message,
        checkpoint_path=run.checkpoint_path,
        attempt_count=run.attempt_count,
        error_message=run.error_message,
        created_at=run.created_at,
        updated_at=run.updated_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        result=result,
    )


def _default_checkpoint_path(ultimate_lineup_run_id: str) -> str:
    return str(
        Path(
            "artifacts",
            "checkpoints",
            "ultimate-runs",
            f"{ultimate_lineup_run_id}.sqlite3",
        ).resolve()
    )


def _checkpoint_can_resume(checkpoint_path: str) -> bool:
    path = Path(checkpoint_path)
    if not path.exists():
        return False
    try:
        return CandidateCheckpointStore(path).load() is not None
    except (OSError, ValueError):
        return False


def _update_progress(
    session_factory: SessionFactory,
    *,
    ultimate_lineup_run_id: str,
    stage: str,
    current: int,
    total: int,
    message: str,
) -> None:
    timestamp = _utcnow_naive()
    with session_factory() as session:
        session.execute(
            update(UltimateLineupRun)
            .where(
                UltimateLineupRun.ultimate_lineup_run_id
                == ultimate_lineup_run_id,
                UltimateLineupRun.status == "running",
            )
            .values(
                stage=stage,
                progress_current=max(0, int(current)),
                progress_total=max(1, int(total)),
                progress_message=message,
                updated_at=timestamp,
            )
        )
        session.commit()


def execute_ultimate_lineup_run(
    ultimate_lineup_run_id: str,
    *,
    session_factory: SessionFactory = SessionLocal,
) -> None:
    with session_factory() as session:
        queued_run = session.get(UltimateLineupRun, ultimate_lineup_run_id)
        if queued_run is None or queued_run.status != "queued":
            return
        request = UltimateLineupRequest.model_validate(queued_run.request_json)
        checkpoint_path = str(
            Path(
                request.checkpoint_path
                or _default_checkpoint_path(ultimate_lineup_run_id)
            )
            .expanduser()
            .resolve()
        )
        timestamp = _utcnow_naive()
        claim = session.execute(
            update(UltimateLineupRun)
            .where(
                UltimateLineupRun.ultimate_lineup_run_id
                == ultimate_lineup_run_id,
                UltimateLineupRun.status == "queued",
            )
            .values(
                status="running",
                stage="training",
                progress_current=0,
                progress_total=max(1, request.training_window_slates),
                progress_message="Building the historical training pool.",
                checkpoint_path=checkpoint_path,
                attempt_count=UltimateLineupRun.attempt_count + 1,
                error_message=None,
                started_at=timestamp,
                completed_at=None,
                updated_at=timestamp,
            )
        )
        session.commit()
        if claim.rowcount != 1:
            return
        claimed_run = session.get(UltimateLineupRun, ultimate_lineup_run_id)
        if claimed_run is None:
            return
        resume_from_checkpoint = bool(request.resume_from_checkpoint)
        if claimed_run.attempt_count > 1 and _checkpoint_can_resume(
            checkpoint_path
        ):
            resume_from_checkpoint = True
        effective_request = request.model_copy(
            update={
                "checkpoint_path": checkpoint_path,
                "resume_from_checkpoint": resume_from_checkpoint,
            }
        )

    def progress_hook(
        stage: str,
        current: int,
        total: int,
        message: str,
    ) -> None:
        try:
            _update_progress(
                session_factory,
                ultimate_lineup_run_id=ultimate_lineup_run_id,
                stage=stage,
                current=current,
                total=total,
                message=message,
            )
        except Exception:  # noqa: BLE001
            # A transient telemetry write must not discard deterministic model
            # work; terminal persistence below still records success/failure.
            return

    try:
        with session_factory() as work_session:
            result = LineupLearningService(
                work_session
            ).build_ultimate_lineups(
                effective_request,
                progress_hook=progress_hook,
            )
        timestamp = _utcnow_naive()
        with session_factory() as session:
            session.execute(
                update(UltimateLineupRun)
                .where(
                    UltimateLineupRun.ultimate_lineup_run_id
                    == ultimate_lineup_run_id,
                    UltimateLineupRun.status == "running",
                )
                .values(
                    status="completed",
                    stage="completed",
                    progress_current=1,
                    progress_total=1,
                    progress_message="Ultimate-lineup portfolio comparison completed.",
                    result_json=result.model_dump(mode="json"),
                    error_message=None,
                    completed_at=timestamp,
                    updated_at=timestamp,
                )
            )
            session.commit()
    except Exception as exc:  # noqa: BLE001
        timestamp = _utcnow_naive()
        with session_factory() as session:
            session.execute(
                update(UltimateLineupRun)
                .where(
                    UltimateLineupRun.ultimate_lineup_run_id
                    == ultimate_lineup_run_id,
                    UltimateLineupRun.status == "running",
                )
                .values(
                    status="failed",
                    stage="failed",
                    progress_message="Ultimate-lineup generation failed.",
                    result_json=None,
                    error_message=str(exc)[:8000],
                    completed_at=timestamp,
                    updated_at=timestamp,
                )
            )
            session.commit()
