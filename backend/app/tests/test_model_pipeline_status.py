from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import Base
from backend.app.product_schemas import PipelineOperationResult
from backend.app.services.job_queue import (
    FEATURE_MATRIX_JOB,
    PROJECTION_JOB,
    SYMBOLIC_JOB,
    enqueue_job,
)
from backend.app.services.model_pipeline_status import (
    _operation_summary,
    get_model_pipeline_summary,
)


def _factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'pipeline.sqlite3'}")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def _time(minutes: int) -> datetime:
    return datetime(2026, 9, 6, 18, 0, tzinfo=UTC) + timedelta(minutes=minutes)


def test_pipeline_summary_restores_jobs_and_scopes_season_build_outcomes(
    tmp_path: Path,
) -> None:
    factory = _factory(tmp_path)
    with factory() as session:
        feature, _ = enqueue_job(
            session,
            job_type=FEATURE_MATRIX_JOB,
            idempotency_key="features-2026",
            request_payload={
                "season": 2026,
                "weeks": None,
                "slate": None,
                "source_system": "draftkings",
            },
            run_id="feature-season-1",
        )
        feature.status = "completed"
        feature.progress_current = 2
        feature.progress_total = 2
        feature.result_json = {
            "rows_written": 60,
            "message": "Built the season matrix.",
            "rows": [
                {
                    "season": 2026,
                    "week": 1,
                    "slate": "WEDNESDAY_NIGHT",
                    "status": "ok",
                    "rows_written": 40,
                    "completed_at": _time(1).isoformat(),
                },
                {
                    "season": 2026,
                    "week": 1,
                    "slate": "SUNDAY_MAIN",
                    "status": "ok",
                    "rows_written": 20,
                    "completed_at": _time(2).isoformat(),
                },
            ],
        }
        feature.created_at = _time(0).replace(tzinfo=None)
        feature.updated_at = _time(3).replace(tzinfo=None)
        feature.completed_at = _time(3).replace(tzinfo=None)

        projection, _ = enqueue_job(
            session,
            job_type=PROJECTION_JOB,
            idempotency_key="projection-wed",
            request_payload={"season": 2026, "week": 1, "slate": "WEDNESDAY_NIGHT"},
            run_id="projection-wed-1",
        )
        projection.status = "completed"
        projection.result_json = {
            "projection_run_id": "projection-wed-1",
            "rows_written": 148,
            "message": "Predictions generated",
        }
        projection.created_at = _time(4).replace(tzinfo=None)
        projection.updated_at = _time(5).replace(tzinfo=None)
        projection.completed_at = _time(5).replace(tzinfo=None)
        session.commit()

    # A new session models a page/API process restart; no React memory is involved.
    with factory() as session:
        wednesday = get_model_pipeline_summary(
            session,
            season=2026,
            week=1,
            slate="wednesday_night",
            selected_projection_run_id="projection-wed-1",
        )
        sunday = get_model_pipeline_summary(
            session,
            season=2026,
            week=1,
            slate="SUNDAY_MAIN",
        )

    assert wednesday.features.status == "completed"
    assert wednesday.features.latest_attempt.rows_written == 40
    assert wednesday.features.latest_attempt.scope == "season"
    assert wednesday.projections.status == "completed"
    assert wednesday.projections.status_at == _time(5)
    assert wednesday.selected_projection is not None
    assert wednesday.selected_projection.is_latest_success is True
    assert sunday.features.latest_attempt.rows_written == 20
    assert sunday.projections.status == "not_run"


def test_newer_persisted_projection_is_the_latest_attempt_without_a_queue_job(
    tmp_path: Path,
) -> None:
    factory = _factory(tmp_path)
    with factory() as session:
        job, _ = enqueue_job(
            session,
            job_type=PROJECTION_JOB,
            idempotency_key="older-queued-projection",
            request_payload={
                "season": 2026,
                "week": 1,
                "slate": "WEDNESDAY_NIGHT",
            },
            run_id="older-run",
        )
        job.status = "completed"
        job.created_at = _time(1).replace(tzinfo=None)
        job.updated_at = _time(2).replace(tzinfo=None)
        job.completed_at = _time(2).replace(tzinfo=None)
        artifact = PipelineOperationResult(
            status="completed",
            status_at=_time(3),
            run_id="newer-direct-run",
            rows_written=37,
        )

        summary = _operation_summary(
            "projections",
            [job],
            [artifact],
            season=2026,
            week=1,
            slate="WEDNESDAY_NIGHT",
            now=_time(4),
        )

    assert summary.latest_attempt.run_id == "newer-direct-run"
    assert summary.status_at == _time(3)
    assert summary.last_success.run_id == "newer-direct-run"


