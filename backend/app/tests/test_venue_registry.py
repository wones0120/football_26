from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import (
    Base,
    CuratedGameVenue,
    IngestRun,
    RawNflSchedule,
    VenueRegistryRecord,
)
from backend.app.schemas import NflReadPySeasonRequest
from backend.app.services.ingest import IngestService
from backend.app.services.venue_registry import (
    DEFAULT_VENUE_REGISTRY_PATH,
    VENUE_REGISTRY_CONTRACT_ID,
    apply_venue_registry,
    assess_venue_registry,
    load_venue_registry_seed,
)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, future=True)()


def _run(session: Session, run_id: str) -> None:
    session.add(
        IngestRun(
            ingest_run_id=run_id,
            source_system="nflreadpy",
            source_table="nfl_schedule",
            status="completed",
        )
    )
    session.flush()


def _schedule(
    *,
    run_id: str,
    game_id: str,
    stadium_id: str | None,
    stadium: str,
    location: str = "Home",
) -> RawNflSchedule:
    return RawNflSchedule(
        ingest_run_id=run_id,
        source_system="nflreadpy",
        season=2025,
        week=int(game_id.split("_")[1]),
        game_id=game_id,
        home_team="PHI",
        away_team="DAL",
        game_type="REG",
        kickoff="13:00",
        stadium=stadium,
        raw_row_json={
            "stadium_id": stadium_id,
            "stadium": stadium,
            "location": location,
            "gameday": "2025-09-07",
            "gametime": "13:00",
            "roof": "outdoors",
        },
        created_at=datetime(2025, 1, 1),
    )


def test_production_seed_is_versioned_and_covers_reviewed_2025_exceptions() -> None:
    seed = load_venue_registry_seed()

    assert seed.contract_id == VENUE_REGISTRY_CONTRACT_ID
    assert seed.registry_version == 1
    assert len(seed.records) == 37
    assert len(seed.overrides) == 15
    assert all(record["latitude"] is not None for record in seed.records)
    assert all(record["longitude"] is not None for record in seed.records)
    assert all(record["timezone"] for record in seed.records)

    overrides = {override["game_id"]: override for override in seed.overrides}
    assert overrides["2025_04_MIN_PIT"]["registry_record_id"] == (
        "venue-ie-dublin-croke-park:v1"
    )
    assert overrides["2025_10_ATL_IND"]["registry_record_id"] == (
        "venue-de-berlin-olympiastadion:v1"
    )
    assert overrides["2025_11_WAS_MIA"]["registry_record_id"] == (
        "venue-es-madrid-bernabeu:v1"
    )


def test_mapping_uses_source_id_and_reviewed_override_not_display_name() -> None:
    session = _session()
    _run(session, "run-1")
    session.add_all(
        [
            _schedule(
                run_id="run-1",
                game_id="2025_01_DAL_PHI",
                stadium_id="PHI00",
                stadium="Incorrect Display Name Must Be Ignored",
            ),
            _schedule(
                run_id="run-1",
                game_id="2025_04_MIN_PIT",
                stadium_id="PIT00",
                stadium="Acrisure Stadium",
                location="Neutral",
            ),
            _schedule(
                run_id="run-1",
                game_id="2025_08_FAKE_PHI",
                stadium_id=None,
                stadium="Unknown Venue",
            ),
        ]
    )
    session.commit()

    assessment = assess_venue_registry(
        session,
        season_start=2025,
        season_end=2025,
    )
    report = assessment.report()

    assert report["mapping_status_counts"] == {"resolved": 2, "unresolved": 1}
    assert report["mapping_method_counts"] == {
        "missing_source_venue_id": 1,
        "reviewed_game_override": 1,
        "source_venue_id": 1,
    }
    assert report["neutral_games"] == 1
    assert report["neutral_games_without_override"] == []
    assert report["unresolved_games"] == ["2025_08_FAKE_PHI"]
    assert report["acceptance_ready"] is False

    result = apply_venue_registry(session, assessment)
    session.commit()
    assert result["registry_created"] == 37
    assert result["overrides_created"] == 15
    assert result["mapping_rows_written"] == 3

    home = session.get(CuratedGameVenue, "2025_01_DAL_PHI")
    assert home is not None
    assert home.registry_record_id == "venue-us-phi-lincoln-financial:v1"
    assert home.mapping_method == "source_venue_id"
    assert home.evidence_json["source_stadium_name_diagnostic_only"] == (
        "Incorrect Display Name Must Be Ignored"
    )

    dublin = session.get(CuratedGameVenue, "2025_04_MIN_PIT")
    assert dublin is not None
    assert dublin.registry_record_id == "venue-ie-dublin-croke-park:v1"
    assert dublin.mapping_method == "reviewed_game_override"
    assert dublin.evidence_json["source_venue_id"] == "PIT00"

    quarantined = session.get(CuratedGameVenue, "2025_08_FAKE_PHI")
    assert quarantined is not None
    assert quarantined.mapping_status == "unresolved"
    assert quarantined.registry_record_id is None
    assert quarantined.evidence_json["quarantine_reason"] == (
        "missing_source_venue_id"
    )

    second = apply_venue_registry(session, assessment)
    session.commit()
    assert second["registry_created"] == 0
    assert second["registry_existing"] == 37
    assert second["overrides_created"] == 0
    assert session.query(CuratedGameVenue).count() == 3


