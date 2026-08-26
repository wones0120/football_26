"""Immutable Open-Meteo Previous Runs capture for historical game forecasts."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    CuratedGameVenue,
    IngestRun,
    RawNflSchedule,
    VenueRegistryRecord,
    WeatherForecastCaptureResult,
    WeatherForecastSnapshot,
)
from .historical_weather import schedule_kickoff_at


WEATHER_FORECAST_CONTRACT_ID = "weather_forecast_source_contract_v1"
WEATHER_FORECAST_DATA_KIND = "historical_fixed_lead_forecast"
WEATHER_FORECAST_PROVIDER = "open_meteo_previous_runs"
WEATHER_FORECAST_MODEL = "ncep_gfs_seamless"
WEATHER_FORECAST_FIXED_LEAD_HOURS = 24
WEATHER_FORECAST_BASIS_KIND = "provider_fixed_lead"
WEATHER_FORECAST_UUID_NAMESPACE = uuid.UUID(
    "a8f87ac2-f394-47f6-a027-80225d5dad62"
)
OPEN_METEO_HOURLY_VARIABLES = (
    "temperature_2m_previous_day1",
    "relative_humidity_2m_previous_day1",
    "precipitation_previous_day1",
    "wind_speed_10m_previous_day1",
    "wind_direction_10m_previous_day1",
    "wind_gusts_10m_previous_day1",
)
NORMALIZED_VARIABLES = (
    "temperature_c",
    "relative_humidity_pct",
    "precipitation_mm",
    "wind_speed_mps",
    "wind_direction_degrees",
    "wind_gusts_mps",
)
VARIABLE_MAP = dict(zip(OPEN_METEO_HOURLY_VARIABLES, NORMALIZED_VARIABLES, strict=True))
SECRET_QUERY_KEYS = {"apikey", "api_key", "key", "token", "access_token"}
UNSAFE_PATH_COMPONENT_RE = re.compile(r"[^a-zA-Z0-9._-]+")
REPO_ROOT = Path(__file__).resolve().parents[3]


class WeatherForecastIntegrityError(RuntimeError):
    """Immutable forecast evidence differs from its stored digest or manifest."""


class WeatherForecastProviderError(RuntimeError):
    """A provider request or response failed without exposing request secrets."""


@dataclass(frozen=True)
class HistoricalForecastCandidate:
    game_id: str
    season: int
    week: int | None
    registry_record_id: str | None
    requested_latitude: float | None
    requested_longitude: float | None
    kickoff_at: datetime | None
    valid_at: datetime | None
    quarantine_reason: str | None


@dataclass(frozen=True)
class HistoricalForecastAssessment:
    generated_at: str
    season_start: int
    season_end: int
    source_rows: int
    latest_games: int
    skipped_without_game_id: int
    candidates: tuple[HistoricalForecastCandidate, ...]

    def report(self) -> dict[str, Any]:
        quarantine_counts = Counter(
            candidate.quarantine_reason
            for candidate in self.candidates
            if candidate.quarantine_reason
        )
        eligible = sum(
            candidate.quarantine_reason is None for candidate in self.candidates
        )
        return {
            "contract_id": WEATHER_FORECAST_CONTRACT_ID,
            "generated_at": self.generated_at,
            "season_start": self.season_start,
            "season_end": self.season_end,
            "source_rows": self.source_rows,
            "latest_games": self.latest_games,
            "skipped_without_game_id": self.skipped_without_game_id,
            "expected_games": len(self.candidates),
            "eligible_games": eligible,
            "quarantined_games": len(self.candidates) - eligible,
            "quarantine_reason_counts": dict(sorted(quarantine_counts.items())),
            "provider": WEATHER_FORECAST_PROVIDER,
            "provider_model": WEATHER_FORECAST_MODEL,
            "fixed_lead_hours": WEATHER_FORECAST_FIXED_LEAD_HOURS,
            "provider_timing": {
                "provider_issued_at": None,
                "provider_available_at": None,
                "forecast_basis_kind": WEATHER_FORECAST_BASIS_KIND,
            },
        }


@dataclass(frozen=True)
class OpenMeteoRequest:
    request_uri: str
    request_uri_redacted: str


@dataclass(frozen=True)
class NormalizedForecast:
    status: str
    values: dict[str, float | None]
    units: dict[str, str | None]
    returned_latitude: float | None
    returned_longitude: float | None
    returned_elevation_m: float | None
    returned_timezone: str | None
    quality_flags: tuple[str, ...]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset")
    return value.astimezone(UTC)


def _stored_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _aware_utc(value, field_name="timestamp").isoformat().replace("+00:00", "Z")


def _stored_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _iso(_stored_utc(value))


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            byte_count += len(chunk)
    return digest.hexdigest(), byte_count


def _resolve_root(root: str | Path | None) -> Path:
    configured = Path(root or get_settings().weather_forecast_snapshot_root).expanduser()
    if not configured.is_absolute():
        configured = REPO_ROOT / configured
    return configured.resolve()


def _write_immutable(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        path.chmod(0o444)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise WeatherForecastIntegrityError(
                f"Immutable forecast path already exists with different content: {path}"
            ) from None


def _safe_path_component(value: str, *, fallback: str) -> str:
    cleaned = UNSAFE_PATH_COMPONENT_RE.sub("_", value.strip()).strip("._-")
    return cleaned[:128] or fallback


def _snapshot_id(candidate: HistoricalForecastCandidate) -> str:
    if candidate.valid_at is None or candidate.registry_record_id is None:
        raise ValueError("eligible forecast candidates require valid time and venue record")
    identity = "|".join(
        (
            WEATHER_FORECAST_CONTRACT_ID,
            candidate.game_id,
            candidate.registry_record_id,
            WEATHER_FORECAST_MODEL,
            str(WEATHER_FORECAST_FIXED_LEAD_HOURS),
            _iso(candidate.valid_at) or "",
        )
    )
    return str(uuid.uuid5(WEATHER_FORECAST_UUID_NAMESPACE, identity))


def _capture_result_id(ingest_run_id: str, game_id: str) -> str:
    return str(
        uuid.uuid5(
            WEATHER_FORECAST_UUID_NAMESPACE,
            f"capture-result|{ingest_run_id}|{game_id}",
        )
    )


def _redacted_base_url(base_url: str) -> tuple[Any, list[tuple[str, str]]]:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("OPEN_METEO_BASE_URL must be an absolute HTTP(S) URL")
    safe_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in SECRET_QUERY_KEYS
    ]
    return parsed, safe_pairs


def historical_forecast_visible_at_cutoff(
    snapshot: WeatherForecastSnapshot,
    cutoff_at: datetime,
) -> bool:
    """Apply the reviewed fixed-lead basis without inventing provider timestamps."""
    cutoff = _aware_utc(cutoff_at, field_name="cutoff_at")
    if (
        snapshot.contract_id != WEATHER_FORECAST_CONTRACT_ID
        or snapshot.data_kind != WEATHER_FORECAST_DATA_KIND
        or snapshot.fixed_lead_hours != WEATHER_FORECAST_FIXED_LEAD_HOURS
        or snapshot.forecast_basis_kind != WEATHER_FORECAST_BASIS_KIND
        or snapshot.provider_issued_at is not None
        or snapshot.provider_available_at is not None
    ):
        return False
    valid_at = _stored_utc(snapshot.valid_at)
    forecast_basis_at = _stored_utc(snapshot.forecast_basis_at)
    expected_basis = valid_at - timedelta(
        hours=WEATHER_FORECAST_FIXED_LEAD_HOURS
    )
    return forecast_basis_at == expected_basis and forecast_basis_at <= cutoff


def assess_historical_forecast_backfill(
    session: Session,
    *,
    season_start: int,
    season_end: int,
) -> HistoricalForecastAssessment:
    if season_start > season_end:
        raise ValueError("season_start must be less than or equal to season_end")
    source_rows = list(
        session.scalars(
            select(RawNflSchedule)
            .where(
                RawNflSchedule.season >= season_start,
                RawNflSchedule.season <= season_end,
            )
            .order_by(
                RawNflSchedule.created_at,
                RawNflSchedule.raw_nfl_schedule_id,
            )
        )
    )
    latest_by_game: dict[str, RawNflSchedule] = {}
    skipped_without_game_id = 0
    for schedule in source_rows:
        if not schedule.game_id:
            skipped_without_game_id += 1
            continue
        latest_by_game[schedule.game_id] = schedule

    game_venues = {
        mapping.game_id: mapping
        for mapping in session.scalars(
            select(CuratedGameVenue).where(
                CuratedGameVenue.season >= season_start,
                CuratedGameVenue.season <= season_end,
            )
        )
    }
    registry_ids = {
        mapping.registry_record_id
        for mapping in game_venues.values()
        if mapping.registry_record_id
    }
    registry = {
        record.registry_record_id: record
        for record in session.scalars(
            select(VenueRegistryRecord).where(
                VenueRegistryRecord.registry_record_id.in_(registry_ids)
            )
        )
    }

    candidates: list[HistoricalForecastCandidate] = []
    for game_id, schedule in sorted(latest_by_game.items()):
        mapping = game_venues.get(game_id)
        record = (
            registry.get(mapping.registry_record_id)
            if mapping and mapping.registry_record_id
            else None
        )
        kickoff_at = schedule_kickoff_at(schedule)
        valid_at = (
            kickoff_at.replace(minute=0, second=0, microsecond=0)
            if kickoff_at
            else None
        )
        reason: str | None = None
        if schedule.week is None:
            reason = "missing_week"
        elif mapping is None:
            reason = "missing_game_venue_mapping"
        elif mapping.mapping_status != "resolved":
            reason = f"venue_mapping_{mapping.mapping_status}"
        elif record is None:
            reason = "missing_venue_registry_record"
        elif kickoff_at is None:
            reason = "missing_kickoff"
        candidates.append(
            HistoricalForecastCandidate(
                game_id=game_id,
                season=schedule.season,
                week=int(schedule.week) if schedule.week is not None else None,
                registry_record_id=record.registry_record_id if record else None,
                requested_latitude=record.latitude if record else None,
                requested_longitude=record.longitude if record else None,
                kickoff_at=kickoff_at,
                valid_at=valid_at,
                quarantine_reason=reason,
            )
        )
    return HistoricalForecastAssessment(
        generated_at=_iso(_utc_now()) or "",
        season_start=season_start,
        season_end=season_end,
        source_rows=len(source_rows),
        latest_games=len(latest_by_game),
        skipped_without_game_id=skipped_without_game_id,
        candidates=tuple(candidates),
    )


def audit_historical_forecast_coverage(
    session: Session,
    assessment: HistoricalForecastAssessment,
    *,
    verify_artifacts: bool = False,
) -> dict[str, Any]:
    snapshots = list(
        session.scalars(
            select(WeatherForecastSnapshot).where(
                WeatherForecastSnapshot.contract_id
                == WEATHER_FORECAST_CONTRACT_ID,
                WeatherForecastSnapshot.data_kind == WEATHER_FORECAST_DATA_KIND,
                WeatherForecastSnapshot.season >= assessment.season_start,
                WeatherForecastSnapshot.season <= assessment.season_end,
            )
        )
    )
    snapshots_by_key = {
        (
            snapshot.game_id,
            snapshot.registry_record_id,
            snapshot.provider_model,
            snapshot.fixed_lead_hours,
            _stored_utc(snapshot.valid_at),
        ): snapshot
        for snapshot in snapshots
    }
    status_counts: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()
    if assessment.skipped_without_game_id:
        issue_counts["source_rows_without_game_id"] += (
            assessment.skipped_without_game_id
        )
    artifact_errors: list[str] = []
    matched_snapshot_ids: set[str] = set()
    for candidate in assessment.candidates:
        if candidate.quarantine_reason:
            status_counts["quarantined"] += 1
            issue_counts[candidate.quarantine_reason] += 1
            continue
        if candidate.valid_at is None:
            status_counts["missing_snapshot"] += 1
            issue_counts["missing_valid_at"] += 1
            continue
        key = (
            candidate.game_id,
            candidate.registry_record_id,
            WEATHER_FORECAST_MODEL,
            WEATHER_FORECAST_FIXED_LEAD_HOURS,
            _stored_utc(candidate.valid_at),
        )
        snapshot = snapshots_by_key.get(key)
        if snapshot is None:
            status_counts["missing_snapshot"] += 1
            issue_counts["missing_snapshot"] += 1
            continue
        matched_snapshot_ids.add(snapshot.forecast_snapshot_id)
        status_counts[snapshot.status] += 1
        expected_basis = _stored_utc(candidate.valid_at) - timedelta(
            hours=WEATHER_FORECAST_FIXED_LEAD_HOURS
        )
        if _stored_utc(snapshot.forecast_basis_at) != expected_basis:
            issue_counts["forecast_basis_mismatch"] += 1
        if snapshot.provider_issued_at is not None:
            issue_counts["provider_issued_at_fabricated"] += 1
        if snapshot.provider_available_at is not None:
            issue_counts["provider_available_at_fabricated"] += 1
        if snapshot.provider != WEATHER_FORECAST_PROVIDER:
            issue_counts["provider_mismatch"] += 1
        if tuple(snapshot.variables_json) != OPEN_METEO_HOURLY_VARIABLES:
            issue_counts["variables_mismatch"] += 1
        if any(getattr(snapshot, name) is None for name in NORMALIZED_VARIABLES):
            issue_counts["forecast_value_missing"] += 1
        stored_query = parse_qsl(
            urlsplit(snapshot.source_uri_redacted).query,
            keep_blank_values=True,
        )
        if any(key.lower() in SECRET_QUERY_KEYS for key, _value in stored_query):
            issue_counts["source_uri_contains_secret_parameter"] += 1
        if verify_artifacts:
            try:
                verify_weather_forecast_artifact(snapshot)
            except WeatherForecastIntegrityError as exc:
                issue_counts["artifact_integrity_error"] += 1
                artifact_errors.append(f"{snapshot.game_id}: {exc}")

    extra_snapshots = len(snapshots) - len(matched_snapshot_ids)
    if extra_snapshots:
        issue_counts["snapshots_outside_current_registry_mapping"] += extra_snapshots
    expected_games = len(assessment.candidates)
    complete = (
        status_counts["available"] == expected_games
        and not issue_counts
        and not artifact_errors
    )
    return {
        "contract_id": WEATHER_FORECAST_CONTRACT_ID,
        "season_start": assessment.season_start,
        "season_end": assessment.season_end,
        "expected_games": expected_games,
        "stored_snapshots": len(snapshots),
        "matched_snapshots": len(matched_snapshot_ids),
        "coverage_status_counts": dict(sorted(status_counts.items())),
        "issue_counts": dict(sorted(issue_counts.items())),
        "artifact_verification": "verified" if verify_artifacts else "not_requested",
        "artifact_errors": artifact_errors,
        "complete": complete,
    }


class OpenMeteoPreviousRunsClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        timeout_seconds: float = 30.0,
        transport: Callable[[str, float], bytes] | None = None,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key.strip() if api_key and api_key.strip() else None
        self.timeout_seconds = timeout_seconds
        self.transport = transport or self._default_transport

    @staticmethod
    def _default_transport(uri: str, timeout_seconds: float) -> bytes:
        request = Request(uri, headers={"User-Agent": "football-26-weather/1"})
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                return response.read()
        except HTTPError as exc:
            raise WeatherForecastProviderError(
                f"provider_http_error status={exc.code}"
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise WeatherForecastProviderError(
                f"provider_transport_error type={type(exc).__name__}"
            ) from exc

    def build_request(self, candidate: HistoricalForecastCandidate) -> OpenMeteoRequest:
        if (
            candidate.valid_at is None
            or candidate.requested_latitude is None
            or candidate.requested_longitude is None
        ):
            raise ValueError("Open-Meteo requests require valid time and coordinates")
        parsed, base_pairs = _redacted_base_url(self.base_url)
        game_date = candidate.valid_at.date().isoformat()
        contract_pairs = [
            ("latitude", f"{candidate.requested_latitude:.6f}"),
            ("longitude", f"{candidate.requested_longitude:.6f}"),
            ("models", WEATHER_FORECAST_MODEL),
            ("hourly", ",".join(OPEN_METEO_HOURLY_VARIABLES)),
            ("timezone", "GMT"),
            ("timeformat", "iso8601"),
            ("temperature_unit", "celsius"),
            ("wind_speed_unit", "ms"),
            ("precipitation_unit", "mm"),
            ("cell_selection", "nearest"),
            ("start_date", game_date),
            ("end_date", game_date),
        ]
        redacted_query = urlencode(base_pairs + contract_pairs)
        live_pairs = base_pairs + contract_pairs
        if self.api_key:
            live_pairs.append(("apikey", self.api_key))
        request_query = urlencode(live_pairs)
        request_uri = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, request_query, parsed.fragment)
        )
        request_uri_redacted = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, redacted_query, parsed.fragment)
        )
        return OpenMeteoRequest(
            request_uri=request_uri,
            request_uri_redacted=request_uri_redacted,
        )

    def fetch(self, request: OpenMeteoRequest) -> bytes:
        try:
            return self.transport(request.request_uri, self.timeout_seconds)
        except WeatherForecastProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise WeatherForecastProviderError(
                f"provider_transport_error type={type(exc).__name__}"
            ) from exc


def _parse_provider_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def normalize_open_meteo_response(
    payload: bytes,
    *,
    valid_at: datetime,
    variable_map: Mapping[str, str] = VARIABLE_MAP,
) -> NormalizedForecast:
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WeatherForecastProviderError("provider_response_invalid_json") from exc
    if not isinstance(document, dict):
        raise WeatherForecastProviderError("provider_response_not_object")
    if document.get("error"):
        raise WeatherForecastProviderError("provider_response_error")

    target_valid = _aware_utc(valid_at, field_name="valid_at")
    hourly = document.get("hourly")
    hourly_units = document.get("hourly_units")
    hourly = hourly if isinstance(hourly, dict) else {}
    hourly_units = hourly_units if isinstance(hourly_units, dict) else {}
    times = hourly.get("time")
    times = times if isinstance(times, list) else []
    target_index = next(
        (
            index
            for index, raw_time in enumerate(times)
            if _parse_provider_time(raw_time) == target_valid
        ),
        None,
    )

    values: dict[str, float | None] = {}
    units: dict[str, str | None] = {}
    flags: list[str] = []
    if target_index is None:
        flags.append("valid_hour_not_returned")
    for provider_name, normalized_name in variable_map.items():
        series = hourly.get(provider_name)
        value = None
        if target_index is not None and isinstance(series, list) and target_index < len(series):
            value = _float_or_none(series[target_index])
        values[normalized_name] = value
        unit = hourly_units.get(provider_name)
        units[normalized_name] = str(unit) if unit is not None else None
        if value is None:
            flags.append(f"missing_{normalized_name}")
        if unit is None:
            flags.append(f"missing_unit_{normalized_name}")

    populated = sum(value is not None for value in values.values())
    if populated == len(values):
        status = "available"
    elif populated:
        status = "partial"
    else:
        status = "missing"

    returned_latitude = _float_or_none(document.get("latitude"))
    returned_longitude = _float_or_none(document.get("longitude"))
    returned_elevation = _float_or_none(document.get("elevation"))
    returned_timezone = document.get("timezone")
    if returned_latitude is None or returned_longitude is None:
        flags.append("missing_returned_coordinates")
    if not isinstance(returned_timezone, str) or not returned_timezone.strip():
        returned_timezone = None
        flags.append("missing_returned_timezone")

    return NormalizedForecast(
        status=status,
        values=values,
        units=units,
        returned_latitude=returned_latitude,
        returned_longitude=returned_longitude,
        returned_elevation_m=returned_elevation,
        returned_timezone=returned_timezone,
        quality_flags=tuple(sorted(set(flags))),
    )


def _manifest_payload(snapshot: WeatherForecastSnapshot) -> dict[str, Any]:
    return {
        "contract_id": snapshot.contract_id,
        "forecast_snapshot_id": snapshot.forecast_snapshot_id,
        "data_kind": snapshot.data_kind,
        "game_id": snapshot.game_id,
        "season": snapshot.season,
        "week": snapshot.week,
        "registry_record_id": snapshot.registry_record_id,
        "provider": snapshot.provider,
        "provider_model": snapshot.provider_model,
        "variables": snapshot.variables_json,
        "valid_at": _stored_iso(snapshot.valid_at),
        "fixed_lead_hours": snapshot.fixed_lead_hours,
        "forecast_basis_at": _stored_iso(snapshot.forecast_basis_at),
        "forecast_basis_kind": snapshot.forecast_basis_kind,
        "provider_issued_at": _stored_iso(snapshot.provider_issued_at),
        "provider_available_at": _stored_iso(snapshot.provider_available_at),
        "received_at": _stored_iso(snapshot.received_at),
        "requested_coordinates": {
            "latitude": snapshot.requested_latitude,
            "longitude": snapshot.requested_longitude,
        },
        "returned_coordinates": {
            "latitude": snapshot.returned_latitude,
            "longitude": snapshot.returned_longitude,
            "elevation_m": snapshot.returned_elevation_m,
            "timezone": snapshot.returned_timezone,
        },
        "values": {
            name: getattr(snapshot, name) for name in NORMALIZED_VARIABLES
        },
        "units": snapshot.units_json,
        "status": snapshot.status,
        "quality_flags": snapshot.quality_flags_json,
        "source_uri_redacted": snapshot.source_uri_redacted,
        "raw_sha256": snapshot.raw_sha256,
        "byte_count": snapshot.byte_count,
        "raw_artifact_path": snapshot.raw_artifact_path,
        "manifest_path": snapshot.manifest_path,
    }


def verify_weather_forecast_artifact(snapshot: WeatherForecastSnapshot) -> None:
    raw_path = Path(snapshot.raw_artifact_path)
    manifest_path = Path(snapshot.manifest_path)
    if not raw_path.is_file():
        raise WeatherForecastIntegrityError(f"Forecast artifact is missing: {raw_path}")
    actual_sha256, byte_count = _sha256_file(raw_path)
    if actual_sha256 != snapshot.raw_sha256 or byte_count != snapshot.byte_count:
        raise WeatherForecastIntegrityError(
            f"Forecast artifact no longer matches recorded evidence: {raw_path}"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WeatherForecastIntegrityError(
            f"Forecast manifest is missing or invalid: {manifest_path}"
        ) from exc
    if manifest != _manifest_payload(snapshot):
        raise WeatherForecastIntegrityError(
            f"Forecast manifest no longer matches recorded evidence: {manifest_path}"
        )


class HistoricalForecastBackfillService:
    def __init__(
        self,
        session: Session,
        *,
        client: OpenMeteoPreviousRunsClient,
        snapshot_root: str | Path | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.session = session
        self.client = client
        self.snapshot_root = _resolve_root(snapshot_root)
        self.clock = clock

    def _existing_snapshot(
        self,
        candidate: HistoricalForecastCandidate,
    ) -> WeatherForecastSnapshot | None:
        if candidate.registry_record_id is None or candidate.valid_at is None:
            return None
        return self.session.scalar(
            select(WeatherForecastSnapshot).where(
                WeatherForecastSnapshot.contract_id == WEATHER_FORECAST_CONTRACT_ID,
                WeatherForecastSnapshot.data_kind == WEATHER_FORECAST_DATA_KIND,
                WeatherForecastSnapshot.game_id == candidate.game_id,
                WeatherForecastSnapshot.registry_record_id
                == candidate.registry_record_id,
                WeatherForecastSnapshot.provider_model == WEATHER_FORECAST_MODEL,
                WeatherForecastSnapshot.fixed_lead_hours
                == WEATHER_FORECAST_FIXED_LEAD_HOURS,
                WeatherForecastSnapshot.valid_at == candidate.valid_at,
            )
        )

    def _capture_new_snapshot(
        self,
        candidate: HistoricalForecastCandidate,
        request: OpenMeteoRequest,
    ) -> WeatherForecastSnapshot:
        if (
            candidate.valid_at is None
            or candidate.registry_record_id is None
            or candidate.requested_latitude is None
            or candidate.requested_longitude is None
            or candidate.week is None
        ):
            raise ValueError("cannot capture a quarantined forecast candidate")
        raw_payload = self.client.fetch(request)
        received_at = _aware_utc(self.clock(), field_name="received_at")
        normalized = normalize_open_meteo_response(
            raw_payload,
            valid_at=candidate.valid_at,
        )
        snapshot_id = _snapshot_id(candidate)
        raw_sha256 = _sha256_bytes(raw_payload)
        artifact_directory = (
            self.snapshot_root
            / WEATHER_FORECAST_PROVIDER
            / str(candidate.season)
            / f"week_{candidate.week:02d}"
            / _safe_path_component(candidate.game_id, fallback="unknown_game")
            / snapshot_id
            / raw_sha256
        )
        raw_path = artifact_directory / "response.json"
        manifest_path = artifact_directory / "manifest.json"
        snapshot = WeatherForecastSnapshot(
            forecast_snapshot_id=snapshot_id,
            contract_id=WEATHER_FORECAST_CONTRACT_ID,
            data_kind=WEATHER_FORECAST_DATA_KIND,
            game_id=candidate.game_id,
            season=candidate.season,
            week=candidate.week,
            registry_record_id=candidate.registry_record_id,
            provider=WEATHER_FORECAST_PROVIDER,
            provider_model=WEATHER_FORECAST_MODEL,
            variables_json=list(OPEN_METEO_HOURLY_VARIABLES),
            valid_at=candidate.valid_at,
            fixed_lead_hours=WEATHER_FORECAST_FIXED_LEAD_HOURS,
            forecast_basis_at=candidate.valid_at
            - timedelta(hours=WEATHER_FORECAST_FIXED_LEAD_HOURS),
            forecast_basis_kind=WEATHER_FORECAST_BASIS_KIND,
            provider_issued_at=None,
            provider_available_at=None,
            received_at=received_at,
            requested_latitude=candidate.requested_latitude,
            requested_longitude=candidate.requested_longitude,
            returned_latitude=normalized.returned_latitude,
            returned_longitude=normalized.returned_longitude,
            returned_elevation_m=normalized.returned_elevation_m,
            returned_timezone=normalized.returned_timezone,
            temperature_c=normalized.values["temperature_c"],
            relative_humidity_pct=normalized.values["relative_humidity_pct"],
            precipitation_mm=normalized.values["precipitation_mm"],
            wind_speed_mps=normalized.values["wind_speed_mps"],
            wind_direction_degrees=normalized.values[
                "wind_direction_degrees"
            ],
            wind_gusts_mps=normalized.values["wind_gusts_mps"],
            status=normalized.status,
            units_json=normalized.units,
            quality_flags_json=list(normalized.quality_flags),
            raw_artifact_path=str(raw_path),
            manifest_path=str(manifest_path),
            source_uri_redacted=request.request_uri_redacted,
            raw_sha256=raw_sha256,
            byte_count=len(raw_payload),
            created_at=received_at,
        )
        _write_immutable(raw_path, raw_payload)
        manifest_payload = json.dumps(
            _manifest_payload(snapshot),
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        _write_immutable(manifest_path, manifest_payload)
        self.session.add(snapshot)
        self.session.flush()
        return snapshot

    def _record_result(
        self,
        *,
        ingest_run_id: str,
        candidate: HistoricalForecastCandidate,
        status: str,
        attempted_at: datetime,
        snapshot: WeatherForecastSnapshot | None = None,
        reason: str | None = None,
        request_uri_redacted: str | None = None,
    ) -> None:
        self.session.add(
            WeatherForecastCaptureResult(
                capture_result_id=_capture_result_id(
                    ingest_run_id,
                    candidate.game_id,
                ),
                ingest_run_id=ingest_run_id,
                game_id=candidate.game_id,
                season=candidate.season,
                week=candidate.week,
                capture_kind="historical_backfill",
                registry_record_id=candidate.registry_record_id,
                forecast_snapshot_id=(
                    snapshot.forecast_snapshot_id if snapshot else None
                ),
                valid_at=candidate.valid_at,
                status=status,
                reason=reason,
                request_uri_redacted=request_uri_redacted,
                attempted_at=attempted_at,
            )
        )
        self.session.commit()

    def run(
        self,
        assessment: HistoricalForecastAssessment,
        *,
        game_ids: set[str] | None = None,
        progress: Callable[[int, int, str, str], None] | None = None,
    ) -> dict[str, Any]:
        selected = [
            candidate
            for candidate in assessment.candidates
            if not game_ids or candidate.game_id in game_ids
        ]
        if game_ids:
            missing = sorted(game_ids - {candidate.game_id for candidate in selected})
            if missing:
                raise ValueError(f"unknown game IDs: {', '.join(missing)}")
        ingest_run_id = str(uuid.uuid4())
        run_config = {
            "contract_id": WEATHER_FORECAST_CONTRACT_ID,
            "provider": WEATHER_FORECAST_PROVIDER,
            "provider_model": WEATHER_FORECAST_MODEL,
            "fixed_lead_hours": WEATHER_FORECAST_FIXED_LEAD_HOURS,
            "season_start": assessment.season_start,
            "season_end": assessment.season_end,
            "game_ids": sorted(game_ids) if game_ids else None,
        }
        self.session.add(
            IngestRun(
                ingest_run_id=ingest_run_id,
                source_system="open_meteo",
                source_table="weather_forecast_snapshot",
                source_path=str(self.snapshot_root),
                source_checksum=hashlib.sha256(
                    json.dumps(run_config, sort_keys=True).encode("utf-8")
                ).hexdigest(),
                season=(
                    assessment.season_start
                    if assessment.season_start == assessment.season_end
                    else None
                ),
                week=None,
                slate="historical_all_games",
                status="running",
                rows_raw=0,
                rows_curated=0,
                rows_unresolved=0,
                started_at=_aware_utc(
                    self.clock(), field_name="started_at"
                ).replace(tzinfo=None),
            )
        )
        self.session.commit()

        status_counts: Counter[str] = Counter()
        snapshot_status_counts: Counter[str] = Counter()
        errors: list[str] = []
        for index, candidate in enumerate(selected, start=1):
            attempted_at = _aware_utc(self.clock(), field_name="attempted_at")
            result_status = "error"
            try:
                if candidate.quarantine_reason:
                    result_status = "quarantined"
                    self._record_result(
                        ingest_run_id=ingest_run_id,
                        candidate=candidate,
                        status=result_status,
                        attempted_at=attempted_at,
                        reason=candidate.quarantine_reason,
                    )
                else:
                    request = self.client.build_request(candidate)
                    snapshot = self._existing_snapshot(candidate)
                    if snapshot is not None:
                        verify_weather_forecast_artifact(snapshot)
                        result_status = "reused"
                        result_request_uri_redacted = (
                            snapshot.source_uri_redacted
                        )
                    else:
                        snapshot = self._capture_new_snapshot(candidate, request)
                        result_status = (
                            "captured"
                            if snapshot.status == "available"
                            else snapshot.status
                        )
                        result_request_uri_redacted = (
                            request.request_uri_redacted
                        )
                    snapshot_status_counts[snapshot.status] += 1
                    reason = (
                        None
                        if snapshot.status == "available"
                        else f"forecast_snapshot_status={snapshot.status}"
                    )
                    self._record_result(
                        ingest_run_id=ingest_run_id,
                        candidate=candidate,
                        status=result_status,
                        attempted_at=attempted_at,
                        snapshot=snapshot,
                        reason=reason,
                        request_uri_redacted=result_request_uri_redacted,
                    )
            except Exception as exc:  # noqa: BLE001
                self.session.rollback()
                safe_reason = (
                    str(exc).replace(self.client.api_key, "[redacted]")
                    if self.client.api_key
                    else str(exc)
                )
                errors.append(f"{candidate.game_id}: {safe_reason}")
                result_status = "error"
                try:
                    request_uri_redacted = self.client.build_request(
                        candidate
                    ).request_uri_redacted
                except Exception:  # noqa: BLE001
                    request_uri_redacted = None
                self._record_result(
                    ingest_run_id=ingest_run_id,
                    candidate=candidate,
                    status=result_status,
                    attempted_at=attempted_at,
                    reason=safe_reason,
                    request_uri_redacted=request_uri_redacted,
                )
            status_counts[result_status] += 1
            if progress:
                progress(index, len(selected), candidate.game_id, result_status)

        rows_with_snapshot = sum(snapshot_status_counts.values())
        unresolved = (
            status_counts["error"]
            + status_counts["quarantined"]
            + snapshot_status_counts["partial"]
            + snapshot_status_counts["missing"]
        )
        run = self.session.get(IngestRun, ingest_run_id)
        if run is None:
            raise RuntimeError(f"ingest run disappeared: {ingest_run_id}")
        run.status = "completed_with_warnings" if unresolved else "completed"
        run.rows_raw = (
            len(selected)
            - status_counts["reused"]
            - status_counts["quarantined"]
            - status_counts["error"]
        )
        run.rows_curated = rows_with_snapshot
        run.rows_unresolved = unresolved
        run.error_message = json.dumps(errors) if errors else None
        run.completed_at = _aware_utc(
            self.clock(), field_name="completed_at"
        ).replace(tzinfo=None)
        self.session.commit()
        return {
            "contract_id": WEATHER_FORECAST_CONTRACT_ID,
            "ingest_run_id": ingest_run_id,
            "status": run.status,
            "season_start": assessment.season_start,
            "season_end": assessment.season_end,
            "expected_games": len(selected),
            "result_status_counts": dict(sorted(status_counts.items())),
            "snapshot_status_counts": dict(sorted(snapshot_status_counts.items())),
            "rows_raw": run.rows_raw,
            "rows_curated": run.rows_curated,
            "rows_unresolved": run.rows_unresolved,
            "errors": errors,
        }