def test_failed_rerun_keeps_last_success_and_selected_older_projection(
    tmp_path: Path,
) -> None:
    factory = _factory(tmp_path)
    with factory() as session:
        success, _ = enqueue_job(
            session,
            job_type=PROJECTION_JOB,
            idempotency_key="projection-success",
            request_payload={"season": 2026, "week": 1, "slate": "SUNDAY_MAIN"},
            run_id="projection-good",
        )
        success.status = "completed"
        success.result_json = {
            "projection_run_id": "projection-good",
            "rows_written": 148,
            "message": "Predictions generated",
        }
        success.created_at = _time(0).replace(tzinfo=None)
        success.updated_at = _time(1).replace(tzinfo=None)
        success.completed_at = _time(1).replace(tzinfo=None)

        failed, _ = enqueue_job(
            session,
            job_type=PROJECTION_JOB,
            idempotency_key="projection-failed",
            request_payload={"season": 2026, "week": 1, "slate": "SUNDAY_MAIN"},
            run_id="projection-bad",
        )
        failed.status = "failed"
        failed.error_message = "Model fit failed."
        failed.created_at = _time(2).replace(tzinfo=None)
        failed.updated_at = _time(3).replace(tzinfo=None)
        failed.completed_at = _time(3).replace(tzinfo=None)
        session.commit()

        summary = get_model_pipeline_summary(
            session,
            season=2026,
            week=1,
            slate="SUNDAY_MAIN",
            selected_projection_run_id="projection-good",
        )

    assert summary.projections.status == "failed"
    assert summary.projections.latest_attempt.error_message == "Model fit failed."
    assert summary.projections.last_success.run_id == "projection-good"
    assert summary.projections.last_success.rows_written == 148
    assert summary.selected_projection is not None
    assert summary.selected_projection.run_id == "projection-good"
    assert summary.selected_projection.status == "completed"


def test_queued_job_explains_worker_wait_and_expired_lease_is_interrupted(
    tmp_path: Path,
) -> None:
    factory = _factory(tmp_path)
    with factory() as session:
        queued, _ = enqueue_job(
            session,
            job_type=SYMBOLIC_JOB,
            idempotency_key="symbolic-queued",
            request_payload={"season": 2026, "week": 1, "slate": "SUNDAY_MAIN"},
            run_id="symbolic-1",
        )
        queued.created_at = _time(0).replace(tzinfo=None)

        interrupted, _ = enqueue_job(
            session,
            job_type=PROJECTION_JOB,
            idempotency_key="projection-interrupted",
            request_payload={"season": 2026, "week": 1, "slate": "SUNDAY_MAIN"},
            run_id="projection-interrupted",
        )
        interrupted.status = "running"
        interrupted.attempt_count = 1
        interrupted.started_at = _time(1).replace(tzinfo=None)
        interrupted.lease_expires_at = (
            datetime.now(UTC) - timedelta(minutes=1)
        ).replace(tzinfo=None)
        interrupted.created_at = _time(1).replace(tzinfo=None)
        interrupted.updated_at = _time(1).replace(tzinfo=None)
        session.commit()

        summary = get_model_pipeline_summary(
            session,
            season=2026,
            week=1,
            slate="SUNDAY_MAIN",
        )

    assert summary.symbolic.status == "queued"
    assert "waiting for an operational worker" in summary.symbolic.latest_attempt.message.lower()
    assert summary.projections.status == "interrupted"
    assert "lease expired" in summary.projections.latest_attempt.message.lower()
    assert summary.has_active_jobs is True


def test_failed_season_build_keeps_successful_selected_slate_outcome(
    tmp_path: Path,
) -> None:
    factory = _factory(tmp_path)
    with factory() as session:
        feature, _ = enqueue_job(
            session,
            job_type=FEATURE_MATRIX_JOB,
            idempotency_key="features-partial-season",
            request_payload={
                "season": 2026,
                "weeks": None,
                "slate": None,
                "source_system": "draftkings",
            },
            run_id="feature-partial-1",
            checkpoint={"rows": []},
        )
        feature.status = "failed"
        feature.error_message = "One later slate failed."
        feature.checkpoint_json = {
            "rows": [
                {
                    "season": 2026,
                    "week": 1,
                    "slate": "WEDNESDAY_NIGHT",
                    "status": "ok",
                    "rows_written": 40,
                    "completed_at": _time(1).isoformat(),
                },
                {
                    "season": 2026,
                    "week": 1,
                    "slate": "SUNDAY_MAIN",
                    "status": "failed",
                    "rows_written": 0,
                    "completed_at": _time(2).isoformat(),
                },
            ]
        }
        feature.created_at = _time(0).replace(tzinfo=None)
        feature.updated_at = _time(3).replace(tzinfo=None)
        feature.completed_at = _time(3).replace(tzinfo=None)
        session.commit()

        summary = get_model_pipeline_summary(
            session,
            season=2026,
            week=1,
            slate="WEDNESDAY_NIGHT",
        )

    assert summary.features.status == "failed"
    assert summary.features.latest_attempt.slice_outcome["status"] == "ok"
    assert summary.features.last_success is not None
    assert summary.features.last_success.rows_written == 40
    assert summary.features.last_success.status_at == _time(1)
