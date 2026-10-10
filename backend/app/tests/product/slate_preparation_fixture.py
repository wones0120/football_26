"""Synthetic API/queue/worker fixture; no application database or network sources.

Collector and model I/O are deterministic adapters. Routes, durable queue/worker,
orchestration, dependency verification and target lineage reads execute normally.
"""
from contextlib import ExitStack
from copy import deepcopy
from datetime import UTC, datetime
import json
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.product_routes import router
from backend.app.api.job_routes import router as job_router
from backend.app.db import get_db_session
from backend.app.models import OperationalJob
from backend.app.services.job_queue import claim_next_job
from backend.app.worker import execute_claimed_job


class PreparationFixture:
    def __init__(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        OperationalJob.__table__.create(self.engine)
        with self.engine.begin() as c:
            c.execute(text("ATTACH DATABASE ':memory:' AS target"))
            c.execute(text("CREATE TABLE target.feature_generation_run (feature_run_id TEXT PRIMARY KEY, source_versions_json TEXT)"))
            c.execute(text("CREATE TABLE target.model_run (model_run_id TEXT PRIMARY KEY, feature_run_id TEXT)"))
            c.execute(text("CREATE TABLE target.projection_run (projection_run_id TEXT PRIMARY KEY, model_run_id TEXT, season INT, week INT, slate_id TEXT, status TEXT)"))
            c.execute(text("CREATE TABLE target.feature_player_game (feature_run_id TEXT, game_id TEXT, player_id TEXT, feature_json TEXT)"))

        @event.listens_for(self.engine, "before_cursor_execute", retval=True)
        def sqlite_json_adapter(conn, cursor, statement, parameters, context, executemany):
            # Equivalent database JSON merge for this isolated SQLite fixture only.
            return statement.replace("source_versions_json || CAST(? AS JSONB)", "json_patch(source_versions_json, ?)"), parameters

        self.manifest = {"scope": {"season": 2000, "week": 1, "slate": "SUNDAY_MAIN"},
            "games": [{"game_id": "synthetic-game", "home_team": "BUF", "away_team": "NYJ", "kickoff_at": "2099-01-01T17:00:00+00:00"}],
            "salaries": [{"curated_salary_id": 1, "player_master_id": "synthetic-player", "source_checksum": "fixture-salary-sha", "ingest_status": "completed"}],
            "injuries": [], "availability": [],
            "starters": [{"player_master_id": "synthetic-player", "evidence_tier": "confirmed", "source": "fixture"}],
            "markets": [{"game_id": "synthetic-game", "market_snapshot_id": "synthetic-market-1", "observed_at": "2026-10-04T12:00:00+00:00", "source": "nflverse_schedules", "observation_basis": "capture_clock", "content_sha256": "fixture-market-sha"}]}
        self.corrupt = False
        self.fail_capture = False
        self.calls = []
        self.stack = ExitStack()
        for name in ("backend.app.db.SessionLocal", "backend.app.services.job_handlers.SessionLocal", "backend.app.worker.SessionLocal"):
            self.stack.enter_context(patch(name, self.factory))
        prefix = "backend.app.product_services.slate_preparation."
        self.stack.enter_context(patch(prefix + "source_manifest", side_effect=lambda *a, **kw: deepcopy(self.manifest)))
        self.stack.enter_context(patch(prefix + "slate_games", side_effect=lambda *a: deepcopy(self.manifest["games"])))
        self.stack.enter_context(patch(prefix + "verify_artifacts", return_value=None))
        self.stack.enter_context(patch(prefix + "capture_source", side_effect=self.capture))
        self.stack.enter_context(patch(prefix + "import_file", side_effect=self.import_file))
        self.stack.enter_context(patch("backend.app.services.slate_weather.SlateWeatherService.report", return_value={"games": [{"game_id": "synthetic-game", "weather_state": "missing", "venue": None}]}))
        self.stack.enter_context(patch("backend.app.services.ingest.IngestService.get_data_freshness", return_value=SimpleNamespace(model_dump=lambda **kw: {"rows": []})))
        self.stack.enter_context(patch("backend.app.services.lineup_learning.LineupLearningService.rebuild_player_game_feature_matrix", side_effect=self.features))
        self.stack.enter_context(patch("backend.app.services.job_handlers.DataQualityService.record_load"))
        self.stack.enter_context(patch("backend.app.services.job_handlers.get_connection_string", return_value="sqlite://"))
        self.stack.enter_context(patch("backend.app.product_services.predictions.PredictionsService.__init__", return_value=None))
        self.stack.enter_context(patch("backend.app.product_services.predictions.PredictionsService.fetch_completed_run_summary", return_value=None))
        self.stack.enter_context(patch("backend.app.product_services.predictions.PredictionsService.train_and_predict", side_effect=self.projections))
        self.stack.enter_context(patch("backend.app.product_services.optimizer.OptimizerService.run_job", side_effect=AssertionError("Preparation must never solve")))
        self.app = FastAPI(); self.app.include_router(router); self.app.include_router(job_router)
        def session():
            with self.factory() as db:
                yield db
        self.app.dependency_overrides[get_db_session] = session
        self.client = TestClient(self.app)

        @self.app.post("/fixture/work")
        def work():
            return self.work()

    def close(self):
        self.stack.close(); self.engine.dispose()

    def capture(self, request, games):
        self.calls.append(request.action)
        if self.fail_capture:
            raise ValueError("Synthetic source unavailable; use supported manual evidence.")
        if request.action == "markets":
            self.manifest["markets"][0]["market_snapshot_id"] = "synthetic-market-2"
            self.manifest["markets"][0]["observed_at"] = datetime.now(UTC).isoformat()
        return {"fixture_only": True, "observation_basis": "capture_clock", "provider_issued_at": None}

    def import_file(self, session, request):
        self.calls.append(request.action)
        return {"fixture_only": True, "rows_curated": 1}

    def features(self, **kwargs):
        self.calls.append("features")
        kwargs["status_hook"](1, 1, {"season": 2000, "week": 1, "slate": "SUNDAY_MAIN", "status": "ok", "rows_written": 1})
        return {"rows_written": 1, "slates_total": 1, "slates_completed": 1, "slates_failed": 0}

    def projections(self, **kwargs):
        self.calls.append("projections")
        assert kwargs["data_cutoff_at"] is not None
        feature = {"market_snapshot_row_id": "old-market" if self.corrupt else self.manifest["markets"][0]["market_snapshot_id"],
                   "team_starting_qb_player_id": "synthetic-player"}
        for context in self.manifest["availability"]:
            feature["pregame_context_row_id"] = context["pregame_player_context_id"]
        with self.engine.begin() as c:
            c.execute(text("INSERT INTO target.feature_generation_run VALUES (:f, :sources)"), {"f": kwargs["feature_run_id"], "sources": json.dumps({"salary_row_ids": [1]})})
            c.execute(text("INSERT INTO target.model_run VALUES (:m, :f)"), {"m": kwargs["model_run_id"], "f": kwargs["feature_run_id"]})
            c.execute(text("INSERT INTO target.projection_run VALUES (:p, :m, 2000, 1, 'SUNDAY_MAIN', 'completed')"), {"p": kwargs["projection_run_id"], "m": kwargs["model_run_id"]})
            c.execute(text("INSERT INTO target.feature_player_game VALUES (:f, 'synthetic-game', 'synthetic-player', :j)"), {"f": kwargs["feature_run_id"], "j": json.dumps(feature)})
        return SimpleNamespace(records=[{}], target_persisted=True, calibration_metrics={},
            feature_run_id=kwargs["feature_run_id"], model_run_id=kwargs["model_run_id"],
            projection_run_id=kwargs["projection_run_id"], data_cutoff_at=kwargs["data_cutoff_at"])

    def work(self):
        with self.factory() as db:
            job = claim_next_job(db, worker_id="fixture-worker")
        if not job:
            return {"status": "idle"}
        assert job.job_type == "slate_preparation", "Fixture worker only executes preparation, never user portfolios"
        execute_claimed_job(job_id=job.job_id, job_type=job.job_type, request_payload=job.request_json,
            worker_id="fixture-worker", run_id=job.run_id, checkpoint=job.checkpoint_json, lease_seconds=300)
        return self.client.get("/api/jobs/" + job.job_id).json()


if __name__ == "__main__":
    import sys
    import uvicorn
    fixture = PreparationFixture()
    uvicorn.run(fixture.app, host="127.0.0.1", port=int(sys.argv[1]))
