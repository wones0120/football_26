"""Isolated frontend/API/solver fixture. Never connects to application data.

CLI accepts frontend JSON on stdin. --serve exposes only this fixture for the
browser regression harness. Upstream data and persistence use synthetic SQLite.
"""
from contextlib import redirect_stdout
from dataclasses import asdict
from datetime import datetime
import io
import json
import sqlite3
import sys
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock, patch

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.api.product_routes import router
from backend.app.db import get_db_session
from backend.app.models import OperationalJob
from backend.app.product_dependencies import get_optimizer_service
from backend.app.product_services.optimizer import OptimizerService
from backend.app.product_schemas import OptimizerRunRequest
from backend.app.tests.product.test_classic_strategy_contract import pool
from backend.app.services.job_handlers import _optimizer_handler


def fixture_app():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    OperationalJob.__table__.create(engine)
    store = sqlite3.connect(":memory:", check_same_thread=False)
    store.execute("CREATE TABLE saved_run (id TEXT PRIMARY KEY, document TEXT NOT NULL)")
    service = OptimizerService.__new__(OptimizerService)
    service.engine = MagicMock()
    service._jobs = {}
    service._load_persisted_job = lambda _: None
    service._resolve_run_lineage = Mock(return_value=("synthetic-projection", None, None))
    rows = [{**asdict(p), "player_team": p.team, "opponent_team": p.opponent,
             "p90": p.ceiling, "predicted_p10": p.projection - 4,
             "is_starting_qb": p.position == "QB", "injury_status": None}
            for p in pool()]
    frame = pd.DataFrame(rows)
    service._load_player_pool = Mock(side_effect=lambda *args, **kwargs: frame.copy(deep=True))
    # This synthetic historical fixture deliberately has no live evidence.
    # The internal preview is explicit and cannot be supplied by public JSON.
    original_run_job = service.run_job
    service.run_job = lambda **kwargs: original_run_job(**kwargs, allow_incomplete_evidence=True)
    service._attach_symbolic_explanations = Mock()
    # Only the database adapter is replaced. run_job, contract construction,
    # production solver, and independent portfolio audit run unchanged.
    def persist(job):
        document = {key: getattr(job, key) for key in
                    ("job_id", "status", "strategy", "contest_format", "objective",
                     "params", "projection_run_id", "rule_run_id", "data_cutoff_at",
                     "message", "results", "created_at", "updated_at")}
        document["lineage_persisted"] = True
        store.execute("INSERT OR REPLACE INTO saved_run VALUES (?, ?)",
                      (job.job_id, json.dumps(document, default=str)))
        store.commit()
        return True
    service._persist_optimizer_run = persist

    def reload(job_id):
        row = store.execute("SELECT document FROM saved_run WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        document = json.loads(row[0])
        for key in ("created_at", "updated_at", "data_cutoff_at"):
            if document[key]:
                document[key] = datetime.fromisoformat(document[key])
        return SimpleNamespace(**document)

    app = FastAPI()
    app.include_router(router)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["POST"], allow_headers=["content-type"])
    def session():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db_session] = session
    app.dependency_overrides[get_optimizer_service] = lambda: SimpleNamespace(
        get_job=reload, engine=service.engine,
        run_job=lambda **kwargs: reload(kwargs["optimizer_run_id"]))
    client = TestClient(app)

    @app.post("/fixture/submit")
    def submit(payload: dict):
        assert payload["season"] == 2000 and payload["week"] == 1, "Synthetic fixture scope only"
        assert payload["strategy"] == "classic_large_gpp_v1", "Large fixture only"
        queued = client.post("/api/optimizer/jobs", json=payload)
        assert queued.status_code == 202, queued.text
        with Session(engine) as db:
            queue = db.scalar(select(OperationalJob).where(OperationalJob.run_id == payload["optimizer_run_id"]))
            saved_request = json.loads(json.dumps(queue.request_json))
        request = OptimizerRunRequest.model_validate(saved_request)
        # Patch the call, not inherited object.__new__: restoring that descriptor
        # changes constructor argument handling for subsequent service fixtures.
        # Worker preparation checks share this fixture database, never the application SessionLocal.
        with redirect_stdout(io.StringIO()), patch("backend.app.services.job_handlers.SessionLocal", side_effect=lambda: Session(engine)), patch.object(OptimizerService, "__init__", return_value=None), patch.object(OptimizerService, "run_job", side_effect=service.run_job):
            execution = _optimizer_handler(SimpleNamespace(run_id=request.optimizer_run_id, progress=Mock()), saved_request)
        job = reload(execution["optimizer_run_id"])
        report = client.get("/api/optimizer/results/" + job.job_id)
        assert report.status_code == 200, report.text
        synchronous_report = client.post("/api/optimizer/run", json=payload)
        assert synchronous_report.status_code == 200, synchronous_report.text
        assert synchronous_report.json() == report.json(), "Normal response paths must propagate the same saved evidence"
        return {"api_request": saved_request, "backend_parsed_request": request.model_dump(mode="json"), "saved_options": reload(job.job_id).params,
                "report": report.json(), "fixture_only": True, "executor": "durable optimizer handler"}

    return app


if __name__ == "__main__":
    app = fixture_app()
    if "--serve" in sys.argv:
        import uvicorn
        uvicorn.run(app, host="127.0.0.1", port=8001)
    else:
        client = TestClient(app)
        payloads = json.load(sys.stdin)
        responses = []
        for payload in payloads:
            response = client.post("/fixture/submit", json=payload)
            assert response.status_code == 200, response.text
            responses.append(response.json())
        print(json.dumps(responses))
