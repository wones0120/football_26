from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import (
    Base,
    CuratedGameVenue,
    IngestRun,
    RawNflSchedule,
    VenueRegistryRecord,
    WeatherForecastCaptureResult,
    WeatherForecastSnapshot,
)
from backend.app.services.current_weather_forecast import (
    CURRENT_OPEN_METEO_HOURLY_VARIABLES,
    CURRENT_WEATHER_FORECAST_DATA_KIND,
    CurrentForecastCaptureService,
    OpenMeteoForecastClient,
    assess_current_forecast_capture,
    audit_current_forecast_capture,
    current_forecast_visible_at_cutoff,
    select_current_forecast_at_cutoff,
)


GAME_ONE = "2026_01_BUF_MIA"
GAME_TWO = "2026_01_NE_NYJ"
LOCK_AT = datetime(2026, 9, 13, 17, 0, tzinfo=UTC)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _seed_game(session: Session, game_id: str, *, hour: str = "13:00") -> None:
    run = IngestRun(
        ingest_run_id=f"schedule-{game_id}",
        source_system="nflverse",
        source_table="schedules",
        season=2026,
        week=1,
        status="completed",
    )
    session.add(run)
    session.flush()
    schedule = RawNflSchedule(
        ingest_run_id=run.ingest_run_id,
        source_system="nflverse",
        season=2026,
        week=1,
        game_id=game_id,
        home_team=game_id.rsplit("_", 1)[-1],
        away_team=game_id.rsplit("_", 2)[-2],
        game_type="REG",
        kickoff=hour,
        stadium="Test Stadium",
        raw_row_json={"gameday": "2026-09-13", "gametime": hour},
    )
    session.add(schedule)
    session.flush()
    record = session.get(VenueRegistryRecord, "test-stadium:v1")
    if record is None:
        record = VenueRegistryRecord(
            registry_record_id="test-stadium:v1",
            venue_id="test-stadium",
            registry_version=1,
            canonical_name="Test Stadium",
            effective_from_season=2026,
            effective_to_season=None,
            latitude=25.958,
            longitude=-80.239,
            timezone="America/New_York",
            default_roof="outdoor",
            country_code="US",
            source_system="nflverse",
            source_venue_id="TEST00",
            source_evidence_uri="https://example.test/stadium",
            coordinate_source_uri="https://example.test/coordinates",
            review_notes="test fixture",
            review_classifications_json=[],
            definition_sha256="b" * 64,
        )
        session.add(record)
        session.flush()
    session.add(
        CuratedGameVenue(
            game_id=game_id,
            season=2026,
            week=1,
            mapping_status="resolved",
            mapping_method="source_venue_id",
            source_venue_id="TEST00",
            registry_record_id=record.registry_record_id,
            evidence_json={},
            candidate_registry_record_ids_json=[],
            source_ingest_run_id=run.ingest_run_id,
            raw_nfl_schedule_id=schedule.raw_nfl_schedule_id,
        )
    )
    session.commit()


def _assessment(session: Session, *game_ids: str):
    return assess_current_forecast_capture(
        session,
        season=2026,
        week=1,
        slate="sunday_main",
        slate_lock_at=LOCK_AT,
        game_ids=set(game_ids),
    )


def _response(
    valid_at: datetime,
    *,
    temperature: float = 24.0,
    additional_valid_times: tuple[datetime, ...] = (),
) -> bytes:
    values = {
        "temperature_2m": temperature,
        "relative_humidity_2m": 71.0,
        "precipitation": 0.4,
        "wind_speed_10m": 5.5,
        "wind_direction_10m": 135.0,
        "wind_gusts_10m": 9.2,
    }
    units = {
        "temperature_2m": "°C",
        "relative_humidity_2m": "%",
        "precipitation": "mm",
        "wind_speed_10m": "m/s",
        "wind_direction_10m": "°",
        "wind_gusts_10m": "m/s",
    }
    valid_times = (valid_at, *additional_valid_times)
    return json.dumps(
        {
            "latitude": 25.96,
            "longitude": -80.24,
            "elevation": 3.0,
            "timezone": "GMT",
            "hourly_units": {"time": "iso8601", **units},
            "hourly": {
                "time": [
                    value.isoformat().replace("+00:00", "")
                    for value in valid_times
                ],
                **{
                    name: [value] * len(valid_times)
                    for name, value in values.items()
                },
            },
        },
        separators=(",", ":"),
    ).encode()


