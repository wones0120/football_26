from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import select, text

from backend.app.models import OperationalJob
from backend.app.product_services.slate_preparation import (
    SlatePreparationRequest, capture_source, digest, require_prelock,
    validate_prepared_optimizer, verify_consumption, verify_artifacts,
)
from backend.app.tests.product.slate_preparation_fixture import PreparationFixture
from backend.app.services.job_queue import enqueue_job


@pytest.fixture
def fixture(monkeypatch):
    monkeypatch.setattr("backend.app.product_services.analyst_personal_context.load_inputs", lambda engine: [])
    value = PreparationFixture()
    yield value
    value.close()


def enqueue(fixture, action="rebuild", key="fixture-build"):
    response = fixture.client.post("/api/slate/preparation/jobs", headers={"Idempotency-Key": key},
        json={"season": 2000, "week": 1, "slate": "SUNDAY_MAIN", "action": action})
    assert response.status_code == 202, response.text
    return response.json()["job"]["job_id"]


def optimizer_payload(result):
    return {"season": 2000, "week": 1, "slate": "SUNDAY_MAIN", "projection_run_id": result["projection_run_id"],
            "params": {"prepared_input_job_id": result["prepared_input_job_id"]}}


def test_real_queue_worker_persistence_and_consumption(fixture):
    enqueue(fixture, "markets", "fixture-capture"); capture = fixture.work()
    assert capture["result"]["operation"] == "Fetched new source evidence"
    job_id = enqueue(fixture)
    repeated = enqueue(fixture)
    assert repeated == job_id
    result = fixture.work()
    assert result["status"] == "completed", result
    assert fixture.calls == ["markets", "features", "projections"]
    status = fixture.client.get("/api/slate/preparation?season=2000&week=1&slate=SUNDAY_MAIN").json()
    build = status["latest_build"]
    assert status["build_current"] is True
    assert build["source_sha256"] == digest(result["result"]["source_manifest"])
    assert 'source_manifest' not in build
    assert build['audit_url'] == f'/api/jobs/{job_id}'
    assert build["consumption"]["market_snapshot_ids"] == ["synthetic-market-2"]
    assert build["consumption"]["weather_consumed"] is False
    assert status["inputs"]["markets"][0]["quote_freshness"].startswith("unknown")
    assert status["inputs"]["salaries"][0]["consumed_by_latest_prepared_build"] is True
    assert build["entry_ready"] is False
    with fixture.factory() as db:
        validate_prepared_optimizer(db, optimizer_payload(build))
        stored = db.execute(text("SELECT source_versions_json FROM target.feature_generation_run")).scalar()
        assert "slate_preparation" in stored and "synthetic-market-2" in stored
        assert db.scalar(select(OperationalJob).where(OperationalJob.job_id == job_id)).status == "completed"


def test_source_change_and_queued_or_failed_preparation_block_old_build(fixture):
    enqueue(fixture); fixture.work()
    result = fixture.client.get("/api/slate/preparation?season=2000&week=1&slate=SUNDAY_MAIN").json()["latest_build"]
    payload = optimizer_payload(result)
    with fixture.factory() as db:
        wrong = {**payload, "week": 2}
        with pytest.raises(ValueError, match="another season"):
            validate_prepared_optimizer(db, wrong)
        changed = deepcopy(payload); changed["params"]["exclude_questionable"] = True
        with pytest.raises(ValueError, match="scenario changed"):
            validate_prepared_optimizer(db, changed)
        changed = {**payload, "projection_run_id": "old-projection"}
        with pytest.raises(ValueError, match="does not match"):
            validate_prepared_optimizer(db, changed)
        fixture.manifest["markets"][0]["market_snapshot_id"] = "changed"
        with pytest.raises(ValueError, match="inputs changed"):
            validate_prepared_optimizer(db, payload)
    enqueue(fixture, "weather", "new-weather")
    with fixture.factory() as db, pytest.raises(ValueError, match="newer preparation"):
        validate_prepared_optimizer(db, payload)
    fixture.fail_capture = True
    assert fixture.work()["status"] == "failed"
    with fixture.factory() as db, pytest.raises(ValueError, match="newer preparation"):
        validate_prepared_optimizer(db, payload)


