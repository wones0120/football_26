"""Execution handlers for jobs claimed by the standalone worker."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import text

from Database.config import get_connection_string
from Database.features import build_player_features
from Database.manager import NFLDatabaseManager
from Database.scoring import build_weekly_scores

from ..db import SessionLocal
from ..models import UltimateLineupRun
from ..product_schemas import (
    PredictionRunRequest,
    PredictionRunResponse,
    SimulationRunRequest,
    SimulationRunResponse,
)
from ..product_services.predictions import PredictionsService
from ..product_services.simulations import SimulationService as SlateSimulationService
from ..schemas import (
    BenchmarkSuiteRunRequest,
    BenchmarkSuiteRunResponse,
    SimulateWeekRequest,
    SimulateWeekResponse,
)
from .benchmarks import (
    allocate_benchmark_run_directory,
    build_benchmark_run_response,
    run_benchmark_suite,
)
from .job_queue import (
    BENCHMARK_JOB,
    PROJECTION_JOB,
    RESEARCH_SIMULATION_JOB,
    SLATE_SIMULATION_JOB,
    ULTIMATE_LINEUP_JOB,
    WEEKLY_RUN_JOB,
    PermanentJobError,
)
from .weekly_orchestrator import WeeklyOrchestrator, WeeklyStageBlockedError
from ..weekly_schemas import WeeklyRunRequest
from .simulation import SimulationService as ResearchSimulationService
from .ultimate_lineup_runs import execute_ultimate_lineup_run


class ExecutionContext(Protocol):
    run_id: str | None
    checkpoint: dict[str, Any]

    def progress(
        self,
        stage: str,
        current: int,
        total: int,
        message: str,
        *,
        run_id: str | None = None,
        checkpoint: dict[str, Any] | None = None,
    ) -> None: ...


def _benchmark_handler(
    context: ExecutionContext,
    payload: dict[str, Any],
) -> dict[str, Any]:
    request = BenchmarkSuiteRunRequest.model_validate(payload)
    run_dir = (
        Path(context.run_id).expanduser().resolve()
        if context.run_id
        else allocate_benchmark_run_directory()
    )
    if (run_dir / "suite_manifest.json").is_file():
        existing = build_benchmark_run_response(run_dir)
        if existing.get("status") == "ok":
            context.progress(
                "benchmark_suite",
                1,
                1,
                "Recovered the already-completed benchmark artifacts.",
                run_id=str(run_dir),
            )
            return BenchmarkSuiteRunResponse(
                status="ok",
                run=existing,
            ).model_dump(mode="json")
    context.progress(
        "benchmark_suite",
        0,
        1,
        "Running classic, showdown, captain A/B, and analysis benchmarks.",
        run_id=str(run_dir),
    )
    result = BenchmarkSuiteRunResponse.model_validate(
        run_benchmark_suite(request, run_directory=run_dir)
    )
    if result.status != "ok":
        raise PermanentJobError(
            result.error_message or "Benchmark suite failed."
        )
    return result.model_dump(mode="json")


def _projection_handler(
    context: ExecutionContext,
    payload: dict[str, Any],
) -> dict[str, Any]:
    request = PredictionRunRequest.model_validate(payload)
    connection_string = get_connection_string()
    slate_for_prediction = request.slate
    prediction_service = PredictionsService(connection_string)
    if context.run_id:
        existing = prediction_service.fetch_completed_run_summary(context.run_id)
        if existing is not None:
            context.progress(
                "projection_model",
                4,
                4,
                "Recovered the already-persisted immutable projection run.",
            )
            return PredictionRunResponse(**existing).model_dump(mode="json")

    context.progress(
        "input_validation",
        0,
        4,
        "Checking salary coverage for the requested projection slice.",
    )
    if request.slate:
        db_manager = NFLDatabaseManager(connection_string)
        with db_manager.engine.connect() as connection:
            salary_count = connection.execute(
                text(
                    "SELECT COUNT(*) FROM curated_salaries "
                    "WHERE season = :season AND week = :week AND slate = :slate"
                ),
                {
                    "season": request.season,
                    "week": request.week,
                    "slate": request.slate,
                },
            ).scalar_one()
        if salary_count == 0:
            logging.warning(
                "No curated_salaries found for season=%s week=%s slate=%s; "
                "running projections without slate filter.",
                request.season,
                request.week,
                request.slate,
            )
            slate_for_prediction = None

    context.progress(
        "weekly_scoring",
        1,
        4,
        "Building time-safe weekly fantasy scores.",
    )
    scored_rows = build_weekly_scores(
        season=request.season,
        weeks=None,
        connection_string=connection_string,
    )
    if scored_rows == 0:
        raise PermanentJobError(
            f"No weekly stats found for season {request.season}. "
            "Load any completed week first."
        )

    context.progress(
        "feature_build",
        2,
        4,
        "Building point-in-time player features.",
    )
    feature_rows = build_player_features(
        season=request.season,
        weeks=None,
        connection_string=connection_string,
    )
    if feature_rows == 0:
        try:
            feature_rows = build_player_features(
                season=request.season,
                weeks=None,
                future_week=request.week,
                connection_string=connection_string,
            )
        except Exception:  # noqa: BLE001
            feature_rows = 0
    if feature_rows == 0:
        raise PermanentJobError(
            f"No predictive features available for season {request.season} "
            f"week {request.week}. Load stats and salaries, then retry."
        )

    checkpoint = dict(context.checkpoint)
    data_cutoff_at = request.data_cutoff_at
    if data_cutoff_at is None and checkpoint.get("data_cutoff_at"):
        data_cutoff_at = datetime.fromisoformat(str(checkpoint["data_cutoff_at"]))
    context.progress(
        "projection_model",
        3,
        4,
        "Training the projection model and persisting immutable outputs.",
    )
    try:
        result = prediction_service.train_and_predict(
            season=request.season,
            week=request.week,
            positions=request.positions,
            slate=slate_for_prediction,
            data_cutoff_at=data_cutoff_at,
            feature_run_id=checkpoint.get("feature_run_id"),
            model_run_id=checkpoint.get("model_run_id"),
            projection_run_id=context.run_id,
        )
    except ValueError as exc:
        raise PermanentJobError(str(exc)) from exc

    response = PredictionRunResponse(
        season=request.season,
        week=request.week,
        rows_written=len(result.records),
        message=(
            "Predictions generated"
            if result.records
            else "No predictions generated"
        ),
        feature_run_id=result.feature_run_id,
        model_run_id=result.model_run_id,
        projection_run_id=result.projection_run_id,
        data_cutoff_at=result.data_cutoff_at,
        target_persisted=result.target_persisted,
        calibration_metrics=result.calibration_metrics or {},
    )
    return response.model_dump(mode="json")


def _research_simulation_handler(
    context: ExecutionContext,
    payload: dict[str, Any],
) -> dict[str, Any]:
    request = SimulateWeekRequest.model_validate(payload)
    context.progress(
        "simulation",
        0,
        max(1, request.iterations),
        "Sampling historical player outcome distributions.",
    )
    with SessionLocal() as session:
        result = ResearchSimulationService(session).simulate_week(
            request,
            simulation_run_id=context.run_id,
        )
    response = SimulateWeekResponse.model_validate(result)
    if response.status == "failed":
        raise PermanentJobError(response.error_message or "Simulation failed.")
    return response.model_dump(mode="json")


def _slate_simulation_handler(
    context: ExecutionContext,
    payload: dict[str, Any],
) -> dict[str, Any]:
    request = SimulationRunRequest.model_validate(payload)
    context.progress(
        "simulation",
        0,
        max(1, request.num_simulations),
        "Solving deterministic optimal lineups across sampled outcomes.",
    )
    try:
        result = SlateSimulationService().run(
            **request.model_dump(),
            simulation_run_id=context.run_id,
        )
    except ValueError as exc:
        raise PermanentJobError(str(exc)) from exc
    return SimulationRunResponse(**result.__dict__).model_dump(mode="json")


def _ultimate_lineup_handler(
    context: ExecutionContext,
    _payload: dict[str, Any],
) -> dict[str, Any]:
    if not context.run_id:
        raise PermanentJobError("Ultimate-lineup queue item has no run ID.")
    context.progress(
        "ultimate_lineup",
        0,
        1,
        "Executing the persisted ultimate-lineup run.",
    )
    execute_ultimate_lineup_run(context.run_id)
    with SessionLocal() as session:
        run = session.get(UltimateLineupRun, context.run_id)
        if run is None:
            raise PermanentJobError("Ultimate-lineup run was not found.")
        if run.status == "failed":
            raise PermanentJobError(
                run.error_message or "Ultimate-lineup generation failed."
            )
        if run.status != "completed" or run.result_json is None:
            raise RuntimeError(
                f"Ultimate-lineup run ended in unexpected status {run.status}."
            )
        return dict(run.result_json)


def _weekly_run_handler(
    context: ExecutionContext,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if not context.run_id:
        raise PermanentJobError("Weekly queue item has no run ID.")
    request = WeeklyRunRequest.model_validate(payload)
    if request.data_cutoff_at is None and context.checkpoint.get("data_cutoff_at"):
        request = request.model_copy(
            update={
                "data_cutoff_at": datetime.fromisoformat(
                    str(context.checkpoint["data_cutoff_at"])
                )
            }
        )

    def progress(
        stage: str,
        current: int,
        total: int,
        message: str,
        checkpoint: dict[str, Any],
    ) -> None:
        context.progress(
            stage,
            current,
            total,
            message,
            checkpoint=checkpoint,
        )

    try:
        result = WeeklyOrchestrator(SessionLocal).run(
            context.run_id,
            request,
            progress=progress,
        )
    except WeeklyStageBlockedError as exc:
        raise PermanentJobError(str(exc)) from exc
    return result.model_dump(mode="json")


HANDLERS = {
    BENCHMARK_JOB: _benchmark_handler,
    PROJECTION_JOB: _projection_handler,
    RESEARCH_SIMULATION_JOB: _research_simulation_handler,
    SLATE_SIMULATION_JOB: _slate_simulation_handler,
    ULTIMATE_LINEUP_JOB: _ultimate_lineup_handler,
    WEEKLY_RUN_JOB: _weekly_run_handler,
}


def execute_job_handler(
    job_type: str,
    context: ExecutionContext,
    payload: dict[str, Any],
) -> dict[str, Any]:
    handler = HANDLERS.get(job_type)
    if handler is None:
        raise PermanentJobError(f"No worker handler for job type {job_type}.")
    return handler(context, payload)
