"""Public contracts for the durable operational worker queue."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


OperationalJobStatus = Literal["queued", "running", "completed", "failed"]


class OperationalJobResponse(BaseModel):
    job_id: str
    job_type: str
    idempotency_key: str
    status: OperationalJobStatus
    stage: str
    progress_current: int
    progress_total: int
    progress_percent: float
    progress_message: str | None = None
    run_id: str | None = None
    attempt_count: int
    max_attempts: int
    error_message: str | None = None
    result: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class OperationalJobCreateResponse(BaseModel):
    created: bool
    job: OperationalJobResponse


class OperationalJobListResponse(BaseModel):
    rows: list[OperationalJobResponse] = Field(default_factory=list)
