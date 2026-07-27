from __future__ import annotations

from datetime import timedelta
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app import worker
from backend.app.api.product_routes import router as product_router
from backend.app.api.job_routes import router as job_router
from backend.app.db import get_db_session
from backend.app.models import Base
from backend.app.services.job_queue import (
    JobConflictError,
    claim_next_job,
    enqueue_job,
    fail_job,
    get_job,
    job_response,
    retry_job,
)


def _factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'queue.sqlite3'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def test_enqueue_is_idempotent_and_rejects_payload_mismatch(
    tmp_path: Path,
) -> None:
    factory = _factory(tmp_path)
    with factory() as session:
        created, was_created = enqueue_job(
            session,
            job_type="projection_build",
            idempotency_key="projection-2025-w11",
            request_payload={"season": 2025, "week": 11},
            run_id="projection-run-1",
        )
        reused, reused_created = enqueue_job(
            session,
            job_type="projection_build",
            idempotency_key="projection-2025-w11",
            request_payload={"season": 2025, "week": 11},
            run_id="unused-new-run-id",
        )

        assert was_created is True
        assert reused_created is False
        assert reused.job_id == created.job_id
        assert reused.run_id == "projection-run-1"

        with pytest.raises(JobConflictError, match="different projection_build"):
            enqueue_job(
                session,
                job_type="projection_build",
                idempotency_key="projection-2025-w11",
                request_payload={"season": 2025, "week": 12},
            )


def test_worker_claim_survives_api_session_and_persists_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = _factory(tmp_path)
    with factory() as api_session:
        queued, _created = enqueue_job(
            api_session,
            job_type="benchmark_suite",
            idempotency_key="nightly-smoke",
            request_payload={"limit_slates": 1},
            run_id="benchmark-run-1",
        )
        job_id = queued.job_id

    with factory() as worker_session:
        claimed = claim_next_job(
            worker_session,
            worker_id="worker-a",
            lease_seconds=60,
        )
        assert claimed is not None
        assert claimed.job_id == job_id
        assert claimed.attempt_count == 1

    monkeypatch.setattr(worker, "SessionLocal", factory)

    def handler(job_type, context, payload):
        assert job_type == "benchmark_suite"
        assert payload == {"limit_slates": 1}
        context.progress("benchmark_suite", 1, 2, "Classic track complete.")
        return {"status": "ok", "run": {"run_directory": context.run_id}}

    worker.execute_claimed_job(
        job_id=job_id,
        job_type="benchmark_suite",
        request_payload={"limit_slates": 1},
        worker_id="worker-a",
        run_id="benchmark-run-1",
        checkpoint=None,
        lease_seconds=60,
        handler=handler,
        heartbeat_seconds=60,
    )

    with factory() as restarted_api_session:
        completed = get_job(restarted_api_session, job_id)
        assert completed is not None
        response = job_response(completed)
        assert response.status == "completed"
        assert response.progress_percent == 100.0
        assert response.run_id == "benchmark-run-1"
        assert response.result == {
            "status": "ok",
            "run": {"run_directory": "benchmark-run-1"},
        }


def test_expired_claim_is_recovered_with_same_run_id(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    with factory() as session:
        queued, _created = enqueue_job(
            session,
            job_type="slate_simulation",
            idempotency_key="simulation-1",
            request_payload={"season": 2025, "week": 11},
            run_id="simulation-run-1",
        )
        job_id = queued.job_id
        first_claim = claim_next_job(
            session,
            worker_id="worker-that-crashed",
            lease_seconds=60,
        )
        assert first_claim is not None
        first_claim.lease_expires_at = first_claim.lease_expires_at - timedelta(
            seconds=120
        )
        session.commit()

    with factory() as session:
        recovered = claim_next_job(
            session,
            worker_id="replacement-worker",
            lease_seconds=60,
        )
        assert recovered is not None
        assert recovered.job_id == job_id
        assert recovered.run_id == "simulation-run-1"
        assert recovered.attempt_count == 2
        assert recovered.locked_by == "replacement-worker"


def test_failed_job_can_be_manually_requeued_without_changing_identity(
    tmp_path: Path,
) -> None:
    factory = _factory(tmp_path)
    with factory() as session:
        queued, _created = enqueue_job(
            session,
            job_type="research_simulation",
            idempotency_key="research-sim-1",
            request_payload={"season": 2025, "week": 11},
            run_id="research-run-1",
            max_attempts=1,
        )
        claimed = claim_next_job(
            session,
            worker_id="worker-a",
            lease_seconds=60,
        )
        assert claimed is not None
        assert fail_job(
            session,
            job_id=queued.job_id,
            worker_id="worker-a",
            error_message="fixture failure",
            permanent=True,
        )
        retried = retry_job(session, queued.job_id)

        assert retried.status == "queued"
        assert retried.run_id == "research-run-1"
        assert retried.attempt_count == 1
        assert retried.max_attempts == 2


def test_expired_final_attempt_is_marked_failed(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    with factory() as session:
        queued, _created = enqueue_job(
            session,
            job_type="benchmark_suite",
            idempotency_key="one-attempt-only",
            request_payload={"limit_slates": 1},
            max_attempts=1,
        )
        claimed = claim_next_job(
            session,
            worker_id="lost-worker",
            lease_seconds=60,
        )
        assert claimed is not None
        claimed.lease_expires_at = claimed.lease_expires_at - timedelta(seconds=120)
        session.commit()

        assert claim_next_job(
            session,
            worker_id="replacement-worker",
            lease_seconds=60,
        ) is None
        expired = get_job(session, queued.job_id)
        assert expired is not None
        assert expired.status == "failed"
        assert "lease expired" in str(expired.error_message).lower()


def test_projection_dispatch_and_job_status_api_are_idempotent(
    tmp_path: Path,
) -> None:
    factory = _factory(tmp_path)
    app = FastAPI()
    app.include_router(product_router)
    app.include_router(job_router)

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    client = TestClient(app)
    body = {"season": 2025, "week": 11, "slate": "SUNDAY_MAIN"}
    headers = {"Idempotency-Key": "projection-api-2025-w11"}

    created = client.post("/api/predict/run", json=body, headers=headers)
    reused = client.post("/api/predict/run", json=body, headers=headers)

    assert created.status_code == 202
    assert reused.status_code == 202
    created_payload = created.json()
    reused_payload = reused.json()
    assert created_payload["created"] is True
    assert reused_payload["created"] is False
    assert reused_payload["job"]["job_id"] == created_payload["job"]["job_id"]
    assert reused_payload["job"]["run_id"] == created_payload["job"]["run_id"]

    fetched = client.get(f"/api/jobs/{created_payload['job']['job_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "queued"

    listed = client.get("/api/jobs?job_type=projection_build")
    assert listed.status_code == 200
    assert [row["job_id"] for row in listed.json()["rows"]] == [
        created_payload["job"]["job_id"]
    ]
