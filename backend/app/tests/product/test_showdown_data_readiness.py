from backend.app.tests.product.prepared_optimizer_fixture import prepared_optimizer
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from backend.app.config import get_settings
from backend.app.product_schemas import OptimizerRunRequest
from backend.app.product_services.optimizer import OptimizerService
from backend.app.product_services.showdown_data_readiness import (
    ShowdownDataNotReady, evaluate_readiness, freshness_rules, freeze_evidence,
    requires_ownership, validate_frozen_evidence,
    is_live_slate,
    refresh_projection_player_context,
)


NOW = datetime.now(UTC)
AT = NOW.isoformat()
PROJECTION = "synthetic-projection"


def ready_rows():
    kickoff = (NOW + timedelta(days=2)).astimezone(ZoneInfo("America/New_York"))
    game = f"AAA@BBB {kickoff.strftime('%m/%d/%Y %I:%M%p')} ET"
    return [dict(player_id=f"player-{i}", identity_resolved=True, dk_player_id=f"flex-{i}",
                 dk_captain_id=f"captain-{i}", salary=6000, salary_source_row_id=f"salary-{i}",
                 salary_source_system="draftkings", salary_source_observed_at=AT,
                 name=f"Player {i}", position="QB" if i in {0, 3} else "WR",
                 player_team="AAA" if i < 3 else "BBB", opponent_team="BBB" if i < 3 else "AAA", game_id=game,
                 projection=10., p90=20., predicted_p50=10., predicted_p10=5.,
                 projection_run_id=PROJECTION, projection_observed_at=AT, data_cutoff_at=AT,
                 projection_model_version="synthetic-v1", pregame_context_source="official-report",
                 pregame_context_run_id="context-1", pregame_context_observed_at=AT,
                 pregame_availability_probability=1., expected_depth_role="expected_starter",
                 player_status_evidence_present=True,
                 role_optimizer_eligible=True, is_starting_qb=i in {0, 3},
                 starting_qb_source="official-chart" if i in {0, 3} else None,
                 starting_qb_observed_at=AT if i in {0, 3} else None,
                 team_spread_line=-3. if i < 3 else 3., game_total_line=50.,
                 team_implied_total=26.5 if i < 3 else 23.5, market_context_point_in_time_safe=True,
                 market_source_system="nflverse", market_observed_at=AT, market_snapshot_row_id="market-1",
                 captain_ownership=None, flex_ownership=None, ownership=None, ownership_run_id=None)
            for i in range(6)]


def assess(rows=None, **kwargs):
    return evaluate_readiness(ready_rows() if rows is None else rows, season=NOW.year, week=5,
        slate="THURSDAY_NIGHT", projection_run_id=PROJECTION, evidence_cutoff=NOW, evaluated_at=NOW,
        rules=freshness_rules(get_settings()), **kwargs)


def test_ready_contract_deterministic_and_optional_ownership_truthful():
    result = assess(ownership_attempted=True)
    assert result == assess(ownership_attempted=True)
    assert result["status"] == "READY"
    assert result["baseline_market"]["favorite"] == "AAA"
    assert result["baseline_market"]["teams"]["AAA"]["implied_total"] == 26.5
    assert result["ownership"]["status"] == "OPTIONAL_MISSING"
    assert result["ownership"]["ownership_attempted"] is True
    assert result["ownership"]["ownership_available"] is False
    assert result["ownership"]["ownership_fresh"] is False


def test_prior_season_with_future_kickoff_still_uses_live_gate():
    service = MagicMock(); service.engine.dialect.name = "postgresql"
    connection = service.engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalars.return_value.all.return_value = [ready_rows()[0]["game_id"]]
    assert is_live_slate(service, season=NOW.year - 1, week=18, slate="SUNDAY_NIGHT")


def test_pickem_is_complete_market_evidence_not_missing_favorite():
    from backend.app.product_services.ai_showdown_packet import _game, _market_compatibility
    rows = ready_rows()
    for row in rows: row.update(team_spread_line=0, team_implied_total=25)
    assert assess(rows)["baseline_market"]["pickem"] is True
    assert assess(rows)["status"] == "READY"
    game = _game(rows, NOW)
    result = _market_compatibility({"primary_football_scenario": "balanced_competitive_game"}, game)
    assert "saved_baseline_market_incomplete" not in result["market_compatibility_reason_codes"]


