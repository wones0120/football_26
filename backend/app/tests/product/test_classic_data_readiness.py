from backend.app.tests.product.prepared_optimizer_fixture import prepared_optimizer
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from backend.app.config import get_settings
from backend.app.product_services import classic_data_readiness as gate
from backend.app.product_services.optimizer import OptimizerService
from backend.app.product_services.showdown_player_context import CONTEXT_CONTRACT
from backend.app.tests.product.test_classic_strategy_contract import pool

NOW = datetime.now(UTC)
CUT = NOW - timedelta(seconds=30)
OBS = CUT - timedelta(minutes=5)
PROJECTION = str(uuid5(NAMESPACE_URL, "classic-ready-projection"))
OWNERSHIP = str(uuid5(NAMESPACE_URL, "classic-ready-ownership"))


def fixture():
    teams = dict(zip(["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"], ["ARI", "BUF", "CHI", "DAL", "DEN", "DET"]))
    games = [{"game_id": f"game-{i}", "home_team": teams[a], "away_team": teams[b],
              "kickoff_at": (NOW + timedelta(days=2)).astimezone(ZoneInfo("America/New_York")).replace(hour=13, minute=0, second=0, microsecond=0).isoformat()} for i, (a,b) in enumerate([("AAA","BBB"),("CCC","DDD"),("EEE","FFF")])]
    rows, salaries, markets = [], [], []
    for i,g in enumerate(games):
        markets.append(dict(market_snapshot_id=f"market-{i}", source_snapshot_id=f"source-{i}",
            content_sha256="market-checksum", source="fixture_market", game_id=g["game_id"], game_total=48.,
            home_spread=0., observed_at=OBS.isoformat(), ingested_at=OBS.isoformat()))
    for i,p in enumerate(pool()):
        pid = str(uuid5(NAMESPACE_URL, p.player_id)); team, opponent = teams[p.team], teams[p.opponent]
        g = next(g for g in games if team in {g["home_team"],g["away_team"]}); mi=games.index(g)
        r = dict(player_id=pid, name=p.name, player_team=team, opponent_team=opponent, position=p.position,
            salary=p.salary, salary_source_row_id=str(i), salary_ingest_run_id="salary-ingest", dk_player_id=str(i),
            salary_status_eligible=True, identity_resolved=True, projection_run_id=PROJECTION,
            projection=p.projection, p90=p.ceiling, projection_inputs_complete=True, feature_inputs_complete=True,
            projection_model_version="fixture-model", projection_observed_at=CUT.isoformat(),
            projection_created_at=(CUT+timedelta(seconds=5)).isoformat(), data_cutoff_at=CUT.isoformat(),
            canonical_context_contract=CONTEXT_CONTRACT, availability_state="AVAILABLE", availability_status="ACTIVE",
            availability_source="official", availability_source_ids=["status-1"], availability_observed_at=OBS.isoformat(),
            canonical_role="expected_starter", role_source="depth", role_source_ids=["depth-1"],
            role_observed_at=OBS.isoformat(), canonical_context_reason_codes=[], role_optimizer_eligible=True,
            is_starting_qb=p.position=="QB", team_starting_qb_player_id=pid if p.position=="QB" else None,
            market_snapshot_row_id=f"market-{mi}", canonical_game_id=g["game_id"],
            market_context_point_in_time_safe=True, game_total_line=48., team_spread_line=0., team_implied_total=24.,
            market_source_system="fixture_market", market_observed_at=OBS.isoformat(),
            ownership=10., ownership_run_id=OWNERSHIP, ownership_observed_at=CUT.isoformat(),
            game_id=f"{team}@{opponent} {(NOW+timedelta(days=2)).astimezone(ZoneInfo('America/New_York')).strftime('%m/%d/%Y')} 01:00PM ET")
        rows.append(r)
        salaries.append(dict(curated_salary_id=i, player_master_id=pid, source_player_key=str(i),
            source_system="draftkings", ingest_run_id="salary-ingest", salary=p.salary,
            team=team, opponent=opponent, position=p.position, game_info=r["game_id"], snapshot_id="salary-source",
            ingest_status="completed", source_checksum="salary-checksum", source_observed_at=OBS.isoformat(),
            captured_at=OBS.isoformat(), metadata_json={"native_draft_group":"12345"}, observation_basis="capture_clock"))
    evidence = dict(source_manifest=dict(games=games,salaries=salaries,markets=markets), artifact_error=None,
        projection_lineage={"run":{"projection_run_id":PROJECTION},"consumption":{}})
    return rows,evidence