def test_failed_consumption_cannot_publish_a_prepared_build(fixture):
    fixture.corrupt = True; enqueue(fixture)
    result = fixture.work()
    assert result["status"] == "failed"
    assert "not consumed" in result["error_message"]
    status = fixture.client.get("/api/slate/preparation?season=2000&week=1&slate=SUNDAY_MAIN").json()
    assert status["latest_build"] is None


def test_failed_first_import_visible_without_salary_scope(fixture):
    enqueue(fixture, "salary", "missing-salary")
    fixture.work()
    with patch("backend.app.product_services.slate_preparation.source_manifest", side_effect=ValueError("Load the correct salary CSV first")):
        status = fixture.client.get("/api/slate/preparation?season=2000&week=1&slate=SUNDAY_MAIN").json()
    assert status["jobs"][0]["action"] == "salary"
    assert status["limitations"] == ["Load the correct salary CSV first"]


def test_lock_idempotency_conflict_and_read_only_history(fixture):
    with fixture.factory() as db:
        saved, _ = enqueue_job(db, job_type="optimizer_run", idempotency_key="frozen-reference",
            request_payload={"synthetic": True}, run_id="synthetic-reference")
        saved.status = "completed"; saved.result_json = {"readiness": "BLOCKED", "observed_at": "old-original-clock"}
        db.commit(); original = deepcopy(saved.result_json); saved_id = saved.job_id
    before = deepcopy(fixture.manifest)
    fixture.client.get("/api/slate/preparation?season=2000&week=1&slate=SUNDAY_MAIN")
    assert before == fixture.manifest and fixture.calls == []
    enqueue(fixture)
    conflict = fixture.client.post("/api/slate/preparation/jobs", headers={"Idempotency-Key": "fixture-build"},
        json={"season": 2000, "week": 1, "slate": "SUNDAY_MAIN", "action": "weather"})
    assert conflict.status_code == 409
    fixture.manifest["games"][0]["kickoff_at"] = "2000-01-01T17:00:00+00:00"
    assert "lock has passed" in fixture.work()["error_message"]
    with fixture.factory() as db:
        assert db.get(OperationalJob, saved_id).result_json == original


def test_optimizer_queue_receipt_skips_expensive_audit_but_worker_rejects_changed_dependencies(fixture):
    enqueue(fixture); fixture.work()
    build = fixture.client.get("/api/slate/preparation?season=2000&week=1&slate=SUNDAY_MAIN").json()["latest_build"]
    payload = {**optimizer_payload(build), "strategy": "classic_large_gpp_v1", "contest_format": "classic", "objective": "gpp"}
    with fixture.factory() as db:
        db.execute(text("UPDATE target.feature_player_game SET feature_json='{}'")); db.commit()
    payload["optimizer_run_id"] = "slow-audit-regression"
    with patch("backend.app.product_services.slate_preparation.source_manifest", side_effect=AssertionError("No heavy source audit before receipt")):
        response = fixture.client.post("/api/optimizer/jobs", json=payload)
        repeated = fixture.client.post("/api/optimizer/jobs", json=payload)
    assert response.status_code == repeated.status_code == 202
    assert response.json()["job"]["job_id"] == repeated.json()["job"]["job_id"]
    assert repeated.json()["created"] is False
    from backend.app.services.job_queue import claim_next_job
    from backend.app.worker import execute_claimed_job
    with fixture.factory() as db:
        job = claim_next_job(db, worker_id="fixture-worker")
    execute_claimed_job(job_id=job.job_id, job_type=job.job_type, request_payload=job.request_json,
        worker_id="fixture-worker", run_id=job.run_id, checkpoint=job.checkpoint_json, lease_seconds=300)
    with fixture.factory() as db:
        saved = db.get(OperationalJob, job.job_id)
        assert saved.status == "failed" and "lineage changed" in saved.error_message


