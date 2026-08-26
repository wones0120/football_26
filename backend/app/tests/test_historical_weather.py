from __future__ import annotations

import sys
from datetime import UTC, datetime
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import (
    Base,
    CuratedGameWeather,
    IngestRun,
    RawNflSchedule,
)
from backend.app.schemas import NflReadPySeasonRequest
from backend.app.services.historical_weather import (
    HISTORICAL_GAME_WEATHER_DATA_KIND,
    apply_historical_weather_rebuild,
    assess_historical_game_weather,
    schedule_kickoff_at,
)
from backend.app.services.ingest import IngestService
from backend.app.product_services.point_in_time import snapshot_visible_at_cutoff


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
    stadium: str,
    roof: str,
    temp: float | None,
    wind: float | None,
    created_at: datetime,
) -> RawNflSchedule:
    return RawNflSchedule(
        ingest_run_id=run_id,
        source_system="nflreadpy",
        season=2025,
        week=10,
        game_id=game_id,
        home_team="BUF",
        away_team="MIA",
        game_type="REG",
        kickoff="13:00",
        stadium=stadium,
        raw_row_json={
            "gameday": "2025-11-09",
            "gametime": "13:00",
            "roof": roof,
            "surface": "grass",
            "temp": temp,
            "wind": wind,
        },
        created_at=created_at,
    )


def test_schedule_kickoff_uses_documented_eastern_time_and_dst() -> None:
    winter = _schedule(
        run_id="run-1",
        game_id="winter",
        stadium="Example",
        roof="outdoors",
        temp=40,
        wind=10,
        created_at=datetime(2025, 1, 1),
    )
    winter.raw_row_json["gameday"] = "2025-11-09"
    assert schedule_kickoff_at(winter) == datetime(2025, 11, 9, 18, 0, tzinfo=UTC)

    summer = _schedule(
        run_id="run-1",
        game_id="summer",
        stadium="Example",
        roof="outdoors",
        temp=80,
        wind=5,
        created_at=datetime(2025, 1, 1),
    )
    summer.raw_row_json["gameday"] = "2025-09-07"
    assert schedule_kickoff_at(summer) == datetime(2025, 9, 7, 17, 0, tzinfo=UTC)


def test_assessment_uses_latest_schedule_and_keeps_actuals_replay_ineligible() -> None:
    session = _session()
    _run(session, "run-old")
    _run(session, "run-new")
    session.add_all(
        [
            _schedule(
                run_id="run-old",
                game_id="game-outdoor",
                stadium="Old Stadium Name",
                roof="outdoors",
                temp=None,
                wind=None,
                created_at=datetime(2025, 1, 1),
            ),
            _schedule(
                run_id="run-new",
                game_id="game-outdoor",
                stadium="Current Stadium Name",
                roof="outdoors",
                temp=38,
                wind=12,
                created_at=datetime(2025, 2, 1),
            ),
            _schedule(
                run_id="run-new",
                game_id="game-dome",
                stadium="Dome",
                roof="dome",
                temp=None,
                wind=None,
                created_at=datetime(2025, 2, 1),
            ),
            _schedule(
                run_id="run-new",
                game_id="game-missing",
                stadium="Outdoor",
                roof="outdoors",
                temp=None,
                wind=None,
                created_at=datetime(2025, 2, 1),
            ),
            _schedule(
                run_id="run-new",
                game_id="game-extreme",
                stadium="Windy",
                roof="outdoors",
                temp=43,
                wind=71,
                created_at=datetime(2025, 2, 1),
            ),
        ]
    )
    session.commit()

    assessment = assess_historical_game_weather(
        session,
        season_start=2025,
        season_end=2025,
    )
    report = assessment.report()

    assert assessment.source_rows == 5
    assert assessment.latest_games == 4
    assert report["weather_status_counts"] == {
        "indoor_not_applicable": 1,
        "missing_exposed": 1,
        "observed": 2,
    }
    assert report["quality_flag_counts"] == {
        "exposed_weather_incomplete": 1,
        "extreme_wind_review": 1,
    }
    assert report["replay_eligible_rows"] == 0

    result = apply_historical_weather_rebuild(session, assessment)
    session.commit()
    assert result["rows_written"] == 4
    outdoor = session.get(CuratedGameWeather, "game-outdoor")
    assert outdoor is not None
    assert outdoor.stadium == "Current Stadium Name"
    assert outdoor.temperature_f == 38
    assert outdoor.data_kind == HISTORICAL_GAME_WEATHER_DATA_KIND
    assert outdoor.observed_at is None
    assert outdoor.replay_eligible is False
    assert snapshot_visible_at_cutoff(
        outdoor.observed_at,
        datetime(2025, 11, 9, 17, 0, tzinfo=UTC),
    ) is False

    # Rebuild is deterministic and replaces only the selected season range.
    apply_historical_weather_rebuild(session, assessment)
    session.commit()
    assert session.query(CuratedGameWeather).count() == 4


def test_schedule_ingest_rebuilds_curated_weather_automatically(
    monkeypatch,
) -> None:
    session = _session()
    schedule_rows = pd.DataFrame(
        [
            {
                "season": 2025,
                "week": 1,
                "game_id": "2025_01_MIA_BUF",
                "home_team": "BUF",
                "away_team": "MIA",
                "game_type": "REG",
                "gametime": "13:00",
                "gameday": "2025-09-07",
                "stadium": "New Era Field",
                "roof": "outdoors",
                "surface": "a_turf",
                "temp": 58.0,
                "wind": 8.0,
            }
        ]
    )
    fake_nflreadpy = SimpleNamespace(load_schedules=lambda seasons: schedule_rows)
    monkeypatch.setitem(sys.modules, "nflreadpy", fake_nflreadpy)

    result = IngestService(session).ingest_nflreadpy_schedules(
        NflReadPySeasonRequest(season=2025)
    )

    assert result.status == "completed"
    weather = session.get(CuratedGameWeather, "2025_01_MIA_BUF")
    assert weather is not None
    assert weather.temperature_f == 58.0
    assert weather.wind_mph == 8.0
    assert weather.weather_status == "observed"
    assert weather.kickoff_at == datetime(2025, 9, 7, 17, 0)

    # A refresh replaces referenced raw schedule rows and rebuilds weather atomically.
    refreshed = IngestService(session).ingest_nflreadpy_schedules(
        NflReadPySeasonRequest(season=2025)
    )
    assert refreshed.status == "completed"
    assert session.query(RawNflSchedule).count() == 1
    assert session.query(CuratedGameWeather).count() == 1


def test_database_contract_rejects_replay_eligible_retrospective_weather() -> None:
    session = _session()
    _run(session, "run-1")
    raw = _schedule(
        run_id="run-1",
        game_id="unsafe-game",
        stadium="Example",
        roof="outdoors",
        temp=50,
        wind=5,
        created_at=datetime(2025, 1, 1),
    )
    session.add(raw)
    session.flush()
    session.add(
        CuratedGameWeather(
            game_id="unsafe-game",
            season=2025,
            week=10,
            weather_status="observed",
            data_kind=HISTORICAL_GAME_WEATHER_DATA_KIND,
            observation_basis="retrospective_test",
            observed_at=datetime(2025, 11, 9, 17, 0, tzinfo=UTC),
            replay_eligible=True,
            quality_flags_json=[],
            source_system="nflreadpy",
            source_ingest_run_id="run-1",
            raw_nfl_schedule_id=raw.raw_nfl_schedule_id,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