def assess(rows=None,evidence=None,refresh=None):
    default_rows,default_evidence=fixture()
    return gate.evaluate_readiness(rows if rows is not None else default_rows,
        season=NOW.year,week=5,slate="SUNDAY_MAIN",projection_run_id=PROJECTION,
        evidence_cutoff=CUT,evaluated_at=NOW,rules=gate.freshness_rules(get_settings()),
        evidence=evidence if evidence is not None else default_evidence,refresh=refresh)


def test_ready_contract_preserves_clocks_and_conditional_weather():
    ready=assess()
    assert ready["status"]=="READY",ready["reason_codes"]
    assert len(ready["generation_eligible_player_ids"])==72
    assert ready["optional_sources"]["weather"]["status"]=="NOT_REQUIRED_BY_CURRENT_MODEL"
    assert ready["optional_sources"]["final_game_day_clearance"]["status"]=="UNEVALUATED"
    assert ready==assess()


@pytest.mark.parametrize("field,value,source,reason", [
    ("projection",None,"projection","projection_inputs_missing_or_invalid"),
    ("p90",None,"projection","projection_inputs_missing_or_invalid"),
    ("projection_inputs_complete",False,"projection","projection_inputs_missing_or_invalid"),
    ("projection_observed_at",(CUT-timedelta(days=2)).isoformat(),"projection","projection_stale"),
    ("availability_state","UNKNOWN","player_status","player_availability_unknown"),
    ("canonical_context_contract",None,"player_status","player_status_canonical_evidence_missing"),
    ("availability_observed_at",(CUT+timedelta(seconds=1)).isoformat(),"player_status","player_status_after_cutoff"),
    ("role_observed_at",(CUT-timedelta(days=2)).isoformat(),"player_status","player_status_stale"),
    ("canonical_role","uncertain","player_status","player_role_unknown"),
    ("market_snapshot_row_id",None,"market","market_game_evidence_missing"),
    ("team_implied_total",22.,"market","market_values_or_derived_totals_invalid"),
    ("ownership",None,"ownership","ownership_missing"),
    ("ownership_observed_at",(CUT-timedelta(days=2)).isoformat(),"ownership","ownership_stale"),
    ("salary_source_row_id","foreign","salary_pool","salary_identity_or_game_invalid"),
    ("identity_resolved",False,"salary_pool","salary_identity_or_game_invalid"),
])
def test_required_evidence_fields(field,value,source,reason):
    rows,evidence=fixture();rows[0][field]=value
    result=assess(rows,evidence)
    assert result["status"]=="NOT_READY"
    assert reason in result["required_sources"][source]["reason_codes"]


def test_no_markets_11_games_cannot_use_neutral_defaults():
    rows,evidence=fixture()
    evidence["source_manifest"]["markets"]=[]
    # All numeric fields remain populated: provenance, not a positive default,
    # controls readiness. Eleven games include the diagnostic missing-coverage case.
    evidence["source_manifest"]["games"] += [dict(game_id=f"extra-{i}",home_team="NYG",away_team="WAS",kickoff_at=(NOW+timedelta(days=2)).isoformat()) for i in range(8)]
    result=assess(rows,evidence)
    assert result["status"]=="NOT_READY"
    assert result["market_coverage"]["covered_game_ids"]==[]


@pytest.mark.parametrize("key,value,reason", [
    ("metadata_json",{},"salary_native_draft_group_missing"),
    ("source_observed_at",(CUT-timedelta(days=8)).isoformat(),"salary_pool_stale"),
    ("captured_at",(CUT+timedelta(seconds=1)).isoformat(),"salary_pool_after_cutoff"),
    ("source_checksum",None,"salary_native_source_unverified"),
])
def test_salary_source_clocks_and_native_provenance(key,value,reason):
    rows,evidence=fixture();evidence["source_manifest"]["salaries"][0][key]=value
    assert reason in assess(rows,evidence)["reason_codes"]


def test_missing_dependency_and_failed_refresh_cannot_use_old_projection():
    rows,evidence=fixture();evidence["projection_lineage"]=None
    assert "projection_dependency_lineage_unverified" in assess(rows,evidence)["reason_codes"]
    result=assess(refresh={"projection":{"status":"ERROR"}})
    assert result["status"]=="ERROR" and "projection_refresh_failed" in result["reason_codes"]


def test_freeze_is_independent_and_tamper_evident():
    rows,evidence=fixture();ready=assess(rows,evidence)
    frozen=gate.freeze_evidence(rows,ready,optimizer_run_id="frozen",evidence=evidence)
    rows[0]["projection"]=999
    assert gate.validate_frozen_evidence(frozen)["status"]=="READY"
    assert frozen["player_pool"][0]["projection"]!=999
    frozen["canonical_evidence"]["source_manifest"]["markets"]=[]
    with pytest.raises(ValueError,match="checksum"):gate.validate_frozen_evidence(frozen)


