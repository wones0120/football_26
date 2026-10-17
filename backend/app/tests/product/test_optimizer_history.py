from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.product_routes import router
from backend.app.db import get_db_session
from backend.app.models import Base
from backend.app.product_dependencies import get_optimizer_service
from backend.app.product_services.optimizer_history import list_optimizer_runs
from backend.app.services.job_queue import OPTIMIZER_JOB, enqueue_job, claim_next_job, PermanentJobError


@pytest.fixture
def history_db():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def attach(connection, record):
        connection.execute("ATTACH DATABASE ':memory:' AS target")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("""CREATE TABLE target.optimizer_run (
            optimizer_run_id TEXT PRIMARY KEY, season INTEGER, week INTEGER, slate_id TEXT,
            contest_format TEXT, objective TEXT, strategy TEXT, status TEXT, message TEXT,
            created_at TEXT, updated_at TEXT, projection_run_id TEXT, constraint_config_json JSON)""")
        connection.exec_driver_sql("CREATE TABLE target.lineup (lineup_id TEXT, optimizer_run_id TEXT)")
    factory = sessionmaker(engine, expire_on_commit=False)
    yield engine, factory
    engine.dispose()


def request(**overrides):
    return {"season": 2026, "week": 4, "slate": "SUNDAY_MAIN", "contest_format": "classic", "objective": "gpp",
        "strategy": "classic_small_field_gpp", "optimizer_run_id": "queued-1", "projection_run_id": "projection-1",
        "params": {"num_lineups": 5, "classic_expanded_discovery": True}, **overrides}