def test_readiness_retains_preparation_limitations_without_entry_clearance():
    from backend.app.tests.product.test_classic_large_gpp_readiness import frame, assess
    from backend.app.product_services.classic_prospective import digest_payload
    from backend.app.product_services.classic_strategy_contract import digest as contract_digest
    contract, snapshot, lineups = frame()
    snapshot["payload"]["parameters"]["prepared_input_evidence"] = {"prepared_input_job_id": "synthetic-prep",
        "projection_run_id": "synthetic-projection", "source_sha256": "synthetic-source-sha"}
    snapshot["sha256"] = digest_payload(snapshot["payload"])
    contract["metadata"]["input_snapshot_sha256"] = snapshot["sha256"]
    contract["sha256"] = contract_digest({k: v for k, v in contract.items() if k != "sha256"})
    readiness = assess(contract, snapshot, lineups)
    assert readiness["checks"]["Prepared input dependency lineage"]["status"] == "PASS"
    assert "unknown" in readiness["checks"]["Upstream market quote publication freshness"]["reason"]
    assert readiness["entry_ready"] is False


def test_actual_collector_interfaces_and_clock_preservation():
    request = SlatePreparationRequest(season=2000, week=1, slate="SUNDAY_MAIN", action="weather", allow_free_weather_evaluation=True)
    games = [{"game_id": "canonical-game", "kickoff_at": "2099-01-01T17:00:00+00:00"}]
    with patch("backend.app.product_services.slate_preparation.subprocess.run") as run:
        run.return_value.returncode = 0; run.return_value.stdout = '{"fixture":true}'
        capture_source(request, games)
        args = run.call_args.args[0]
        assert args[-1] == "--allow-free-evaluation" and "--apply" in args
        assert args[args.index("--game-id") + 1] == "canonical-game"
        assert "--slate-lock-at" in args and "--watch" not in args
        request.action = "markets"
        capture_source(request, games)
        args = run.call_args.args[0]
        assert args[1].endswith("capture_nflverse_markets.py")
        assert args[args.index("--provider") + 1] == "espn"
        assert "--apply" not in args and "--game-id" not in args
    with pytest.raises(ValueError, match="lock has passed"):
        require_prelock(games, datetime(2099, 1, 1, 17, tzinfo=UTC))


def test_artifact_checksums_and_availability_consumption(tmp_path):
    file = tmp_path / "source.csv"; file.write_text("fixture")
    manifest = {"salaries": [{"source_path": str(file), "source_checksum": "wrong", "ingest_status": "completed"}], "markets": []}
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_artifacts(manifest)
    manifest = {"salaries": [{"curated_salary_id": 1}], "markets": [], "starters": [],
                "availability": [{"player_master_id": "p", "pregame_player_context_id": 2}]}
    rows = [{"game_id": "g", "player_id": "p", "feature_json": {"pregame_context_row_id": 1}}]
    with pytest.raises(ValueError, match="Availability evidence was not consumed"):
        verify_consumption(manifest, rows, {"salary_row_ids": [1]})
    rows[0]["feature_json"]["pregame_context_row_id"] = 2
    assert verify_consumption(manifest, rows, {"salary_row_ids": [1]})["availability_row_ids"] == ["2"]


def prepared_refresh(build):
    return {"projection_run_id": build["projection_run_id"],
            "ownership_run_id": "prepared-ownership", "data_cutoff_at": datetime.now(UTC),
            "report": {"projection": {"status": "completed", "result": build}}}


def test_prepare_job_publishes_ready_build_and_revalidates_without_collectors(fixture):
    enqueue(fixture); build = fixture.work()['result']
    with patch("backend.app.product_services.classic_data_readiness.refresh_live_sources", return_value=prepared_refresh(build)) as refresh, \
         patch("backend.app.product_services.slate_preparation.assess_prepared_inputs", return_value={"status": "READY", "reason_codes": []}):
        enqueue(fixture, "prepare", "prepare-ready")
        completed = fixture.work()
        assert completed["status"] == "completed", completed
        status = fixture.client.get("/api/slate/preparation?season=2000&week=1&slate=SUNDAY_MAIN").json()
        assert status["build_current"]
        prepared = status["latest_build"]
        assert prepared["action"] == "prepare" and prepared["ownership_run_id"] == "prepared-ownership"
        payload = {**optimizer_payload(prepared), "contest_format": "classic"}
        with fixture.factory() as db:
            for _ in range(2):
                evidence = validate_prepared_optimizer(db, payload)
                assert evidence["ownership_run_id"] == "prepared-ownership"
            with pytest.raises(ValueError, match="contest format"):
                validate_prepared_optimizer(db, {**payload, "contest_format": "showdown"})
        refresh.assert_called_once()
    with patch("backend.app.product_services.slate_preparation.assess_prepared_inputs", return_value={"status": "NOT_READY", "reason_codes": ["projection_stale"]}):
        status = fixture.client.get("/api/slate/preparation?season=2000&week=1&slate=SUNDAY_MAIN").json()
        assert not status["build_current"]
        assert "projection_stale" in status["build_issue"]
        with fixture.factory() as db, pytest.raises(ValueError, match="no longer ready"):
            validate_prepared_optimizer(db, payload)


