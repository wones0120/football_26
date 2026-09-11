"""Persisted Models-workbench pipeline summaries."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Iterable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import OperationalJob
from ..product_schemas import (
    ModelPipelineSummaryResponse,
    PipelineOperationResult,
    PipelineOperationSummary,
    ProjectionSelectionSummary,
)
from .job_queue import FEATURE_MATRIX_JOB, PROJECTION_JOB, SYMBOLIC_JOB


ACTIVE_STATUSES = frozenset({"queued", "running", "interrupted"})


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parsed_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _utc(value)
    if isinstance(value, str):
        try:
            return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _same_slate(left: Any, right: str) -> bool:
    return str(left or "").strip().upper() == right.strip().upper()


def _job_scope(job: OperationalJob) -> str:
    request = job.request_json or {}
    if (
        job.job_type == FEATURE_MATRIX_JOB
        and not request.get("weeks")
        and not request.get("slate")
    ):
        return "season"
    return "slate"


def _feature_slice(
    job: OperationalJob,
    *,
    season: int,
    week: int,
    slate: str,
) -> dict[str, Any] | None:
    sources = (job.result_json or {}, job.checkpoint_json or {})
    for source in sources:
        rows = source.get("rows") if isinstance(source, dict) else None
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            if (
                int(row.get("season") or 0) == season
                and int(row.get("week") or 0) == week
                and _same_slate(row.get("slate"), slate)
            ):
                return dict(row)
    return None


def _job_matches(
    job: OperationalJob,
    *,
    season: int,
    week: int,
    slate: str,
) -> bool:
    request = job.request_json or {}
    if int(request.get("season") or 0) != season:
        return False
    if job.job_type == FEATURE_MATRIX_JOB:
        weeks = request.get("weeks")
        if weeks and week not in [int(value) for value in weeks]:
            return False
        requested_slate = request.get("slate")
        if requested_slate and not _same_slate(requested_slate, slate):
            return False
        if job.status == "completed" and _job_scope(job) == "season":
            return _feature_slice(job, season=season, week=week, slate=slate) is not None
        return True
    return int(request.get("week") or 0) == week and _same_slate(request.get("slate"), slate)


def _job_status(job: OperationalJob, now: datetime) -> tuple[str, datetime | None, str | None]:
    if (
        job.status == "running"
        and job.lease_expires_at is not None
        and _utc(job.lease_expires_at) < now
    ):
        return (
            "interrupted",
            _utc(job.lease_expires_at),
            "The worker lease expired; this attempt is waiting for job recovery.",
        )
    if job.status == "queued":
        reached_at = job.updated_at if job.attempt_count else job.created_at
        message = job.progress_message
        if job.attempt_count == 0:
            message = "Waiting for an operational worker to claim this job."
        return "queued", _utc(reached_at), message
    if job.status == "running":
        reached_at = job.updated_at if job.attempt_count > 1 else job.started_at
        return "running", _utc(reached_at or job.updated_at), job.progress_message
    return job.status, _utc(job.completed_at or job.updated_at), job.progress_message


def _job_result(
    job: OperationalJob,
    *,
    season: int,
    week: int,
    slate: str,
    now: datetime,
) -> PipelineOperationResult:
    status, status_at, status_message = _job_status(job, now)
    result = job.result_json or {}
    slice_outcome = (
        _feature_slice(job, season=season, week=week, slate=slate)
        if job.job_type == FEATURE_MATRIX_JOB
        else None
    )
    rows_written: int | None = None
    if slice_outcome is not None:
        rows_written = int(slice_outcome.get("rows_written") or 0)
    elif result.get("rows_written") is not None:
        rows_written = int(result["rows_written"])
    elif result.get("adjusted_rows") is not None:
        rows_written = int(result["adjusted_rows"])
    total = max(1, int(job.progress_total or 1))
    progress = min(100.0, max(0.0, (int(job.progress_current or 0) / total) * 100.0))
    if status == "completed":
        progress = 100.0
    message = str(result.get("message") or status_message or "") or None
    return PipelineOperationResult(
        status=status,
        status_at=status_at,
        job_id=job.job_id,
        run_id=job.run_id,
        scope=_job_scope(job),
        stage=job.stage,
        progress_current=int(job.progress_current or 0),
        progress_total=total,
        progress_percent=progress,
        message=message,
        error_message=job.error_message,
        rows_written=rows_written,
        slice_outcome=slice_outcome,
        result=(
            dict(result)
            if job.job_type == PROJECTION_JOB
            else None
        ),
    )


def _timestamp_key(result: PipelineOperationResult) -> float:
    value = _utc(result.status_at)
    return value.timestamp() if value is not None else 0.0


def _newest(results: Iterable[PipelineOperationResult]) -> PipelineOperationResult | None:
    rows = list(results)
    return max(rows, key=_timestamp_key) if rows else None


def _query_rows(session: Session, statement: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    bind = session.get_bind()
    try:
        with bind.connect() as connection:
            return [dict(row) for row in connection.execute(text(statement), params).mappings()]
    except Exception:  # noqa: BLE001 - legacy/target artifacts are optional fallbacks
        return []


def _projection_artifacts(
    session: Session,
    *,
    season: int,
    week: int,
    slate: str,
) -> list[PipelineOperationResult]:
    rows = _query_rows(
        session,
        """
        SELECT projection_run_id, row_count, status, created_at
        FROM target.projection_run
        WHERE season = :season AND week = :week AND UPPER(slate_id) = UPPER(:slate)
          AND status = 'completed'
        ORDER BY created_at DESC
        LIMIT 100
        """,
        {"season": season, "week": week, "slate": slate},
    )
    return [
        PipelineOperationResult(
            status="completed",
            status_at=_utc(row.get("created_at")),
            run_id=str(row["projection_run_id"]),
            rows_written=int(row.get("row_count") or 0),
            progress_current=1,
            progress_total=1,
            progress_percent=100.0,
            message="Persisted projection run completed.",
        )
        for row in rows
    ]


def _symbolic_artifacts(
    session: Session,
    *,
    season: int,
    week: int,
    slate: str,
) -> list[PipelineOperationResult]:
    rows = _query_rows(
        session,
        """
        SELECT rule_run_id, projections_adjusted, created_at
        FROM symbolic_rule_runs
        WHERE season = :season AND week = :week AND UPPER(slate) = UPPER(:slate)
          AND status = 'completed'
        ORDER BY created_at DESC
        LIMIT 100
        """,
        {"season": season, "week": week, "slate": slate},
    )
    return [
        PipelineOperationResult(
            status="completed",
            status_at=_utc(row.get("created_at")),
            run_id=str(row["rule_run_id"]),
            rows_written=int(row.get("projections_adjusted") or 0),
            progress_current=1,
            progress_total=1,
            progress_percent=100.0,
            message="Persisted symbolic run completed.",
        )
        for row in rows
    ]


def _feature_artifacts(
    session: Session,
    *,
    season: int,
    week: int,
    slate: str,
) -> list[PipelineOperationResult]:
    rows = _query_rows(
        session,
        """
        SELECT quality_run_id, week, slate, source_context_json, created_at
        FROM target.data_quality_run
        WHERE trigger = 'feature_build' AND season = :season
          AND status = 'pass'
          AND (week = :week OR week IS NULL)
          AND (UPPER(slate) = UPPER(:slate) OR slate IS NULL)
        ORDER BY created_at DESC
        LIMIT 100
        """,
        {"season": season, "week": week, "slate": slate},
    )
    results: list[PipelineOperationResult] = []
    for row in rows:
        context = row.get("source_context_json") or {}
        if not isinstance(context, dict):
            context = {}
        requested_weeks = context.get("weeks")
        if requested_weeks and week not in [int(value) for value in requested_weeks]:
            continue
        requested_slate = context.get("slate")
        if requested_slate and not _same_slate(requested_slate, slate):
            continue
        results.append(
            PipelineOperationResult(
                status="completed",
                status_at=_utc(row.get("created_at")),
                run_id=str(row["quality_run_id"]),
                scope="season" if not requested_weeks and not requested_slate else "slate",
                progress_current=1,
                progress_total=1,
                progress_percent=100.0,
                message="Persisted feature-matrix build completed.",
            )
        )
    return results


def _operation_summary(
    operation: str,
    jobs: list[OperationalJob],
    artifacts: list[PipelineOperationResult],
    *,
    season: int,
    week: int,
    slate: str,
    now: datetime,
) -> PipelineOperationSummary:
    attempts = [
        _job_result(job, season=season, week=week, slate=slate, now=now)
        for job in jobs
    ]
    # A projection can be persisted by an operational worker or by an explicit
    # synchronous/admin workflow. Treat both as attempts and choose by the time
    # the stored state was actually reached.
    latest_attempt = _newest([*attempts, *artifacts])
    successful_jobs = [
        result
        for job, result in zip(jobs, attempts, strict=True)
        if job.status == "completed"
        and (
            job.job_type != FEATURE_MATRIX_JOB
            or _job_scope(job) == "slate"
            or result.slice_outcome is not None
        )
    ]
    successful_feature_slices = [
        result.model_copy(
            update={
                "status": "completed",
                "status_at": _parsed_datetime(result.slice_outcome.get("completed_at"))
                or result.status_at,
                "message": "The selected slate's feature-matrix slice completed.",
                "error_message": None,
                "progress_current": 1,
                "progress_total": 1,
                "progress_percent": 100.0,
            }
        )
        for result in attempts
        if operation == "features"
        and result.slice_outcome is not None
        and result.slice_outcome.get("status") == "ok"
    ]
    last_success = _newest(
        [*successful_jobs, *successful_feature_slices, *artifacts]
    )
    return PipelineOperationSummary(
        operation=operation,
        status=latest_attempt.status if latest_attempt else "not_run",
        status_at=latest_attempt.status_at if latest_attempt else None,
        latest_attempt=latest_attempt,
        last_success=last_success,
    )


def get_model_pipeline_summary(
    session: Session,
    *,
    season: int,
    week: int,
    slate: str,
    selected_projection_run_id: str | None = None,
) -> ModelPipelineSummaryResponse:
    now = datetime.now(UTC)
    job_types = (FEATURE_MATRIX_JOB, PROJECTION_JOB, SYMBOLIC_JOB)
    rows = list(
        session.scalars(
            select(OperationalJob)
            .where(OperationalJob.job_type.in_(job_types))
            .order_by(OperationalJob.updated_at.desc(), OperationalJob.created_at.desc())
            .limit(1000)
        )
    )
    matching = [
        job
        for job in rows
        if _job_matches(job, season=season, week=week, slate=slate)
    ]
    by_type = {
        job_type: [job for job in matching if job.job_type == job_type]
        for job_type in job_types
    }
    projection_artifacts = _projection_artifacts(
        session, season=season, week=week, slate=slate
    )
    features = _operation_summary(
        "features",
        by_type[FEATURE_MATRIX_JOB],
        _feature_artifacts(session, season=season, week=week, slate=slate),
        season=season,
        week=week,
        slate=slate,
        now=now,
    )
    projections = _operation_summary(
        "projections",
        by_type[PROJECTION_JOB],
        projection_artifacts,
        season=season,
        week=week,
        slate=slate,
        now=now,
    )
    symbolic = _operation_summary(
        "symbolic",
        by_type[SYMBOLIC_JOB],
        _symbolic_artifacts(session, season=season, week=week, slate=slate),
        season=season,
        week=week,
        slate=slate,
        now=now,
    )

    selected: ProjectionSelectionSummary | None = None
    if selected_projection_run_id:
        selected_result = next(
            (
                result
                for job in by_type[PROJECTION_JOB]
                if (
                    job.run_id == selected_projection_run_id
                    or (job.result_json or {}).get("projection_run_id")
                    == selected_projection_run_id
                )
                for result in [
                    _job_result(job, season=season, week=week, slate=slate, now=now)
                ]
            ),
            None,
        )
        if selected_result is None:
            selected_result = next(
                (
                    result
                    for result in projection_artifacts
                    if result.run_id == selected_projection_run_id
                ),
                None,
            )
        selected = ProjectionSelectionSummary(
            run_id=selected_projection_run_id,
            status=selected_result.status if selected_result else "not_run",
            status_at=selected_result.status_at if selected_result else None,
            rows_written=selected_result.rows_written if selected_result else None,
            is_latest_success=bool(
                projections.last_success
                and projections.last_success.run_id == selected_projection_run_id
            ),
        )

    return ModelPipelineSummaryResponse(
        season=season,
        week=week,
        slate=slate,
        generated_at=now,
        has_active_jobs=any(
            summary.status in ACTIVE_STATUSES
            for summary in (features, projections, symbolic)
        ),
        features=features,
        projections=projections,
        symbolic=symbolic,
        selected_projection=selected,
    )
