"""Persisted, resumable orchestration for one DFS weekly decision chain."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, Protocol
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..models import CuratedSalary, WeeklyRun, WeeklyRunStage
from ..product_schemas import PredictionRunRequest
from ..product_services.agent import NewsMatchupAgent
from ..product_services.batch_import import DraftKingsBatchImportService
from ..product_services.draftkings_export import DraftKingsExportService
from ..product_services.optimizer import OptimizerService
from ..product_services.portfolio import PortfolioService
from ..product_services.predictions import PredictionsService
from ..product_services.readiness import SlateReadinessService
from ..product_services.simulations import SimulationService
from ..schemas import InjuryIngestRequest, SalaryIngestRequest
from ..weekly_schemas import (
    WeeklyRunRequest,
    WeeklyRunResponse,
    WeeklyRunStageResponse,
)
from .ingest import IngestService
from .job_queue import PROJECTION_JOB


WEEKLY_STAGES = (
    "ingest",
    "readiness",
    "predict",
    "adjust",
    "simulate",
    "optimize",
    "validate",
    "export",
)


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _naive(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


@dataclass
class StageExecutionResult:
    message: str
    counts: dict[str, Any] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    artifact_ids: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None


class WeeklyStageBlockedError(RuntimeError):
    """A stage failed a deterministic precondition and needs operator action."""

    def __init__(self, outcome: StageExecutionResult) -> None:
        super().__init__(outcome.message)
        self.outcome = outcome


class WeeklyStageExecutor(Protocol):
    def execute(
        self,
        stage: str,
        *,
        request: WeeklyRunRequest,
        artifact_ids: dict[str, Any],
        completed_artifacts: dict[str, dict[str, Any]],
    ) -> StageExecutionResult: ...


class WeeklyProgress(Protocol):
    def __call__(
        self,
        stage: str,
        current: int,
        total: int,
        message: str,
        checkpoint: dict[str, Any],
    ) -> None: ...


def allocate_stage_artifacts(request: WeeklyRunRequest) -> dict[str, dict[str, Any]]:
    ingest: dict[str, Any] = {}
    if request.draftkings_directory:
        ingest["batch_id"] = str(uuid4())
    if request.salary_path:
        ingest["salary_ingest_run_id"] = str(uuid4())
    if request.injury_path:
        ingest["injury_ingest_run_id"] = str(uuid4())
    return {
        "ingest": ingest,
        "readiness": {},
        "predict": {
            "projection_run_id": request.projection_run_id or str(uuid4()),
            "feature_run_id": str(uuid4()),
            "model_run_id": str(uuid4()),
        },
        "adjust": {"rule_run_id": str(uuid4())},
        "simulate": {"simulation_run_id": str(uuid4())},
        "optimize": {"optimizer_run_id": str(uuid4())},
        "validate": {
            "portfolio_id": str(uuid4()),
            "validation_id": str(uuid4()),
        },
        "export": {"export_id": str(uuid4())},
    }


def create_weekly_run(
    session: Session,
    *,
    weekly_run_id: str,
    operational_job_id: str,
    request: WeeklyRunRequest,
    stage_artifacts: dict[str, dict[str, Any]] | None = None,
) -> WeeklyRun:
    existing = session.get(WeeklyRun, weekly_run_id)
    if existing is not None:
        return existing

    timestamp = _utcnow_naive()
    run = WeeklyRun(
        weekly_run_id=weekly_run_id,
        operational_job_id=operational_job_id,
        season=request.season,
        week=request.week,
        slate=request.slate.upper(),
        status="queued",
        current_stage="queued",
        data_cutoff_at=_naive(request.data_cutoff_at),
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(run)
    artifacts = stage_artifacts or allocate_stage_artifacts(request)
    for stage_order, stage in enumerate(WEEKLY_STAGES, start=1):
        session.add(
            WeeklyRunStage(
                weekly_run_id=weekly_run_id,
                stage=stage,
                stage_order=stage_order,
                status="pending",
                attempt_count=0,
                message="Waiting for the preceding stage.",
                counts_json={},
                logs_json=[],
                warnings_json=[],
                errors_json=[],
                artifact_ids_json=dict(artifacts.get(stage) or {}),
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
    session.commit()
    session.refresh(run)
    return run


def _stage_rows(session: Session, weekly_run_id: str) -> list[WeeklyRunStage]:
    return list(
        session.scalars(
            select(WeeklyRunStage)
            .where(WeeklyRunStage.weekly_run_id == weekly_run_id)
            .order_by(WeeklyRunStage.stage_order)
        )
    )


def get_weekly_run(session: Session, weekly_run_id: str) -> WeeklyRun | None:
    return session.get(WeeklyRun, weekly_run_id)


def list_weekly_runs(
    session: Session,
    *,
    season: int | None = None,
    week: int | None = None,
    slate: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[WeeklyRun]:
    query = select(WeeklyRun)
    if season is not None:
        query = query.where(WeeklyRun.season == season)
    if week is not None:
        query = query.where(WeeklyRun.week == week)
    if slate is not None:
        query = query.where(func.upper(WeeklyRun.slate) == slate.upper())
    if status is not None:
        query = query.where(WeeklyRun.status == status)
    return list(
        session.scalars(query.order_by(WeeklyRun.created_at.desc()).limit(limit))
    )


def weekly_run_response(session: Session, run: WeeklyRun) -> WeeklyRunResponse:
    stages = _stage_rows(session, run.weekly_run_id)
    completed = sum(stage.status == "completed" for stage in stages)
    total = len(stages) or len(WEEKLY_STAGES)
    artifact_ids = {
        stage.stage: dict(stage.artifact_ids_json or {})
        for stage in stages
        if stage.artifact_ids_json
    }
    warning_count = sum(len(stage.warnings_json or []) for stage in stages)
    error_count = sum(len(stage.errors_json or []) for stage in stages)
    return WeeklyRunResponse(
        weekly_run_id=run.weekly_run_id,
        operational_job_id=run.operational_job_id,
        season=run.season,
        week=run.week,
        slate=run.slate,
        status=run.status,
        current_stage=run.current_stage,
        progress_current=completed,
        progress_total=total,
        progress_percent=100.0 if run.status == "completed" else completed / total * 100.0,
        warning_count=warning_count,
        error_count=error_count,
        artifact_ids=artifact_ids,
        data_cutoff_at=run.data_cutoff_at,
        stages=[
            WeeklyRunStageResponse(
                stage=stage.stage,
                stage_order=stage.stage_order,
                status=stage.status,
                attempt_count=stage.attempt_count,
                message=stage.message,
                counts=dict(stage.counts_json or {}),
                logs=list(stage.logs_json or []),
                warnings=list(stage.warnings_json or []),
                errors=list(stage.errors_json or []),
                artifact_ids=dict(stage.artifact_ids_json or {}),
                result=dict(stage.result_json) if stage.result_json else None,
                created_at=stage.created_at,
                updated_at=stage.updated_at,
                started_at=stage.started_at,
                completed_at=stage.completed_at,
            )
            for stage in stages
        ],
        created_at=run.created_at,
        updated_at=run.updated_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


class _NestedJobContext:
    def __init__(
        self,
        *,
        run_id: str,
        checkpoint: dict[str, Any],
    ) -> None:
        self.run_id: str | None = run_id
        self.checkpoint = dict(checkpoint)
        self.logs: list[str] = []

    def progress(
        self,
        stage: str,
        current: int,
        total: int,
        message: str,
        *,
        run_id: str | None = None,
        checkpoint: dict[str, Any] | None = None,
    ) -> None:
        if run_id is not None:
            self.run_id = run_id
        if checkpoint is not None:
            self.checkpoint = dict(checkpoint)
        self.logs.append(f"{stage} ({current}/{total}): {message}")


class DefaultWeeklyStageExecutor:
    """Adapter that invokes the existing persisted services for every stage."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def execute(
        self,
        stage: str,
        *,
        request: WeeklyRunRequest,
        artifact_ids: dict[str, Any],
        completed_artifacts: dict[str, dict[str, Any]],
    ) -> StageExecutionResult:
        handler = getattr(self, f"_{stage}", None)
        if handler is None:
            raise RuntimeError(f"No weekly executor for stage {stage}.")
        return handler(request, artifact_ids, completed_artifacts)

    def _ingest(
        self,
        request: WeeklyRunRequest,
        artifact_ids: dict[str, Any],
        _completed: dict[str, dict[str, Any]],
    ) -> StageExecutionResult:
        logs: list[str] = []
        warnings: list[str] = []
        counts: dict[str, Any] = {}
        artifacts = dict(artifact_ids)

        if request.salary_path:
            with self.session_factory() as session:
                result = IngestService(session).ingest_salaries(
                    SalaryIngestRequest(
                        source_system=request.source_system,
                        season=request.season,
                        week=request.week,
                        slate=request.slate,
                        path=request.salary_path,
                    ),
                    ingest_run_id=str(artifact_ids["salary_ingest_run_id"]),
                )
            if result.status != "completed":
                raise WeeklyStageBlockedError(
                    StageExecutionResult(
                        message="Salary ingest failed.",
                        logs=logs,
                        errors=[result.error_message or "Salary ingest failed."],
                        artifact_ids=artifacts,
                    )
                )
            counts["salary_rows_raw"] = result.rows_raw
            counts["salary_rows_curated"] = result.rows_curated
            counts["salary_rows_unresolved"] = result.rows_unresolved
            logs.append(f"Salary ingest {result.ingest_run_id} completed.")
            if result.rows_unresolved:
                warnings.append(
                    f"Salary ingest left {result.rows_unresolved} unresolved player rows quarantined."
                )

        if request.injury_path:
            with self.session_factory() as session:
                result = IngestService(session).ingest_injuries(
                    InjuryIngestRequest(
                        source_system=request.source_system,
                        season=request.season,
                        week=request.week,
                        slate=request.slate,
                        path=request.injury_path,
                    ),
                    ingest_run_id=str(artifact_ids["injury_ingest_run_id"]),
                )
            if result.status != "completed":
                raise WeeklyStageBlockedError(
                    StageExecutionResult(
                        message="Injury ingest failed.",
                        logs=logs,
                        warnings=warnings,
                        errors=[result.error_message or "Injury ingest failed."],
                        artifact_ids=artifacts,
                    )
                )
            counts["injury_rows_raw"] = result.rows_raw
            counts["injury_rows_curated"] = result.rows_curated
            counts["injury_rows_unresolved"] = result.rows_unresolved
            logs.append(f"Injury ingest {result.ingest_run_id} completed.")
            if result.rows_unresolved:
                warnings.append(
                    f"Injury ingest left {result.rows_unresolved} unresolved player rows quarantined."
                )

        if request.draftkings_directory:
            if request.source_system != "draftkings":
                raise WeeklyStageBlockedError(
                    StageExecutionResult(
                        message="DraftKings directory import requires source_system=draftkings.",
                        logs=logs,
                        warnings=warnings,
                        errors=["DraftKings directory import cannot be used for FanDuel."],
                        artifact_ids=artifacts,
                    )
                )
            batch = DraftKingsBatchImportService().import_directory(
                request.draftkings_directory,
                season=request.season,
                week=request.week,
                slate=request.slate,
                recursive=request.recursive,
                dry_run=False,
                batch_id=str(artifact_ids["batch_id"]),
            )
            counts.update(
                {
                    "files_discovered": batch.discovered,
                    "files_imported": batch.imported,
                    "files_deduplicated": batch.deduplicated,
                    "files_skipped": batch.skipped,
                    "files_failed": batch.failed,
                }
            )
            artifacts["source_file_ids"] = sorted(
                {row.source_file_id for row in batch.files if row.source_file_id}
            )
            artifacts["template_ids"] = sorted(
                {row.template_id for row in batch.files if row.template_id}
            )
            artifacts["contest_ids"] = sorted(
                {row.contest_id for row in batch.files if row.contest_id}
            )
            logs.append(f"DraftKings batch {batch.batch_id} inspected {batch.discovered} files.")
            if batch.failed:
                failed = [row.message for row in batch.files if row.status == "failed"]
                raise WeeklyStageBlockedError(
                    StageExecutionResult(
                        message=f"DraftKings batch failed for {batch.failed} file(s).",
                        counts=counts,
                        logs=logs,
                        warnings=warnings,
                        errors=failed or ["One or more DraftKings files failed."],
                        artifact_ids=artifacts,
                    )
                )

        if not any(
            (request.salary_path, request.injury_path, request.draftkings_directory)
        ):
            with self.session_factory() as session:
                salary_rows = session.scalar(
                    select(func.count())
                    .select_from(CuratedSalary)
                    .where(
                        CuratedSalary.season == request.season,
                        CuratedSalary.week == request.week,
                        func.upper(CuratedSalary.slate) == request.slate.upper(),
                    )
                )
            counts["existing_salary_rows"] = int(salary_rows or 0)
            warnings.append(
                "No ingest files were supplied; the run is using the existing persisted slice."
            )
            logs.append("Inspected the existing salary slice without creating source writes.")

        return StageExecutionResult(
            message="Weekly inputs are persisted and inspectable.",
            counts=counts,
            logs=logs,
            warnings=warnings,
            artifact_ids=artifacts,
        )

    def _readiness(
        self,
        request: WeeklyRunRequest,
        artifact_ids: dict[str, Any],
        _completed: dict[str, dict[str, Any]],
    ) -> StageExecutionResult:
        report = SlateReadinessService().report(
            season=request.season,
            week=request.week,
            slate=request.slate,
        )
        gate = report["gates"]["prediction"]
        checks = {row["check_id"]: row for row in report["checks"]}
        warnings = [
            checks[check_id]["message"]
            for check_id in gate["attention_checks"]
            if checks[check_id]["status"] == "warn"
        ]
        errors = [
            checks[check_id]["message"]
            for check_id in gate["blocking_checks"]
        ]
        outcome = StageExecutionResult(
            message=f"Prediction readiness is {gate['status']} ({gate['score']}/100).",
            counts=dict(gate["summary"]),
            logs=[gate["message"]],
            warnings=warnings,
            errors=errors,
            artifact_ids={**artifact_ids, "readiness_report_id": report["report_id"]},
            result={
                "contract_id": report["contract_id"],
                "gate": "prediction",
                "status": gate["status"],
                "score": gate["score"],
                "blocking_checks": gate["blocking_checks"],
                "attention_checks": gate["attention_checks"],
            },
        )
        if errors:
            raise WeeklyStageBlockedError(outcome)
        return outcome

    def _predict(
        self,
        request: WeeklyRunRequest,
        artifact_ids: dict[str, Any],
        _completed: dict[str, dict[str, Any]],
    ) -> StageExecutionResult:
        from .job_handlers import execute_job_handler

        selected_projection_run_id = request.projection_run_id
        selection_source = "requested"
        if selected_projection_run_id is None:
            report = SlateReadinessService().report(
                season=request.season,
                week=request.week,
                slate=request.slate,
            )
            projection_check = next(
                (
                    row
                    for row in report["checks"]
                    if row["check_id"] == "projection_run_lineage"
                ),
                None,
            )
            if projection_check is not None:
                selected_projection_run_id = (
                    projection_check.get("details") or {}
                ).get("selected_projection_run_id")
                selection_source = "active"

        if selected_projection_run_id:
            recovered = PredictionsService().fetch_completed_run_summary(
                str(selected_projection_run_id)
            )
            if recovered is not None:
                if (
                    int(recovered["season"]) != request.season
                    or int(recovered["week"]) != request.week
                ):
                    raise WeeklyStageBlockedError(
                        StageExecutionResult(
                            message="Selected projection run belongs to a different week.",
                            errors=[
                                f"Projection run {selected_projection_run_id} belongs to "
                                f"{recovered['season']} W{recovered['week']}."
                            ],
                            artifact_ids=artifact_ids,
                        )
                    )
                if int(recovered.get("rows_written") or 0) <= 0:
                    raise WeeklyStageBlockedError(
                        StageExecutionResult(
                            message="Selected projection run has no persisted rows.",
                            errors=[
                                f"Projection run {selected_projection_run_id} is empty."
                            ],
                            artifact_ids=artifact_ids,
                        )
                    )
                return StageExecutionResult(
                    message=(
                        "Selected the requested immutable projection run."
                        if selection_source == "requested"
                        else "Reused the active immutable projection run."
                    ),
                    counts={"rows_written": int(recovered.get("rows_written") or 0)},
                    logs=[
                        f"Projection run {selected_projection_run_id} was already complete."
                    ],
                    artifact_ids={
                        **artifact_ids,
                        "planned_projection_run_id": artifact_ids["projection_run_id"],
                        "projection_run_id": str(selected_projection_run_id),
                        "feature_run_id": recovered.get("feature_run_id"),
                        "model_run_id": recovered.get("model_run_id"),
                    },
                    result={
                        "target_persisted": True,
                        "recovered": True,
                        "selection_source": selection_source,
                        "calibration_metrics": recovered.get("calibration_metrics") or {},
                    },
                )
            if selection_source == "requested":
                raise WeeklyStageBlockedError(
                    StageExecutionResult(
                        message="Requested projection run is not complete.",
                        errors=[
                            f"Projection run {selected_projection_run_id} was not found "
                            "as a completed immutable run."
                        ],
                        artifact_ids=artifact_ids,
                    )
                )

        nested = _NestedJobContext(
            run_id=str(artifact_ids["projection_run_id"]),
            checkpoint={
                "feature_run_id": artifact_ids["feature_run_id"],
                "model_run_id": artifact_ids["model_run_id"],
                "data_cutoff_at": request.data_cutoff_at.isoformat()
                if request.data_cutoff_at
                else None,
            },
        )
        payload = PredictionRunRequest(
            season=request.season,
            week=request.week,
            positions=request.positions,
            slate=request.slate,
            data_cutoff_at=request.data_cutoff_at,
        ).model_dump(mode="json")
        result = execute_job_handler(PROJECTION_JOB, nested, payload)
        outcome = StageExecutionResult(
            message=str(result.get("message") or "Projection build completed."),
            counts={"rows_written": int(result.get("rows_written") or 0)},
            logs=nested.logs,
            artifact_ids={
                **artifact_ids,
                "projection_run_id": result.get("projection_run_id")
                or artifact_ids["projection_run_id"],
                "feature_run_id": result.get("feature_run_id")
                or artifact_ids["feature_run_id"],
                "model_run_id": result.get("model_run_id")
                or artifact_ids["model_run_id"],
            },
            result={
                "target_persisted": bool(result.get("target_persisted")),
                "calibration_metrics": result.get("calibration_metrics") or {},
            },
        )
        if not result.get("target_persisted"):
            outcome.errors.append(
                "Projection outputs were not persisted to the target lineage tables."
            )
            raise WeeklyStageBlockedError(outcome)
        return outcome

    def _adjust(
        self,
        request: WeeklyRunRequest,
        artifact_ids: dict[str, Any],
        completed: dict[str, dict[str, Any]],
    ) -> StageExecutionResult:
        rule_run_id = str(artifact_ids["rule_run_id"])
        projection_run_id = str(completed["predict"]["projection_run_id"])
        service = NewsMatchupAgent()
        recovered = service.fetch_completed_run_summary(rule_run_id)
        if recovered is not None:
            return StageExecutionResult(
                message="Recovered the completed symbolic-adjustment run.",
                counts=recovered,
                logs=[f"Rule run {rule_run_id} was already complete."],
                artifact_ids=artifact_ids,
                result={"target_persisted": True, "recovered": True},
            )
        projections, adjustments, config, traces = service.run(
            request.season,
            request.week,
            slate=request.slate,
            projection_run_id=projection_run_id,
            rule_run_id=rule_run_id,
        )
        if projections.empty:
            raise WeeklyStageBlockedError(
                StageExecutionResult(
                    message="No projection rows were available for symbolic adjustment.",
                    errors=["The adjustment stage requires persisted projection rows."],
                    artifact_ids=artifact_ids,
                )
            )
        outcome = StageExecutionResult(
            message=f"Applied symbolic rules to {len(projections)} projections.",
            counts={
                "projections_seen": len(projections),
                "projections_adjusted": len(adjustments),
                "trace_rows": len(traces),
                "rules_loaded": config.rules_loaded,
            },
            logs=[f"Rule run {rule_run_id} completed."],
            warnings=list(service.load_warnings),
            artifact_ids=artifact_ids,
            result={"target_persisted": config.target_persisted},
        )
        if not config.target_persisted:
            outcome.errors.append(
                "Symbolic outputs were not persisted to the target lineage tables."
            )
            raise WeeklyStageBlockedError(outcome)
        return outcome

    def _simulate(
        self,
        request: WeeklyRunRequest,
        artifact_ids: dict[str, Any],
        completed: dict[str, dict[str, Any]],
    ) -> StageExecutionResult:
        if request.contest_format != "classic":
            raise WeeklyStageBlockedError(
                StageExecutionResult(
                    message="Showdown weekly simulation is not yet supported.",
                    errors=[
                        "The current persisted slate simulator supports classic contests only."
                    ],
                    artifact_ids=artifact_ids,
                )
            )
        result = SimulationService().run(
            season=request.season,
            week=request.week,
            slate=request.slate,
            contest_format=request.contest_format,
            num_simulations=request.num_simulations,
            seed=request.seed,
            salary_cap=request.salary_cap,
            projection_run_id=str(completed["predict"]["projection_run_id"]),
            ownership_run_id=request.ownership_run_id,
            simulation_run_id=str(artifact_ids["simulation_run_id"]),
        )
        return StageExecutionResult(
            message=result.message,
            counts={
                "requested_simulations": result.num_simulations,
                "successful_simulations": result.successful_simulations,
                "player_rows": len(result.rows),
            },
            logs=[f"Simulation run {result.simulation_run_id} completed with seed {result.seed}."],
            artifact_ids={
                **artifact_ids,
                "projection_run_id": result.projection_run_id,
                "ownership_run_id": result.ownership_run_id,
            },
            result={"simulation_model_id": result.simulation_model_id},
        )

    def _optimize(
        self,
        request: WeeklyRunRequest,
        artifact_ids: dict[str, Any],
        completed: dict[str, dict[str, Any]],
    ) -> StageExecutionResult:
        gate_key = f"{request.contest_format}_{request.objective}"
        report = SlateReadinessService().report(
            season=request.season,
            week=request.week,
            slate=request.slate,
        )
        gate = report["gates"][gate_key]
        checks = {row["check_id"]: row for row in report["checks"]}
        warnings = [
            checks[check_id]["message"]
            for check_id in gate["attention_checks"]
            if checks[check_id]["status"] == "warn"
        ]
        if gate["blocking_checks"]:
            errors = [checks[check_id]["message"] for check_id in gate["blocking_checks"]]
            raise WeeklyStageBlockedError(
                StageExecutionResult(
                    message=f"Optimizer readiness is blocked ({gate['score']}/100).",
                    counts=dict(gate["summary"]),
                    logs=[gate["message"]],
                    warnings=warnings,
                    errors=errors,
                    artifact_ids={
                        **artifact_ids,
                        "readiness_report_id": report["report_id"],
                    },
                )
            )
        service = OptimizerService()
        result = service.run_job(
            season=request.season,
            week=request.week,
            slate=request.slate,
            strategy=request.strategy,
            params=request.optimizer_params,
            contest_format=request.contest_format,
            objective=request.objective,
            projection_run_id=str(completed["predict"]["projection_run_id"]),
            rule_run_id=str(completed["adjust"]["rule_run_id"]),
            data_cutoff_at=request.data_cutoff_at,
            optimizer_run_id=str(artifact_ids["optimizer_run_id"]),
        )
        if result.status != "completed":
            raise WeeklyStageBlockedError(
                StageExecutionResult(
                    message=result.message or "Optimizer failed.",
                    counts={"lineups": 0},
                    logs=[gate["message"]],
                    warnings=warnings,
                    errors=[result.message or "Optimizer failed."],
                    artifact_ids=artifact_ids,
                )
            )
        if not result.lineage_persisted:
            raise WeeklyStageBlockedError(
                StageExecutionResult(
                    message="Optimizer lineage was not persisted.",
                    counts={"lineups": len(result.results or [])},
                    logs=[gate["message"]],
                    warnings=warnings,
                    errors=[
                        "The optimizer completed in memory but its durable run artifact is missing."
                    ],
                    artifact_ids={
                        **artifact_ids,
                        "readiness_report_id": report["report_id"],
                    },
                    result={"lineage_persisted": False},
                )
            )
        return StageExecutionResult(
            message=result.message or "Optimizer completed.",
            counts={"lineups": len(result.results or [])},
            logs=[
                gate["message"],
                f"Optimizer run {result.job_id} persisted={result.lineage_persisted}.",
            ],
            warnings=warnings,
            artifact_ids={
                **artifact_ids,
                "projection_run_id": result.projection_run_id,
                "rule_run_id": result.rule_run_id,
                "simulation_run_id": completed["simulate"]["simulation_run_id"],
                "readiness_report_id": report["report_id"],
            },
            result={"lineage_persisted": result.lineage_persisted},
        )

    def _validate(
        self,
        request: WeeklyRunRequest,
        artifact_ids: dict[str, Any],
        completed: dict[str, dict[str, Any]],
    ) -> StageExecutionResult:
        template_ids = list(completed.get("ingest", {}).get("template_ids") or [])
        template_id = request.template_id or (template_ids[0] if template_ids else None)
        if not template_id:
            raise WeeklyStageBlockedError(
                StageExecutionResult(
                    message="No DraftKings entry template is available.",
                    errors=[
                        "Set template_id or ingest a directory containing an entry template."
                    ],
                    artifact_ids=artifact_ids,
                )
            )
        portfolio = PortfolioService().create_portfolio(
            portfolio_name=request.portfolio_name
            or f"{request.season} W{request.week} {request.slate}",
            optimizer_run_id=str(completed["optimize"]["optimizer_run_id"]),
            template_id=template_id,
            default_contest_id=request.default_contest_id,
            portfolio_id=str(artifact_ids["portfolio_id"]),
        )
        validation = DraftKingsExportService().validate_portfolio(
            portfolio.portfolio_id,
            validation_id=str(artifact_ids["validation_id"]),
        )
        artifacts = {
            **artifact_ids,
            "portfolio_id": portfolio.portfolio_id,
            "validation_id": validation.validation_id,
            "template_id": template_id,
        }
        errors = [issue.message for issue in validation.errors]
        warnings = [issue.message for issue in validation.warnings]
        outcome = StageExecutionResult(
            message=(
                "Portfolio passed DraftKings export validation."
                if validation.status == "passed"
                else "Portfolio failed DraftKings export validation."
            ),
            counts={
                "lineups": portfolio.lineup_count,
                "assignments": portfolio.assignment_count,
                "checks_run": validation.checks_run,
                "errors": len(validation.errors),
                "warnings": len(validation.warnings),
            },
            logs=[f"Portfolio {portfolio.portfolio_id} assigned to template {template_id}."],
            warnings=warnings,
            errors=errors,
            artifact_ids=artifacts,
            result={"validation_status": validation.status},
        )
        if errors:
            raise WeeklyStageBlockedError(outcome)
        return outcome

    def _export(
        self,
        _request: WeeklyRunRequest,
        artifact_ids: dict[str, Any],
        completed: dict[str, dict[str, Any]],
    ) -> StageExecutionResult:
        validation_artifacts = completed["validate"]
        result = DraftKingsExportService().generate_export(
            str(validation_artifacts["portfolio_id"]),
            export_id=str(artifact_ids["export_id"]),
            validation_id=str(validation_artifacts["validation_id"]),
        )
        return StageExecutionResult(
            message=f"Generated {result.file_name}.",
            counts={"rows": result.row_count, "bytes": len(result.csv_content.encode("utf-8"))},
            logs=[f"DraftKings export SHA-256: {result.content_sha256}"],
            artifact_ids={
                **artifact_ids,
                "portfolio_id": result.portfolio_id,
                "validation_id": result.validation_id,
                "content_sha256": result.content_sha256,
            },
            result={"file_name": result.file_name},
        )