def test_failed_prepare_keeps_source_checks_upstream_and_supersedes_old_build(fixture):
    enqueue(fixture); fixture.work()
    build = fixture.client.get("/api/slate/preparation?season=2000&week=1&slate=SUNDAY_MAIN").json()["latest_build"]
    with patch("backend.app.product_services.classic_data_readiness.refresh_live_sources", return_value={
        "projection_run_id": None, "ownership_run_id": None, "data_cutoff_at": datetime.now(UTC),
        "report": {"projection": {"status": "blocked", "reason": "Unresolved canonical player evidence"}}}):
        enqueue(fixture, "prepare", "prepare-blocked")
        failed = fixture.work()
    assert failed["status"] == "failed"
    assert "Unresolved canonical" in failed["error_message"]
    status = fixture.client.get("/api/slate/preparation?season=2000&week=1&slate=SUNDAY_MAIN").json()
    assert not status["build_current"] and status["latest_build"] is None
    assert status["jobs"][0]["checkpoint"]["preparation_result"]["source_refresh"]["projection"]["status"] == "blocked"
    with fixture.factory() as db, pytest.raises(ValueError, match="newer preparation"):
        validate_prepared_optimizer(db, optimizer_payload(build))


def test_live_optimizer_enqueue_requires_preparation_before_creating_job(fixture):
    with patch("backend.app.product_services.showdown_data_readiness.is_live_slate", return_value=True):
        response = fixture.client.post("/api/optimizer/jobs", json={
            "season": 2026, "week": 5, "slate": "SUNDAY_MAIN", "strategy": "classic_single_lineup_v1",
            "contest_format": "classic", "objective": "cash", "params": {}})
    assert response.status_code == 409
    assert "Prepare slate" in response.json()["detail"]
    with fixture.factory() as db:
        assert list(db.scalars(select(OperationalJob))) == []


def test_weekly_readiness_runs_durable_preparation_before_predict_and_reuses_it(fixture):
    from backend.app.product_services.slate_preparation import run_weekly_preparation
    from backend.app.services.weekly_orchestrator import DefaultWeeklyStageExecutor
    from backend.app.weekly_schemas import WeeklyRunRequest
    enqueue(fixture); build = fixture.work()['result']
    request = WeeklyRunRequest(season=2000, week=1, slate="SUNDAY_MAIN", refresh_projections=True)
    executor = DefaultWeeklyStageExecutor(fixture.factory)
    with patch("backend.app.product_services.showdown_data_readiness.is_live_slate", return_value=True), \
         patch("backend.app.product_services.classic_data_readiness.refresh_live_sources", return_value=prepared_refresh(build)) as refresh, \
         patch("backend.app.product_services.slate_preparation.assess_prepared_inputs", return_value={"status": "READY", "reason_codes": []}):
        outcome = executor._readiness(request, {"preparation_key": "weekly-test"}, {})
        assert outcome.result["status"] == "READY"
        assert outcome.artifact_ids["prepared_input_job_id"]
        same = executor._readiness(request, {"preparation_key": "weekly-test"}, {})
        assert same.artifact_ids == outcome.artifact_ids
        predicted = executor._predict(request, {}, {"readiness": outcome.artifact_ids})
        assert predicted.artifact_ids["projection_run_id"] == build["projection_run_id"]
        refresh.assert_called_once()


