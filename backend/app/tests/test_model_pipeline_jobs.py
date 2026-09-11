from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.api.product_routes import router as product_router
from backend.app.db import get_db_session
from backend.app.models import Base, OperationalJob
from backend.app.services.job_handlers import _feature_matrix_handler
from backend.app.services.job_queue import PermanentJobError


def _factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'pipeline-jobs.sqlite3'}")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def test_models_actions_enqueue_durable_feature_and_symbolic_jobs(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    app = FastAPI()
    app.include_router(product_router)

    def override_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    client = TestClient(app)

    feature = client.post(
        "/api/features/matrix/jobs",
        json={"season": 2026, "weeks": [1], "slate": "WEDNESDAY_NIGHT"},
        headers={"Idempotency-Key": "feature-w1-wed"},
    )
    symbolic = client.post(
        "/api/agent/jobs",
        json={
            "season": 2026,
            "week": 1,
            "slate": "WEDNESDAY_NIGHT",
            "projection_run_id": "projection-1",
        },
        headers={"Idempotency-Key": "symbolic-w1-wed"},
    )

    assert feature.status_code == 202
    assert feature.json()["job"]["status"] == "queued"
    assert feature.json()["job"]["job_type"] == "feature_matrix_build"
    assert symbolic.status_code == 202
    assert symbolic.json()["job"]["job_type"] == "symbolic_run"
    with factory() as session:
        jobs = session.query(OperationalJob).order_by(OperationalJob.created_at).all()
        assert [job.job_type for job in jobs] == ["feature_matrix_build", "symbolic_run"]
        assert jobs[0].request_json["weeks"] == [1]
        assert jobs[1].request_json["projection_run_id"] == "projection-1"


class _Context:
    run_id = "feature-run-1"
    checkpoint: dict = {}

    def progress(
        self,
        stage: str,
        current: int,
        total: int,
        message: str,
        *,
        run_id: str | None = None,
        checkpoint: dict | None = None,
    ) -> None:
        if checkpoint is not None:
            self.checkpoint = checkpoint


def test_season_feature_handler_checkpoints_each_slate_outcome() -> None:
    context = _Context()
    session = MagicMock()

    def rebuild(**kwargs):
        hook = kwargs["status_hook"]
        hook(1, 2, {
            "season": 2026,
            "week": 1,
            "slate": "WEDNESDAY_NIGHT",
            "status": "ok",
            "rows_written": 40,
        })
        hook(2, 2, {
            "season": 2026,
            "week": 1,
            "slate": "SUNDAY_MAIN",
            "status": "failed",
            "rows_written": 0,
            "error_message": "fixture failure",
        })
        return {
            "slates_total": 2,
            "slates_completed": 1,
            "slates_failed": 1,
            "rows_written": 40,
            "rows": [],
        }

    with patch(
        "backend.app.services.job_handlers.SessionLocal",
        return_value=nullcontext(session),
    ), patch(
        "backend.app.services.job_handlers.LineupLearningService"
    ) as service:
        service.return_value.rebuild_player_game_feature_matrix.side_effect = rebuild
        try:
            _feature_matrix_handler(context, {"season": 2026})
        except PermanentJobError as exc:
            assert "1 slate(s)" in str(exc)
        else:
            raise AssertionError("partial season build should fail")

    assert [row["status"] for row in context.checkpoint["rows"]] == ["ok", "failed"]
    assert all(row["completed_at"].endswith("+00:00") for row in context.checkpoint["rows"])