def service_fixture(rows):
    service=OptimizerService("sqlite://")
    frame=pd.DataFrame(rows)
    frame.attrs["role_context"]=[dict(player_master_id=r["player_id"],source="official",source_uri="fixture://official",
        observed_at=OBS.isoformat(),received_at=OBS.isoformat(),injury_status="ACTIVE",
        evidence_json={"roster_status":"ACT","expected_depth_role":"expected_starter", "starter_evidence":"official",
            **{k:r[k] for k in ("canonical_context_contract","availability_state","availability_status","availability_source",
               "availability_source_ids","availability_observed_at","canonical_role","role_source","role_source_ids","role_observed_at","canonical_context_reason_codes")}}) for r in rows]
    service._load_player_pool=MagicMock(return_value=frame)
    service._resolve_run_lineage=MagicMock(return_value=(PROJECTION,None,CUT))
    service._persist_optimizer_run=MagicMock(return_value=True)
    service._solve_lineup=MagicMock(side_effect=AssertionError("Legacy solver must not run"))
    return service


def run(service,**kwargs):
    return service.run_job(season=NOW.year,week=5,slate="SUNDAY_MAIN",strategy="classic_large_gpp_v1",
        contest_format="classic",objective="gpp",params={"num_lineups":1,"max_exposure":1.,
            "max_lineup_overlap":5,"max_players_per_team":4,"max_players_per_game":5,
            "max_lineups_per_primary_game":3},**kwargs)


def refresh_result():
    return dict(projection_run_id=PROJECTION,data_cutoff_at=CUT,ownership_run_id=OWNERSHIP,
        report={"projection":{"status":"completed"}})


def test_blocked_generation_persists_reasons_without_calling_candidate_engine():
    rows,evidence=fixture();evidence["source_manifest"]["markets"]=[];service=service_fixture(rows)
    with prepared_optimizer(service, return_value=refresh_result()) as refresh,patch.object(gate,"read_evidence",return_value=evidence),patch("backend.app.product_services.classic_strategy_contract.execute_strategy_contract") as solve:
        with pytest.raises(gate.ClassicDataNotReady):run(service)
    refresh.assert_called_once();solve.assert_not_called();service._solve_lineup.assert_not_called()
    failed=service._persist_optimizer_run.call_args.args[0]
    assert failed.status=="failed" and failed.results is None
    assert failed.params["data_readiness"]["status"]=="NOT_READY"
    assert "classic_evidence_snapshot" not in failed.params


def test_first_live_run_without_any_saved_projection_persists_readiness_failure():
    rows,evidence=fixture();service=service_fixture(rows)
    evidence["projection_lineage"]=None
    service._load_player_pool.return_value["projection_run_id"]=None
    service._resolve_run_lineage.return_value=(None,None,CUT)
    refreshed=dict(projection_run_id=None,data_cutoff_at=CUT,ownership_run_id=None,
        report={"projection":{"status":"blocked","reason":"Missing current player evidence"}})
    with prepared_optimizer(service, return_value=refreshed),patch.object(gate,"read_evidence",return_value=evidence),patch("backend.app.product_services.classic_strategy_contract.execute_strategy_contract") as solve:
        with pytest.raises(gate.ClassicDataNotReady):run(service)
    failed=service._persist_optimizer_run.call_args.args[0]
    assert failed.status=="failed" and failed.results is None
    assert failed.params["data_readiness"]["status"]=="NOT_READY"
    assert "projection_refresh_failed" in failed.params["data_readiness"]["reason_codes"]
    solve.assert_not_called()


def test_ready_generation_persists_both_freezes_before_real_solver():
    rows,evidence=fixture();service=service_fixture(rows);events=[]
    def persist(job):
        events.append("completed" if job.status=="completed" else "strategy_freeze" if job.params.get("effective_strategy_contract") else "final_freeze" if "classic_run_input_snapshot" in job.params.get("strategy_runtime",{}) else "source_freeze")
        gate.validate_frozen_evidence(job.params["classic_evidence_snapshot"])
        return True
    service._persist_optimizer_run.side_effect=persist
    from backend.app.product_services.classic_strategy_contract import execute_strategy_contract
    def solve(contract,**kwargs):
        assert events==["source_freeze","final_freeze","strategy_freeze"]
        events.append("solve")
        return execute_strategy_contract(contract,**kwargs)
    with prepared_optimizer(service, return_value=refresh_result()),patch.object(gate,"read_evidence",return_value=evidence),patch("backend.app.product_services.classic_strategy_contract.execute_strategy_contract",side_effect=solve):
        job=run(service)
    assert job.status=="completed",job.message
    assert events==["source_freeze","final_freeze","strategy_freeze","solve","completed"]
    assert job.params["data_readiness"]["solver_called"] is True
    assert job.params["classic_final_input_proof"]["strategy_sha256"] == job.params["effective_strategy_contract"]["sha256"]
    assert job.results[0][0]["lineup_objective_components"]["reconciliation_delta"] == pytest.approx(0, abs=1e-7)
    assert job.params["effective_strategy_contract"]["effective"]["resolved_config"]["objective_weights"]==dict(projection=.35,ceiling=.45,leverage=.05,correlation=.15)
    assert job.params["max_lineup_overlap"]==5 and job.params["max_players_per_team"]==4
    with patch.object(gate,"refresh_live_sources") as refresh:
        assert run(service,optimizer_run_id=job.job_id) is job
    refresh.assert_not_called()


