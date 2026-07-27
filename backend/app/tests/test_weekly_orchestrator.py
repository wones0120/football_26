from __future__ import annotations

from collections import Counter
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.api.weekly_routes import router as weekly_router
from backend.app.db import get_db_session
from backend.app.models import Base
from backend.app.services.job_queue import WEEKLY_RUN_JOB, enqueue_job, get_job
from backend.app.services.weekly_orchestrator import (
    WEEKLY_STAGES,
    DefaultWeeklyStageExecutor,
    StageExecutionResult,
    WeeklyOrchestrator,
    allocate_stage_artifacts,
    create_weekly_run,
    get_weekly_run,
    weekly_run_response,
)
from backend.app.product_services.predictions import PredictionsService
from backend.app.product_services.readiness import SlateReadinessService
from backend.app.weekly_schemas import WeeklyRunRequest


def _factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'weekly.sqlite3'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


class RecordingExecutor:
    def __init__(self, *, fail_once_at: str | None = None) -> None:
        self.fail_once_at = fail_once_at
        self.calls: Counter[str] = Counter()

    def execute(
        self,
        stage: str,
        *,
        request: WeeklyRunRequest,
        artifact_ids: dict,
        completed_artifacts: dict[str, dict],
    ) -> StageExecutionResult:
        self.calls[stage] += 1
        if stage == self.fail_once_at and self.calls[stage] == 1:
            raise RuntimeError("simulated worker interruption")
        expected_predecessors = WEEKLY_STAGES[: WEEKLY_STAGES.index(stage)]
        assert set(completed_artifacts) == set(expected_predecessors)
        return StageExecutionResult(
            message=f"{stage} complete",
            counts={"rows_written": self.calls[stage]},
            logs=[f"{stage} log"],
            warnings=[f"{stage} warning"] if stage == "readiness" else [],
            artifact_ids={**artifact_ids, f"{stage}_artifact_id": f"artifact-{stage}"},
            result={"season": request.season},
        )


def _create_run(
    factory: sessionmaker[Session],
    request: WeeklyRunRequest,
) -> str:
    with factory() as session:
        job, _created = enqueue_job(
            session,
            job_type=WEEKLY_RUN_JOB,
            idempotency_key="weekly-test",
            request_payload=request.model_dump(mode="json"),
            run_id="weekly-run-1",
        )
        create_weekly_run(
            session,
            weekly_run_id="weekly-run-1",
            operational_job_id=job.job_id,
            request=request,
            stage_artifacts=allocate_stage_artifacts(request),
        )
    return "weekly-run-1"


def test_weekly_run_resumes_after_interruption_without_repeating_completed_stages(
    tmp_path: Path,
) -> None:
    factory = _factory(tmp_path)
    request = WeeklyRunRequest(season=2025, week=11, slate="SUNDAY_MAIN")
    weekly_run_id = _create_run(factory, request)
    executor = RecordingExecutor(fail_once_at="simulate")
    orchestrator = WeeklyOrchestrator(factory, executor=executor)

    with pytest.raises(RuntimeError, match="simulated worker interruption"):
        orchestrator.run(weekly_run_id, request)

    with factory() as session:
        failed = get_weekly_run(session, weekly_run_id)
        assert failed is not None
        failed_response = weekly_run_response(session, failed)
        assert failed_response.status == "failed"
        assert failed_response.current_stage == "simulate"
        assert failed_response.progress_current == 4
        simulate = next(
            stage for stage in failed_response.stages if stage.stage == "simulate"
        )
        assert simulate.status == "failed"
        assert simulate.errors == ["simulated worker interruption"]
        assert simulate.attempt_count == 1

    completed = orchestrator.run(weekly_run_id, request)

    assert completed.status == "completed"
    assert completed.progress_current == len(WEEKLY_STAGES)
    assert completed.progress_percent == 100.0
    assert completed.warning_count == 1
    assert completed.error_count == 0
    assert executor.calls == Counter(
        {
            "ingest": 1,
            "readiness": 1,
            "predict": 1,
            "adjust": 1,
            "simulate": 2,
            "optimize": 1,
            "validate": 1,
            "export": 1,
        }
    )
    simulate = next(stage for stage in completed.stages if stage.stage == "simulate")
    assert simulate.attempt_count == 2
    assert any("prior attempt" in row.lower() for row in simulate.logs)
    assert completed.artifact_ids["export"]["export_artifact_id"] == "artifact-export"


