"""Public contracts for durable weekly workflow orchestration."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .job_schemas import OperationalJobResponse


WeeklyRunStatus = Literal["queued", "running", "completed", "failed"]
WeeklyStageStatus = Literal["pending", "running", "completed", "failed"]


class WeeklyRunRequest(BaseModel):
    season: int = Field(..., ge=2000)
    week: int = Field(..., ge=1, le=25)
    slate: str = Field(..., min_length=1)
    source_system: Literal["draftkings", "fanduel"] = "draftkings"
    salary_path: str | None = None
    injury_path: str | None = None
    draftkings_directory: str | None = None
    recursive: bool = False
    data_cutoff_at: datetime | None = None
    positions: list[str] | None = None
    projection_run_id: str | None = None
    contest_format: Literal["classic", "showdown"] = "classic"
    objective: Literal["cash", "gpp"] = "gpp"
    strategy: str = Field(default="gpp", min_length=1)
    num_simulations: int = Field(default=1000, ge=1, le=20000)
    seed: int = 502
    salary_cap: int = Field(default=50000, ge=1)
    ownership_run_id: str | None = None
    optimizer_params: dict[str, Any] = Field(
        default_factory=lambda: {"num_lineups": 1}
    )
    template_id: str | None = None
    portfolio_name: str | None = None
    default_contest_id: str | None = None


class WeeklyRunStageResponse(BaseModel):
    stage: str
    stage_order: int
    status: WeeklyStageStatus
    attempt_count: int
    message: str | None = None
    counts: dict[str, Any] = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    artifact_ids: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class WeeklyRunResponse(BaseModel):
    weekly_run_id: str
    operational_job_id: str
    season: int
    week: int
    slate: str
    status: WeeklyRunStatus
    current_stage: str
    progress_current: int
    progress_total: int
    progress_percent: float
    warning_count: int
    error_count: int
    artifact_ids: dict[str, Any] = Field(default_factory=dict)
    data_cutoff_at: datetime | None = None
    stages: list[WeeklyRunStageResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class WeeklyRunCreateResponse(BaseModel):
    created: bool
    job: OperationalJobResponse
    run: WeeklyRunResponse


class WeeklyRunListResponse(BaseModel):
    rows: list[WeeklyRunResponse] = Field(default_factory=list)
