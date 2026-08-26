"""Append-only Open-Meteo capture for current NFL game forecasts."""

from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import IngestRun, WeatherForecastCaptureResult, WeatherForecastSnapshot
from .weather_forecast_backfill import (
    NORMALIZED_VARIABLES,
    WEATHER_FORECAST_CONTRACT_ID,
    WEATHER_FORECAST_MODEL,
    WEATHER_FORECAST_UUID_NAMESPACE,
    HistoricalForecastCandidate,
    NormalizedForecast,
    OpenMeteoPreviousRunsClient,
    OpenMeteoRequest,
    WeatherForecastIntegrityError,
    _aware_utc,
    _capture_result_id,
    _iso,
    _manifest_payload,
    _redacted_base_url,
    _resolve_root,
    _safe_path_component,
    _sha256_bytes,
    _stored_iso,
    _stored_utc,
    _utc_now,
    _write_immutable,
    assess_historical_forecast_backfill,
    normalize_open_meteo_response,
    verify_weather_forecast_artifact,
)


CURRENT_WEATHER_FORECAST_DATA_KIND = "current_forecast_capture"
CURRENT_WEATHER_FORECAST_PROVIDER = "open_meteo_forecast"
CURRENT_WEATHER_FORECAST_BASIS_KIND = "server_received_at"
CURRENT_OPEN_METEO_HOURLY_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
)
CURRENT_VARIABLE_MAP = dict(
    zip(CURRENT_OPEN_METEO_HOURLY_VARIABLES, NORMALIZED_VARIABLES, strict=True)
)


@dataclass(frozen=True)
class CurrentForecastAssessment:
    generated_at: str
    season: int
    week: int
    slate: str
    slate_lock_at: datetime
    source_rows: int
    latest_season_games: int
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
            "data_kind": CURRENT_WEATHER_FORECAST_DATA_KIND,
            "generated_at": self.generated_at,
            "season": self.season,
            "week": self.week,
            "slate": self.slate,
            "slate_lock_at": _iso(self.slate_lock_at),
            "source_rows": self.source_rows,
            "latest_season_games": self.latest_season_games,
            "expected_games": len(self.candidates),
            "eligible_games": eligible,
            "quarantined_games": len(self.candidates) - eligible,
            "quarantine_reason_counts": dict(sorted(quarantine_counts.items())),
            "provider": CURRENT_WEATHER_FORECAST_PROVIDER,
            "provider_model": WEATHER_FORECAST_MODEL,
            "provider_timing": {
                "provider_issued_at": None,
                "provider_available_at": None,
                "forecast_basis_kind": CURRENT_WEATHER_FORECAST_BASIS_KIND,
                "eligibility": "received_at <= cutoff_at",
            },
        }


def assess_current_forecast_capture(
    session: Session,
    *,
    season: int,
    week: int,
    slate: str,
    slate_lock_at: datetime,
    game_ids: set[str],
) -> CurrentForecastAssessment:
    if season < 2000:
        raise ValueError("season must be at least 2000")
    if not 1 <= week <= 25:
        raise ValueError("week must be between 1 and 25")
    normalized_slate = slate.strip()
    if not normalized_slate:
        raise ValueError("slate must not be blank")
    if not game_ids:
        raise ValueError("at least one canonical game ID is required")
    lock_at = _aware_utc(slate_lock_at, field_name="slate_lock_at")
    historical = assess_historical_forecast_backfill(
        session,
        season_start=season,
        season_end=season,
    )
    week_candidates = tuple(
        candidate
        for candidate in historical.candidates
        if candidate.week == week
        and candidate.game_id in game_ids
    )
    missing = sorted(game_ids - {row.game_id for row in week_candidates})
    if missing:
        raise ValueError(f"unknown game IDs for season/week: {', '.join(missing)}")
    return CurrentForecastAssessment(
        generated_at=_iso(_utc_now()) or "",
        season=season,
        week=week,
        slate=normalized_slate,
        slate_lock_at=lock_at,
        source_rows=historical.source_rows,
        latest_season_games=historical.latest_games,
        candidates=week_candidates,
    )


