from copy import deepcopy
from dataclasses import asdict, replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.product_routes import router
from backend.app.product_dependencies import get_optimizer_service
from backend.app.product_services.classic_large_gpp_readiness import assess_large_gpp_saved_inputs
from backend.app.product_services.classic_prospective import digest_payload
from backend.app.product_services.classic_strategy_contract import build_strategy_contract
from backend.app.tests.product.test_classic_strategy_contract import options, pool


def frame(observed="2026-10-04T14:00:00+00:00", missing_source=False):
    players = [replace(p, game_id=f"{p.team}@{p.opponent} 10/04/2026 01:00PM ET",
                       game_total=44, spread=0, team_total=22,
                       market_context_point_in_time_safe=True) for p in pool()]
    rows = [{**asdict(p), "tags": list(p.tags), "player_team": p.team, "opponent_team": p.opponent,
             "market_observed_at": observed,
             "market_source_system": None if missing_source else "fixture_market"} for p in players]
    payload = {"metadata": {"created_at": "2026-10-04T15:45:00+00:00"},
               "parameters": {}, "final_solver_rows": rows}
    snapshot = {"payload": payload, "sha256": digest_payload(payload)}
    contract = build_strategy_contract(players=players,
        pipeline_options={**options(), "num_lineups": 1, "max_exposure": 1}, requested={},
        metadata={"input_snapshot_sha256": snapshot["sha256"]})
    ids = ["AAA-QB-0", "AAA-WR-0", "AAA-WR-1", "BBB-RB-0", "CCC-RB-0",
           "BBB-WR-0", "CCC-TE-0", "DDD-WR-0", "EEE-DST-0"]
    lineups = [[{"player_id": pid} for pid in ids]]
    return contract, snapshot, lineups


def assess(contract, snapshot, lineups):
    return assess_large_gpp_saved_inputs(contract=contract, snapshot=snapshot,
        lineups=lineups, salary_identity={"status": "PASS"},
        assessed_at=datetime(2026, 10, 4, 15, 46, tzinfo=UTC))


def test_large_reuses_market_policy_without_small_candidate_or_automatic_risk_rules():
    ready = assess(*frame())
    assert ready["checks"]["Market/game environment"]["status"] == "PASS"
    assert ready["market_coverage"]["sourced_games"] == 6
    assert "Candidate-pool size" not in ready["checks"]
    assert ready["entry_ready"] is False  # Current clearance remains unavailable.
    assert ready["current_entry_clearance"] == "UNEVALUATED"
    assert assess(*frame("2026-10-02T02:37:35+00:00"))["checks"]["Market/game environment"]["status"] == "BLOCKER"
    assert assess(*frame(None))["checks"]["Market/game environment"]["status"] == "DEVELOPMENT_PREVIEW"
    assert assess(*frame(missing_source=True))["checks"]["Market source provenance"]["status"] == "DEVELOPMENT_PREVIEW"


def test_checksum_failure_cannot_substitute_current_inputs():
    contract, snapshot, lineups = frame()
    snapshot["payload"]["final_solver_rows"][0]["projection"] = 999
    with pytest.raises(ValueError, match="checksum"):
        assess(contract, snapshot, lineups)


def test_saved_validation_endpoint_is_separate_and_never_persists_or_solves():
    contract, snapshot, lineups = frame()
    job = SimpleNamespace(strategy="classic_large_gpp_v1", status="completed", results=lineups,
        params={"effective_strategy_contract": contract,
                "strategy_runtime": {"classic_run_input_snapshot": snapshot}})
    before = deepcopy(job.__dict__)
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_optimizer_service] = lambda: SimpleNamespace(get_job=lambda _: job, engine=None)
    with patch("backend.app.product_services.classic_large_gpp_readiness.saved_salary_identity", return_value={"status": "PASS"}), patch("backend.app.product_services.optimizer.OptimizerService.run_job", side_effect=AssertionError("Must not solve")):
        response = TestClient(app).post("/api/optimizer/results/saved/readiness")
    assert response.status_code == 200
    assert response.json()["scope"] == "present-time assessment of frozen saved inputs; original readiness unchanged"
    assert response.json()["original_decision_at"] == "2026-10-04T15:45:00+00:00"
    assert response.json()["assessed_at"] != response.json()["original_decision_at"]
    assert job.__dict__ == before
    assert "entry_readiness" not in job.params
