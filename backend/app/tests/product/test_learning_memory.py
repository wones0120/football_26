from copy import deepcopy
import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
import weakref

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.app.api import product_routes
from backend.app.product_services import optimizer
from backend.app.product_services.optimizer import OptimizerJob, OptimizerService
from backend.app.product_services.optimizer_effectiveness import build_optimizer_effectiveness, correlation_samples, _digest
from backend.app.product_services.slate_learning import SlateLearningService, build_slate_learning_report, build_weekly_learning_report, _canonical_hash, _json_value
from backend.app.tests.product.test_slate_learning import complete_evidence, NOW


def memory_fixture():
    evidence = complete_evidence()
    candidate = {"players": [{"player_id": "alpha", "slot": "CPT"}] + [
        {"player_id": name, "slot": "FLEX"} for name in ("beta", "gamma", "delta", "epsilon", "zeta")],
        "mean": 60, "p90": 80, "objective_score": 10,
        "games_represented": ["AAA@BBB 09/14/2026 08:00PM ET"]}
    configs = {}
    evidence["optimizer_runs"] = []
    for run_id in ("optimizer-1", "unrelated", "diagnostic"):
        configs[run_id] = {"strategy_runtime": {"small_max": {"all_candidates": [candidate]}}}
        evidence["optimizer_runs"].append({"optimizer_run_id": run_id, "contest_format": "showdown",
            "strategy": "showdown_gpp_captain_informed_v2", "data_cutoff_at": NOW,
            "optimizer_created_at": NOW, "configuration_hash": run_id})
    for name in ("gamma", "delta", "epsilon", "zeta"):
        evidence["observations"].append({"player_id": name, "roster_position": "FLEX",
            "actual_points": 5, "resolution_status": "resolved", "contest_id": "contest-1"})
    return evidence, configs


def test_compact_policy_preserves_linked_metrics_and_loads_one_config_at_a_time():
    evidence, configs = memory_fixture()
    legacy = deepcopy(evidence)
    for run in legacy["optimizer_runs"]:
        run["constraint_config_json"] = configs[run["optimizer_run_id"]]
    baseline = build_slate_learning_report(season=2026, week=1, slate="SUNDAY_NIGHT",
        entry_user="wones0120", evidence=legacy, generated_at=NOW)
    class Config(dict):
        pass
    loaded = []
    live = []
    details = {}
    def load(run_id):
        assert all(reference() is None for reference in live)
        config = Config(deepcopy(configs[run_id]))
        live.append(weakref.ref(config))
        loaded.append(run_id)
        return {"constraint_config_json": config}
    def save(run):
        details[run["optimizer_run_id"]] = deepcopy(run)
        return {"detail_id": run["optimizer_run_id"], "candidate_count": len(run["candidates"])}
    report = build_slate_learning_report(season=2026, week=1, slate="SUNDAY_NIGHT",
        entry_user="wones0120", evidence=evidence, generated_at=NOW,
        run_loader=load, detail_sink=save, diagnostic_run_ids=["diagnostic"])
    assert loaded == ["optimizer-1", "diagnostic"]
    assert report["contract_id"] == "slate_learning_report_v2"
    assert report["summary"] == baseline["summary"]
    assert report["entries"] == baseline["entries"]
    assert report["missing_evidence"] == baseline["missing_evidence"]
    policy = report["optimizer_effectiveness"]["inclusion_policy"]
    assert policy["excluded_runs"] == [{"optimizer_run_id": "unrelated", "reason": "unrelated_completed_run", "configuration_hash": "unrelated"}]
    old = next(run for run in baseline["optimizer_effectiveness"]["runs"] if run["optimizer_run_id"] == "optimizer-1")
    for key, value in old.items():
        assert details["optimizer-1"][key] == value
    assert all("candidates" not in run for run in report["optimizer_effectiveness"]["runs"])
    assert details["diagnostic"]["inclusion_reason"] == "explicit_diagnostic_request"


def test_unscoped_diagnostic_is_rejected_before_loading_configuration():
    evidence, _ = memory_fixture()
    load = MagicMock()
    with pytest.raises(ValueError, match="requested slate"):
        build_optimizer_effectiveness({"entries": [], "run_ids": {}}, evidence,
            run_loader=load, diagnostic_run_ids=["other-week"])
    load.assert_not_called()


