from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from fastapi import HTTPException

from backend.app.api.product_routes import decide_skill_exposure, download_optimizer_lineups
from backend.app.product_schemas import SkillExposureDecisionRequest
from backend.app.product_services.skill_exposure_approval import (
    approval_status, ensure_classic_export_ready, record_decision,
    required_skill_players,
)


NOW = datetime(2026, 9, 29, 22, tzinfo=UTC)


def job(position="RB", readiness="ENTRY_READY_WITH_APPROVAL_REQUIRED"):
    report = {"entry_readiness": {"status": readiness},
              "prelock_timing": {"first_saved_kickoff_at": "2026-10-04T17:00:00+00:00"}}
    player = {"player_id": "core", "name": "Core", "position": position,
              "classic_small_field_report": report}
    return SimpleNamespace(job_id="run-1", contest_format="classic",
                           strategy="classic_small_field_gpp",
                           results=[[player], [{"player_id": "core", "name": "Core", "position": position}]])


@pytest.fixture
def engine():
    db = create_engine("sqlite://")

    @event.listens_for(db, "connect")
    def attach(connection, _record):
        connection.execute("ATTACH DATABASE ':memory:' AS target")

    with db.begin() as connection:
        connection.execute(text("""
            CREATE TABLE target.skill_exposure_decision (
                decision_id TEXT PRIMARY KEY, optimizer_run_id TEXT, player_id TEXT,
                selected_exposure REAL, decision TEXT, requested_cap REAL,
                resulting_optimizer_run_id TEXT, reason TEXT, decided_at TEXT,
                first_kickoff_at TEXT, UNIQUE(optimizer_run_id, player_id))
        """))
    return db


@pytest.mark.parametrize("position,required", [("RB", True), ("WR", True),
                                                ("TE", True), ("DST", False), ("QB", False)])
def test_only_full_skill_player_exposure_requires_approval(position, required):
    assert bool(required_skill_players(job(position))) is required


def test_reason_and_prelock_required_and_decision_is_immutable(engine):
    current = job()
    with pytest.raises(ValueError, match="reason"):
        record_decision(current, engine, player_id="core", decision="approve", reason=" ", now=NOW)
    with pytest.raises(ValueError, match="before slate kickoff"):
        record_decision(current, engine, player_id="core", decision="approve", reason="yes",
                        now=datetime(2026, 10, 4, 17, tzinfo=UTC))
    with pytest.raises(ValueError, match="new optimizer run"):
        record_decision(current, engine, player_id="core", decision="cap", reason="reduce",
                        requested_cap=.8, now=NOW)
    with pytest.raises(ValueError, match="between 0 and 80%"):
        record_decision(current, engine, player_id="core", decision="cap", reason="reduce",
                        requested_cap=.9, resulting_run_id="run-2", now=NOW)
    with pytest.raises(ValueError, match="approval required"):
        ensure_classic_export_ready(current, engine)
    saved = record_decision(current, engine, player_id="core", decision="approve",
                            reason="Accept elite-core dependency", now=NOW)
    assert saved["decision"] == "approve"
    assert not approval_status(current, engine)["pending"]
    assert ensure_classic_export_ready(current, engine)["approved"]
    with pytest.raises(ValueError, match="immutable"):
        record_decision(current, engine, player_id="core", decision="approve",
                        reason="Different reason", now=NOW)


def test_preview_cannot_export_with_approval(engine):
    with pytest.raises(ValueError, match="DEVELOPMENT_PREVIEW"):
        ensure_classic_export_ready(job(readiness="DEVELOPMENT_PREVIEW"), engine)


def test_showdown_bypasses_classic_approval_gate(engine):
    other = job()
    other.contest_format = "showdown"
    assert ensure_classic_export_ready(other, engine)["pending"] == []


def test_cap_route_creates_new_run_and_preserves_original(engine):
    original = job()
    original.status = "completed"
    original.params = {"classic_candidate_pool_size": 100}
    original.season, original.week, original.slate = 2026, 4, "SUNDAY_MAIN"
    original.objective = "gpp"
    original.projection_run_id = "projection"
    original.rule_run_id = None
    original.data_cutoff_at = NOW
    requests = []
    replacement = SimpleNamespace(status="completed", message="ok", results=[
        [{"player_id": "core"}], [{"player_id": "other"}],
    ])
    service = SimpleNamespace(engine=engine, get_job=lambda _: original,
                              run_job=lambda **kwargs: (requests.append(kwargs), replacement)[1])
    saved = decide_skill_exposure("run-1", SkillExposureDecisionRequest(
        player_id="core", decision="cap", reason="Reduce dependency", requested_cap=0.5,
    ), service=service)
    assert saved["decision"] == "cap"
    assert saved["new_optimizer_run_id"] != original.job_id
    assert requests[0]["params"]["maximum_exposure_by_player"] == {"core": 0.5}
    assert "maximum_exposure_by_player" not in original.params
    assert approval_status(original, engine)["pending"]


def test_direct_classic_export_requires_saved_approval(engine):
    current = job()
    current.status = "completed"
    service = SimpleNamespace(engine=engine, get_job=lambda _: current)
    with pytest.raises(HTTPException, match="approval required") as error:
        download_optimizer_lineups("run-1", service=service)
    assert error.value.status_code == 422