def test_weekly_preparation_failure_is_durable_and_retryable_upstream(fixture):
    from backend.app.product_services.slate_preparation import run_weekly_preparation
    from backend.app.services.job_queue import PermanentJobError
    request = SlatePreparationRequest(season=2000, week=1, slate="SUNDAY_MAIN", action="prepare")
    with patch("backend.app.product_services.slate_preparation.prepare_optimizer_inputs", side_effect=PermanentJobError("Provider unavailable")):
        failed = run_weekly_preparation(fixture.factory, request, idempotency_key="weekly-retry")
    assert failed.status == "failed" and failed.error_message == "Provider unavailable"
    with patch("backend.app.product_services.slate_preparation.prepare_optimizer_inputs", return_value={"data_readiness": {"status": "READY"}}):
        retried = run_weekly_preparation(fixture.factory, request, idempotency_key="weekly-retry")
    assert retried.status == "completed" and retried.job_id == failed.job_id
    assert retried.attempt_count == 2


def test_live_training_audit_follows_current_features_and_precedes_projection(fixture):
    from backend.app.product_services import slate_preparation
    original = slate_preparation.execute_preparation
    def live(context, payload):
        return original(context, payload, refresh_training_before_cutoff=True)
    with patch.object(slate_preparation, "execute_preparation", side_effect=live), \
         patch("backend.app.product_services.showdown_data_readiness.refresh_training_labels",
               side_effect=lambda *args, **kwargs: fixture.calls.append("training_labels")):
        enqueue(fixture)
        result = fixture.work()
    assert result["status"] == "completed", result
    assert fixture.calls == ["features", "training_labels", "projections"]


def test_status_history_scopes_in_sql_and_defers_heavy_audits(fixture):
    from sqlalchemy import inspect
    from backend.app.product_services.slate_preparation import preparation_jobs, preparation_summary
    job_id = enqueue(fixture)
    fixture.client.post('/api/slate/preparation/jobs', headers={'Idempotency-Key':'another-week'},
        json={'season':2000,'week':2,'slate':'SUNDAY_MAIN','action':'rebuild'})
    with fixture.factory() as db:
        jobs = preparation_jobs(db, SlatePreparationRequest(season=2000,week=1,slate='sunday_main',action='rebuild'))
        assert [j.job_id for j in jobs] == [job_id]
        assert {'result_json','checkpoint_json'} <= inspect(jobs[0]).unloaded
    raw = {'source_sha256':'hash','source_manifest':{'large':'immutable'},
           'data_readiness':{'status':'READY','reason_codes':[],'players':['large']},
           'source_refresh':{'projection':{'status':'blocked','reason':'missing source','result':{'large':'audit'}}}}
    summary = preparation_summary(raw)
    assert 'source_manifest' not in summary
    assert summary['data_readiness'] == {'status':'READY','reason_codes':[]}
    assert summary['source_refresh']['projection'] == {'status':'blocked','reason':'missing source'}
    assert raw['source_manifest'] == {'large':'immutable'}


def test_display_summary_retains_scores_missingness_and_model_refs_without_nested_audits():
    import copy
    from backend.app.product_services.slate_preparation import preparation_summary, preparation_input_summary
    large = {'raw_history': ['evidence'] * 1000}
    player = {'player_master_id': 'canonical', 'name': 'Player', 'team': 'CHI',
              'conditional_mean': None, 'supported_components': [], 'missing_evidence': ['unknown workload'],
              'new_model_evidence': large, 'native_salary_actor': True, 'counts': {'targets': None},
              'reasons': ['missing participation'], 'position': 'WR', 'utility': None}
    raw = {'scenario_mode': {'sha256': 'original-full-receipt', 'players': [player],
        'primary_model_forecast': {'players': [player], 'team_model_consumption': {
            'model_publication_record_id': 'publication', 'model_refs': ['tree', 'neural'], 'inference_rows': large},
            'all_player_audit': {'errors': [], 'unknown_native_scores': 1}}},
        'workload_forecast': {'sha256': 'full-count-receipt', 'players': [player], 'raw_history': large}}
    original = copy.deepcopy(raw)
    summary = preparation_summary(raw)
    assert raw == original
    assert summary['scenario_mode']['sha256'] == 'original-full-receipt'
    compact = summary['scenario_mode']['players'][0]
    assert compact['conditional_mean'] is None and compact['missing_evidence'] == ['unknown workload']
    assert 'new_model_evidence' not in compact
    primary = summary['scenario_mode']['primary_model_forecast']
    assert 'players' not in primary and 'inference_rows' not in primary['team_model_consumption']
    assert primary['team_model_consumption']['model_publication_record_id'] == 'publication'
    assert summary['workload_forecast']['players'][0]['counts']['targets'] is None
    manifest = {'availability': [{'context_run_id': 'source-context', 'injury_status': 'Q',
        'observed_at': 'original-clock', 'evidence_json': {'source_facts': large,
            'canonical_context_reason_codes': ['missing practice'], 'designation_resolution': {
                'status': 'conflict', 'effective_designation': None, 'source_facts': large}}}], 'starters': []}
    before = copy.deepcopy(manifest)
    inputs = preparation_input_summary(manifest)
    assert manifest == before
    row = inputs['availability'][0]
    assert row['context_run_id'] == 'source-context' and row['injury_status'] == 'Q'
    assert row['observed_at'] == 'original-clock' and row['evidence_detail_omitted']
    assert row['evidence_json']['canonical_context_reason_codes'] == ['missing practice']
    assert row['evidence_json']['designation_resolution'] == {'status': 'conflict', 'effective_designation': None}
    assert 'source_facts' not in row['evidence_json']