@pytest.mark.parametrize("field,code", [
    ("game_total_line", "market_missing"), ("team_spread_line", "market_missing"),
    ("projection", "projection_missing"), ("p90", "projection_missing"),
    ("projection_run_id", "projection_missing"),
    ("pregame_context_source", "player_status_missing"),
    ("expected_depth_role", "player_status_missing"),
    ("is_starting_qb", "starting_qb_unresolved"),
    ("dk_captain_id", "salary_pool_missing"), ("player_id", "salary_pool_missing"),
])
def test_required_missing_fails_closed(field, code):
    rows = ready_rows(); rows[0][field] = None
    result = assess(rows)
    assert result["status"] == "NOT_READY"
    assert code in result["reason_codes"]
    with pytest.raises(ShowdownDataNotReady, match="not data-ready") as caught:
        freeze_evidence(rows, result, optimizer_run_id="blocked")
    assert code in caught.value.readiness["reason_codes"]


@pytest.mark.parametrize("field,code", [
    ("market_observed_at", "market_stale"), ("projection_observed_at", "projection_stale"),
    ("pregame_context_observed_at", "player_status_stale"),
    ("starting_qb_observed_at", "starting_qb_stale"), ("salary_source_observed_at", "salary_pool_stale")])
def test_required_source_age_is_independent(field, code):
    rows = ready_rows(); rows[0][field] = (NOW - timedelta(days=8)).isoformat()
    assert code in assess(rows)["reason_codes"]


def test_future_evidence_fails_and_custom_freshness_rules_apply():
    rows = ready_rows(); rows[0]["market_observed_at"] = (NOW + timedelta(seconds=1)).isoformat()
    assert "market_after_cutoff" in assess(rows)["reason_codes"]
    rows = ready_rows()
    for row in rows: row["market_observed_at"] = (NOW - timedelta(hours=2)).isoformat()
    assert assess(rows)["status"] == "READY"
    rules = freshness_rules(get_settings()); rules["market"] = 1
    result = evaluate_readiness(rows, season=NOW.year, week=5, slate="THURSDAY_NIGHT", projection_run_id=PROJECTION,
                                evidence_cutoff=NOW, evaluated_at=NOW, rules=rules)
    assert "market_stale" in result["reason_codes"]


def test_ownership_required_missing_and_stale_are_hard_failures():
    assert "ownership_missing_required" in assess(ownership_required=True)["reason_codes"]
    assert requires_ownership({"use_role_ownership": True})
    rows = ready_rows()
    for row in rows:
        row.update(captain_ownership=10., flex_ownership=30., ownership_run_id="ownership-1",
                   ownership_source="model-v1", ownership_observed_at=(NOW - timedelta(days=2)).isoformat())
    assert "ownership_stale" in assess(rows, ownership_required=True)["reason_codes"]
    assert assess(rows)["optional_sources"]["ownership"]["status"] == "OPTIONAL_STALE"
    for row in rows: row["ownership_observed_at"] = AT
    assert assess(rows, ownership_required=True)["status"] == "READY"


def test_default_probability_and_quantile_fallback_do_not_certify_missing_source_facts():
    rows = ready_rows(); rows[0]["player_status_evidence_present"] = False
    assert "player_status_missing" in assess(rows)["reason_codes"]
    rows = ready_rows(); rows[0]["projection_inputs_complete"] = False
    assert "projection_missing" in assess(rows)["reason_codes"]


def test_frozen_snapshot_does_not_follow_source_refresh_or_mutate_inputs():
    rows = ready_rows(); result = assess(rows); before = deepcopy(rows)
    frozen = freeze_evidence(rows, result, optimizer_run_id="saved-run")
    assert rows == before
    rows[0]["projection"] = 99; result["status"] = "NOT_READY"
    assert validate_frozen_evidence(frozen)["status"] == "READY"
    assert frozen["player_pool"][0]["projection"] == 10
    frozen["player_pool"][0]["projection"] = 99
    with pytest.raises(ValueError, match="checksum"):
        validate_frozen_evidence(frozen)