def saved(engine, run_id="saved-1", **overrides):
    values = {**request(), "optimizer_run_id": run_id, "status": "completed", "message": "Saved",
        "created_at": "2026-10-02T14:00:00", "updated_at": "2026-10-02T14:00:00", **overrides}
    import json
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO target.optimizer_run VALUES (
            :optimizer_run_id, :season, :week, :slate, :contest_format, :objective, :strategy,
            :status, :message, :created_at, :updated_at, :projection_run_id, :config)"""),
            {**values, "config": json.dumps(values["params"])})
        connection.execute(text("INSERT INTO target.lineup VALUES (:id, :run_id)"),
            [{"id": "lineup-a-" + run_id, "run_id": run_id}, {"id": "lineup-b-" + run_id, "run_id": run_id}])


def scope():
    return dict(season=2026, week=4, slate="sunday_main", contest_format="classic", objective="gpp")


def test_saved_history_filters_scope_and_counts_without_loading_reports(history_db):
    engine, factory = history_db
    saved(engine, slate="sunday_main")
    for run_id, change in [("other-week", {"week": 3}), ("other-year", {"season": 2025}),
        ("other-slate", {"slate": "SUNDAY_LATE"}), ("showdown", {"contest_format": "showdown"}), ("cash", {"objective": "cash"})]:
        saved(engine, run_id, **change)
    with factory() as session:
        rows = list_optimizer_runs(engine, session, **scope())
    assert len(rows) == 1
    assert rows[0]["optimizer_run_id"] == "saved-1"
    assert rows[0]["lineup_count"] == 2 and rows[0]["requested_lineups"] == 5
    assert rows[0]["expanded_discovery"] is True
    assert rows[0]["created_at"].endswith("+00:00")
    assert "constraint_config_json" not in rows[0]


def test_queued_and_running_runs_are_visible_after_session_restart(history_db):
    engine, factory = history_db
    with factory() as session:
        queued, _ = enqueue_job(session, job_type=OPTIMIZER_JOB, idempotency_key="optimizer:queued-1", request_payload=request(), run_id="queued-1")
        job_id = queued.job_id
    with factory() as session:
        rows = list_optimizer_runs(engine, session, **scope())
        assert rows[0]["status"] == "queued" and rows[0]["operational_job_id"] == job_id
        claimed = claim_next_job(session, worker_id="test-worker", lease_seconds=300)
        assert claimed.request_json == request()
    with factory() as session:
        assert list_optimizer_runs(engine, session, **scope())[0]["status"] == "running"


def test_completed_solve_and_queue_record_merge_to_one_recoverable_row(history_db):
    engine, factory = history_db
    saved(engine, "queued-1")
    with factory() as session:
        enqueue_job(session, job_type=OPTIMIZER_JOB, idempotency_key="optimizer:queued-1", request_payload=request(), run_id="queued-1")
        rows = list_optimizer_runs(engine, session, **scope())
    assert len(rows) == 1 and rows[0]["status"] == "completed"
    assert rows[0]["lineup_count"] == 2 and rows[0]["operational_job_id"]


def test_history_is_newest_first_and_bounded(history_db):
    engine, factory = history_db
    saved(engine, "older")
    saved(engine, "newer", created_at="2026-10-02T15:00:00")
    with factory() as session:
        assert [r["optimizer_run_id"] for r in list_optimizer_runs(engine, session, limit=1, **scope())] == ["newer"]


def test_history_uses_original_utc_decision_time_for_legacy_timezone_columns(history_db):
    engine, factory = history_db
    saved(engine, created_at="2026-10-02T19:19:14-04:00", params={"num_lineups": 1,
        "decision_snapshot": {"captured_at": "2026-10-02T19:19:14"}})
    with factory() as session:
        row = list_optimizer_runs(engine, session, **scope())[0]
    assert row["created_at"] == "2026-10-02T19:19:14+00:00"


def test_history_and_queue_api_are_scoped_and_idempotent(history_db):
    engine, factory = history_db
    app = FastAPI(); app.include_router(router)
    def override_session():
        with factory() as session:
            yield session
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_optimizer_service] = lambda: SimpleNamespace(engine=engine)
    client = TestClient(app)
    first = client.post("/api/optimizer/jobs", json=request())
    assert first.status_code == 202 and first.json()["created"]
    repeat = client.post("/api/optimizer/jobs", json=request())
    assert repeat.json()["job"]["job_id"] == first.json()["job"]["job_id"]
    assert repeat.json()["created"] is False
    assert client.post("/api/optimizer/jobs", json=request(params={"num_lineups": 1})).status_code == 409
    rows = client.get("/api/optimizer/runs", params=scope()).json()["runs"]
    assert rows[0]["optimizer_run_id"] == "queued-1" and rows[0]["status"] == "queued"
    assert client.get("/api/optimizer/runs", params={**scope(), "contest_format": "bad"}).status_code == 422
    assert client.get("/api/optimizer/runs", params={**scope(), "week": 3}).json()["runs"] == []


def test_worker_uses_stable_run_id_and_returns_only_result_reference(monkeypatch):
    from backend.app.services.job_handlers import _optimizer_handler
    from backend.app.product_services import optimizer
    calls = []
    def run_job(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(job_id="queued-1", status="completed", lineage_persisted=True, message="saved")
    monkeypatch.setattr(optimizer, "OptimizerService", lambda: SimpleNamespace(run_job=run_job))
    context = SimpleNamespace(run_id="queued-1", progress=lambda *args: None)
    assert _optimizer_handler(context, request()) == {"optimizer_run_id": "queued-1", "status": "completed"}
    assert calls[0]["optimizer_run_id"] == "queued-1" and calls[0]["projection_run_id"] == "projection-1"
    assert calls[0]["params"]["classic_expanded_discovery"] is True
    with pytest.raises(PermanentJobError, match="no run ID"):
        _optimizer_handler(SimpleNamespace(run_id=None), request())


def test_worker_does_not_claim_unsaved_or_failed_results_are_recoverable(monkeypatch):
    from backend.app.services.job_handlers import _optimizer_handler
    from backend.app.product_services import optimizer
    monkeypatch.setattr(optimizer, "OptimizerService", lambda: SimpleNamespace(run_job=lambda **kwargs:
        SimpleNamespace(status="failed", lineage_persisted=False, message="No legal roster")))
    with pytest.raises(PermanentJobError, match="No legal roster"):
        _optimizer_handler(SimpleNamespace(run_id="queued-1", progress=lambda *args: None), request())


def test_queued_game_cap_is_saved_exactly_and_invalid_cap_never_enqueues(history_db, monkeypatch):
    # Isolate queue payload normalization; real preparation gates have their own fixture.
    monkeypatch.setattr("backend.app.product_services.slate_preparation.validate_prepared_optimizer", lambda *_args, **_kwargs: None)
    engine, factory = history_db
    app = FastAPI(); app.include_router(router)
    def session_dependency():
        with factory() as session:
            yield session
    app.dependency_overrides[get_db_session] = session_dependency
    client = TestClient(app)
    payload = request(strategy="classic_large_gpp_v1", params={"num_lineups": 5, "max_exposure": .8, "max_lineups_per_primary_game": 3,
        "max_lineup_overlap": 4, "elevated_player_max_exposure": .4, "max_elevated_players_per_lineup": 0})
    response = client.post("/api/optimizer/jobs", json=payload)
    assert response.status_code == 202
    with factory() as session:
        claimed = claim_next_job(session, worker_id="cap-test", lease_seconds=300)
        assert claimed.request_json["params"] == payload["params"]
    for value in (0, -1, True, 2.5, "3"):
        invalid = {**payload, "optimizer_run_id": "invalid-cap", "params": {**payload["params"], "max_lineups_per_primary_game": value}}
        assert client.post("/api/optimizer/jobs", json=invalid).status_code == 422


def test_invalid_large_portfolio_controls_never_enqueue(history_db):
    engine, factory = history_db
    app = FastAPI(); app.include_router(router)
    def session_dependency():
        with factory() as session:
            yield session
    app.dependency_overrides[get_db_session] = session_dependency
    client = TestClient(app)
    for key, value in [("max_lineup_overlap", 9), ("elevated_player_max_exposure", 40),
                       ("max_elevated_players_per_lineup", True)]:
        assert client.post("/api/optimizer/jobs", json=request(strategy="classic_large_gpp_v1",
            params={key: value})).status_code == 422
    with factory() as session:
        assert list_optimizer_runs(engine, session, **scope()) == []


def test_saved_underfilled_failure_has_a_reopenable_report(history_db):
    engine, factory = history_db
    saved(engine, "underfilled", status="failed", message="Generated 2/5; no limits relaxed")
    with factory() as session:
        enqueue_job(session, job_type=OPTIMIZER_JOB, idempotency_key="optimizer:underfilled",
                    request_payload=request(optimizer_run_id="underfilled"), run_id="underfilled")
        rows = list_optimizer_runs(engine, session, **scope())
        # Pending retry does not expose a terminal result until it finishes.
        assert rows[0]["saved_report_available"] is True
        assert rows[0]["lineup_count"] == 2
        from backend.app.models import OperationalJob
        from sqlalchemy import select
        job = session.scalar(select(OperationalJob))
        job.status = "failed"; session.commit()
        row = list_optimizer_runs(engine, session, **scope())[0]
        assert row["saved_report_available"] is True and row["status"] == "failed"


def test_normal_history_retains_original_objectives_and_strategies(history_db):
    engine, factory = history_db
    saved(engine, "legacy-gpp")
    saved(engine, "active-cash", objective="cash", strategy="classic_single_lineup_v1", params={"num_lineups": 1})
    query = scope(); query.pop("objective")
    with factory() as session:
        rows = list_optimizer_runs(engine, session, **query)
    assert {(r["strategy"], r["objective"]) for r in rows} == {
        ("classic_small_field_gpp", "gpp"), ("classic_single_lineup_v1", "cash")}


def test_worker_finishes_saved_running_status_on_constraint_exception(monkeypatch):
    from copy import deepcopy
    from contextlib import nullcontext
    from backend.app.services import job_handlers
    from backend.app.product_services import optimizer
    frozen={'showdown_evidence_snapshot':{'sha256':'original','player_pool':[{'player_id':'canonical'}]}}
    original=deepcopy(frozen)
    job=SimpleNamespace(job_id='queued-1',status='running',message='Evidence frozen',params=frozen)
    saved=[]
    def fail(**kwargs):raise ValueError('Explicit leader preference needs history')
    service=SimpleNamespace(run_job=fail,get_job=lambda run_id:job,_persist_optimizer_run=lambda value:saved.append(value))
    monkeypatch.setattr(optimizer,'OptimizerService',lambda:service)
    monkeypatch.setattr(job_handlers,'SessionLocal',lambda:nullcontext(object()))
    monkeypatch.setattr('backend.app.product_services.slate_preparation.validate_prepared_optimizer',lambda *_args:None)
    with pytest.raises(PermanentJobError,match='Explicit leader preference'):
        job_handlers._optimizer_handler(SimpleNamespace(run_id='queued-1',progress=lambda *_args:None),request())
    assert saved==[job] and job.status=='failed' and 'needs history' in job.message
    assert job.params==original


def test_history_exposes_saved_download_clearance_without_loading_lineups(history_db):
    engine,factory=history_db
    saved(engine,'research',params={'entry_readiness':{'entry_ready':False},'preliminary_report':{'status':'research'}})
    saved(engine,'ready',params={'entry_readiness':{'entry_ready':True},'gpp_recommendation':{
        'policy_id':'gpp_projection_first_recommendation_v1','status':'provisional','optimizer_run_id':'ready'}})
    saved(engine,'wrong-recommendation',params={'gpp_recommendation':{
        'policy_id':'gpp_projection_first_recommendation_v1','status':'provisional','optimizer_run_id':'other'}})
    with factory() as session:rows={row['optimizer_run_id']:row for row in list_optimizer_runs(engine,session,**scope())}
    assert rows['research']['entry_ready'] is False and rows['research']['preliminary_export_blocked'] is True
    assert rows['ready']['entry_ready'] is True and rows['ready']['saved_recommendation_available'] is True
    assert not rows['wrong-recommendation']['saved_recommendation_available']
    assert 'constraint_config_json' not in rows['ready']


def test_highest_baseline_projection_mode_survives_saved_history(history_db):
    engine,factory=history_db
    saved(engine,params={'num_lineups':1,'classic_selection_objective':'baseline_mean','analyst_optimization_intent':'MIXED'})
    with factory() as session:
        rows=list_optimizer_runs(engine,session,**scope())
    assert rows[0]['classic_selection_objective']=='baseline_mean'
