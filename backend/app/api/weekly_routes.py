"""Dispatch and inspection API for resumable weekly workflows."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db_session
from ..job_schemas import OperationalJobResponse
from ..services.job_queue import (
    WEEKLY_RUN_JOB,
    JobConflictError,
    JobStateError,
    enqueue_job,
    get_job,
    job_response,
    retry_job,
)
from ..services.weekly_orchestrator import (
    allocate_stage_artifacts,
    create_weekly_run,
    get_weekly_run,
    list_weekly_runs,
    weekly_run_response,
)
from ..weekly_schemas import (
    WeeklyRunCreateResponse,
    WeeklyRunListResponse,
    WeeklyRunRequest,
    WeeklyRunResponse,
)


router = APIRouter(prefix="/api/weekly-runs", tags=["weekly-runs"])


@router.post("", response_model=WeeklyRunCreateResponse, status_code=202)
def create_weekly_workflow(
    request: WeeklyRunRequest,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=1,
        max_length=255,
    ),
    session: Session = Depends(get_db_session),
) -> WeeklyRunCreateResponse:
    weekly_run_id = str(uuid4())
    artifacts = allocate_stage_artifacts(request)
    cutoff = request.data_cutoff_at or datetime.now(UTC)
    try:
        job, created = enqueue_job(
            session,
            job_type=WEEKLY_RUN_JOB,
            idempotency_key=idempotency_key or f"weekly-run:{uuid4()}",
            request_payload=request.model_dump(mode="json"),
            run_id=weekly_run_id,
            checkpoint={
                "data_cutoff_at": cutoff.isoformat(),
                "stage_artifacts": artifacts,
                "completed_stages": [],
                "artifact_ids": {},
            },
            commit=False,
        )
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not job.run_id:
        raise HTTPException(status_code=500, detail="Weekly job has no run ID")
    stored_checkpoint = dict(job.checkpoint_json or {})
    effective_request = request.model_copy(
        update={
            "data_cutoff_at": datetime.fromisoformat(
                str(stored_checkpoint.get("data_cutoff_at") or cutoff.isoformat())
            )
        }
    )
    run = get_weekly_run(session, job.run_id)
    if run is None:
        run = create_weekly_run(
            session,
            weekly_run_id=job.run_id,
            operational_job_id=job.job_id,
            request=effective_request,
            stage_artifacts=dict(stored_checkpoint.get("stage_artifacts") or artifacts),
        )
    return WeeklyRunCreateResponse(
        created=created,
        job=job_response(job),
        run=weekly_run_response(session, run),
    )


@router.get("", response_model=WeeklyRunListResponse)
def weekly_workflows(
    season: int | None = Query(default=None, ge=2000),
    week: int | None = Query(default=None, ge=1, le=25),
    slate: str | None = Query(default=None, min_length=1),
    status: str | None = Query(
        default=None,
        pattern="^(queued|running|completed|failed)$",
    ),
    limit: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_db_session),
) -> WeeklyRunListResponse:
    return WeeklyRunListResponse(
        rows=[
            weekly_run_response(session, run)
            for run in list_weekly_runs(
                session,
                season=season,
                week=week,
                slate=slate,
                status=status,
                limit=limit,
            )
        ]
    )


@router.get("/{weekly_run_id}", response_model=WeeklyRunResponse)
def weekly_workflow(
    weekly_run_id: str,
    session: Session = Depends(get_db_session),
) -> WeeklyRunResponse:
    run = get_weekly_run(session, weekly_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Weekly run not found")
    return weekly_run_response(session, run)


@router.post(
    "/{weekly_run_id}/retry",
    response_model=OperationalJobResponse,
    status_code=202,
)
def retry_weekly_workflow(
    weekly_run_id: str,
    session: Session = Depends(get_db_session),
) -> OperationalJobResponse:
    run = get_weekly_run(session, weekly_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Weekly run not found")
    job = get_job(session, run.operational_job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Operational job not found")
    try:
        return job_response(retry_job(session, job.job_id))
    except JobStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
