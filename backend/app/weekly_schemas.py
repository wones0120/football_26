"""Public contracts for durable weekly workflow orchestration."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .job_schemas import OperationalJobResponse


WeeklyRunStatus = Literal["queued", "running", "completed", "failed"]
WeeklyStageStatus = Literal["pending", "running", "completed", "failed"]


class WeeklyRunRequest(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def active_strategy_default(cls, values):
        values = dict(values)
        from .product_services.single_lineup import SINGLE_LINEUP_STRATEGIES, normalize_single_lineup_params
        if "strategy" not in values:
            showdown = values.get("contest_format") == "showdown"
            if values.get("objective") == "cash":
                values["strategy"] = "captain_single_lineup_v1" if showdown else "classic_single_lineup_v1"
            else:
                values["strategy"] = "showdown_gpp_portfolio_v3" if showdown else "classic_large_gpp_v1"
        if values["strategy"] in SINGLE_LINEUP_STRATEGIES:
            expected_format = SINGLE_LINEUP_STRATEGIES[values["strategy"]]
            values.setdefault("contest_format", expected_format)
            values.setdefault("objective", "cash")
            if values["contest_format"] != expected_format or values["objective"] != "cash":
                raise ValueError("Single-lineup strategy requires its matching format and cash objective")
            params = dict(values.get("optimizer_params") or {})
            if "allow_incomplete_evidence" in params:
                raise ValueError("Incomplete evidence override is restricted to internal/offline callers")
            normalize_single_lineup_params(params, contest_format=expected_format)
            values["optimizer_params"] = params
        else:
            # Preserve the former omitted objective for explicit legacy calls.
            values.setdefault("objective", "gpp")
        return values

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
    availability_overrides: list[dict[str, Any]] = Field(default_factory=list)
    allow_confirmed_inactive_override: bool = False
    assume_questionable_out: bool = False
    refresh_projections: bool = False
    contest_format: Literal["classic", "showdown"] = "classic"
    objective: Literal["cash", "gpp"] = "gpp"
    strategy: str = Field(default="classic_large_gpp_v1", min_length=1,
                         description="Omission selects the active format strategy; explicit historical IDs remain supported")
    num_simulations: int = Field(default=1000, ge=1, le=20000)
    seed: int = 502
    salary_cap: int = Field(default=50000, ge=1)
    ownership_run_id: str | None = None
    optimizer_params: dict[str, Any] = Field(
        default_factory=lambda: {"num_lineups": 5}
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