def test_current_request_pins_model_variables_and_redacts_key() -> None:
    session = _session()
    _seed_game(session, GAME_ONE)
    candidate = _assessment(session, GAME_ONE).candidates[0]
    client = OpenMeteoForecastClient(
        base_url="https://customer-api.open-meteo.com/v1/forecast?apikey=old",
        api_key="new-secret",
    )

    request = client.build_request(candidate)
    live_query = parse_qs(urlsplit(request.request_uri).query)
    stored_query = parse_qs(urlsplit(request.request_uri_redacted).query)

    assert live_query["apikey"] == ["new-secret"]
    assert "apikey" not in stored_query
    assert stored_query["models"] == ["ncep_gfs_seamless"]
    assert stored_query["hourly"] == [
        ",".join(CURRENT_OPEN_METEO_HOURLY_VARIABLES)
    ]
    assert stored_query["start_date"] == ["2026-09-13"]
    assert "new-secret" not in request.request_uri_redacted


def test_current_assessment_requires_explicit_canonical_game_ids() -> None:
    session = _session()
    _seed_game(session, GAME_ONE)

    with pytest.raises(ValueError, match="at least one canonical game ID"):
        assess_current_forecast_capture(
            session,
            season=2026,
            week=1,
            slate="sunday_main",
            slate_lock_at=LOCK_AT,
            game_ids=set(),
        )


def test_refreshes_append_versions_and_reconstruct_pre_lock_knowledge(
    tmp_path: Path,
) -> None:
    session = _session()
    _seed_game(session, GAME_ONE)
    assessment = _assessment(session, GAME_ONE)
    valid_at = assessment.candidates[0].valid_at
    assert valid_at is not None
    first_received = datetime(2026, 9, 13, 14, 0, tzinfo=UTC)
    second_received = datetime(2026, 9, 13, 16, 0, tzinfo=UTC)
    post_lock_received = datetime(2026, 9, 13, 18, 0, tzinfo=UTC)

    for received_at, temperature in (
        (first_received, 21.0),
        (second_received, 23.0),
        (post_lock_received, 27.0),
    ):
        result = CurrentForecastCaptureService(
            session,
            client=OpenMeteoForecastClient(
                base_url="https://api.open-meteo.com/v1/forecast",
                api_key=None,
                transport=lambda _uri, _timeout, value=temperature: _response(
                    valid_at,
                    temperature=value,
                ),
            ),
            snapshot_root=tmp_path,
            request_interval_seconds=0,
            clock=lambda value=received_at: value,
        ).run(assessment)
        assert result["result_status_counts"] == {"captured": 1}

    repeated = CurrentForecastCaptureService(
        session,
        client=OpenMeteoForecastClient(
            base_url="https://api.open-meteo.com/v1/forecast",
            api_key=None,
            transport=lambda _uri, _timeout: _response(
                valid_at,
                temperature=23.0,
            ),
        ),
        snapshot_root=tmp_path,
        request_interval_seconds=0,
        clock=lambda: second_received,
    ).run(assessment)
    assert repeated["result_status_counts"] == {"reused": 1}

    snapshots = list(
        session.scalars(
            select(WeatherForecastSnapshot).order_by(
                WeatherForecastSnapshot.received_at
            )
        )
    )
    assert len(snapshots) == 3
    assert session.scalar(
        select(func.count()).select_from(WeatherForecastCaptureResult)
    ) == 4
    assert all(
        snapshot.data_kind == CURRENT_WEATHER_FORECAST_DATA_KIND
        for snapshot in snapshots
    )
    assert all(snapshot.fixed_lead_hours is None for snapshot in snapshots)
    assert all(
        snapshot.forecast_basis_at == snapshot.received_at
        for snapshot in snapshots
    )
    assert len({snapshot.raw_artifact_path for snapshot in snapshots}) == 3
    assert all(Path(snapshot.manifest_path).is_file() for snapshot in snapshots)

    at_1500 = select_current_forecast_at_cutoff(
        session,
        game_id=GAME_ONE,
        cutoff_at=datetime(2026, 9, 13, 15, 0, tzinfo=UTC),
    )
    at_lock = select_current_forecast_at_cutoff(
        session,
        game_id=GAME_ONE,
        cutoff_at=LOCK_AT,
    )
    assert at_1500 is not None and at_1500.temperature_c == 21.0
    assert at_lock is not None and at_lock.temperature_c == 23.0
    assert not current_forecast_visible_at_cutoff(snapshots[-1], LOCK_AT)
    assert current_forecast_visible_at_cutoff(
        snapshots[-1],
        post_lock_received,
    )

    audit = audit_current_forecast_capture(
        session,
        assessment,
        cutoff_at=LOCK_AT,
        stale_after=timedelta(hours=2),
        verify_artifacts=True,
    )
    assert audit["complete"] is True
    assert audit["state_counts"] == {"available": 1}
    assert audit["games"][0]["received_at"] == "2026-09-13T16:00:00Z"


