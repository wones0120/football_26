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
    CuratedGameWeather,
    IngestRun,
    RawNflSchedule,
    VenueRegistryRecord,
    WeatherForecastCaptureResult,
    WeatherForecastSnapshot,
)
from backend.app.services.weather_forecast_backfill import (
    OPEN_METEO_HOURLY_VARIABLES,
    HistoricalForecastAssessment,
    HistoricalForecastBackfillService,
    HistoricalForecastCandidate,
    OpenMeteoPreviousRunsClient,
    WeatherForecastIntegrityError,
    assess_historical_forecast_backfill,
    audit_historical_forecast_coverage,
    historical_forecast_visible_at_cutoff,
    normalize_open_meteo_response,
    verify_weather_forecast_artifact,
)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _seed_source(
    session: Session,
    *,
    game_id: str = "2024_01_BAL_KC",
    with_mapping: bool = True,
) -> RawNflSchedule:
    ingest_run = IngestRun(
        ingest_run_id=f"run-{game_id}",
        source_system="nflverse",
        source_table="schedules",
        season=2024,
        status="completed",
    )
    session.add(ingest_run)
    session.flush()
    schedule = RawNflSchedule(
        ingest_run_id=ingest_run.ingest_run_id,
        source_system="nflverse",
        season=2024,
        week=1,
        game_id=game_id,
        home_team="KC",
        away_team="BAL",
        game_type="REG",
        kickoff="20:20",
        stadium="GEHA Field at Arrowhead Stadium",
        raw_row_json={"gameday": "2024-09-05", "gametime": "20:20"},
    )
    session.add(schedule)
    session.flush()
    if with_mapping:
        record = session.get(VenueRegistryRecord, "arrowhead:v1")
        if record is None:
            record = VenueRegistryRecord(
                registry_record_id="arrowhead:v1",
                venue_id="arrowhead",
                registry_version=1,
                canonical_name="GEHA Field at Arrowhead Stadium",
                effective_from_season=1972,
                effective_to_season=None,
                latitude=39.0489,
                longitude=-94.4839,
                timezone="America/Chicago",
                default_roof="outdoor",
                country_code="US",
                source_system="nflverse",
                source_venue_id="KAN00",
                source_evidence_uri="https://example.test/stadium",
                coordinate_source_uri="https://example.test/coordinates",
                review_notes="test",
                review_classifications_json=[],
                definition_sha256="a" * 64,
            )
            session.add(record)
            session.flush()
        session.add(
            CuratedGameVenue(
                game_id=game_id,
                season=2024,
                week=1,
                mapping_status="resolved",
                mapping_method="source_venue_id",
                source_venue_id="KAN00",
                registry_record_id=record.registry_record_id,
                evidence_json={},
                candidate_registry_record_ids_json=[],
                source_ingest_run_id=ingest_run.ingest_run_id,
                raw_nfl_schedule_id=schedule.raw_nfl_schedule_id,
            )
        )
    session.commit()
    return schedule


def _candidate() -> HistoricalForecastCandidate:
    valid_at = datetime(2024, 9, 6, 0, 0, tzinfo=UTC)
    return HistoricalForecastCandidate(
        game_id="2024_01_BAL_KC",
        season=2024,
        week=1,
        registry_record_id="arrowhead:v1",
        requested_latitude=39.0489,
        requested_longitude=-94.4839,
        kickoff_at=valid_at + timedelta(minutes=20),
        valid_at=valid_at,
        quarantine_reason=None,
    )


def _assessment(candidate: HistoricalForecastCandidate) -> HistoricalForecastAssessment:
    return HistoricalForecastAssessment(
        generated_at="2026-08-01T12:00:00Z",
        season_start=2024,
        season_end=2024,
        source_rows=1,
        latest_games=1,
        skipped_without_game_id=0,
        candidates=(candidate,),
    )


def _response(*, temperature: float | None = 28.0) -> bytes:
    values = {
        "temperature_2m_previous_day1": temperature,
        "relative_humidity_2m_previous_day1": 67.0,
        "precipitation_previous_day1": 0.2,
        "wind_speed_10m_previous_day1": 4.5,
        "wind_direction_10m_previous_day1": 190.0,
        "wind_gusts_10m_previous_day1": 8.2,
    }
    units = {
        "temperature_2m_previous_day1": "°C",
        "relative_humidity_2m_previous_day1": "%",
        "precipitation_previous_day1": "mm",
        "wind_speed_10m_previous_day1": "m/s",
        "wind_direction_10m_previous_day1": "°",
        "wind_gusts_10m_previous_day1": "m/s",
    }
    return json.dumps(
        {
            "latitude": 39.056,
            "longitude": -94.48,
            "elevation": 264.0,
            "timezone": "GMT",
            "hourly_units": {"time": "iso8601", **units},
            "hourly": {
                "time": ["2024-09-06T00:00"],
                **{name: [value] for name, value in values.items()},
            },
        },
        separators=(",", ":"),
    ).encode()