def test_numeric_correlation_samples_preserve_exact_aggregate_calibration():
    evidence, configs = memory_fixture()
    for run in evidence["optimizer_runs"]:
        run["constraint_config_json"] = configs[run["optimizer_run_id"]]
    report = build_slate_learning_report(season=2026, week=1, slate="SUNDAY_NIGHT",
        entry_user="wones0120", evidence=evidence, generated_at=NOW)
    past = deepcopy(report)
    past.update(week=2, slate="THURSDAY_NIGHT")
    legacy = build_weekly_learning_report(season=2026, week=2, entry_user="wones0120",
        slate_reports=[past], historical_slate_reports=[report])
    compact = build_weekly_learning_report(season=2026, week=2, entry_user="wones0120",
        slate_reports=[past], historical_slate_reports=[report],
        correlation_loader=lambda _, run: correlation_samples(run["candidates"]))
    assert compact["contract_id"] == "weekly_learning_report_v2"
    assert compact["optimizer_correlation_aggregate"] == legacy["optimizer_correlation_aggregate"]


def test_paginated_candidate_api_bounds_and_legacy_route_compatibility():
    service = MagicMock()
    service.candidate_detail.return_value = {"contract_id": "learning_candidate_page_v1", "rows": [], "total": 0}
    app = FastAPI()
    app.include_router(product_routes.router)
    app.dependency_overrides[product_routes.get_slate_learning_service] = lambda: service
    client = TestClient(app)
    url = "/api/learning/reports/legacy-report/optimizer-runs/run-1/candidates"
    assert client.get(url + "?offset=0&limit=100").status_code == 200
    service.candidate_detail.assert_called_once_with("legacy-report", "run-1", offset=0, limit=100)
    assert client.get(url + "?limit=201").status_code == 422
    assert client.get(url + "?offset=-1").status_code == 422
    service.candidate_detail.return_value = None
    assert client.get(url).status_code == 404


def test_completed_optimizer_cache_is_bounded_and_evicted_jobs_reload(monkeypatch):
    monkeypatch.setattr(optimizer, "get_settings", lambda: SimpleNamespace(
        optimizer_result_cache_max_entries=2, optimizer_result_cache_ttl_seconds=60))
    clock = [100.0]
    monkeypatch.setattr(optimizer, "monotonic", lambda: clock[0])
    service = OptimizerService()
    persisted = {}
    for index in range(20):
        job = OptimizerJob(str(index), "completed", NOW, NOW, 2026, 4, "SUNDAY_MAIN", "test",
            "classic", "gpp", {"saved": index}, lineage_persisted=True, results=[[{"player_id": str(index)}]])
        persisted[job.job_id] = job
        clock[0] += 1
        service._cache_job(job)
        assert len(service._jobs) <= 2
    service._load_persisted_job = MagicMock(side_effect=persisted.get)
    assert service.get_job("0").results == persisted["0"].results
    service._load_persisted_job.assert_called_once_with("0")
    clock[0] += 61
    assert service.cache_status()["entries"] == 0
    assert service.get_job("19").params == persisted["19"].params


def test_streamed_hashes_keep_the_saved_canonical_representation():
    value = {"a": [{"canonical_id": "player-1", "slots": ("CPT", "FLEX")}], "cutoff": NOW}
    assert _digest(value) == hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    assert _canonical_hash(value) == hashlib.sha256(json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def test_frozen_drilldown_missing_evidence_fails_explicitly():
    service = SlateLearningService(engine=MagicMock())
    service._rows = MagicMock(return_value=[{"detail_missing": True}])
    with pytest.raises(ValueError, match="candidate evidence is missing"):
        service.candidate_detail("report", "run")
    with pytest.raises(ValueError, match="entry evidence is missing"):
        service.entry_detail("report", "entry", "contest")


def test_weekly_hash_includes_the_exact_historical_reports():
    evidence, configs = memory_fixture()
    for run in evidence["optimizer_runs"]:
        run["constraint_config_json"] = configs[run["optimizer_run_id"]]
    past = build_slate_learning_report(season=2026, week=1, slate="SUNDAY_NIGHT",
        entry_user="wones0120", evidence=evidence, generated_at=NOW)
    current = deepcopy(past)
    current.update(week=2, report_id="current")
    def build():
        return build_weekly_learning_report(season=2026, week=2, entry_user="wones0120",
            slate_reports=[current], historical_slate_reports=[past],
            correlation_loader=lambda _, run: correlation_samples(run["candidates"]))
    initial = build()
    assert build()["evidence_hash"] == initial["evidence_hash"]
    past["report_id"] = "corrected-history"
    assert build()["evidence_hash"] != initial["evidence_hash"]