def test_weekly_run_api_is_idempotent_and_exposes_all_stage_checkpoints(
    tmp_path: Path,
) -> None:
    factory = _factory(tmp_path)
    app = FastAPI()
    app.include_router(weekly_router)

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    client = TestClient(app)
    body = {
        "season": 2025,
        "week": 11,
        "slate": "SUNDAY_MAIN",
        "template_id": "template-1",
    }
    headers = {"Idempotency-Key": "weekly-api-2025-w11-main"}

    created = client.post("/api/weekly-runs", json=body, headers=headers)
    reused = client.post("/api/weekly-runs", json=body, headers=headers)

    assert created.status_code == 202
    assert reused.status_code == 202
    first = created.json()
    second = reused.json()
    assert first["created"] is True
    assert second["created"] is False
    assert second["job"]["job_id"] == first["job"]["job_id"]
    assert second["run"]["weekly_run_id"] == first["run"]["weekly_run_id"]
    assert [stage["stage"] for stage in first["run"]["stages"]] == list(
        WEEKLY_STAGES
    )
    assert first["run"]["artifact_ids"]["predict"]["projection_run_id"]
    assert first["run"]["artifact_ids"]["export"]["export_id"]

    fetched = client.get(f"/api/weekly-runs/{first['run']['weekly_run_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "queued"

    listed = client.get("/api/weekly-runs?season=2025&week=11&slate=sunday_main")
    assert listed.status_code == 200
    assert [row["weekly_run_id"] for row in listed.json()["rows"]] == [
        first["run"]["weekly_run_id"]
    ]


def test_weekly_job_and_stage_checkpoints_become_visible_together(
    tmp_path: Path,
) -> None:
    factory = _factory(tmp_path)
    request = WeeklyRunRequest(season=2025, week=11, slate="SUNDAY_MAIN")

    with factory() as api_session:
        job, created = enqueue_job(
            api_session,
            job_type=WEEKLY_RUN_JOB,
            idempotency_key="weekly-atomic-create",
            request_payload=request.model_dump(mode="json"),
            run_id="weekly-run-atomic",
            commit=False,
        )
        assert created is True
        job_id = job.job_id
        with factory() as worker_session:
            assert get_job(worker_session, job_id) is None
            assert get_weekly_run(worker_session, "weekly-run-atomic") is None

        create_weekly_run(
            api_session,
            weekly_run_id="weekly-run-atomic",
            operational_job_id=job_id,
            request=request,
            stage_artifacts=allocate_stage_artifacts(request),
        )

    with factory() as worker_session:
        assert get_job(worker_session, job_id) is not None
        run = get_weekly_run(worker_session, "weekly-run-atomic")
        assert run is not None
        assert len(weekly_run_response(worker_session, run).stages) == len(WEEKLY_STAGES)


def test_predict_stage_reuses_the_active_immutable_projection_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = _factory(tmp_path)
    request = WeeklyRunRequest(season=2025, week=11, slate="SUNDAY_MAIN")
    planned_artifacts = allocate_stage_artifacts(request)["predict"]

    monkeypatch.setattr(
        SlateReadinessService,
        "report",
        lambda _self, **_kwargs: {
            "checks": [
                {
                    "check_id": "projection_run_lineage",
                    "details": {
                        "selected_projection_run_id": "projection-active-1"
                    },
                }
            ]
        },
    )
    monkeypatch.setattr(
        PredictionsService,
        "fetch_completed_run_summary",
        lambda _self, _projection_run_id: {
            "season": 2025,
            "week": 11,
            "rows_written": 473,
            "feature_run_id": "feature-active-1",
            "model_run_id": "model-active-1",
            "projection_run_id": "projection-active-1",
            "target_persisted": True,
            "calibration_metrics": {},
        },
    )

    result = DefaultWeeklyStageExecutor(factory)._predict(
        request,
        planned_artifacts,
        {},
    )

    assert result.counts == {"rows_written": 473}
    assert result.artifact_ids["planned_projection_run_id"] == (
        planned_artifacts["projection_run_id"]
    )
    assert result.artifact_ids["projection_run_id"] == "projection-active-1"
    assert result.artifact_ids["feature_run_id"] == "feature-active-1"
    assert result.result == {
        "target_persisted": True,
        "recovered": True,
        "selection_source": "active",
        "calibration_metrics": {},
    }