def test_failed_freeze_persistence_blocks_solver():
    rows,evidence=fixture();service=service_fixture(rows);service._persist_optimizer_run.return_value=False
    with prepared_optimizer(service, return_value=refresh_result()),patch.object(gate,"read_evidence",return_value=evidence),patch("backend.app.product_services.classic_strategy_contract.execute_strategy_contract") as solve:
        with pytest.raises(ValueError,match="freeze could not be persisted"):run(service)
    solve.assert_not_called()


def test_unavailable_players_need_no_projection_or_role_but_remain_audited():
    rows,evidence=fixture()
    rows[0].update(availability_state="UNAVAILABLE",availability_status="OUT",canonical_role=None,
        role_source=None,role_source_ids=[],role_observed_at=None,projection=None,p90=None,projection_inputs_complete=False)
    result=assess(rows,evidence)
    assert result["status"]=="READY",result["reason_codes"]
    assert rows[0]["player_id"] not in result["generation_eligible_player_ids"]
    assert result["players"][0]["availability"]=="unavailable"


def test_final_game_status_is_separate_from_practice_and_roster_evidence():
    rows,evidence=fixture();pid=rows[0]["player_id"]
    facts=[dict(kind="injury_status",status="ACTIVE",source="practice",source_ids=["practice"],
        observed_at=OBS.isoformat(),received_at=OBS.isoformat())]
    evidence["source_manifest"]["availability"]=[dict(player_master_id=pid,evidence_json={"source_facts":facts})]
    assert assess(rows,evidence)["players"][0]["game_day_clearance"]=="UNEVALUATED"
    facts.append(dict(kind="game_status",game_active=True,source="official_inactives",source_ids=["final-1"],
        observed_at=OBS.isoformat(),received_at=OBS.isoformat()))
    assert assess(rows,evidence)["players"][0]["game_day_clearance"]=="CLEARED"
    facts[-1]["received_at"]=(CUT+timedelta(seconds=1)).isoformat()
    assert assess(rows,evidence)["players"][0]["game_day_clearance"]=="UNEVALUATED"


@pytest.mark.parametrize("status,expected",[("Q","questionable_elevated"),("D","doubtful"),("ACTIVE","available"),("UNKNOWN","unknown")])
def test_explicit_availability_distinctions_are_preserved(status,expected):
    rows,evidence=fixture();rows[0]["availability_status"]=status
    rows[0].update(practice_participation="LIMITED", practice_observed_at=OBS.isoformat(),
        expected_workload_status="LIMITED", expected_workload_observed_at=OBS.isoformat())
    if status=="UNKNOWN": rows[0]["availability_state"]="UNKNOWN"
    result=assess(rows,evidence)
    assert result["players"][0]["availability"]==expected
    assert result["status"]==("NOT_READY" if status=="UNKNOWN" else "READY")


def test_public_request_cannot_supply_offline_override_or_frozen_proof():
    from backend.app.product_schemas import OptimizerRunRequest
    with pytest.raises(ValueError):
        OptimizerRunRequest(season=NOW.year,week=5,slate="SUNDAY_MAIN",strategy="classic_large_gpp_v1",
            params={"allow_incomplete_evidence":True})
    rows,evidence=fixture();evidence["source_manifest"]["markets"]=[];service=service_fixture(rows)
    with prepared_optimizer(service, return_value=refresh_result()),patch.object(gate,"read_evidence",return_value=evidence):
        with pytest.raises(gate.ClassicDataNotReady):
            service.run_job(season=NOW.year,week=5,slate="SUNDAY_MAIN",strategy="classic_large_gpp_v1",
                contest_format="classic",objective="gpp",params={"data_readiness":{"status":"READY"},
                    "classic_evidence_snapshot":{"status":"READY"},"classic_final_input_proof":{"status":"READY"}})


