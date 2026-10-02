"""Saved contest scope and observation lineage."""

from types import SimpleNamespace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

from backend.app.product_services import saved_contests


@pytest.fixture
def catalog_engine(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def attach_target(connection, record):  # noqa: ARG001
        connection.execute("ATTACH DATABASE ':memory:' AS target")

    with engine.begin() as connection:
        connection.exec_driver_sql("""
            CREATE TABLE target.saved_dk_contest (
                contest_id TEXT PRIMARY KEY, url TEXT, season INTEGER, week INTEGER,
                slate TEXT, contest_format TEXT, contest_type TEXT, name TEXT,
                draft_group_id TEXT, active BOOLEAN, created_at TEXT, updated_at TEXT
            )
        """)
        connection.exec_driver_sql("""
            CREATE TABLE target.saved_dk_contest_observation (
                observation_id TEXT PRIMARY KEY, contest_id TEXT, observed_at TEXT,
                observation_reason TEXT, source TEXT, source_sha256 TEXT,
                source_payload_json TEXT, contest_json TEXT, error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
    monkeypatch.setattr(saved_contests, "validate_target_schema", lambda *args, **kwargs: None)
    yield engine
    engine.dispose()


def _row(entries=50):
    return {
        "contest_id": "123", "url": "https://www.draftkings.com/draft/contest/123",
        "name": "Test GPP", "draft_group_id": 7, "current_entries": entries,
        "capacity": 100, "source": "draftkings_embedded_contest_detail",
        "source_sha256": "a" * 64, "source_payload": {"entries": entries},
    }


def _complete_row():
    return {
        **_row(), "entry_fee": 5, "prize_pool": 400, "paid_places": 20,
        "payout_ladder": [{"from": 1, "to": 20, "cash": 20}],
        "lock_time": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "maximum_entries": 1, "single_entry": True, "state": "Upcoming",
        "slate": "DET @ BUF", "guaranteed": True,
        "observed_at": (datetime.now(UTC) - timedelta(hours=3)).isoformat(),
        "unavailable_fields": [],
    }


def test_failed_live_fetch_recovers_verified_saved_economics_without_stale_overlay(catalog_engine):
    from backend.app.product_services.showdown_contests import select_contests

    saved_contests.save_contests(
        catalog_engine, [_complete_row()], season=2026, week=2,
        slate="THURSDAY_NIGHT", contest_format="showdown", contest_type="gpp",
    )
    failed = {"contest_id": "123", "url": _row()["url"], "source": "unavailable",
              "error": "DraftKings unavailable", "unavailable_fields": ["payout_ladder"]}
    saved_contests.record_saved_observations(catalog_engine, [failed], reason="optimizer")
    recovered = saved_contests.recover_saved_contest_snapshots(
        catalog_engine, [failed], season=2026, week=2, slate="THURSDAY_NIGHT",
    )
    assert recovered[0]["source"] == "saved_snapshot"
    assert recovered[0]["live_fetch_error"] == "DraftKings unavailable"
    assert recovered[0]["snapshot_observation_id"]
    selected, _ = select_contests(recovered)
    assert selected[0]["economics"]["near_lock"] is False
    assert selected[0]["economics"]["current_effective_rake"] is None
    assert selected[0]["economics"]["effective_field_size_used"] == 100
    assert saved_contests.recover_saved_contest_snapshots(
        catalog_engine, [failed], season=2026, week=3, slate="THURSDAY_NIGHT",
    ) == [failed]
    assert saved_contests.recover_saved_contest_snapshots(
        catalog_engine, [{**failed, "unavailable_fields": []}],
        season=2026, week=2, slate="THURSDAY_NIGHT",
    )[0]["source"] == "unavailable"
    assert saved_contests.recover_saved_contest_snapshots(
        catalog_engine, [{**failed, "manual_fields": ["entry_fee"], "entry_fee": 9}],
        season=2026, week=2, slate="THURSDAY_NIGHT",
    )[0]["entry_fee"] == 9


def test_saved_contest_keeps_scope_and_immutable_refresh_history(catalog_engine):
    saved = saved_contests.save_contests(
        catalog_engine, [_row()], season=2026, week=2, slate="THURSDAY_NIGHT",
        contest_format="showdown", contest_type="gpp",
    )
    assert len(saved) == 1
    assert saved[0]["observation_count"] == 1
    assert saved[0]["latest_contest"]["current_entries"] == 50
    assert saved_contests.list_saved_contest_scopes(catalog_engine)[0]["contest_count"] == 1
    saved_contests.save_contests(
        catalog_engine, [{**_row(60), "name": None}], season=2026, week=2,
        slate="THURSDAY_NIGHT", contest_format="showdown", contest_type="gpp",
    )
    assert saved_contests.record_saved_observations(catalog_engine, [_row(75)], reason="preview") == 1
    refreshed = saved_contests.list_saved_contests(
        catalog_engine, season=2026, week=2, slate="THURSDAY_NIGHT", contest_type="gpp",
    )
    assert refreshed[0]["name"] == "Test GPP"
    assert refreshed[0]["observation_count"] == 3
    assert refreshed[0]["latest_contest"]["current_entries"] == 75
    observations = saved_contests.list_contest_observations(catalog_engine, "123")
    assert len(observations) == 3
    assert {row["contest"]["current_entries"] for row in observations} == {50, 60, 75}
    assert all(row["contest"]["catalog_scope"]["contest_type"] == "gpp" for row in observations)
    with catalog_engine.connect() as connection:
        history = connection.execute(text(
            "SELECT source_payload_json FROM target.saved_dk_contest_observation "
            "WHERE contest_id = '123' ORDER BY created_at, observation_id"
        )).scalars().all()
    assert {"entries": 50} in [saved_contests._decoded(row) for row in history]
    assert {"entries": 75} in [saved_contests._decoded(row) for row in history]
    assert saved_contests.archive_saved_contest(catalog_engine, "123") is True
    assert saved_contests.list_saved_contests(
        catalog_engine, season=2026, week=2, slate="THURSDAY_NIGHT",
    ) == []
    assert saved_contests.list_saved_contest_scopes(catalog_engine) == []


def test_saved_scope_browser_lists_groups_across_weeks(catalog_engine):
    saved_contests.save_contests(
        catalog_engine, [_row()], season=2026, week=2, slate="THURSDAY_NIGHT",
        contest_format="showdown", contest_type="gpp",
    )
    other = {**_row(), "contest_id": "456", "url": "https://www.draftkings.com/draft/contest/456"}
    saved_contests.save_contests(
        catalog_engine, [other], season=2026, week=3, slate="SUNDAY_MAIN",
        contest_format="classic", contest_type="cash",
    )
    scopes = saved_contests.list_saved_contest_scopes(catalog_engine)
    assert [(row["week"], row["slate"], row["contest_format"], row["contest_type"], row["contest_count"]) for row in scopes] == [
        (3, "SUNDAY_MAIN", "classic", "cash", 1),
        (2, "THURSDAY_NIGHT", "showdown", "gpp", 1),
    ]


def test_saved_list_retains_last_successful_facts_after_failed_refresh(catalog_engine):
    saved_contests.save_contests(
        catalog_engine, [_row()], season=2026, week=2, slate="THURSDAY_NIGHT",
        contest_format="showdown", contest_type="gpp",
    )
    saved_contests.record_saved_observations(catalog_engine, [{
        "contest_id": "123", "url": _row()["url"], "source": "unavailable",
        "error": "DraftKings unavailable", "unavailable_fields": ["capacity"],
    }], reason="preview")
    listed = saved_contests.list_saved_contests(
        catalog_engine, season=2026, week=2, slate="THURSDAY_NIGHT",
    )[0]
    assert listed["latest_error"] == "DraftKings unavailable"
    assert listed["latest_successful_contest"]["current_entries"] == 50


def test_saved_contest_rejects_scope_reassignment_and_bad_url(catalog_engine):
    saved_contests.save_contests(
        catalog_engine, [_row()], season=2026, week=2, slate="THURSDAY_NIGHT",
        contest_format="showdown", contest_type="gpp",
    )
    with pytest.raises(ValueError, match="another slate"):
        saved_contests.save_contests(
            catalog_engine, [_row()], season=2026, week=3, slate="SUNDAY_MAIN",
            contest_format="showdown", contest_type="gpp",
        )
    with pytest.raises(ValueError, match="DraftKings"):
        saved_contests.save_contests(
            catalog_engine, [{**_row(), "url": "https://example.com/draft/contest/123"}],
            season=2026, week=2, slate="THURSDAY_NIGHT",
            contest_format="showdown", contest_type="gpp",
        )


def test_preview_records_existing_saved_contest(monkeypatch):
    from backend.app.api.product_routes import preview_optimizer_contests
    from backend.app.product_schemas import ContestPreviewRequest
    from backend.app.product_services import showdown_contests

    monkeypatch.setattr(showdown_contests, "fetch_contests", lambda urls, manual: [_row(80)])
    called = []
    monkeypatch.setattr(saved_contests, "record_saved_observations", lambda engine, rows, reason: called.append((rows, reason)))
    result = preview_optimizer_contests(
        ContestPreviewRequest(urls=[_row()["url"]]),
        service=SimpleNamespace(engine=object()),
    )
    assert result["contests"][0]["current_entries"] == 80
    assert called[0][1] == "preview"


def test_saved_contest_api_contracts(monkeypatch):
    from backend.app.api.product_routes import (
        get_saved_optimizer_contests,
        get_saved_optimizer_contest_scopes,
        get_saved_optimizer_contest_observations,
        remove_saved_optimizer_contest,
        save_optimizer_contests,
    )
    from backend.app.product_schemas import SavedContestRequest
    from backend.app.product_services import showdown_contests

    engine = object()
    service = SimpleNamespace(engine=engine)
    monkeypatch.setattr(showdown_contests, "fetch_contests", lambda urls, manual: [_row()])
    monkeypatch.setattr(saved_contests, "save_contests", lambda engine, rows, **scope: [{"contest_id": "123", **scope}])
    monkeypatch.setattr(saved_contests, "list_saved_contests", lambda engine, **scope: [{"contest_id": "123", **scope}])
    monkeypatch.setattr(saved_contests, "list_saved_contest_scopes", lambda engine: [{"slate": "THURSDAY_NIGHT", "contest_count": 1}])
    monkeypatch.setattr(saved_contests, "list_contest_observations", lambda engine, contest_id, limit: [{"observation_id": "obs-1"}])
    monkeypatch.setattr(saved_contests, "archive_saved_contest", lambda engine, contest_id: True)
    request = SavedContestRequest(
        season=2026, week=2, slate="THURSDAY_NIGHT", contest_format="showdown",
        contest_type="gpp", urls=[_row()["url"]],
    )
    assert save_optimizer_contests(request, service=service)["contests"][0]["contest_id"] == "123"
    assert get_saved_optimizer_contests(
        season=2026, week=2, slate="THURSDAY_NIGHT", contest_format="showdown",
        contest_type="gpp", service=service,
    )["contests"][0]["contest_type"] == "gpp"
    assert get_saved_optimizer_contest_scopes(service=service)["scopes"][0]["contest_count"] == 1
    assert get_saved_optimizer_contest_observations("123", limit=50, service=service)["observations"][0]["observation_id"] == "obs-1"
    assert remove_saved_optimizer_contest("123", service=service)["archived"] is True