def test_conflicting_effective_source_ids_are_quarantined_and_reported(
    tmp_path: Path,
) -> None:
    seed = load_venue_registry_seed()
    base = dict(seed.records[0])
    base.update(
        {
            "registry_record_id": "venue-test-one:v1",
            "venue_id": "venue-test-one",
            "canonical_name": "Test One",
            "effective_from_season": 2024,
            "effective_to_season": 2025,
            "source_system": "pfr",
            "source_venue_id": "TEST00",
        }
    )
    conflicting = dict(base)
    conflicting.update(
        {
            "registry_record_id": "venue-test-two:v1",
            "venue_id": "venue-test-two",
            "canonical_name": "Test Two",
        }
    )
    seed_path = tmp_path / "venue_registry.json"
    seed_path.write_text(
        json.dumps(
            {
                "contract_id": VENUE_REGISTRY_CONTRACT_ID,
                "registry_version": 1,
                "reviewed_at": "2026-08-01",
                "venues": [base, conflicting],
                "game_overrides": [],
            }
        ),
        encoding="utf-8",
    )

    session = _session()
    _run(session, "run-1")
    session.add(
        _schedule(
            run_id="run-1",
            game_id="2025_01_TEST_PHI",
            stadium_id="TEST00",
            stadium="Same Name Is Not Evidence",
        )
    )
    session.commit()

    assessment = assess_venue_registry(
        session,
        season_start=2025,
        season_end=2025,
        seed_path=seed_path,
    )
    report = assessment.report()

    assert report["mapping_status_counts"] == {"ambiguous": 1}
    assert report["ambiguous_games"] == ["2025_01_TEST_PHI"]
    assert len(report["source_alias_conflicts"]) == 1
    assert assessment.rows[0]["registry_record_id"] is None
    assert assessment.rows[0]["candidate_registry_record_ids_json"] == [
        "venue-test-one:v1",
        "venue-test-two:v1",
    ]


def test_database_contract_rejects_resolved_mapping_without_registry_record() -> None:
    session = _session()
    _run(session, "run-1")
    schedule = _schedule(
        run_id="run-1",
        game_id="2025_01_DAL_PHI",
        stadium_id="PHI00",
        stadium="Lincoln Financial Field",
    )
    session.add(schedule)
    session.flush()
    session.add(
        CuratedGameVenue(
            game_id=schedule.game_id or "",
            season=2025,
            week=1,
            mapping_status="resolved",
            mapping_method="source_venue_id",
            source_venue_id="PHI00",
            registry_record_id=None,
            evidence_json={},
            candidate_registry_record_ids_json=[],
            source_ingest_run_id="run-1",
            raw_nfl_schedule_id=schedule.raw_nfl_schedule_id,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_schedule_ingest_rebuilds_game_venue_mapping(monkeypatch) -> None:
    session = _session()
    schedule_rows = pd.DataFrame(
        [
            {
                "season": 2025,
                "week": 1,
                "game_id": "2025_01_DAL_PHI",
                "home_team": "PHI",
                "away_team": "DAL",
                "game_type": "REG",
                "gametime": "20:20",
                "gameday": "2025-09-04",
                "stadium_id": "PHI00",
                "stadium": "A Display Name That Can Change",
                "location": "Home",
                "roof": "outdoors",
                "surface": "grass",
                "temp": 75.0,
                "wind": 11.0,
            }
        ]
    )
    fake_nflreadpy = SimpleNamespace(load_schedules=lambda seasons: schedule_rows)
    monkeypatch.setitem(sys.modules, "nflreadpy", fake_nflreadpy)

    result = IngestService(session).ingest_nflreadpy_schedules(
        NflReadPySeasonRequest(season=2025)
    )

    assert result.status == "completed"
    mapping = session.get(CuratedGameVenue, "2025_01_DAL_PHI")
    assert mapping is not None
    assert mapping.mapping_status == "resolved"
    assert mapping.registry_record_id == "venue-us-phi-lincoln-financial:v1"
    assert session.query(VenueRegistryRecord).count() == 37

    refreshed = IngestService(session).ingest_nflreadpy_schedules(
        NflReadPySeasonRequest(season=2025)
    )
    assert refreshed.status == "completed"
    assert session.query(RawNflSchedule).count() == 1
    assert session.query(CuratedGameVenue).count() == 1


def test_default_seed_path_is_inside_repository() -> None:
    assert DEFAULT_VENUE_REGISTRY_PATH.name == "venue_registry_v1.json"
    assert DEFAULT_VENUE_REGISTRY_PATH.exists()