@pytest.mark.parametrize("ready",[False,True])
def test_public_queue_and_durable_worker_use_gate_and_preserve_preparation(ready):
    from contextlib import ExitStack
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from backend.app.api.product_routes import router
    from backend.app.api.job_routes import router as job_router
    from backend.app.db import get_db_session
    from backend.app.models import OperationalJob
    from backend.app.product_dependencies import get_optimizer_service
    from backend.app.services.job_queue import claim_next_job
    from backend.app.worker import execute_claimed_job
    rows,evidence=fixture();service=service_fixture(rows)
    if not ready:evidence["source_manifest"]["markets"]=[]
    engine=create_engine("sqlite://",poolclass=StaticPool,connect_args={"check_same_thread":False})
    factory=sessionmaker(engine,expire_on_commit=False)
    OperationalJob.__table__.create(engine)
    app=FastAPI();app.include_router(router);app.include_router(job_router)
    def session():
        with factory() as db:yield db
    app.dependency_overrides[get_db_session]=session
    app.dependency_overrides[get_optimizer_service]=lambda:service
    with ExitStack() as stack:
        for name in ("backend.app.services.job_handlers.SessionLocal","backend.app.worker.SessionLocal"):
            stack.enter_context(patch(name,factory))
        # The real service runs; only source/model/database I/O is synthetic.
        stack.enter_context(patch.object(OptimizerService,"run_job",side_effect=service.run_job))
        stack.enter_context(prepared_optimizer(service, return_value=refresh_result()))
        stack.enter_context(patch.object(gate,"read_evidence",return_value=evidence))
        client=TestClient(app)
        request=dict(season=NOW.year,week=5,slate="SUNDAY_MAIN",strategy="classic_large_gpp_v1",
            contest_format="classic",objective="gpp",params={"num_lineups":1,"max_exposure":1.,
                "prepared_input_job_id":"prepared-fixture", "max_lineup_overlap":5},
            projection_run_id=PROJECTION)
        response=client.post("/api/optimizer/jobs",json=request)
        assert response.status_code==202,response.text
        with factory() as db:queued=claim_next_job(db,worker_id="classic-fixture")
        execute_claimed_job(job_id=queued.job_id,job_type=queued.job_type,request_payload=queued.request_json,
            worker_id="classic-fixture",run_id=queued.run_id,checkpoint=queued.checkpoint_json,lease_seconds=300)
        status=client.get("/api/jobs/"+queued.job_id).json()
        assert status["status"]==("completed" if ready else "failed"),status
        saved=service.get_job(queued.run_id)
        assert saved.params["data_readiness"]["status"]==("READY" if ready else "NOT_READY")
        assert saved.params["prepared_input_job_id"] == "prepared-fixture"
        assert saved.projection_run_id == PROJECTION
        if ready:
            assert len(saved.results)==1
            assert saved.params["entry_readiness"]["status"] in {"ENTRY_CLEARANCE_PENDING", "BLOCKED"}
            assert saved.params["entry_readiness"]["generation_readiness"]["status"]=="READY"
            assert saved.params["entry_readiness"]["checks"]["Current weather evidence"]["status"]=="NOT_REQUIRED_BY_CURRENT_MODEL"
        else:
            assert saved.results is None
            assert "No candidates or lineups were generated" in status["error_message"]
    engine.dispose()


def test_existing_sourced_non_scoring_specialist_gate_does_not_require_projection():
    rows,evidence=fixture();rows[1].update(canonical_role="long_snapper",role_source_position="LS",
        projection=None,p90=None,projection_inputs_complete=False)
    result=assess(rows,evidence)
    assert result["status"]=="READY",result["reason_codes"]
    assert result["players"][1]["disposition"]=="explicitly_excluded_specialist"
    rows[1]["role_source_ids"]=[]
    assert assess(rows,evidence)["status"]=="NOT_READY"