def test_assessment_requires_resolved_venue_and_kickoff() -> None:
    session = _session()
    _seed_source(session)
    _seed_source(session, game_id="2024_01_GB_PHI", with_mapping=False)

    assessment = assess_historical_forecast_backfill(
        session,
        season_start=2024,
        season_end=2024,
    )

    assert assessment.report()["expected_games"] == 2
    assert assessment.report()["eligible_games"] == 1
    rows = {candidate.game_id: candidate for candidate in assessment.candidates}
    assert rows["2024_01_BAL_KC"].valid_at == datetime(
        2024, 9, 6, 0, 0, tzinfo=UTC
    )
    assert rows["2024_01_GB_PHI"].quarantine_reason == (
        "missing_game_venue_mapping"
    )


def test_request_pins_contract_and_redacts_api_key() -> None:
    client = OpenMeteoPreviousRunsClient(
        base_url="https://customer-api.open-meteo.com/v1/forecast?apikey=old-secret",
        api_key="new-secret",
    )

    request = client.build_request(_candidate())
    live_query = parse_qs(urlsplit(request.request_uri).query)
    stored_query = parse_qs(urlsplit(request.request_uri_redacted).query)

    assert live_query["apikey"] == ["new-secret"]
    assert "apikey" not in stored_query
    assert stored_query["models"] == ["ncep_gfs_seamless"]
    assert stored_query["hourly"] == [",".join(OPEN_METEO_HOURLY_VARIABLES)]
    assert stored_query["timezone"] == ["GMT"]
    assert stored_query["start_date"] == ["2024-09-06"]
    assert stored_query["end_date"] == ["2024-09-06"]
    assert "old-secret" not in request.request_uri
    assert "new-secret" not in request.request_uri_redacted


def test_normalization_selects_exact_valid_hour_without_interpolation() -> None:
    normalized = normalize_open_meteo_response(
        _response(),
        valid_at=datetime(2024, 9, 6, 0, 0, tzinfo=UTC),
    )
    missing_hour = normalize_open_meteo_response(
        _response(),
        valid_at=datetime(2024, 9, 6, 1, 0, tzinfo=UTC),
    )

    assert normalized.status == "available"
    assert normalized.values["temperature_c"] == 28.0
    assert normalized.values["wind_gusts_mps"] == 8.2
    assert normalized.units["precipitation_mm"] == "mm"
    assert missing_hour.status == "missing"
    assert "valid_hour_not_returned" in missing_hour.quality_flags


def test_capture_is_immutable_idempotent_and_time_safe(tmp_path: Path) -> None:
    session = _session()
    _seed_source(session)
    calls: list[str] = []

    def transport(uri: str, _timeout: float) -> bytes:
        calls.append(uri)
        return _response()

    captured_at = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    client = OpenMeteoPreviousRunsClient(
        base_url="https://customer-api.open-meteo.com/v1/forecast",
        api_key="super-secret",
        transport=transport,
    )
    service = HistoricalForecastBackfillService(
        session,
        client=client,
        snapshot_root=tmp_path,
        clock=lambda: captured_at,
    )

    first = service.run(_assessment(_candidate()))
    second = service.run(_assessment(_candidate()))

    snapshot = session.scalar(select(WeatherForecastSnapshot))
    assert snapshot is not None
    assert first["result_status_counts"] == {"captured": 1}
    assert second["result_status_counts"] == {"reused": 1}
    assert len(calls) == 1
    assert session.scalar(
        select(func.count()).select_from(WeatherForecastSnapshot)
    ) == 1
    assert session.scalar(
        select(func.count()).select_from(WeatherForecastCaptureResult)
    ) == 2
    result_uris = list(
        session.scalars(
            select(WeatherForecastCaptureResult.request_uri_redacted).order_by(
                WeatherForecastCaptureResult.attempted_at
            )
        )
    )
    assert len(set(result_uris)) == 1
    assert snapshot.forecast_basis_at == datetime(2024, 9, 5, 0, 0)
    assert snapshot.provider_issued_at is None
    assert snapshot.provider_available_at is None
    assert snapshot.received_at == captured_at.replace(tzinfo=None)
    assert "super-secret" not in snapshot.source_uri_redacted
    assert "super-secret" not in Path(snapshot.manifest_path).read_text()
    assert historical_forecast_visible_at_cutoff(
        snapshot,
        datetime(2024, 9, 5, 0, 0, tzinfo=UTC),
    )
    assert not historical_forecast_visible_at_cutoff(
        snapshot,
        datetime(2024, 9, 4, 23, 59, 59, tzinfo=UTC),
    )
    snapshot.forecast_basis_at = datetime(2024, 9, 4, 23, 0)
    assert not historical_forecast_visible_at_cutoff(
        snapshot,
        datetime(2024, 9, 5, 0, 0, tzinfo=UTC),
    )
    snapshot.forecast_basis_at = datetime(2024, 9, 5, 0, 0)
    verify_weather_forecast_artifact(snapshot)
    coverage = audit_historical_forecast_coverage(
        session,
        _assessment(_candidate()),
        verify_artifacts=True,
    )
    assert coverage["complete"] is True
    assert coverage["coverage_status_counts"] == {"available": 1}

    raw_path = Path(snapshot.raw_artifact_path)
    raw_path.chmod(0o644)
    raw_path.write_bytes(b"tampered")
    try:
        verify_weather_forecast_artifact(snapshot)
    except WeatherForecastIntegrityError:
        pass
    else:
        raise AssertionError("tampered forecast evidence was accepted")