def service_fixture(rows):
    service = OptimizerService("sqlite://")
    service._resolve_run_lineage = MagicMock(return_value=(PROJECTION, None, NOW))
    frame = pd.DataFrame(rows)
    frame.attrs["role_context"] = [dict(player_master_id=r["player_id"], source="official-report",
        source_uri="https://example.test/report", availability_probability=1.,
        evidence_json={"roster_status": "ACT", "expected_depth_role": "expected_starter", "starter_evidence": "official chart"})
        for r in rows]
    service._load_player_pool = MagicMock(return_value=frame)
    service._persist_optimizer_run = MagicMock(return_value=True)
    def solve(pool, **kwargs):
        selected = pool.to_dict("records")
        for i, row in enumerate(selected):
            row["roster_position"] = "CPT" if i == 0 else "FLEX"
            row["salary"] *= 1.5 if i == 0 else 1
            row["projection"] *= 1.5 if i == 0 else 1
            row["p90"] *= 1.5 if i == 0 else 1
        return selected
    service._solve_lineup = MagicMock(side_effect=solve)
    return service


def run(service, **kwargs):
    return service.run_job(season=NOW.year, week=5, slate="THURSDAY_NIGHT", strategy="showdown_cash_baseline_v1",
        params={"num_lineups": 1, "max_exposure": 1.0}, contest_format="showdown", objective="cash", **kwargs)


def refresh_result():
    return dict(projection_run_id=PROJECTION, data_cutoff_at=NOW, ownership_run_id=None,
                report={"market": {"status": "completed"}, "projection": {"status": "completed"}, "ownership": {"status": "completed"}})


def test_live_generation_uses_preparation_and_persists_freeze_before_solver():
    rows = ready_rows(); service = service_fixture(rows); events = []
    def refresh(*args, **kwargs):
        events.append("prepared_lookup"); return refresh_result()
    def persist(job):
        events.append("freeze" if job.status == "running" else "completed")
        assert validate_frozen_evidence(job.params["showdown_evidence_snapshot"])["status"] == "READY"
        return True
    original_solve = service._solve_lineup.side_effect
    def solve(pool, **kwargs):
        events.append("solve"); assert events[:2] == ["prepared_lookup", "freeze"]
        return original_solve(pool, **kwargs)
    service._persist_optimizer_run.side_effect = persist
    service._solve_lineup.side_effect = solve
    with prepared_optimizer(service, side_effect=refresh):
        job = run(service)
    assert job.status == "completed", job.message
    assert events == ["prepared_lookup", "freeze", "solve", "completed"]
    assert job.params["data_readiness"]["status"] == "READY"
    assert job.params["showdown_evidence_snapshot"]["non_production_override"] is False
    service._load_player_pool.assert_called_once()


@pytest.mark.parametrize("field", ["game_total_line", "projection", "pregame_context_source", "is_starting_qb"])
def test_live_generator_never_called_when_readiness_fails(field):
    rows = ready_rows(); rows[0][field] = None; service = service_fixture(rows)
    with prepared_optimizer(service, return_value=refresh_result()) as refresh:
        with pytest.raises(ShowdownDataNotReady): run(service)
    refresh.assert_called_once()
    service._solve_lineup.assert_not_called()
    failed = service._persist_optimizer_run.call_args.args[0]
    assert failed.status == "failed" and failed.params["data_readiness"]["status"] == "NOT_READY"


def test_persistence_failure_prevents_generator():
    service = service_fixture(ready_rows()); service._persist_optimizer_run.return_value = False
    with prepared_optimizer(service, return_value=refresh_result()):
        with pytest.raises(ValueError, match="freeze could not be persisted"): run(service)
    service._solve_lineup.assert_not_called()


def test_failed_projection_refresh_is_error_and_cannot_use_an_older_build():
    service = service_fixture(ready_rows()); refreshed = refresh_result()
    refreshed["report"]["projection"] = {"status": "ERROR", "reason": "collector failed"}
    with prepared_optimizer(service, return_value=refreshed):
        with pytest.raises(ShowdownDataNotReady) as caught: run(service)
    assert caught.value.readiness["status"] == "ERROR"
    assert "projection_refresh_failed" in caught.value.readiness["reason_codes"]
    assert caught.value.readiness["player_pool_readiness"]["status"] == "ERROR"
    assert "projection_refresh_failed" in caught.value.readiness["player_pool_readiness"]["readiness_blockers"]
    service._solve_lineup.assert_not_called()