def test_actual_ilp_receives_configured_pair_coefficients_and_missing_markets_remove_positive_stack_signals():
    from backend.app.product_services.gpp_optimizer import _build_lineup,build_large_gpp_config,analyze_slate
    from backend.app.product_services.lineup_correlation_scoring import build_lineup_correlation_terms
    from backend.app.product_services.rule_library import resolve_strategy_profile
    from dataclasses import replace
    rows,_=fixture();players=OptimizerService._gpp_players_from_pool(pd.DataFrame(rows))
    config=build_large_gpp_config(analyze_slate(players),ownership_available=True)
    terms=build_lineup_correlation_terms(players,profile=resolve_strategy_profile(contest_format="classic",objective="gpp"))
    models=[];_build_lineup(players,config,None,[],model_capture=models.append)
    coefficients={v.name:float(c) for v,c in models[0].objective.items()}
    assert config.objective_weights.correlation==.15
    for i,term in enumerate(terms):
        assert coefficients[f"gpp_rule_correlation_{i}"]==pytest.approx(.15*term.adjustment)
    positive=[t for t in terms if any(r.rule_id=="correlation.qb_pass_catcher_v2" for r in t.evaluation.triggered_rules)]
    assert positive
    missing=[replace(p,game_total=None,spread=None,team_total=None,market_context_point_in_time_safe=False) for p in players]
    assert not any(r.rule_id=="correlation.qb_pass_catcher_v2" for t in build_lineup_correlation_terms(missing,
        profile=resolve_strategy_profile(contest_format="classic",objective="gpp")) for r in t.evaluation.triggered_rules)


def test_salary_refresh_reuses_canonical_import_without_inventing_a_new_clock(monkeypatch):
    rows,evidence=fixture();manifest=evidence['source_manifest']
    for s in manifest['salaries']:
        s['source_path']='/fixture/immutable-salary.csv'
        s['metadata_json']['capture_mode']='manual_file_import'
    monkeypatch.setattr('Database.player_identity.repair_salary_identities',lambda *a,**k: type('Repair',(),{})())
    monkeypatch.setattr(gate,'Session',MagicMock())
    monkeypatch.setattr(gate,'source_manifest',lambda *a,**k:deepcopy(manifest))
    monkeypatch.setattr(gate,'verify_artifacts',lambda *a,**k:None)
    provenance={'salary-ingest':{'verified':True,'imported_at':OBS.isoformat(),'completed_at':OBS.isoformat()}}
    monkeypatch.setattr('backend.app.product_services.classic_salary_provenance.read_salary_provenance',lambda *a,**k:deepcopy(provenance))
    importer=MagicMock(return_value={'snapshot_id':'salary-source','observed_at':OBS.isoformat()})
    monkeypatch.setattr('backend.app.product_services.slate_preparation.import_file',importer)
    result=gate.refresh_salary_evidence(service_fixture(rows),season=NOW.year,week=5,slate='SUNDAY_MAIN')
    importer.assert_not_called()
    assert result['source_clocks_preserved'] is True
    assert result['canonical_import_replay'] is None
    assert result['original_import_provenance']==provenance


@pytest.mark.parametrize("name,source", list(gate.REQUIRED_REFRESH_SOURCES.items()))
def test_required_refresh_failure_cannot_be_cleared_by_complete_cached_rows(name, source):
    result = assess(refresh={name: {"status": "ERROR", "reason": "Provider unavailable"}})
    assert result["status"] == "ERROR"
    assert f"{name}_refresh_failed" in result["required_sources"][source]["reason_codes"]


def test_optional_unconsumed_raw_injury_capture_failure_does_not_certify_or_block_readiness():
    result = assess(refresh={"injuries": {"status": "ERROR", "reason": "Unsupported feed"}})
    assert result["status"] == "READY"
    assert result["refresh"]["injuries"]["status"] == "ERROR"


@pytest.mark.parametrize("age,expected", [(1, "READY"), (7, "NOT_READY")])
def test_market_freshness_uses_source_observation_not_new_fetch(age, expected):
    rows, evidence = fixture()
    for market in evidence["source_manifest"]["markets"]:
        market.update(observed_at=(CUT-timedelta(hours=age)).isoformat(), ingested_at=OBS.isoformat())
    result = assess(rows, evidence)
    assert result["required_sources"]["market"]["status"] == expected
    assert ("market_stale" in result["reason_codes"]) == (expected == "NOT_READY")


def test_one_missing_game_blocks_and_records_affected_players():
    rows, evidence = fixture()
    evidence["source_manifest"]["markets"].pop()
    result = assess(rows, evidence)
    assert result["status"] == "NOT_READY"
    assert len(result["market_coverage"]["required_game_ids"]) == 3
    assert len(result["market_coverage"]["covered_game_ids"]) == 2
    assert result["required_sources"]["market"]["affected_player_ids"]


def test_salary_lineage_without_observation_clock_blocks():
    rows, evidence = fixture()
    evidence["source_manifest"]["salaries"][0]["source_observed_at"] = None
    assert "salary_pool_timestamp_missing" in assess(rows, evidence)["reason_codes"]


def test_native_salary_player_missing_from_pool_cannot_disappear_silently():
    rows, evidence = fixture()
    removed = rows.pop()
    result = assess(rows, evidence)
    assert result["status"] == "NOT_READY"
    player = next(p for p in result["players"] if p["player_id"] == removed["player_id"])
    assert player["disposition"] == "unresolved"
    assert "native_salary_player_unassessed" in player["reason_codes"]


