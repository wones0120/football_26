"""Execution handlers for jobs claimed by the standalone worker."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from fastapi.encoders import jsonable_encoder

from Database.config import get_connection_string

from ..db import SessionLocal
from ..models import UltimateLineupRun
from ..product_schemas import (
    AgentRunRequest,
    BuildFeatureMatrixRequest,
    BuildFeaturesResponse,
    PredictionRunRequest,
    OptimizerRunRequest,
    PredictionRunResponse,
    SimulationRunRequest,
    SimulationRunResponse,
)
from ..product_services.agent import NewsMatchupAgent
from ..product_services.data_quality import DataQualityService
from ..product_services.canonical_projection_inputs import StaleTrainingOutcomeError
from ..product_services.predictions import PredictionsService
from ..product_services.showdown_data_readiness import refresh_projection_player_context
from ..product_services.simulations import SimulationService as SlateSimulationService
from ..product_services.starters import StartingQBService
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
    FEATURE_MATRIX_JOB,
    PROJECTION_JOB,
    OPTIMIZER_JOB,
    RESEARCH_SIMULATION_JOB,
    SLATE_SIMULATION_JOB,
    SYMBOLIC_JOB,
    ULTIMATE_LINEUP_JOB,
    WEEKLY_RUN_JOB,
    PermanentJobError,
)
from .lineup_learning import LineupLearningService
from .simulation import SimulationService as ResearchSimulationService
from .ultimate_lineup_runs import execute_ultimate_lineup_run
from .weekly_orchestrator import WeeklyOrchestrator, WeeklyStageBlockedError
from ..weekly_schemas import WeeklyRunRequest


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


def _feature_matrix_handler(
    context: ExecutionContext,
    payload: dict[str, Any],
) -> dict[str, Any]:
    request = BuildFeatureMatrixRequest.model_validate(payload)
    completed_rows: list[dict[str, Any]] = []
    context.progress(
        "feature_matrix",
        0,
        1,
        "Discovering salary slates for the requested feature-matrix build.",
        checkpoint={"rows": []},
    )

    def record_slice(current: int, total: int, row: dict[str, Any]) -> None:
        persisted = dict(row)
        persisted["completed_at"] = datetime.now(UTC).isoformat()
        completed_rows.append(persisted)
        outcome = str(row.get("status") or "unknown")
        context.progress(
            "feature_matrix",
            current,
            total,
            (
                f"{row.get('season')} W{int(row.get('week') or 0):02d} "
                f"{row.get('slate')} {outcome}; "
                f"{int(row.get('rows_written') or 0)} rows written."
            ),
            checkpoint={"rows": completed_rows},
        )

    with SessionLocal() as session:
        summary = LineupLearningService(session).rebuild_player_game_feature_matrix(
            source_system=request.source_system,
            season_start=request.season,
            season_end=request.season,
            weeks=request.weeks,
            slate=request.slate,
            status_hook=record_slice,
        )
    summary["rows"] = completed_rows
    if not summary["slates_total"]:
        raise PermanentJobError(
            "No curated salaries found for the selected season, weeks, and slate. "
            "Load salaries first."
        )
    if summary["slates_failed"]:
        raise PermanentJobError(
            f"Feature build failed for {summary['slates_failed']} slate(s); "
            f"{summary['slates_completed']} completed. Review the stored per-slate outcomes."
        )

    rows = int(summary["rows_written"])
    message = (
        f"Built {rows} feature rows for season {request.season} across "
        f"{summary['slates_completed']} slate(s)."
    )
    try:
        DataQualityService().record_load(
            trigger="feature_build",
            season=request.season,
            week=(
                request.weeks[0]
                if request.weeks and len(request.weeks) == 1
                else None
            ),
            slate=request.slate,
            summaries=[
                {
                    "dataset": "player_game_feature_matrix",
                    "rows_written": rows,
                    "message": message,
                }
            ],
            source_context=request.model_dump(mode="json"),
        )
    except Exception:  # noqa: BLE001 - telemetry cannot rewrite a successful build
        logging.exception("Unable to persist data-quality history for feature_build")

    return BuildFeaturesResponse(
        season=request.season,
        weeks=request.weeks,
        rows_written=rows,
        message=message,
        source_system=request.source_system,
        slates_total=int(summary["slates_total"]),
        slates_completed=int(summary["slates_completed"]),
        slates_failed=int(summary["slates_failed"]),
        rows=completed_rows,
    ).model_dump(mode="json")


def _symbolic_handler(
    context: ExecutionContext,
    payload: dict[str, Any],
) -> dict[str, Any]:
    request = AgentRunRequest.model_validate(payload)
    service = NewsMatchupAgent()
    if context.run_id:
        existing = service.fetch_completed_run_summary(context.run_id)
        if existing is not None:
            context.progress(
                "symbolic_rules",
                1,
                1,
                "Recovered the already-persisted symbolic run.",
            )
            return {
                "season": request.season,
                "week": request.week,
                "rule_run_id": context.run_id,
                "projection_run_id": request.projection_run_id,
                "target_persisted": True,
                "adjusted_rows": existing["projections_adjusted"],
                "adjustments": [],
                "config": {"rules_loaded": existing["rules_loaded"]},
                "trace_rows": existing["trace_rows"],
                "traces": [],
            }

    context.progress(
        "symbolic_rules",
        0,
        1,
        "Loading persisted projections and evaluating symbolic rules.",
    )
    projections, adjustments, config, traces = service.run(
        request.season,
        request.week,
        slate=request.slate,
        projection_run_id=request.projection_run_id,
        rule_run_id=context.run_id,
    )
    if projections.empty:
        raise PermanentJobError(
            "No persisted projections were available for the selected season, week, slate, "
            "and projection run."
        )
    context.progress(
        "symbolic_rules",
        1,
        1,
        f"Persisted {len(traces)} symbolic trace rows.",
    )
    return {
        "season": request.season,
        "week": request.week,
        "rule_run_id": config.rule_run_id,
        "projection_run_id": config.projection_run_id,
        "target_persisted": config.target_persisted,
        "adjusted_rows": len(adjustments),
        "adjustments": [adjustment.__dict__ for adjustment in adjustments],
        "config": config.__dict__,
        "trace_rows": len(traces),
        "traces": [trace.__dict__ for trace in traces],
    }


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
        "Loading canonical salary and feature coverage for the requested projection slice.",
    )

    # The UI resolves starters before enqueueing, but API and weekly jobs can
    # reach this handler directly. Resolve live slates here as the final gate.
    # Historical cutoff runs must use their saved prelock evidence instead.
    checkpoint = dict(context.checkpoint)
    if request.slate and request.data_cutoff_at is None:
        context.progress(
            "starting_qb_resolution",
            1,
            4,
            "Resolving and persisting starting-QB evidence for this slate.",
        )
        try:
            player_refresh = refresh_projection_player_context(
                prediction_service, season=request.season, week=request.week,
                slate=request.slate, progress=context.progress,
            )
        except ValueError as exc:
            raise PermanentJobError(str(exc)) from exc
        if player_refresh is None:
            starter_result = StartingQBService(connection_string).derive_starters(
                season=request.season, week=request.week, slate=request.slate,
            )
            if starter_result.rows_written <= 0:
                raise PermanentJobError(starter_result.message)
            refresh_message = starter_result.message
        else:
            checkpoint["automatic_player_context_refresh"] = jsonable_encoder(player_refresh)
            refresh_message = "Refreshed Showdown roster, injury, starter and canonical player evidence."
        # Jobs freeze a cutoff when queued. Evidence recorded by this worker
        # would otherwise be invisible to the time-safe projection loader.
        checkpoint["data_cutoff_at"] = datetime.now(UTC).isoformat()
        context.progress(
            "starting_qb_resolution",
            1,
            4,
            refresh_message,
            checkpoint=checkpoint,
        )

    data_cutoff_at = request.data_cutoff_at
    if data_cutoff_at is None and checkpoint.get("data_cutoff_at"):
        data_cutoff_at = datetime.fromisoformat(str(checkpoint["data_cutoff_at"]))
    context.progress(
        "projection_model",
        3,
        4,
        "Training the projection model and persisting immutable outputs.",
    )
    def train(effective_cutoff: datetime | None):
        return prediction_service.train_and_predict(
            season=request.season,
            week=request.week,
            positions=request.positions,
            slate=request.slate,
            data_cutoff_at=effective_cutoff,
            feature_run_id=checkpoint.get("feature_run_id"),
            model_run_id=checkpoint.get("model_run_id"),
            projection_run_id=context.run_id,
            availability_overrides=[
                row.model_dump(mode="json") for row in request.availability_overrides
            ],
            allow_confirmed_inactive_override=request.allow_confirmed_inactive_override,
            assume_questionable_out=request.assume_questionable_out,
        )

    try:
        result = train(data_cutoff_at)
    except StaleTrainingOutcomeError as exc:
        if request.data_cutoff_at is not None:
            raise PermanentJobError(
                f"{exc} Automatic repair is disabled for an explicit historical cutoff."
            ) from exc
        grouped_weeks: dict[int, list[int]] = {}
        for stale_season, stale_week in exc.periods:
            grouped_weeks.setdefault(stale_season, []).append(stale_week)
        refreshed_rows = 0
        refreshed_slices = 0
        context.progress(
            "training_feature_refresh",
            1,
            4,
            "Refreshing completed prior-week feature labels from loaded weekly results.",
        )
        for stale_season, stale_weeks in sorted(grouped_weeks.items()):
            with SessionLocal() as session:
                summary = LineupLearningService(
                    session
                ).rebuild_player_game_feature_matrix(
                    source_system="draftkings",
                    season_start=stale_season,
                    season_end=stale_season,
                    weeks=sorted(set(stale_weeks)),
                )
            if not summary["slates_total"] or summary["slates_failed"]:
                raise PermanentJobError(
                    "Automatic training-feature refresh could not rebuild all stale "
                    f"slices for {stale_season} weeks {sorted(set(stale_weeks))}."
                ) from exc
            refreshed_rows += int(summary["rows_written"])
            refreshed_slices += int(summary["slates_completed"])
        data_cutoff_at = datetime.now(UTC)
        checkpoint = {
            **checkpoint,
            "data_cutoff_at": data_cutoff_at.isoformat(),
            "automatic_training_feature_refresh": {
                "periods": [
                    {"season": season, "week": week}
                    for season, week in exc.periods
                ],
                "slates_completed": refreshed_slices,
                "rows_written": refreshed_rows,
            },
        }
        context.progress(
            "projection_model",
            3,
            4,
            (
                f"Refreshed {refreshed_rows} training rows across "
                f"{refreshed_slices} slate(s); retrying projections."
            ),
            checkpoint=checkpoint,
        )
        try:
            result = train(data_cutoff_at)
        except ValueError as retry_exc:
            raise PermanentJobError(str(retry_exc)) from retry_exc
    except ValueError as exc:
        raise PermanentJobError(str(exc)) from exc

    coverage = (result.calibration_metrics or {}).get("input_coverage", {})
    warnings = []
    if coverage.get("excluded_positions"):
        warnings.append("excluded positions: " + ", ".join(coverage["excluded_positions"]))
    if coverage.get("unresolved_salary_source_keys"):
        warnings.append(f"{len(coverage['unresolved_salary_source_keys'])} unresolved salary entries excluded")
    if not result.records or not result.target_persisted:
        raise PermanentJobError("No persisted projections were produced for the selected slate.")
    response = PredictionRunResponse(
        season=request.season,
        week=request.week,
        rows_written=len(result.records),
        message="Predictions generated" + ("; " + "; ".join(warnings) if warnings else ""),
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


def _optimizer_handler(context: ExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
    from ..product_services.optimizer import OptimizerService
    from ..product_services.slate_preparation import validate_prepared_optimizer

    if not context.run_id:
        raise PermanentJobError("Optimizer queue item has no run ID.")
    context.progress("input_validation", 0, 1, "Verifying prepared source evidence before lineup generation.")
    with SessionLocal() as session:
        try:
            preparation = validate_prepared_optimizer(session, payload)
        except ValueError as exc:
            raise PermanentJobError(str(exc)) from exc
    if preparation:
        payload = {**payload, "params": {**payload.get("params", {}), "prepared_input_evidence": preparation}}
    request = OptimizerRunRequest.model_validate({**payload, "optimizer_run_id": context.run_id})
    context.progress("optimizer", 0, 1, "Preparing the optimizer request; live evidence must pass before generation.")
    try:
        job = OptimizerService().run_job(**request.model_dump(), progress=context.progress)
    except ValueError as exc:
        raise PermanentJobError(str(exc)) from exc
    if job.status != "completed" or not job.lineage_persisted:
        raise PermanentJobError(job.message or "Optimizer did not save a completed result.")
    context.progress("optimizer", 1, 1, "Optimizer results saved; ready to reopen.")
    # Keep queue polling lightweight; the full report lives in optimizer lineage.
    return {"optimizer_run_id": job.job_id, "status": job.status}


def _preparation_handler(context: ExecutionContext, payload: dict[str, Any]) -> dict[str, Any]:
    from ..product_services.slate_preparation import execute_preparation
    return execute_preparation(context, payload)


HANDLERS = {
    BENCHMARK_JOB: _benchmark_handler,
    FEATURE_MATRIX_JOB: _feature_matrix_handler,
    PROJECTION_JOB: _projection_handler,
    OPTIMIZER_JOB: _optimizer_handler,
    RESEARCH_SIMULATION_JOB: _research_simulation_handler,
    SLATE_SIMULATION_JOB: _slate_simulation_handler,
    SYMBOLIC_JOB: _symbolic_handler,
    ULTIMATE_LINEUP_JOB: _ultimate_lineup_handler,
    WEEKLY_RUN_JOB: _weekly_run_handler,
    "slate_preparation": _preparation_handler,
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