def test_completed_frozen_run_is_reopened_without_refresh_and_interrupted_freeze_requires_new_id():
    service = service_fixture(ready_rows())
    with prepared_optimizer(service, return_value=refresh_result()):
        job = run(service)
    before = deepcopy(job.params["showdown_evidence_snapshot"])
    with patch("backend.app.product_services.showdown_data_readiness.refresh_live_sources") as refresh:
        assert run(service, optimizer_run_id=job.job_id) is job
    refresh.assert_not_called()
    assert job.params["showdown_evidence_snapshot"] == before
    job.status = "running"
    with pytest.raises(ValueError, match="already has frozen"):
        run(service, optimizer_run_id=job.job_id)


@pytest.mark.parametrize("official_unresolved", [False, True])
@pytest.mark.parametrize("identity_unresolved", [False, True])
def test_existing_collectors_refresh_before_saved_projection_build_and_ownership(official_unresolved, identity_unresolved):
    from contextlib import ExitStack
    from types import SimpleNamespace
    from backend.app.product_services.showdown_data_readiness import refresh_live_sources
    service = service_fixture(ready_rows()); calls = []
    def mark(name, result):
        def action(*args, **kwargs):
            calls.append(name)
            if name == "official_status" and official_unresolved:
                from backend.app.product_services.showdown_player_context import PlayerContextUnresolved
                raise PlayerContextUnresolved("Official injury player identities require review")
            return result
        return action
    capture = SimpleNamespace(capture=SimpleNamespace(snapshot=SimpleNamespace(snapshot_id="roster-1")),
                              ingest=SimpleNamespace(rows_curated=6))
    with ExitStack() as stack:
        def mocked(path, **kwargs): return stack.enter_context(patch(path, **kwargs))
        mocked("backend.app.product_services.slate_preparation.slate_games", return_value=[{"game_id":"test"}])
        mocked("backend.app.product_services.slate_preparation.require_prelock", return_value=NOW + timedelta(days=2))
        mocked("Database.player_identity.repair_salary_identities", side_effect=mark("salary", SimpleNamespace(salary_rows_quarantined=int(identity_unresolved))))
        mocked("backend.app.product_services.slate_preparation.capture_source", side_effect=mark("market", {}))
        mocked("backend.app.services.source_capture.SourceCaptureService.capture_and_ingest_nflreadpy_weekly_rosters",
               side_effect=mark("status", capture))
        mocked("backend.app.services.source_capture.capture_nflreadpy_datasets", side_effect=mark("injuries", []))
        mocked("backend.app.product_services.official_injuries.refresh_official_injuries",
               side_effect=mark("official_status", {"game_status_rows":1}))
        mocked("backend.app.product_services.starters.StartingQBService.derive_starters",
               side_effect=mark("starters", SimpleNamespace(rows_written=2)))
        mocked("backend.app.product_services.showdown_player_context.refresh_canonical_context",
               side_effect=mark("canonical_context", {"rows":6}))
        mocked("backend.app.product_services.showdown_data_readiness.refresh_training_labels",
               side_effect=mark("historical_features", {"periods":[]}))
        mocked("backend.app.product_services.slate_preparation.execute_preparation",
               side_effect=mark("projection", {"projection_run_id":PROJECTION, "data_cutoff_at":AT}))
        ownership = mocked("backend.app.product_services.ownership.OwnershipService.run_projection_model",
                           side_effect=mark("ownership", SimpleNamespace(ownership_run_id="own-1")))
        result = refresh_live_sources(service, season=NOW.year, week=5, slate="THURSDAY_NIGHT", params={})
    if identity_unresolved:
        assert calls == ["market", "status", "salary"]
        assert result["projection_run_id"] is None
        assert result["ownership_run_id"] is None
        assert result["report"]["projection"]["status"] == "blocked"
        ownership.assert_not_called()
        return
    expected = ["market", "status", "salary", "injuries", "official_status", "starters", "canonical_context", "projection", "ownership"]
    if official_unresolved:
        expected.remove("projection")
        assert result["report"]["projection"]["status"] == "blocked"
    assert calls == expected
    assert result["projection_run_id"] == (None if official_unresolved else PROJECTION)
    assert result["ownership_run_id"] == "own-1"
    assert ownership.call_args.kwargs["projection_run_id"] == result["projection_run_id"]


