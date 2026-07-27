"""Inspection and retry API for the standalone operational worker queue."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db_session
from ..job_schemas import (
    OperationalJobListResponse,
    OperationalJobResponse,
)
from ..services.job_queue import (
    JobStateError,
    SUPPORTED_JOB_TYPES,
    get_job,
    job_response,
    list_jobs,
    retry_job,
)
from ..services.ultimate_lineup_runs import (
    get_ultimate_lineup_run,
    retry_ultimate_lineup_run,
)


router = APIRouter(prefix="/api/jobs", tags=["operational-jobs"])


@router.get("", response_model=OperationalJobListResponse)
def operational_jobs(
    status: str | None = Query(
        default=None,
        pattern="^(queued|running|completed|failed)$",
    ),
    job_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db_session),
) -> OperationalJobListResponse:
    if job_type is not None and job_type not in SUPPORTED_JOB_TYPES:
        raise HTTPException(status_code=422, detail="Unsupported operational job type")
    return OperationalJobListResponse(
        rows=[
            job_response(job)
            for job in list_jobs(
                session,
                status=status,
                job_type=job_type,
                limit=limit,
            )
        ]
    )


@router.get("/{job_id}", response_model=OperationalJobResponse)
def operational_job(
    job_id: str,
    session: Session = Depends(get_db_session),
) -> OperationalJobResponse:
    job = get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Operational job not found")
    return job_response(job)


@router.post(
    "/{job_id}/retry",
    response_model=OperationalJobResponse,
    status_code=202,
)
def retry_operational_job(
    job_id: str,
    session: Session = Depends(get_db_session),
) -> OperationalJobResponse:
    try:
        job = get_job(session, job_id)
        if job is None:
            raise LookupError("Operational job not found.")
        if job.job_type == "ultimate_lineup" and job.run_id:
            ultimate_run = get_ultimate_lineup_run(session, job.run_id)
            if ultimate_run is not None and ultimate_run.status == "failed":
                retry_ultimate_lineup_run(session, job.run_id)
        return job_response(retry_job(session, job_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except JobStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