def test_retrospective_actual_never_repairs_missing_forecast_value(
    tmp_path: Path,
) -> None:
    session = _session()
    schedule = _seed_source(session)
    session.add(
        CuratedGameWeather(
            game_id=schedule.game_id,
            season=2024,
            week=1,
            game_type="REG",
            kickoff_at=datetime(2024, 9, 6, 0, 20, tzinfo=UTC),
            home_team="KC",
            away_team="BAL",
            stadium=schedule.stadium,
            roof="outdoors",
            surface="grass",
            temperature_f=99.0,
            wind_mph=30.0,
            weather_status="observed",
            data_kind="retrospective_game_observation",
            observation_basis="nflverse_schedule_result_context",
            observed_at=None,
            effective_at=datetime(2024, 9, 6, 0, 20, tzinfo=UTC),
            replay_eligible=False,
            quality_flags_json=[],
            source_system="nflverse",
            source_ingest_run_id=schedule.ingest_run_id,
            raw_nfl_schedule_id=schedule.raw_nfl_schedule_id,
        )
    )
    session.commit()
    client = OpenMeteoPreviousRunsClient(
        base_url="https://previous-runs-api.open-meteo.com/v1/forecast",
        api_key=None,
        transport=lambda _uri, _timeout: _response(temperature=None),
    )
    service = HistoricalForecastBackfillService(
        session,
        client=client,
        snapshot_root=tmp_path,
        clock=lambda: datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
    )

    result = service.run(_assessment(_candidate()))

    snapshot = session.scalar(select(WeatherForecastSnapshot))
    assert snapshot is not None
    assert result["result_status_counts"] == {"partial": 1}
    assert result["rows_unresolved"] == 1
    assert snapshot.temperature_c is None
    assert snapshot.status == "partial"
    assert snapshot.temperature_c != 99.0


def test_provider_failure_has_explicit_coverage_reason(tmp_path: Path) -> None:
    session = _session()
    _seed_source(session)

    def fail(_uri: str, _timeout: float) -> bytes:
        raise TimeoutError("secret transport detail")

    service = HistoricalForecastBackfillService(
        session,
        client=OpenMeteoPreviousRunsClient(
            base_url="https://previous-runs-api.open-meteo.com/v1/forecast",
            api_key=None,
            transport=fail,
        ),
        snapshot_root=tmp_path,
        clock=lambda: datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
    )

    result = service.run(_assessment(_candidate()))

    capture_result = session.scalar(select(WeatherForecastCaptureResult))
    assert capture_result is not None
    assert result["status"] == "completed_with_warnings"
    assert result["rows_unresolved"] == 1
    assert capture_result.status == "error"
    assert capture_result.reason == "provider_transport_error type=TimeoutError"
    assert capture_result.forecast_snapshot_id is None


def test_database_contract_rejects_fabricated_provider_timing(
    tmp_path: Path,
) -> None:
    session = _session()
    _seed_source(session)
    service = HistoricalForecastBackfillService(
        session,
        client=OpenMeteoPreviousRunsClient(
            base_url="https://previous-runs-api.open-meteo.com/v1/forecast",
            api_key=None,
            transport=lambda _uri, _timeout: _response(),
        ),
        snapshot_root=tmp_path,
        clock=lambda: datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
    )
    service.run(_assessment(_candidate()))
    snapshot = session.scalar(select(WeatherForecastSnapshot))
    assert snapshot is not None
    snapshot.provider_issued_at = datetime(2024, 9, 5, 0, 0, tzinfo=UTC)

    with pytest.raises(IntegrityError):
        session.commit()
