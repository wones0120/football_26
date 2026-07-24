from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api import routes
from backend.app.api.routes import router
from backend.app.db import get_db_session
from backend.app.models import Base
from backend.app.schemas import UltimateLineupRequest, UltimateLineupResponse
from backend.app.services import ultimate_lineup_runs
from backend.app.services.lineup_learning import LineupLearningService
from backend.app.services.ultimate_lineup_runs import (
    UltimateLineupRunConflictError,
    create_ultimate_lineup_run,
    execute_ultimate_lineup_run,
    get_ultimate_lineup_run,
    retry_ultimate_lineup_run,
    ultimate_lineup_run_response,
)


def _request(*, checkpoint_path: Path | None = None) -> UltimateLineupRequest:
    return UltimateLineupRequest(
        source_system="draftkings",
        season=2025,
        week=18,
        slate="sunday_main",
        simulation_run_id="scenario-run",
        baseline_simulation_run_id="baseline-run",
        candidate_lineups=1000,
        output_lineups=10,
        learned_only=False,
        random_seed=42,
        checkpoint_path=(str(checkpoint_path) if checkpoint_path else None),
        checkpoint_interval_attempts=100,
    )


def _result() -> UltimateLineupResponse:
    return UltimateLineupResponse(
        source_system="draftkings",
        season=2025,
        week=18,
        slate="sunday_main",
        simulation_run_id="scenario-run",
        simulation_outcomes_loaded=20,
        simulation_projection_overrides=20,
        baseline_simulation_run_id="baseline-run",
        baseline_simulation_outcomes_loaded=20,
        baseline_simulation_projection_overrides=20,
        portfolio_comparison=None,
        contest_objective="balanced",
        contest_objective_weights={"base": 1.0},
        candidate_lineups_requested=1000,
        generated_candidate_lineups=1000,
        output_lineups=10,
        training_slates_used=4,
        training_rows_used=2000,
        training_positive_rate=0.05,
        discovered_patterns=[],
        rows=[],
        exposures=[],
    )


def _file_session_factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'jobs.sqlite3'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )


def test_create_reuses_exact_idempotent_request_and_rejects_mismatch(
    tmp_path: Path,
) -> None:
    factory = _file_session_factory(tmp_path)
    with factory() as session:
        run, created = create_ultimate_lineup_run(
            session,
            idempotency_key="portfolio-2025-w18",
            request=_request(),
        )
        reused, reused_created = create_ultimate_lineup_run(
            session,
            idempotency_key="portfolio-2025-w18",
            request=_request(),
        )

        assert created is True
        assert reused_created is False
        assert reused.ultimate_lineup_run_id == run.ultimate_lineup_run_id

        with pytest.raises(
            UltimateLineupRunConflictError,
            match="different ultimate-lineup request",
        ):
            create_ultimate_lineup_run(
                session,
                idempotency_key="portfolio-2025-w18",
                request=_request().model_copy(
                    update={"contest_objective": "gpp"}
                ),
            )


def test_worker_persists_progress_and_completed_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = _file_session_factory(tmp_path)
    checkpoint_path = tmp_path / "ultimate-checkpoint.sqlite3"
    with factory() as session:
        run, _created = create_ultimate_lineup_run(
            session,
            idempotency_key="completed-run",
            request=_request(checkpoint_path=checkpoint_path),
        )
        run_id = run.ultimate_lineup_run_id

    observed_requests: list[UltimateLineupRequest] = []

    def build(
        _service: LineupLearningService,
        request: UltimateLineupRequest,
        progress_hook=None,
    ) -> UltimateLineupResponse:
        observed_requests.append(request)
        assert progress_hook is not None
        progress_hook("training", 4, 4, "Training ready.")
        progress_hook("candidate_generation", 650, 1000, "Candidates underway.")
        progress_hook("portfolio_selection", 3, 3, "Portfolio ready.")
        return _result()

    monkeypatch.setattr(LineupLearningService, "build_ultimate_lineups", build)
    execute_ultimate_lineup_run(run_id, session_factory=factory)

    with factory() as session:
        completed = get_ultimate_lineup_run(session, run_id)
        assert completed is not None
        response = ultimate_lineup_run_response(completed)

    assert response.status == "completed"
    assert response.stage == "completed"
    assert response.progress_percent == 100.0
    assert response.attempt_count == 1
    assert response.checkpoint_path == str(checkpoint_path.resolve())
    assert response.result is not None
    assert response.result.generated_candidate_lineups == 1000
    assert observed_requests[0].checkpoint_path == str(checkpoint_path.resolve())
    assert observed_requests[0].resume_from_checkpoint is False