class WeeklyOrchestrator:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        executor: WeeklyStageExecutor | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.executor = executor or DefaultWeeklyStageExecutor(session_factory)

    def _mark_run_running(self, weekly_run_id: str) -> None:
        with self.session_factory() as session:
            run = session.get(WeeklyRun, weekly_run_id)
            if run is None:
                raise LookupError(f"Weekly run not found: {weekly_run_id}")
            timestamp = _utcnow_naive()
            run.status = "running"
            run.started_at = run.started_at or timestamp
            run.completed_at = None
            run.updated_at = timestamp
            session.commit()

    def _mark_stage_running(self, weekly_run_id: str, stage_name: str) -> WeeklyRunStage:
        with self.session_factory() as session:
            run = session.get(WeeklyRun, weekly_run_id)
            stage = session.get(WeeklyRunStage, (weekly_run_id, stage_name))
            if run is None or stage is None:
                raise LookupError(f"Weekly run stage not found: {weekly_run_id}/{stage_name}")
            timestamp = _utcnow_naive()
            prior_errors = list(stage.errors_json or [])
            logs = list(stage.logs_json or [])
            if prior_errors:
                logs.append(
                    f"Retrying after prior attempt: {'; '.join(str(value) for value in prior_errors)}"
                )
            stage.status = "running"
            stage.attempt_count += 1
            stage.message = f"Executing {stage_name} stage."
            stage.logs_json = logs
            stage.errors_json = []
            stage.started_at = timestamp
            stage.completed_at = None
            stage.updated_at = timestamp
            run.status = "running"
            run.current_stage = stage_name
            run.updated_at = timestamp
            session.commit()
            session.refresh(stage)
            return stage

    def _mark_stage_completed(
        self,
        weekly_run_id: str,
        stage_name: str,
        outcome: StageExecutionResult,
    ) -> None:
        with self.session_factory() as session:
            run = session.get(WeeklyRun, weekly_run_id)
            stage = session.get(WeeklyRunStage, (weekly_run_id, stage_name))
            if run is None or stage is None:
                raise LookupError(f"Weekly run stage not found: {weekly_run_id}/{stage_name}")
            timestamp = _utcnow_naive()
            stage.status = "completed"
            stage.message = outcome.message
            stage.counts_json = dict(outcome.counts)
            stage.logs_json = [*list(stage.logs_json or []), *outcome.logs]
            stage.warnings_json = list(outcome.warnings)
            stage.errors_json = []
            stage.artifact_ids_json = dict(outcome.artifact_ids)
            stage.result_json = dict(outcome.result) if outcome.result is not None else None
            stage.completed_at = timestamp
            stage.updated_at = timestamp
            run.current_stage = stage_name
            run.updated_at = timestamp
            session.commit()

    def _mark_stage_failed(
        self,
        weekly_run_id: str,
        stage_name: str,
        outcome: StageExecutionResult,
    ) -> None:
        with self.session_factory() as session:
            run = session.get(WeeklyRun, weekly_run_id)
            stage = session.get(WeeklyRunStage, (weekly_run_id, stage_name))
            if run is None or stage is None:
                raise LookupError(f"Weekly run stage not found: {weekly_run_id}/{stage_name}")
            timestamp = _utcnow_naive()
            stage.status = "failed"
            stage.message = outcome.message
            stage.counts_json = dict(outcome.counts)
            stage.logs_json = [*list(stage.logs_json or []), *outcome.logs]
            stage.warnings_json = list(outcome.warnings)
            stage.errors_json = list(outcome.errors) or [outcome.message]
            stage.artifact_ids_json = dict(outcome.artifact_ids)
            stage.result_json = dict(outcome.result) if outcome.result is not None else None
            stage.completed_at = timestamp
            stage.updated_at = timestamp
            run.status = "failed"
            run.current_stage = stage_name
            run.completed_at = timestamp
            run.updated_at = timestamp
            session.commit()

    def _mark_run_completed(self, weekly_run_id: str) -> WeeklyRunResponse:
        with self.session_factory() as session:
            run = session.get(WeeklyRun, weekly_run_id)
            if run is None:
                raise LookupError(f"Weekly run not found: {weekly_run_id}")
            timestamp = _utcnow_naive()
            run.status = "completed"
            run.current_stage = "completed"
            run.completed_at = timestamp
            run.updated_at = timestamp
            session.commit()
            session.refresh(run)
            return weekly_run_response(session, run)

    def run(
        self,
        weekly_run_id: str,
        request: WeeklyRunRequest,
        *,
        progress: WeeklyProgress | None = None,
    ) -> WeeklyRunResponse:
        self._mark_run_running(weekly_run_id)
        completed_artifacts: dict[str, dict[str, Any]] = {}

        for stage_index, stage_name in enumerate(WEEKLY_STAGES, start=1):
            with self.session_factory() as session:
                stage = session.get(WeeklyRunStage, (weekly_run_id, stage_name))
                if stage is None:
                    raise LookupError(
                        f"Weekly run stage not found: {weekly_run_id}/{stage_name}"
                    )
                stage_status = stage.status
                artifact_ids = dict(stage.artifact_ids_json or {})
            if stage_status == "completed":
                completed_artifacts[stage_name] = artifact_ids
                if progress:
                    progress(
                        stage_name,
                        stage_index,
                        len(WEEKLY_STAGES),
                        f"Skipped completed {stage_name} stage.",
                        {
                            "completed_stages": list(completed_artifacts),
                            "artifact_ids": completed_artifacts,
                        },
                    )
                continue

            stage = self._mark_stage_running(weekly_run_id, stage_name)
            if progress:
                progress(
                    stage_name,
                    stage_index - 1,
                    len(WEEKLY_STAGES),
                    f"Executing {stage_name} stage (attempt {stage.attempt_count}).",
                    {
                        "completed_stages": list(completed_artifacts),
                        "artifact_ids": completed_artifacts,
                    },
                )
            try:
                outcome = self.executor.execute(
                    stage_name,
                    request=request,
                    artifact_ids=artifact_ids,
                    completed_artifacts=completed_artifacts,
                )
            except WeeklyStageBlockedError as exc:
                self._mark_stage_failed(weekly_run_id, stage_name, exc.outcome)
                raise
            except Exception as exc:
                outcome = StageExecutionResult(
                    message=f"{stage_name.capitalize()} stage failed.",
                    logs=[f"Unhandled {type(exc).__name__} in {stage_name} stage."],
                    errors=[str(exc)],
                    artifact_ids=artifact_ids,
                )
                self._mark_stage_failed(weekly_run_id, stage_name, outcome)
                raise

            self._mark_stage_completed(weekly_run_id, stage_name, outcome)
            completed_artifacts[stage_name] = dict(outcome.artifact_ids)
            if progress:
                progress(
                    stage_name,
                    stage_index,
                    len(WEEKLY_STAGES),
                    outcome.message,
                    {
                        "completed_stages": list(completed_artifacts),
                        "artifact_ids": completed_artifacts,
                    },
                )

        return self._mark_run_completed(weekly_run_id)