def test_learned_opportunities_require_explicit_normal_showdown_prepare():
    payload=dict(season=2026,week=7,slate='THURSDAY_NIGHT',action='prepare',
        contest_format='showdown',learned_opportunities=True)
    assert SlatePreparationRequest(**payload).include_workload_forecast
    for change in ({'contest_format':'classic'},{'action':'rebuild'},{'preliminary_research':True},
                   {'reuse_prepared_input_job_id':'11111111-1111-1111-1111-111111111111'}):
        with pytest.raises(ValueError,match='Learned opportunities'):
            SlatePreparationRequest(**{**payload,**change})


def test_preliminary_request_is_explicit_classic_only_and_cannot_certify_normal_optimizer(fixture):
    for changed in ({'contest_format':'showdown'}, {'availability_overrides':[{'player_id':'canonical','availability':'assume_out'}]}, {'action':'markets'}):
        payload={'season':2000,'week':1,'slate':'SUNDAY_MAIN','action':'prepare','preliminary_research':True,**changed}
        assert fixture.client.post('/api/slate/preparation/jobs',json=payload).status_code==422
    job_id=enqueue(fixture);fixture.work()
    with fixture.factory() as db:
        job=db.get(OperationalJob,job_id)
        job.request_json={**job.request_json,'preliminary_research':True};db.commit()
        with pytest.raises(ValueError,match='cannot certify normal optimization'):
            validate_prepared_optimizer(db,{'season':2000,'week':1,'slate':'SUNDAY_MAIN','params':{'prepared_input_job_id':job_id}})


def test_showdown_preparation_binds_the_salary_floor_before_new_players_can_enter(fixture):
    enqueue(fixture)
    build = fixture.work()["result"]
    with patch("backend.app.product_services.showdown_data_readiness.refresh_live_sources", return_value=prepared_refresh(build)), \
         patch("backend.app.product_services.slate_preparation.assess_prepared_inputs", return_value={"status": "READY", "reason_codes": []}):
        response = fixture.client.post("/api/slate/preparation/jobs", headers={"Idempotency-Key": "floor-bound-prepare"},
            json={"season": 2000, "week": 1, "slate": "SUNDAY_MAIN", "action": "prepare",
                  "contest_format": "showdown", "minimum_player_salary": 1700})
        assert response.status_code == 202, response.text
        completed = fixture.work()
        assert completed["status"] == "completed", completed
        prepared = {**completed["result"], "prepared_input_job_id": response.json()["job"]["job_id"]}
        assert prepared["minimum_player_salary"] == 1700
        payload = {**optimizer_payload(prepared), "contest_format": "showdown"}
        with fixture.factory() as db:
            for value in [1700, 2000]:
                validate_prepared_optimizer(db, {**payload, "params": {**payload["params"], "minimum_player_salary": value}}, verify_current=False)
            for value in [None, 200]:
                with pytest.raises(ValueError, match="salary was lowered"):
                    validate_prepared_optimizer(db, {**payload, "params": {**payload["params"], "minimum_player_salary": value}}, verify_current=False)