class OpenMeteoForecastClient(OpenMeteoPreviousRunsClient):
    """Pinned current Forecast API client using the WTHR v1 variable family."""

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
            ("hourly", ",".join(CURRENT_OPEN_METEO_HOURLY_VARIABLES)),
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
        return OpenMeteoRequest(
            request_uri=urlunsplit(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    request_query,
                    parsed.fragment,
                )
            ),
            request_uri_redacted=urlunsplit(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    redacted_query,
                    parsed.fragment,
                )
            ),
        )


def normalize_current_open_meteo_response(
    payload: bytes,
    *,
    valid_at: datetime,
) -> NormalizedForecast:
    return normalize_open_meteo_response(
        payload,
        valid_at=valid_at,
        variable_map=CURRENT_VARIABLE_MAP,
    )


def current_forecast_visible_at_cutoff(
    snapshot: WeatherForecastSnapshot,
    cutoff_at: datetime,
) -> bool:
    cutoff = _aware_utc(cutoff_at, field_name="cutoff_at")
    if (
        snapshot.contract_id != WEATHER_FORECAST_CONTRACT_ID
        or snapshot.data_kind != CURRENT_WEATHER_FORECAST_DATA_KIND
        or snapshot.provider != CURRENT_WEATHER_FORECAST_PROVIDER
        or snapshot.provider_model != WEATHER_FORECAST_MODEL
        or tuple(snapshot.variables_json) != CURRENT_OPEN_METEO_HOURLY_VARIABLES
        or snapshot.fixed_lead_hours is not None
        or snapshot.forecast_basis_kind != CURRENT_WEATHER_FORECAST_BASIS_KIND
        or snapshot.provider_issued_at is not None
        or snapshot.provider_available_at is not None
    ):
        return False
    received_at = _stored_utc(snapshot.received_at)
    forecast_basis_at = _stored_utc(snapshot.forecast_basis_at)
    return forecast_basis_at == received_at and received_at <= cutoff


def select_current_forecast_at_cutoff(
    session: Session,
    *,
    game_id: str,
    cutoff_at: datetime,
    registry_record_id: str | None = None,
) -> WeatherForecastSnapshot | None:
    """Return the newest live snapshot actually received by the requested cutoff."""
    cutoff = _aware_utc(cutoff_at, field_name="cutoff_at")
    query = select(WeatherForecastSnapshot).where(
        WeatherForecastSnapshot.contract_id == WEATHER_FORECAST_CONTRACT_ID,
        WeatherForecastSnapshot.data_kind == CURRENT_WEATHER_FORECAST_DATA_KIND,
        WeatherForecastSnapshot.game_id == game_id,
    )
    if registry_record_id is not None:
        query = query.where(
            WeatherForecastSnapshot.registry_record_id == registry_record_id
        )
    candidates = list(session.scalars(query))
    eligible = [
        snapshot
        for snapshot in candidates
        if current_forecast_visible_at_cutoff(snapshot, cutoff)
    ]
    return max(eligible, key=lambda row: _stored_utc(row.received_at), default=None)


def _current_snapshot_id(
    candidate: HistoricalForecastCandidate,
    received_at: datetime,
) -> str:
    if candidate.valid_at is None or candidate.registry_record_id is None:
        raise ValueError("eligible forecast candidates require valid time and venue record")
    identity = "|".join(
        (
            WEATHER_FORECAST_CONTRACT_ID,
            CURRENT_WEATHER_FORECAST_DATA_KIND,
            candidate.game_id,
            candidate.registry_record_id,
            WEATHER_FORECAST_MODEL,
            _iso(candidate.valid_at) or "",
            _iso(received_at) or "",
        )
    )
    return str(uuid.uuid5(WEATHER_FORECAST_UUID_NAMESPACE, identity))


