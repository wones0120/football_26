from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.routes import router
from backend.app.db import get_db_session
from backend.app.models import (
    Base,
    CuratedGameVenue,
    CuratedGameWeather,
    CuratedSalary,
    IngestRun,
    RawNflSchedule,
    VenueRegistryRecord,
    WeatherForecastCaptureResult,
    WeatherForecastSnapshot,
)
from backend.app.services.current_weather_forecast import (
    CURRENT_OPEN_METEO_HOURLY_VARIABLES,
    CURRENT_WEATHER_FORECAST_BASIS_KIND,
    CURRENT_WEATHER_FORECAST_DATA_KIND,
    CURRENT_WEATHER_FORECAST_PROVIDER,
)
from backend.app.services.slate_weather import SlateWeatherService
from backend.app.services.weather_forecast_backfill import (
    OPEN_METEO_HOURLY_VARIABLES,
    WEATHER_FORECAST_BASIS_KIND,
    WEATHER_FORECAST_CONTRACT_ID,
    WEATHER_FORECAST_DATA_KIND,
    WEATHER_FORECAST_FIXED_LEAD_HOURS,
    WEATHER_FORECAST_MODEL,
    WEATHER_FORECAST_PROVIDER,
)


def _session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _seed_slice(
    session: Session,
    *,
    season: int,
    week: int,
    slate: str,
) -> IngestRun:
    run = IngestRun(
        ingest_run_id=f"salary-{season}-{week}-{slate}",
        source_system="draftkings",
        source_table="salary",
        season=season,
        week=week,
        slate=slate,
        status="completed",
    )
    session.add(run)
    session.flush()
    return run


def _seed_game(
    session: Session,
    *,
    salary_run: IngestRun,
    game_id: str,
    season: int,
    week: int,
    slate: str,
    away_team: str,
    home_team: str,
    gameday: str,
    gametime: str,
    default_roof: str = "outdoor",
) -> RawNflSchedule:
    schedule_run = IngestRun(
        ingest_run_id=f"schedule-{game_id}",
        source_system="nflverse",
        source_table="schedules",
        season=season,
        week=week,
        status="completed",
    )
    session.add(schedule_run)
    session.flush()
    schedule = RawNflSchedule(
        ingest_run_id=schedule_run.ingest_run_id,
        source_system="nflverse",
        season=season,
        week=week,
        game_id=game_id,
        home_team=home_team,
        away_team=away_team,
        game_type="REG",
        kickoff=gametime,
        status="final",
        stadium=f"{home_team} Test Stadium",
        raw_row_json={"gameday": gameday, "gametime": gametime},
    )
    session.add(schedule)
    session.flush()
    registry_record_id = f"{home_team.lower()}-test:v1"
    venue = VenueRegistryRecord(
        registry_record_id=registry_record_id,
        venue_id=f"{home_team.lower()}-test",
        registry_version=1,
        canonical_name=f"{home_team} Test Stadium",
        effective_from_season=season,
        effective_to_season=None,
        latitude=40.0,
        longitude=-75.0,
        timezone="America/New_York",
        default_roof=default_roof,
        country_code="US",
        source_system="nflverse",
        source_venue_id=f"{home_team}00",
        source_evidence_uri="https://example.test/stadium",
        coordinate_source_uri="https://example.test/coordinates",
        review_notes="test fixture",
        review_classifications_json=[],
        definition_sha256=(home_team.lower()[0] * 64),
    )
    session.add(venue)
    session.flush()
    session.add(
        CuratedGameVenue(
            game_id=game_id,
            season=season,
            week=week,
            mapping_status="resolved",
            mapping_method="source_venue_id",
            source_venue_id=f"{home_team}00",
            registry_record_id=registry_record_id,
            evidence_json={},
            candidate_registry_record_ids_json=[],
            source_ingest_run_id=schedule_run.ingest_run_id,
            raw_nfl_schedule_id=schedule.raw_nfl_schedule_id,
        )
    )
    session.add_all(
        [
            CuratedSalary(
                ingest_run_id=salary_run.ingest_run_id,
                source_system="draftkings",
                season=season,
                week=week,
                slate=slate,
                source_player_key=f"{game_id}-{team}",
                player_name=f"{team} Player",
                normalized_name=f"{team.lower()} player",
                team=team,
                opponent=home_team if team == away_team else away_team,
                position="QB",
                roster_position="QB",
                salary=5000,
                game_info=f"{away_team}@{home_team}",
            )
            for team in (away_team, home_team)
        ]
    )
    return schedule