def test_questionable_context_gap_is_unresolved_but_sourced_limited_usage_is_eligible():
    rows, evidence = fixture()
    rows[0]["availability_status"] = "Q"
    result = assess(rows, evidence)
    assert "questionable_usage_context_unresolved" in result["reason_codes"]
    assert result["players"][0]["availability"] == "questionable_elevated"
    assert result["players"][0]["disposition"] == "unresolved"
    rows[0].update(practice_participation="LIMITED", practice_observed_at=OBS.isoformat(),
        expected_workload_status="LIMITED", expected_workload_observed_at=OBS.isoformat())
    result = assess(rows, evidence)
    assert result["status"] == "READY", result["reason_codes"]
    assert result["players"][0]["risk_assessment"]["bucket"] == "questionable_elevated"
    assert result["players"][0]["disposition"] == "generation_eligible"


def test_undeclared_material_weather_consumption_cannot_borrow_informational_exemption():
    rows, evidence = fixture()
    evidence["projection_lineage"]["consumption"]["weather_consumed"] = True
    result = assess(rows, evidence)
    assert result["status"] == "NOT_READY"
    assert result["required_sources"]["weather"]["required"] is True
    assert "material_weather_evidence_unverified" in result["reason_codes"]


def test_explicit_preview_retains_exact_blockers_and_records_solver_override():
    rows, evidence = fixture()
    evidence["source_manifest"]["markets"] = []
    service = service_fixture(rows)
    with patch.object(gate, "refresh_live_sources") as refresh, patch.object(gate, "read_evidence", return_value=evidence):
        job = run(service, allow_incomplete_evidence=True)
    refresh.assert_not_called()
    assert job.status == "completed", job.message
    decision = job.params["data_readiness"]
    assert decision["status"] == "DEVELOPMENT_PREVIEW" and decision["source_status"] == "NOT_READY"
    assert "market_game_evidence_missing" in decision["reason_codes"]
    assert decision["solver_called"] is True and decision["override_used"] is True
    assert "classic_evidence_snapshot" not in job.params
    assert job.params["entry_readiness"]["entry_ready"] is False


def test_saved_preparation_failure_never_calls_solver():
    rows, evidence = fixture()
    service = service_fixture(rows)
    events = []
    def refreshed(*args, **kwargs):
        events.append("prepared_lookup")
        result = refresh_result()
        result["report"]["market"] = {"status": "ERROR", "reason": "Provider down"}
        return result
    original = gate.evaluate_readiness
    with prepared_optimizer(service, side_effect=refreshed), patch.object(gate, "read_evidence", return_value=evidence), patch.object(gate, "evaluate_readiness", side_effect=lambda *a, **k: (events.append("readiness") or original(*a, **k))), patch("backend.app.product_services.classic_strategy_contract.execute_strategy_contract") as solver:
        with pytest.raises(gate.ClassicDataNotReady):
            run(service)
    assert events == ["prepared_lookup", "readiness"]
    solver.assert_not_called()
    decision = service._persist_optimizer_run.call_args.args[0].params["data_readiness"]
    assert decision["solver_called"] is False and decision["override_used"] is False


def test_later_refresh_gets_a_distinct_snapshot_and_leaves_first_frozen_evidence_unchanged():
    rows, evidence = fixture()
    first = gate.freeze_evidence(rows, assess(rows, evidence), optimizer_run_id="run-1", evidence=evidence)
    preserved = deepcopy(first)
    evidence["source_manifest"]["markets"][0]["market_snapshot_id"] = "new-market"
    for row in rows:
        if row["market_snapshot_row_id"] == "market-0": row["market_snapshot_row_id"] = "new-market"
    second = gate.freeze_evidence(rows, assess(rows, evidence), optimizer_run_id="run-2", evidence=evidence)
    assert first == preserved
    assert first["sha256"] != second["sha256"]
    assert gate.validate_frozen_evidence(first)["status"] == gate.validate_frozen_evidence(second)["status"] == "READY"


def test_user_exclusion_cannot_resolve_unknown_football_availability():
    rows, evidence = fixture()
    player = next(r for r in rows if r["opponent_team"] == "DEN")
    player["availability_state"] = "UNKNOWN"
    service = service_fixture(rows)
    with prepared_optimizer(service, return_value=refresh_result()), patch.object(gate, "read_evidence", return_value=evidence), patch("backend.app.product_services.classic_strategy_contract.execute_strategy_contract") as solver:
        with pytest.raises(gate.ClassicDataNotReady):
            service.run_job(season=NOW.year, week=5, slate="SUNDAY_MAIN", strategy="classic_large_gpp_v1",
                contest_format="classic", objective="gpp", params={"num_lineups":1, "exclude_opponent_teams":["DEN"]})
    solver.assert_not_called()
    decision = service._persist_optimizer_run.call_args.args[0].params["data_readiness"]
    assessment = next(p for p in decision["players"] if p["player_id"] == player["player_id"])
    assert assessment["availability"] == "unknown"
    assert assessment["disposition"] == "unresolved"