def test_api_entry_count_is_independent_and_public_export_has_no_override():
    from backend.app.tests.product.test_ai_showdown_packet import saved
    from backend.app.api.product_routes import download_ai_showdown_packet
    from types import SimpleNamespace
    import inspect, json
    source = saved("thursday")
    job = SimpleNamespace(**source)
    job.params = {"num_lineups": 5, "ai_requested_entries": 3, "strategy_runtime": {
        "showdown_portfolio_policy": {"candidate_selection": {
            "ranked_metrics": source["results"][0][0]["captain_family_coverage_report"]["ranked_metrics"]}}}}
    service = SimpleNamespace(get_job=lambda _: job)
    response = download_ai_showdown_packet(job.job_id, format="json", finalists=20,
        entries=None, ai_requested_entries=2, service=service)
    assert json.loads(response.body)["pool_summary"]["ai_requested_entries"] == 2
    response = download_ai_showdown_packet(job.job_id, format="json", finalists=20,
        entries=None, ai_requested_entries=None, service=service)
    assert json.loads(response.body)["pool_summary"]["ai_requested_entries"] == 3
    assert "allow_incomplete_evidence" not in inspect.signature(download_ai_showdown_packet).parameters


def test_explicit_internal_override_labels_incomplete_run_and_is_not_public():
    rows = ready_rows()
    for row in rows: row["game_total_line"] = None
    service = service_fixture(rows)
    with patch("backend.app.product_services.showdown_data_readiness.refresh_live_sources") as refresh:
        job = run(service, allow_incomplete_evidence=True)
    refresh.assert_not_called()
    assert job.status == "completed", job.message
    assert job.params["showdown_evidence_snapshot"]["non_production_override"] is True
    assert job.params["data_readiness"]["status"] == "NOT_READY"
    with pytest.raises(ValueError, match="restricted"):
        OptimizerRunRequest(season=NOW.year, week=5, slate="THURSDAY_NIGHT", strategy="showdown_cash_baseline_v1",
                            params={"allow_incomplete_evidence": True})


def test_packet_rejects_live_unready_and_exposes_frozen_ready_state_and_ai_count():
    from backend.app.tests.product.test_ai_showdown_packet import universe_source
    from backend.app.product_services.ai_showdown_packet import build_packet, render_markdown
    source = universe_source()
    source["created_at"] = source["data_cutoff_at"] = AT
    for row in source["results"][0]:
        row["game_id"] = ready_rows()[0]["game_id"]
        row["market_observed_at"] = AT
    # This fixture has no source proof and therefore needs a diagnostic override.
    with pytest.raises(ValueError, match="data-ready live run"):
        build_packet(source)
    diagnostic = build_packet(source, allow_incomplete_evidence=True)
    assert diagnostic["data_readiness"]["status"] == "NOT_READY"
    assert "INCOMPLETE EVIDENCE" in render_markdown(diagnostic)
    pool = {}
    for candidate in source["results"][0][0]["captain_family_coverage_report"]["ranked_metrics"]:
        for player in candidate["players"]:
            row = {**ready_rows()[0], **player, "player_team": player["team"],
                   "game_id": source["results"][0][0]["game_id"],
                   "is_starting_qb": player["position"] == "QB",
                   "projection_run_id": source["projection_run_id"],
                   "team_spread_line": -3 if player["team"] == "AAA" else 3,
                   "team_implied_total": 26.5 if player["team"] == "AAA" else 23.5}
            for field in ("market_observed_at", "projection_observed_at", "salary_source_observed_at",
                          "pregame_context_observed_at", "starting_qb_observed_at"):
                row[field] = source["data_cutoff_at"]
            pool[player["player_id"]] = row
    readiness = evaluate_readiness(list(pool.values()), season=2026, week=5, slate=source["slate"],
        projection_run_id=source["projection_run_id"], evidence_cutoff=source["data_cutoff_at"],
        evaluated_at=source["created_at"], rules=freshness_rules(get_settings()))
    frozen = freeze_evidence(list(pool.values()), readiness, optimizer_run_id=source["job_id"])
    source["params"] = {"num_lineups": 5, "ai_requested_entries": 3, "showdown_evidence_snapshot": frozen,
        "strategy_runtime": {"showdown_portfolio_policy": {"candidate_selection": {
            "ranked_metrics": source["results"][0][0]["captain_family_coverage_report"]["ranked_metrics"]}}}}
    packet = build_packet(source, ai_requested_entries=2)
    assert packet["pool_summary"]["ai_requested_entries"] == 2
    assert packet["data_readiness"]["status"] == "READY"
    assert all(c["metrics"]["projected_total_ownership"] is None for c in packet["ai_review_universe"]["candidates"])
    assert "Select 2 entries" in render_markdown(packet)
    assert build_packet(source)["pool_summary"]["requested_entries"] == 3
    source["params"]["num_lineups"] = 1
    assert build_packet(source)["pool_summary"]["requested_entries"] == 3
    selected = source["results"][0][1]
    original_id = selected["player_id"]; selected["player_id"] = "outside-frozen-pool"
    with pytest.raises(ValueError, match="outside the frozen"):
        build_packet(source)
    selected["player_id"] = original_id
    candidate_player = source["params"]["strategy_runtime"]["showdown_portfolio_policy"]["candidate_selection"]["ranked_metrics"][30]["players"][-1]
    original_id = candidate_player["player_id"]; candidate_player["player_id"] = "outside-frozen-pool"
    with pytest.raises(ValueError, match="outside the frozen"):
        build_packet(source)
    candidate_player["player_id"] = original_id
    frozen["data_readiness"]["status"] = "NOT_READY"
    from backend.app.product_services.slate_preparation import digest
    frozen["sha256"] = digest({k:v for k,v in frozen.items() if k != "sha256"})
    with pytest.raises(ValueError, match="data-ready live run"): build_packet(source)