def _seed_forecast(
    session: Session,
    *,
    snapshot_id: str,
    game_id: str,
    registry_record_id: str,
    season: int,
    week: int,
    valid_at: datetime,
    basis_at: datetime,
    received_at: datetime,
    temperature_c: float,
    current: bool = False,
) -> None:
    session.add(
        WeatherForecastSnapshot(
            forecast_snapshot_id=snapshot_id,
            contract_id=WEATHER_FORECAST_CONTRACT_ID,
            data_kind=(
                CURRENT_WEATHER_FORECAST_DATA_KIND
                if current
                else WEATHER_FORECAST_DATA_KIND
            ),
            game_id=game_id,
            season=season,
            week=week,
            registry_record_id=registry_record_id,
            provider=(
                CURRENT_WEATHER_FORECAST_PROVIDER
                if current
                else WEATHER_FORECAST_PROVIDER
            ),
            provider_model=WEATHER_FORECAST_MODEL,
            variables_json=list(
                CURRENT_OPEN_METEO_HOURLY_VARIABLES
                if current
                else OPEN_METEO_HOURLY_VARIABLES
            ),
            valid_at=valid_at,
            fixed_lead_hours=(
                None if current else WEATHER_FORECAST_FIXED_LEAD_HOURS
            ),
            forecast_basis_at=basis_at,
            forecast_basis_kind=(
                CURRENT_WEATHER_FORECAST_BASIS_KIND
                if current
                else WEATHER_FORECAST_BASIS_KIND
            ),
            provider_issued_at=None,
            provider_available_at=None,
            received_at=received_at,
            requested_latitude=40.0,
            requested_longitude=-75.0,
            returned_latitude=40.0,
            returned_longitude=-75.0,
            returned_elevation_m=10.0,
            returned_timezone="GMT",
            temperature_c=temperature_c,
            relative_humidity_pct=60.0,
            precipitation_mm=0.2,
            wind_speed_mps=4.0,
            wind_direction_degrees=180.0,
            wind_gusts_mps=7.0,
            status="available",
            units_json={
                "temperature_c": "°C",
                "wind_speed_mps": "m/s",
            },
            quality_flags_json=[],
            raw_artifact_path=f"/tmp/{snapshot_id}.json",
            manifest_path=f"/tmp/{snapshot_id}.manifest.json",
            source_uri_redacted="https://example.test/forecast",
            raw_sha256="f" * 64,
            byte_count=100,
        )
    )


def _seed_current_capture_result(
    session: Session,
    *,
    snapshot_id: str,
    game_id: str,
    season: int,
    week: int,
    slate: str,
    lock_at: datetime,
    attempted_at: datetime,
) -> None:
    run = IngestRun(
        ingest_run_id=f"capture-{snapshot_id}",
        source_system=CURRENT_WEATHER_FORECAST_PROVIDER,
        source_table="weather_forecast_snapshot",
        season=season,
        week=week,
        slate=slate,
        status="completed",
    )
    session.add(run)
    session.flush()
    session.add(
        WeatherForecastCaptureResult(
            capture_result_id=f"result-{snapshot_id}",
            ingest_run_id=run.ingest_run_id,
            game_id=game_id,
            season=season,
            week=week,
            capture_kind="current_refresh",
            slate=slate,
            slate_lock_at=lock_at,
            registry_record_id="mia-test:v1",
            forecast_snapshot_id=snapshot_id,
            valid_at=lock_at,
            status="captured",
            attempted_at=attempted_at,
        )
    )