def test_failed_run_can_be_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = _file_session_factory(tmp_path)
    with factory() as session:
        run, _created = create_ultimate_lineup_run(
            session,
            idempotency_key="retry-run",
            request=_request(checkpoint_path=tmp_path / "retry.sqlite3"),
        )
        run_id = run.ultimate_lineup_run_id

    def fail(*_args, **_kwargs) -> UltimateLineupResponse:
        raise ValueError("candidate pool unavailable")

    monkeypatch.setattr(LineupLearningService, "build_ultimate_lineups", fail)
    execute_ultimate_lineup_run(run_id, session_factory=factory)
    with factory() as session:
        failed = get_ultimate_lineup_run(session, run_id)
        assert failed is not None
        assert failed.status == "failed"
        assert failed.attempt_count == 1
        assert failed.error_message == "candidate pool unavailable"
        retried = retry_ultimate_lineup_run(session, run_id)
        assert retried.status == "queued"

    resumed_requests: list[UltimateLineupRequest] = []

    def succeed(
        _service: LineupLearningService,
        request: UltimateLineupRequest,
        **_kwargs,
    ) -> UltimateLineupResponse:
        resumed_requests.append(request)
        return _result()

    monkeypatch.setattr(ultimate_lineup_runs, "_checkpoint_can_resume", lambda _path: True)
    monkeypatch.setattr(LineupLearningService, "build_ultimate_lineups", succeed)
    execute_ultimate_lineup_run(run_id, session_factory=factory)
    with factory() as session:
        completed = get_ultimate_lineup_run(session, run_id)
        assert completed is not None
        assert completed.status == "completed"
        assert completed.attempt_count == 2
    assert resumed_requests[0].resume_from_checkpoint is True


def test_ultimate_run_api_create_get_and_idempotency_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)

    app = FastAPI()
    app.include_router(router)

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    scheduled: list[str] = []
    monkeypatch.setattr(
        routes,
        "execute_ultimate_lineup_run",
        lambda run_id: scheduled.append(run_id),
    )
    app.dependency_overrides[get_db_session] = override_session
    client = TestClient(app)
    body = {
        "idempotency_key": "api-run",
        "request": _request().model_dump(mode="json"),
    }

    created = client.post("/api/lineups/ultimate-runs", json=body)
    assert created.status_code == 202
    created_payload = created.json()
    assert created_payload["created"] is True
    run_id = created_payload["run"]["ultimate_lineup_run_id"]
    assert created_payload["run"]["status"] == "queued"
    assert scheduled == [run_id]

    reused = client.post("/api/lineups/ultimate-runs", json=body)
    assert reused.status_code == 202
    assert reused.json()["created"] is False
    assert reused.json()["run"]["ultimate_lineup_run_id"] == run_id
    assert scheduled == [run_id, run_id]

    fetched = client.get(f"/api/lineups/ultimate-runs/{run_id}")
    assert fetched.status_code == 200
    assert fetched.json()["idempotency_key"] == "api-run"

    body["request"]["contest_objective"] = "gpp"
    conflict = client.post("/api/lineups/ultimate-runs", json=body)
    assert conflict.status_code == 409
    assert "different ultimate-lineup request" in conflict.json()["detail"]