@pytest.mark.parametrize("native,live,locked,canonical", [(False,True,False,True),(True,False,False,True),(True,True,True,True),(True,True,False,False)])
def test_projection_player_refresh_skips_classic_and_historical(monkeypatch,native,live,locked,canonical):
    from types import SimpleNamespace
    from backend.app.product_services import showdown_data_readiness as readiness, slate_preparation
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    engine.connect.return_value.__enter__.return_value.execute.return_value.scalar_one.return_value = native
    monkeypatch.setattr("sqlalchemy.inspect",lambda *_args:SimpleNamespace(has_table=lambda *_args:canonical))
    monkeypatch.setattr(readiness,"is_live_slate",lambda *_args,**_kwargs:live)
    monkeypatch.setattr(slate_preparation,"slate_games",lambda *_args:[{"kickoff_at":(datetime.now(UTC)+timedelta(days=-1 if locked else 1)).isoformat()}])
    monkeypatch.setattr(readiness,"_refresh_player_sources",lambda *_args,**_kwargs:pytest.fail("Saved replay/Classic cannot collect live facts"))
    assert refresh_projection_player_context(SimpleNamespace(engine=engine),season=2026,week=5,slate="TEST") is None


@pytest.mark.parametrize("official_status,context_status", [("completed","completed"),("blocked","completed"),("completed","ERROR")])
def test_projection_player_refresh_reuses_collectors_and_blocks_incomplete_transform(monkeypatch,official_status,context_status):
    from types import SimpleNamespace
    from backend.app.product_services import showdown_data_readiness as readiness, slate_preparation
    from backend.app.product_services.showdown_player_context import PlayerContextUnresolved
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    engine.connect.return_value.__enter__.return_value.execute.return_value.scalar_one.return_value = True
    monkeypatch.setattr("sqlalchemy.inspect",lambda *_args:SimpleNamespace(has_table=lambda *_args:True))
    monkeypatch.setattr(readiness,"is_live_slate",lambda *_args,**_kwargs:True)
    monkeypatch.setattr(slate_preparation,"slate_games",lambda *_args:[{"kickoff_at":(datetime.now(UTC)+timedelta(days=1)).isoformat()}])
    events = []
    def collect(_service,**kwargs):
        events.append("collect")
        attempt = kwargs["attempt"]
        def official():
            if official_status == "blocked":raise PlayerContextUnresolved("Official identities require review")
            return {"rows":2}
        def context():
            if context_status == "ERROR":raise RuntimeError("Context transform failed")
            return {"rows":52}
        attempt("official_player_status",official)
        attempt("canonical_player_context",context)
    monkeypatch.setattr(readiness,"_refresh_player_sources",collect)
    service = SimpleNamespace(engine=engine)
    if official_status == "blocked" or context_status == "ERROR":
        with pytest.raises(PlayerContextUnresolved):
            refresh_projection_player_context(service,season=2026,week=5,slate="TEST")
    else:
        report = refresh_projection_player_context(service,season=2026,week=5,slate="TEST")
        assert report["canonical_player_context"]["result"]["rows"] == 52
    assert events == ["collect"]