class CurrentForecastCaptureService:
    def __init__(
        self,
        session: Session,
        *,
        client: OpenMeteoForecastClient,
        snapshot_root: str | Path | None = None,
        request_interval_seconds: float = 0.11,
        clock: Callable[[], datetime] = _utc_now,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if (
            not math.isfinite(request_interval_seconds)
            or request_interval_seconds < 0
        ):
            raise ValueError("request_interval_seconds must be finite and non-negative")
        self.session = session
        self.client = client
        self.snapshot_root = _resolve_root(snapshot_root)
        self.request_interval_seconds = request_interval_seconds
        self.clock = clock
        self.sleeper = sleeper
        self.provider_request_count = 0

    def _fetch(self, request: OpenMeteoRequest) -> bytes:
        if self.provider_request_count and self.request_interval_seconds:
            self.sleeper(self.request_interval_seconds)
        self.provider_request_count += 1
        return self.client.fetch(request)

    def _capture_new_snapshot(
        self,
        candidate: HistoricalForecastCandidate,
        request: OpenMeteoRequest,
    ) -> tuple[WeatherForecastSnapshot, bool]:
        if (
            candidate.valid_at is None
            or candidate.registry_record_id is None
            or candidate.requested_latitude is None
            or candidate.requested_longitude is None
            or candidate.week is None
        ):
            raise ValueError("cannot capture a quarantined forecast candidate")
        raw_payload = self._fetch(request)
        received_at = _aware_utc(self.clock(), field_name="received_at")
        normalized = normalize_current_open_meteo_response(
            raw_payload,
            valid_at=candidate.valid_at,
        )
        snapshot_id = _current_snapshot_id(candidate, received_at)
        raw_sha256 = _sha256_bytes(raw_payload)
        existing = self.session.get(WeatherForecastSnapshot, snapshot_id)
        if existing is not None:
            if existing.raw_sha256 != raw_sha256:
                raise WeatherForecastIntegrityError(
                    "A live forecast receipt timestamp maps to different raw content"
                )
            verify_weather_forecast_artifact(existing)
            return existing, False

        artifact_directory = (
            self.snapshot_root
            / CURRENT_WEATHER_FORECAST_PROVIDER
            / "current"
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
            data_kind=CURRENT_WEATHER_FORECAST_DATA_KIND,
            game_id=candidate.game_id,
            season=candidate.season,
            week=candidate.week,
            registry_record_id=candidate.registry_record_id,
            provider=CURRENT_WEATHER_FORECAST_PROVIDER,
            provider_model=WEATHER_FORECAST_MODEL,
            variables_json=list(CURRENT_OPEN_METEO_HOURLY_VARIABLES),
            valid_at=candidate.valid_at,
            fixed_lead_hours=None,
            forecast_basis_at=received_at,
            forecast_basis_kind=CURRENT_WEATHER_FORECAST_BASIS_KIND,
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
            wind_direction_degrees=normalized.values["wind_direction_degrees"],
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
        _write_immutable(
            manifest_path,
            json.dumps(
                _manifest_payload(snapshot),
                indent=2,
                sort_keys=True,
            ).encode("utf-8"),
        )
        self.session.add(snapshot)
        self.session.flush()
        return snapshot, True

    def _record_result(
        self,
        *,
        ingest_run_id: str,
        assessment: CurrentForecastAssessment,
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
                capture_kind="current_refresh",
                slate=assessment.slate,
                slate_lock_at=assessment.slate_lock_at,
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
        assessment: CurrentForecastAssessment,
        *,
        progress: Callable[[int, int, str, str], None] | None = None,
    ) -> dict[str, Any]:
        selected = list(assessment.candidates)
        self.provider_request_count = 0
        ingest_run_id = str(uuid.uuid4())
        run_config = {
            "contract_id": WEATHER_FORECAST_CONTRACT_ID,
            "data_kind": CURRENT_WEATHER_FORECAST_DATA_KIND,
            "provider": CURRENT_WEATHER_FORECAST_PROVIDER,
            "provider_model": WEATHER_FORECAST_MODEL,
            "season": assessment.season,
            "week": assessment.week,
            "slate": assessment.slate,
            "slate_lock_at": _iso(assessment.slate_lock_at),
            "game_ids": sorted(candidate.game_id for candidate in selected),
            "request_interval_seconds": self.request_interval_seconds,
        }
        self.session.add(
            IngestRun(
                ingest_run_id=ingest_run_id,
                source_system="open_meteo",
                source_table="current_weather_forecast",
                source_path=str(self.snapshot_root),
                source_checksum=hashlib.sha256(
                    json.dumps(run_config, sort_keys=True).encode("utf-8")
                ).hexdigest(),
                season=assessment.season,
                week=assessment.week,
                slate=assessment.slate,
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
        post_lock_snapshots = 0
        for index, candidate in enumerate(selected, start=1):
            attempted_at = _aware_utc(self.clock(), field_name="attempted_at")
            result_status = "error"
            try:
                if candidate.quarantine_reason:
                    result_status = "quarantined"
                    self._record_result(
                        ingest_run_id=ingest_run_id,
                        assessment=assessment,
                        candidate=candidate,
                        status=result_status,
                        attempted_at=attempted_at,
                        reason=candidate.quarantine_reason,
                    )
                else:
                    request = self.client.build_request(candidate)
                    snapshot, created = self._capture_new_snapshot(candidate, request)
                    result_status = (
                        "captured"
                        if created and snapshot.status == "available"
                        else "reused"
                        if not created
                        else snapshot.status
                    )
                    snapshot_status_counts[snapshot.status] += 1
                    if _stored_utc(snapshot.received_at) > assessment.slate_lock_at:
                        post_lock_snapshots += 1
                    reason = (
                        None
                        if snapshot.status == "available"
                        else f"forecast_snapshot_status={snapshot.status}"
                    )
                    self._record_result(
                        ingest_run_id=ingest_run_id,
                        assessment=assessment,
                        candidate=candidate,
                        status=result_status,
                        attempted_at=attempted_at,
                        snapshot=snapshot,
                        reason=reason,
                        request_uri_redacted=request.request_uri_redacted,
                    )
            except Exception as exc:  # noqa: BLE001
                self.session.rollback()
                safe_reason = (
                    str(exc).replace(self.client.api_key, "[redacted]")
                    if self.client.api_key
                    else str(exc)
                )
                errors.append(f"{candidate.game_id}: {safe_reason}")
                try:
                    request_uri_redacted = self.client.build_request(
                        candidate
                    ).request_uri_redacted
                except Exception:  # noqa: BLE001
                    request_uri_redacted = None
                self._record_result(
                    ingest_run_id=ingest_run_id,
                    assessment=assessment,
                    candidate=candidate,
                    status="error",
                    attempted_at=attempted_at,
                    reason=safe_reason,
                    request_uri_redacted=request_uri_redacted,
                )
                result_status = "error"
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
        run.rows_raw = self.provider_request_count
        run.rows_curated = rows_with_snapshot
        run.rows_unresolved = unresolved
        run.error_message = json.dumps(errors) if errors else None
        run.completed_at = _aware_utc(
            self.clock(), field_name="completed_at"
        ).replace(tzinfo=None)
        self.session.commit()
        return {
            "contract_id": WEATHER_FORECAST_CONTRACT_ID,
            "data_kind": CURRENT_WEATHER_FORECAST_DATA_KIND,
            "ingest_run_id": ingest_run_id,
            "status": run.status,
            "season": assessment.season,
            "week": assessment.week,
            "slate": assessment.slate,
            "slate_lock_at": _iso(assessment.slate_lock_at),
            "expected_games": len(selected),
            "result_status_counts": dict(sorted(status_counts.items())),
            "snapshot_status_counts": dict(sorted(snapshot_status_counts.items())),
            "provider_request_count": self.provider_request_count,
            "post_lock_snapshots": post_lock_snapshots,
            "rows_raw": run.rows_raw,
            "rows_curated": run.rows_curated,
            "rows_unresolved": run.rows_unresolved,
            "errors": errors,
        }


def audit_current_forecast_capture(
    session: Session,
    assessment: CurrentForecastAssessment,
    *,
    cutoff_at: datetime,
    stale_after: timedelta,
    verify_artifacts: bool = False,
) -> dict[str, Any]:
    cutoff = _aware_utc(cutoff_at, field_name="cutoff_at")
    if stale_after <= timedelta(0):
        raise ValueError("stale_after must be positive")
    candidate_game_ids = {candidate.game_id for candidate in assessment.candidates}
    results = list(
        session.scalars(
            select(WeatherForecastCaptureResult).where(
                WeatherForecastCaptureResult.capture_kind == "current_refresh",
                WeatherForecastCaptureResult.season == assessment.season,
                WeatherForecastCaptureResult.week == assessment.week,
                WeatherForecastCaptureResult.slate == assessment.slate,
            )
        )
    )
    results = [
        result
        for result in results
        if result.game_id in candidate_game_ids
        and _stored_utc(result.attempted_at) <= cutoff
        and result.slate_lock_at is not None
        and _stored_utc(result.slate_lock_at) == assessment.slate_lock_at
    ]
    latest_result_by_game: dict[str, WeatherForecastCaptureResult] = {}
    for result in results:
        prior = latest_result_by_game.get(result.game_id)
        if prior is None or (
            _stored_utc(result.attempted_at),
            result.capture_result_id,
        ) > (
            _stored_utc(prior.attempted_at),
            prior.capture_result_id,
        ):
            latest_result_by_game[result.game_id] = result

    states: Counter[str] = Counter()
    games: list[dict[str, Any]] = []
    artifact_errors: list[str] = []
    for candidate in assessment.candidates:
        snapshot = select_current_forecast_at_cutoff(
            session,
            game_id=candidate.game_id,
            cutoff_at=cutoff,
            registry_record_id=candidate.registry_record_id,
        )
        latest_result = latest_result_by_game.get(candidate.game_id)
        state = "missing"
        age_seconds: float | None = None
        if snapshot is not None:
            age_seconds = max(
                0.0,
                (cutoff - _stored_utc(snapshot.received_at)).total_seconds(),
            )
            state = snapshot.status
            if state == "available" and age_seconds > stale_after.total_seconds():
                state = "stale"
            if verify_artifacts:
                try:
                    verify_weather_forecast_artifact(snapshot)
                except WeatherForecastIntegrityError as exc:
                    state = "error"
                    artifact_errors.append(f"{candidate.game_id}: {exc}")
        if (
            latest_result is not None
            and latest_result.status in {"error", "quarantined"}
            and (
                snapshot is None
                or _stored_utc(latest_result.attempted_at)
                > _stored_utc(snapshot.received_at)
            )
        ):
            state = "error"
        states[state] += 1
        games.append(
            {
                "game_id": candidate.game_id,
                "state": state,
                "forecast_snapshot_id": (
                    snapshot.forecast_snapshot_id if snapshot else None
                ),
                "valid_at": _stored_iso(snapshot.valid_at) if snapshot else None,
                "received_at": (
                    _stored_iso(snapshot.received_at) if snapshot else None
                ),
                "age_seconds": age_seconds,
                "source": snapshot.provider if snapshot else None,
                "latest_attempt_status": (
                    latest_result.status if latest_result else None
                ),
                "latest_attempted_at": (
                    _stored_iso(latest_result.attempted_at)
                    if latest_result
                    else None
                ),
                "latest_failure_reason": (
                    latest_result.reason
                    if latest_result
                    and latest_result.status in {"error", "quarantined"}
                    else None
                ),
            }
        )
    return {
        "contract_id": WEATHER_FORECAST_CONTRACT_ID,
        "data_kind": CURRENT_WEATHER_FORECAST_DATA_KIND,
        "season": assessment.season,
        "week": assessment.week,
        "slate": assessment.slate,
        "cutoff_at": _iso(cutoff),
        "stale_after_seconds": stale_after.total_seconds(),
        "expected_games": len(assessment.candidates),
        "state_counts": dict(sorted(states.items())),
        "games": games,
        "artifact_verification": "verified" if verify_artifacts else "not_requested",
        "artifact_errors": artifact_errors,
        "complete": states["available"] == len(assessment.candidates),
    }