def test_precompute_false_builds_dynamic_terms_with_same_selection_and_actual_objective():
    from backend.app.product_services.gpp_optimizer import generate_portfolio, build_large_gpp_config
    from backend.app.product_services.lineup_correlation_scoring import score_lineup_correlations
    from backend.app.product_services.rule_library import resolve_strategy_profile
    from dataclasses import replace
    rows, _ = fixture()
    players = OptimizerService._gpp_players_from_pool(pd.DataFrame(rows))
    players = [replace(p, optimizer_context_adjustment=.4 if p.position == "WR" else 0) for p in players]
    results = [generate_portfolio(NOW.year, 5, "SUNDAY_MAIN", 1, players=deepcopy(players),
        ownership_available=True, config_builder=build_large_gpp_config, include_control_comparisons=False,
        max_exposure=1., precompute_correlation_terms=cache) for cache in (False, True)]
    assert [p.player_id for p in results[0].lineups[0]] == [p.player_id for p in results[1].lineups[0]]
    a, b = [result.selection_trace[0]["objective_components"] for result in results]
    assert a == b
    selected = results[0].lineups[0]
    scales = a["normalization"]
    weights = a["weights"]
    assert weights == dict(projection=.35, ceiling=.45, leverage=.05, correlation=.15)
    assert a["projection"] == pytest.approx(.35 * sum(p.projection for p in selected) / scales["projection"])
    assert a["ceiling"] == pytest.approx(.45 * sum(p.ceiling for p in selected) / scales["ceiling"])
    assert a["leverage"] == pytest.approx(.05 * sum(p.leverage for p in selected) / scales["leverage"])
    assert a["context"] != 0
    scored = score_lineup_correlations(selected, profile=resolve_strategy_profile(contest_format="classic", objective="gpp"), objective_multiplier=.15)
    assert a["correlation"] == pytest.approx(scored["total_adjustment"])
    assert a["correlation"] != 0  # This known feasible fixture has positive QB/catcher terms.
    assert sum(a[name] for name in ("projection", "ceiling", "leverage", "context", "correlation")) == pytest.approx(a["solver_objective"], abs=1e-7)


def test_verified_original_csv_does_not_require_draft_group_for_generation():
    rows, evidence = fixture()
    for salary in evidence["source_manifest"]["salaries"]:
        salary["metadata_json"] = {}
        salary["snapshot_id"] = None
    evidence["salary_provenance"] = {"salary-ingest": {
        "verified": True, "source_checksum": "salary-checksum",
        "imported_at": OBS.isoformat(), "completed_at": OBS.isoformat(),
        "observation_basis": "original_import_receipt_clock",
    }}
    assert assess(rows, evidence)["status"] == "READY"
    rows[0]["dk_player_id"] = "different-native-player"
    assert "salary_identity_or_game_invalid" in assess(rows, evidence)["reason_codes"]
    rows[0]["dk_player_id"] = "0"
    evidence["salary_provenance"]["salary-ingest"]["source_checksum"] = "wrong-hash"
    reasons = assess(rows, evidence)["reason_codes"]
    assert "salary_native_source_unverified" in reasons
    assert "salary_native_draft_group_missing" in reasons


def test_fresh_practice_supports_questionable_risk_without_inventing_workload_clearance():
    rows, evidence = fixture()
    rows[0].update(availability_status="Q", practice_participation="LIMITED", practice_observed_at=OBS.isoformat())
    report = assess(rows, evidence)
    assert report["status"] == "READY", report["reason_codes"]
    risk = report["players"][0]["risk_assessment"]
    assert risk["bucket"] == "questionable_elevated"
    assert risk["evidence_gap"] is True
    assert risk["workload_status"] is None
    assert report["players"][0]["game_day_clearance"] == "UNEVALUATED"
    rows[0]["practice_observed_at"] = (CUT-timedelta(days=2)).isoformat()
    assert "player_status_stale" in assess(rows, evidence)["reason_codes"]
    rows[0]["practice_observed_at"] = OBS.isoformat()
    rows[0]["expected_workload_status"] = "FULL"
    assert "player_status_timestamp_missing" in assess(rows, evidence)["reason_codes"]