def test_historical_api_returns_lock_safe_forecast_and_separate_actual() -> None:
    session = _session()
    salary_run = _seed_slice(
        session,
        season=2024,
        week=1,
        slate="sunday_main",
    )
    outdoor = _seed_game(
        session,
        salary_run=salary_run,
        game_id="2024_01_BUF_MIA",
        season=2024,
        week=1,
        slate="sunday_main",
        away_team="BUF",
        home_team="MIA",
        gameday="2024-09-08",
        gametime="13:00",
    )
    _seed_game(
        session,
        salary_run=salary_run,
        game_id="2024_01_DET_LAR",
        season=2024,
        week=1,
        slate="sunday_main",
        away_team="DET",
        home_team="LAR",
        gameday="2024-09-08",
        gametime="20:20",
        default_roof="fixed_indoor",
    )
    lock_at = datetime(2024, 9, 8, 17, 0, tzinfo=UTC)
    _seed_forecast(
        session,
        snapshot_id="historical-pre-lock",
        game_id="2024_01_BUF_MIA",
        registry_record_id="mia-test:v1",
        season=2024,
        week=1,
        valid_at=lock_at,
        basis_at=lock_at - timedelta(hours=24),
        received_at=datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
        temperature_c=24.0,
    )
    _seed_forecast(
        session,
        snapshot_id="current-post-lock",
        game_id="2024_01_BUF_MIA",
        registry_record_id="mia-test:v1",
        season=2024,
        week=1,
        valid_at=lock_at,
        basis_at=lock_at + timedelta(minutes=30),
        received_at=lock_at + timedelta(minutes=30),
        temperature_c=30.0,
        current=True,
    )
    session.add(
        CuratedGameWeather(
            game_id="2024_01_BUF_MIA",
            season=2024,
            week=1,
            game_type="REG",
            kickoff_at=lock_at,
            home_team="MIA",
            away_team="BUF",
            stadium="MIA Test Stadium",
            roof="outdoors",
            surface="grass",
            temperature_f=88.0,
            wind_mph=12.0,
            weather_status="observed",
            data_kind="retrospective_game_actual",
            observation_basis="result_time_schedule_field",
            observed_at=None,
            effective_at=lock_at,
            replay_eligible=False,
            quality_flags_json=[],
            source_system="nflverse",
            source_ingest_run_id=outdoor.ingest_run_id,
            raw_nfl_schedule_id=outdoor.raw_nfl_schedule_id,
        )
    )
    backfill_run = IngestRun(
        ingest_run_id="unrelated-historical-backfill",
        source_system="open_meteo_previous_runs",
        source_table="weather_forecast_snapshot",
        season=2024,
        week=1,
        status="completed_with_warnings",
    )
    session.add(backfill_run)
    session.flush()
    session.add(
        WeatherForecastCaptureResult(
            capture_result_id="unrelated-historical-result",
            ingest_run_id=backfill_run.ingest_run_id,
            game_id="2024_01_NYJ_SF",
            season=2024,
            week=1,
            capture_kind="historical_backfill",
            slate=None,
            registry_record_id=None,
            forecast_snapshot_id=None,
            valid_at=None,
            status="error",
            reason="unrelated_week_game",
            attempted_at=datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
        )
    )
    session.commit()

    app = FastAPI()
    app.include_router(router)

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    response = TestClient(app).get(
        "/api/weather/slate",
        params={
            "source_system": "draftkings",
            "season": 2024,
            "week": 1,
            "slate": "SUNDAY_MAIN",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_id"] == "slate_game_weather_v1"
    assert payload["request_kind"] == "historical"
    assert payload["games_expected"] == 2
    assert payload["games_resolved"] == 2
    assert payload["cutoff_at"] == "2024-09-08T17:00:00Z"
    games = {row["game_id"]: row for row in payload["games"]}
    outdoor_payload = games["2024_01_BUF_MIA"]
    assert outdoor_payload["forecast"]["forecast_snapshot_id"] == (
        "historical-pre-lock"
    )
    assert outdoor_payload["forecast"]["temperature_c"] == 24.0
    assert outdoor_payload["actual"]["temperature_f"] == 88.0
    assert outdoor_payload["actual"]["replay_eligible"] is False
    assert outdoor_payload["forecast"]["data_kind"] != outdoor_payload["actual"]["data_kind"]
    assert games["2024_01_DET_LAR"]["weather_state"] == "indoor"


def test_current_view_clamps_cutoff_and_excludes_post_lock_receipt() -> None:
    session = _session()
    salary_run = _seed_slice(
        session,
        season=2026,
        week=1,
        slate="sunday_main",
    )
    _seed_game(
        session,
        salary_run=salary_run,
        game_id="2026_01_BUF_MIA",
        season=2026,
        week=1,
        slate="sunday_main",
        away_team="BUF",
        home_team="MIA",
        gameday="2026-09-13",
        gametime="13:00",
    )
    lock_at = datetime(2026, 9, 13, 17, 0, tzinfo=UTC)
    captured_at = datetime(2026, 9, 13, 13, 0, tzinfo=UTC)
    _seed_forecast(
        session,
        snapshot_id="current-eligible",
        game_id="2026_01_BUF_MIA",
        registry_record_id="mia-test:v1",
        season=2026,
        week=1,
        valid_at=lock_at,
        basis_at=captured_at,
        received_at=captured_at,
        temperature_c=25.0,
        current=True,
    )
    _seed_current_capture_result(
        session,
        snapshot_id="current-eligible",
        game_id="2026_01_BUF_MIA",
        season=2026,
        week=1,
        slate="sunday_main",
        lock_at=lock_at,
        attempted_at=captured_at,
    )
    other_slate_received_at = datetime(2026, 9, 13, 15, 0, tzinfo=UTC)
    _seed_forecast(
        session,
        snapshot_id="current-other-slate",
        game_id="2026_01_BUF_MIA",
        registry_record_id="mia-test:v1",
        season=2026,
        week=1,
        valid_at=lock_at,
        basis_at=other_slate_received_at,
        received_at=other_slate_received_at,
        temperature_c=29.0,
        current=True,
    )
    _seed_current_capture_result(
        session,
        snapshot_id="current-other-slate",
        game_id="2026_01_BUF_MIA",
        season=2026,
        week=1,
        slate="showdown",
        lock_at=lock_at,
        attempted_at=other_slate_received_at,
    )
    _seed_forecast(
        session,
        snapshot_id="current-post-lock",
        game_id="2026_01_BUF_MIA",
        registry_record_id="mia-test:v1",
        season=2026,
        week=1,
        valid_at=lock_at,
        basis_at=lock_at + timedelta(hours=1),
        received_at=lock_at + timedelta(hours=1),
        temperature_c=31.0,
        current=True,
    )
    _seed_current_capture_result(
        session,
        snapshot_id="current-post-lock",
        game_id="2026_01_BUF_MIA",
        season=2026,
        week=1,
        slate="sunday_main",
        lock_at=lock_at,
        attempted_at=lock_at + timedelta(hours=1),
    )
    session.commit()

    report = SlateWeatherService(
        session,
        stale_after=timedelta(hours=2),
        clock=lambda: datetime(2026, 9, 13, 16, 0, tzinfo=UTC),
    ).report(
        source_system="draftkings",
        season=2026,
        week=1,
        slate="SUNDAY_MAIN",
        cutoff_at=datetime(2026, 9, 13, 19, 0, tzinfo=UTC),
    )

    assert report["cutoff_at"] == "2026-09-13T16:00:00Z"
    assert report["request_kind"] == "current"
    assert report["quality_flags"] == ["cutoff_clamped_to_current_time"]
    game = report["games"][0]
    assert game["forecast"]["forecast_snapshot_id"] == "current-eligible"
    assert game["forecast"]["temperature_c"] == 25.0
    assert game["weather_state"] == "stale"
    assert game["actual"] is None


def test_unresolved_salary_matchup_is_returned_instead_of_silently_omitted() -> None:
    session = _session()
    salary_run = _seed_slice(
        session,
        season=2026,
        week=2,
        slate="showdown",
    )
    session.add(
        CuratedSalary(
            ingest_run_id=salary_run.ingest_run_id,
            source_system="draftkings",
            season=2026,
            week=2,
            slate="showdown",
            source_player_key="missing-game-player",
            player_name="Canonical Player",
            normalized_name="canonical player",
            team="JAC",
            opponent="KC",
            position="QB",
            roster_position="CPT",
            salary=10000,
            game_info="JAC@KC",
        )
    )
    session.commit()

    report = SlateWeatherService(
        session,
        clock=lambda: datetime(2026, 9, 20, 12, 0, tzinfo=UTC),
    ).report(
        source_system="draftkings",
        season=2026,
        week=2,
        slate="showdown",
    )

    assert report["games_expected"] == 1
    assert report["games_resolved"] == 0
    assert report["identity_counts"] == {"unresolved": 1}
    assert "slate_game_identity_incomplete" in report["quality_flags"]
    assert report["games"][0]["game_id"] is None
    assert report["games"][0]["identity_status"] == "unresolved"
    assert "salary_team_pair:JAX-KC" in report["games"][0]["quality_flags"]


def test_api_rejects_naive_cutoff() -> None:
    session = _session()
    app = FastAPI()
    app.include_router(router)

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    response = TestClient(app).get(
        "/api/weather/slate",
        params={
            "season": 2026,
            "week": 1,
            "slate": "sunday_main",
            "cutoff_at": "2026-09-13T16:00:00",
        },
    )

    assert response.status_code == 422
    assert "timezone offset" in response.json()["detail"]