def test_refresh_throttles_calls_and_reports_latest_failure(tmp_path: Path) -> None:
    session = _session()
    _seed_game(session, GAME_ONE)
    _seed_game(session, GAME_TWO, hour="16:00")
    assessment = _assessment(session, GAME_ONE, GAME_TWO)
    valid_by_game = {
        candidate.game_id: candidate.valid_at for candidate in assessment.candidates
    }
    sleeps: list[float] = []

    def transport(_uri: str, _timeout: float) -> bytes:
        valid_times = tuple(
            valid_at
            for valid_at in valid_by_game.values()
            if valid_at is not None
        )
        return _response(
            valid_times[0],
            additional_valid_times=valid_times[1:],
        )

    result = CurrentForecastCaptureService(
        session,
        client=OpenMeteoForecastClient(
            base_url="https://api.open-meteo.com/v1/forecast",
            api_key=None,
            transport=transport,
        ),
        snapshot_root=tmp_path,
        request_interval_seconds=0.25,
        sleeper=sleeps.append,
        clock=lambda: datetime(2026, 9, 13, 14, 0, tzinfo=UTC),
    ).run(assessment)

    assert result["provider_request_count"] == 2
    assert result["result_status_counts"] == {"captured": 2}
    assert sleeps == [0.25]

    failure_at = datetime(2026, 9, 13, 15, 0, tzinfo=UTC)

    def fail(_uri: str, _timeout: float) -> bytes:
        raise TimeoutError("transport detail")

    failure_assessment = _assessment(session, GAME_ONE)
    failed = CurrentForecastCaptureService(
        session,
        client=OpenMeteoForecastClient(
            base_url="https://api.open-meteo.com/v1/forecast",
            api_key=None,
            transport=fail,
        ),
        snapshot_root=tmp_path,
        request_interval_seconds=0,
        clock=lambda: failure_at,
    ).run(failure_assessment)

    assert failed["status"] == "completed_with_warnings"
    assert failed["rows_unresolved"] == 1
    audit = audit_current_forecast_capture(
        session,
        failure_assessment,
        cutoff_at=failure_at,
        stale_after=timedelta(hours=2),
    )
    assert audit["state_counts"] == {"error": 1}
    assert audit["games"][0]["latest_failure_reason"] == (
        "provider_transport_error type=TimeoutError"
    )
    assert audit["games"][0]["forecast_snapshot_id"] is not None
    assert session.scalar(
        select(func.count()).select_from(WeatherForecastCaptureResult)
    ) == 3


def test_current_forecast_becomes_stale_without_mutating_snapshot(
    tmp_path: Path,
) -> None:
    session = _session()
    _seed_game(session, GAME_ONE)
    assessment = _assessment(session, GAME_ONE)
    valid_at = assessment.candidates[0].valid_at
    assert valid_at is not None
    captured_at = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
    CurrentForecastCaptureService(
        session,
        client=OpenMeteoForecastClient(
            base_url="https://api.open-meteo.com/v1/forecast",
            api_key=None,
            transport=lambda _uri, _timeout: _response(valid_at),
        ),
        snapshot_root=tmp_path,
        request_interval_seconds=0,
        clock=lambda: captured_at,
    ).run(assessment)

    audit = audit_current_forecast_capture(
        session,
        assessment,
        cutoff_at=captured_at + timedelta(hours=3),
        stale_after=timedelta(hours=2),
    )

    assert audit["complete"] is False
    assert audit["state_counts"] == {"stale": 1}
    assert audit["games"][0]["age_seconds"] == 10800.0
    assert session.scalar(
        select(func.count()).select_from(WeatherForecastSnapshot)
    ) == 1


def test_database_contract_rejects_fixed_lead_on_current_capture(
    tmp_path: Path,
) -> None:
    session = _session()
    _seed_game(session, GAME_ONE)
    assessment = _assessment(session, GAME_ONE)
    valid_at = assessment.candidates[0].valid_at
    assert valid_at is not None
    CurrentForecastCaptureService(
        session,
        client=OpenMeteoForecastClient(
            base_url="https://api.open-meteo.com/v1/forecast",
            api_key=None,
            transport=lambda _uri, _timeout: _response(valid_at),
        ),
        snapshot_root=tmp_path,
        request_interval_seconds=0,
        clock=lambda: datetime(2026, 9, 13, 12, 0, tzinfo=UTC),
    ).run(assessment)
    snapshot = session.scalar(select(WeatherForecastSnapshot))
    assert snapshot is not None
    snapshot.fixed_lead_hours = 24

    with pytest.raises(IntegrityError):
        session.commit()
