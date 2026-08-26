"""Cutoff-safe weather views for every canonical game in a selected slate."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    CuratedGameVenue,
    CuratedGameWeather,
    CuratedSalary,
    RawNflSchedule,
    VenueRegistryRecord,
    WeatherForecastCaptureResult,
    WeatherForecastSnapshot,
)
from .current_weather_forecast import (
    CURRENT_WEATHER_FORECAST_DATA_KIND,
    current_forecast_visible_at_cutoff,
)
from .historical_weather import schedule_kickoff_at
from .matching import normalize_team
from .weather_forecast_backfill import (
    OPEN_METEO_HOURLY_VARIABLES,
    WEATHER_FORECAST_CONTRACT_ID,
    WEATHER_FORECAST_DATA_KIND,
    WEATHER_FORECAST_MODEL,
    WEATHER_FORECAST_PROVIDER,
    _stored_iso,
    _stored_utc,
    historical_forecast_visible_at_cutoff,
)


SLATE_GAME_WEATHER_CONTRACT_ID = "slate_game_weather_v1"
TEAM_ALIASES = {
    "JAC": "JAX",
    "LA": "LAR",
    "OAK": "LV",
    "SD": "LAC",
    "STL": "LAR",
    "WFT": "WAS",
    "WSH": "WAS",
}
CURRENT_CAPTURE_ERROR_STATES = {"error", "quarantined"}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset")
    return value.astimezone(UTC)


def _canonical_team(value: str | None) -> str | None:
    normalized = normalize_team(value)
    return TEAM_ALIASES.get(normalized, normalized) if normalized else None


def _team_pair(team: str | None, opponent: str | None) -> tuple[str, str] | None:
    left = _canonical_team(team)
    right = _canonical_team(opponent)
    if left is None or right is None or left == right:
        return None
    return tuple(sorted((left, right)))


def _latest_schedules(
    session: Session,
    *,
    season: int,
    week: int,
) -> dict[str, RawNflSchedule]:
    rows = list(
        session.scalars(
            select(RawNflSchedule)
            .where(
                RawNflSchedule.season == season,
                RawNflSchedule.week == week,
            )
            .order_by(
                RawNflSchedule.created_at,
                RawNflSchedule.raw_nfl_schedule_id,
            )
        )
    )
    latest: dict[str, RawNflSchedule] = {}
    for row in rows:
        if row.game_id:
            latest[row.game_id] = row
    return latest


def _forecast_visible_at_cutoff(
    snapshot: WeatherForecastSnapshot,
    cutoff_at: datetime,
) -> bool:
    if snapshot.data_kind == CURRENT_WEATHER_FORECAST_DATA_KIND:
        return current_forecast_visible_at_cutoff(snapshot, cutoff_at)
    if snapshot.data_kind != WEATHER_FORECAST_DATA_KIND:
        return False
    return (
        snapshot.provider == WEATHER_FORECAST_PROVIDER
        and snapshot.provider_model == WEATHER_FORECAST_MODEL
        and tuple(snapshot.variables_json) == OPEN_METEO_HOURLY_VARIABLES
        and historical_forecast_visible_at_cutoff(snapshot, cutoff_at)
    )


def _snapshot_payload(
    snapshot: WeatherForecastSnapshot,
    *,
    cutoff_at: datetime,
) -> dict[str, Any]:
    basis_at = _stored_utc(snapshot.forecast_basis_at)
    return {
        "forecast_snapshot_id": snapshot.forecast_snapshot_id,
        "contract_id": snapshot.contract_id,
        "data_kind": snapshot.data_kind,
        "status": snapshot.status,
        "provider": snapshot.provider,
        "provider_model": snapshot.provider_model,
        "valid_at": _stored_iso(snapshot.valid_at),
        "forecast_basis_at": _stored_iso(snapshot.forecast_basis_at),
        "forecast_basis_kind": snapshot.forecast_basis_kind,
        "received_at": _stored_iso(snapshot.received_at),
        "age_seconds": max(0.0, (cutoff_at - basis_at).total_seconds()),
        "temperature_c": snapshot.temperature_c,
        "relative_humidity_pct": snapshot.relative_humidity_pct,
        "precipitation_mm": snapshot.precipitation_mm,
        "wind_speed_mps": snapshot.wind_speed_mps,
        "wind_direction_degrees": snapshot.wind_direction_degrees,
        "wind_gusts_mps": snapshot.wind_gusts_mps,
        "units": dict(snapshot.units_json or {}),
        "quality_flags": sorted(set(snapshot.quality_flags_json or [])),
    }


def _actual_payload(actual: CuratedGameWeather) -> dict[str, Any]:
    return {
        "data_kind": actual.data_kind,
        "observation_basis": actual.observation_basis,
        "replay_eligible": actual.replay_eligible,
        "effective_at": _stored_iso(actual.effective_at),
        "weather_status": actual.weather_status,
        "stadium": actual.stadium,
        "roof": actual.roof,
        "surface": actual.surface,
        "temperature_f": actual.temperature_f,
        "wind_mph": actual.wind_mph,
        "source_system": actual.source_system,
        "quality_flags": sorted(set(actual.quality_flags_json or [])),
    }


def _latest_capture_results(
    rows: list[WeatherForecastCaptureResult],
    *,
    cutoff_at: datetime,
) -> dict[str, WeatherForecastCaptureResult]:
    latest: dict[str, WeatherForecastCaptureResult] = {}
    for row in rows:
        if (
            row.capture_kind == "current_refresh"
            and _stored_utc(row.attempted_at) > cutoff_at
        ):
            continue
        prior = latest.get(row.game_id)
        if prior is None or (
            _stored_utc(row.attempted_at),
            row.capture_result_id,
        ) > (
            _stored_utc(prior.attempted_at),
            prior.capture_result_id,
        ):
            latest[row.game_id] = row
    return latest


class SlateWeatherService:
    """Build a complete slate-game view without using player display-name joins."""

    def __init__(
        self,
        session: Session,
        *,
        stale_after: timedelta = timedelta(hours=2),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if stale_after <= timedelta(0):
            raise ValueError("stale_after must be positive")
        self.session = session
        self.stale_after = stale_after
        self.clock = clock

    def report(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
        cutoff_at: datetime | None = None,
    ) -> dict[str, Any]:
        source = source_system.strip().lower()
        slate_name = slate.strip()
        if not source:
            raise ValueError("source_system must not be blank")
        if not slate_name:
            raise ValueError("slate must not be blank")
        now = _aware_utc(self.clock(), field_name="clock")
        requested_cutoff = (
            _aware_utc(cutoff_at, field_name="cutoff_at")
            if cutoff_at is not None
            else None
        )

        salary_rows = list(
            self.session.scalars(
                select(CuratedSalary).where(
                    func.lower(CuratedSalary.source_system) == source,
                    CuratedSalary.season == season,
                    CuratedSalary.week == week,
                    func.lower(CuratedSalary.slate) == slate_name.lower(),
                )
            )
        )
        all_capture_rows = list(
            self.session.scalars(
                select(WeatherForecastCaptureResult).where(
                    WeatherForecastCaptureResult.season == season,
                    WeatherForecastCaptureResult.week == week,
                )
            )
        )
        slate_capture_rows = [
            row
            for row in all_capture_rows
            if row.capture_kind == "current_refresh"
            and row.slate is not None
            and row.slate.lower() == slate_name.lower()
        ]

        schedules = _latest_schedules(self.session, season=season, week=week)
        schedules_by_pair: dict[tuple[str, str], list[RawNflSchedule]] = {}
        for schedule in schedules.values():
            pair = _team_pair(schedule.home_team, schedule.away_team)
            if pair is not None:
                schedules_by_pair.setdefault(pair, []).append(schedule)

        salary_pairs: set[tuple[str, str]] = set()
        incomplete_salary_rows = 0
        for row in salary_rows:
            pair = _team_pair(row.team, row.opponent)
            if pair is None:
                incomplete_salary_rows += 1
            else:
                salary_pairs.add(pair)

        captured_game_ids = {
            row.game_id for row in slate_capture_rows if row.game_id
        }
        selected_game_ids = set(captured_game_ids)
        unresolved_references: list[dict[str, Any]] = []
        for pair in sorted(salary_pairs):
            matches = schedules_by_pair.get(pair, [])
            captured_matches = [
                row for row in matches if row.game_id in captured_game_ids
            ]
            if len(captured_matches) == 1:
                selected_game_ids.add(captured_matches[0].game_id or "")
            elif len(matches) == 1:
                selected_game_ids.add(matches[0].game_id or "")
            else:
                unresolved_references.append(
                    {
                        "identity_status": "ambiguous" if matches else "unresolved",
                        "team_pair": pair,
                        "candidate_game_ids": sorted(
                            row.game_id for row in matches if row.game_id
                        ),
                    }
                )
        selected_game_ids.discard("")

        mappings = {
            row.game_id: row
            for row in self.session.scalars(
                select(CuratedGameVenue).where(
                    CuratedGameVenue.game_id.in_(selected_game_ids)
                )
            )
        } if selected_game_ids else {}
        registry_ids = {
            row.registry_record_id
            for row in mappings.values()
            if row.registry_record_id is not None
        }
        venues = {
            row.registry_record_id: row
            for row in self.session.scalars(
                select(VenueRegistryRecord).where(
                    VenueRegistryRecord.registry_record_id.in_(registry_ids)
                )
            )
        } if registry_ids else {}

        schedule_kickoffs = {
            game_id: schedule_kickoff_at(schedule)
            for game_id, schedule in schedules.items()
            if game_id in selected_game_ids
        }
        known_kickoffs = [value for value in schedule_kickoffs.values() if value]
        slate_lock_at = min(known_kickoffs, default=None)
        request_kind = (
            "historical"
            if known_kickoffs and all(kickoff <= now for kickoff in known_kickoffs)
            else "current"
        )
        cutoff_candidates = [now]
        if requested_cutoff is not None:
            cutoff_candidates.append(requested_cutoff)
        if slate_lock_at is not None:
            cutoff_candidates.append(slate_lock_at)
        effective_cutoff = min(cutoff_candidates)
        eligible_current_snapshot_ids = {
            row.forecast_snapshot_id
            for row in slate_capture_rows
            if row.forecast_snapshot_id is not None
            and _stored_utc(row.attempted_at) <= effective_cutoff
            and row.slate_lock_at is not None
            and slate_lock_at is not None
            and _stored_utc(row.slate_lock_at) == slate_lock_at
        }

        snapshots = list(
            self.session.scalars(
                select(WeatherForecastSnapshot).where(
                    WeatherForecastSnapshot.contract_id == WEATHER_FORECAST_CONTRACT_ID,
                    WeatherForecastSnapshot.game_id.in_(selected_game_ids),
                )
            )
        ) if selected_game_ids else []
        snapshots_by_game: dict[str, list[WeatherForecastSnapshot]] = {}
        for snapshot in snapshots:
            if (
                request_kind == "current"
                and snapshot.data_kind != CURRENT_WEATHER_FORECAST_DATA_KIND
            ):
                continue
            if (
                snapshot.data_kind == CURRENT_WEATHER_FORECAST_DATA_KIND
                and snapshot.forecast_snapshot_id
                not in eligible_current_snapshot_ids
            ):
                continue
            mapping = mappings.get(snapshot.game_id)
            if (
                mapping is None
                or mapping.mapping_status != "resolved"
                or mapping.registry_record_id is None
                or snapshot.registry_record_id != mapping.registry_record_id
            ):
                continue
            kickoff_at = schedule_kickoffs.get(snapshot.game_id)
            if (
                kickoff_at is None
                or _stored_utc(snapshot.valid_at)
                != kickoff_at.replace(minute=0, second=0, microsecond=0)
            ):
                continue
            if _forecast_visible_at_cutoff(snapshot, effective_cutoff):
                snapshots_by_game.setdefault(snapshot.game_id, []).append(snapshot)

        selected_forecasts = {
            game_id: max(
                candidates,
                key=lambda row: (
                    _stored_utc(row.forecast_basis_at),
                    _stored_utc(row.received_at),
                    row.forecast_snapshot_id,
                ),
            )
            for game_id, candidates in snapshots_by_game.items()
        }
        relevant_capture_rows = [
            row
            for row in all_capture_rows
            if row.game_id in selected_game_ids
            and (
                row.capture_kind == "historical_backfill"
                or (
                    row.capture_kind == "current_refresh"
                    and row.slate is not None
                    and row.slate.lower() == slate_name.lower()
                )
            )
        ]
        latest_current_results = _latest_capture_results(
            [
                row
                for row in relevant_capture_rows
                if row.capture_kind == "current_refresh"
            ],
            cutoff_at=effective_cutoff,
        )
        latest_historical_results = _latest_capture_results(
            [
                row
                for row in relevant_capture_rows
                if row.capture_kind == "historical_backfill"
            ],
            cutoff_at=effective_cutoff,
        )
        actuals = {
            row.game_id: row
            for row in self.session.scalars(
                select(CuratedGameWeather).where(
                    CuratedGameWeather.game_id.in_(selected_game_ids)
                )
            )
        } if selected_game_ids else {}

        games: list[dict[str, Any]] = []
        for game_id in sorted(selected_game_ids):
            schedule = schedules.get(game_id)
            kickoff_at = schedule_kickoffs.get(game_id)
            mapping = mappings.get(game_id)
            venue = (
                venues.get(mapping.registry_record_id)
                if mapping is not None and mapping.registry_record_id is not None
                else None
            )
            snapshot = selected_forecasts.get(game_id)
            latest_result = (
                latest_current_results.get(game_id)
                if request_kind == "current"
                or (
                    snapshot is not None
                    and snapshot.data_kind == CURRENT_WEATHER_FORECAST_DATA_KIND
                )
                else latest_historical_results.get(game_id)
            )
            if latest_result is None and snapshot is None:
                latest_result = (
                    latest_current_results.get(game_id)
                    or latest_historical_results.get(game_id)
                )
            actual = actuals.get(game_id)
            actual_is_available = bool(
                request_kind == "historical"
                and actual is not None
                and (kickoff_at is None or kickoff_at <= now)
            )

            flags: set[str] = set()
            if schedule is None:
                flags.add("schedule_missing")
            if kickoff_at is None:
                flags.add("kickoff_missing")
            if mapping is None:
                flags.add("venue_mapping_missing")
            elif mapping.mapping_status != "resolved":
                flags.add(f"venue_mapping_{mapping.mapping_status}")
            if venue is None:
                flags.add("venue_missing")

            state = "missing"
            if venue is not None and venue.default_roof == "fixed_indoor":
                state = "indoor"
            elif snapshot is not None:
                state = (
                    "available" if snapshot.status == "available" else "missing"
                )
                if (
                    snapshot.data_kind == CURRENT_WEATHER_FORECAST_DATA_KIND
                    and state == "available"
                    and effective_cutoff - _stored_utc(snapshot.received_at)
                    > self.stale_after
                ):
                    state = "stale"
                    flags.add("forecast_stale")
            if snapshot is None:
                flags.add("forecast_missing")
            else:
                flags.update(snapshot.quality_flags_json or [])
                if snapshot.status != "available":
                    flags.add(f"forecast_{snapshot.status}")
            if (
                latest_result is not None
                and latest_result.status in CURRENT_CAPTURE_ERROR_STATES
                and (
                    snapshot is None
                    or (
                        latest_result.capture_kind == "current_refresh"
                        and _stored_utc(latest_result.attempted_at)
                        > _stored_utc(snapshot.received_at)
                    )
                )
            ):
                state = "error"
                flags.add("forecast_capture_error")
            if (
                request_kind == "historical"
                and kickoff_at is not None
                and kickoff_at <= now
                and not actual_is_available
            ):
                flags.add("actual_conditions_missing")

            games.append(
                {
                    "game_id": game_id,
                    "identity_status": "resolved",
                    "candidate_game_ids": [],
                    "home_team": _canonical_team(schedule.home_team) if schedule else None,
                    "away_team": _canonical_team(schedule.away_team) if schedule else None,
                    "kickoff_at": _stored_iso(kickoff_at),
                    "schedule_status": schedule.status if schedule else None,
                    "weather_state": state,
                    "venue": (
                        {
                            "registry_record_id": venue.registry_record_id,
                            "venue_id": venue.venue_id,
                            "name": venue.canonical_name,
                            "timezone": venue.timezone,
                            "country_code": venue.country_code,
                            "default_roof": venue.default_roof,
                            "roof_basis": "venue_registry_default",
                        }
                        if venue is not None
                        else None
                    ),
                    "forecast": (
                        _snapshot_payload(snapshot, cutoff_at=effective_cutoff)
                        if snapshot is not None
                        else None
                    ),
                    "actual": (
                        _actual_payload(actual)
                        if actual is not None and actual_is_available
                        else None
                    ),
                    "latest_capture_status": (
                        latest_result.status if latest_result else None
                    ),
                    "latest_capture_reason": (
                        latest_result.reason
                        if latest_result
                        and latest_result.status in CURRENT_CAPTURE_ERROR_STATES
                        else None
                    ),
                    "quality_flags": sorted(flags),
                }
            )

        for reference in unresolved_references:
            team_a, team_b = reference["team_pair"]
            games.append(
                {
                    "game_id": None,
                    "identity_status": reference["identity_status"],
                    "candidate_game_ids": reference["candidate_game_ids"],
                    "home_team": None,
                    "away_team": None,
                    "kickoff_at": None,
                    "schedule_status": None,
                    "weather_state": "missing",
                    "venue": None,
                    "forecast": None,
                    "actual": None,
                    "latest_capture_status": None,
                    "latest_capture_reason": None,
                    "quality_flags": [
                        f"salary_matchup_identity_{reference['identity_status']}",
                        f"salary_team_pair:{team_a}-{team_b}",
                    ],
                }
            )

        games.sort(
            key=lambda row: (
                row["kickoff_at"] is None,
                row["kickoff_at"] or "",
                row["game_id"] or "",
                row["quality_flags"],
            )
        )
        state_counts = Counter(row["weather_state"] for row in games)
        identity_counts = Counter(row["identity_status"] for row in games)
        report_flags: set[str] = set()
        if not salary_rows:
            report_flags.add("slate_salary_rows_missing")
        if incomplete_salary_rows:
            report_flags.add("salary_rows_without_matchup_identity")
        if unresolved_references:
            report_flags.add("slate_game_identity_incomplete")
        if slate_lock_at is None:
            report_flags.add("slate_lock_missing")
        if requested_cutoff is not None and effective_cutoff < requested_cutoff:
            if effective_cutoff == now:
                report_flags.add("cutoff_clamped_to_current_time")
            if slate_lock_at is not None and effective_cutoff == slate_lock_at:
                report_flags.add("cutoff_clamped_to_slate_lock")

        return {
            "contract_id": SLATE_GAME_WEATHER_CONTRACT_ID,
            "forecast_contract_id": WEATHER_FORECAST_CONTRACT_ID,
            "source_system": source,
            "season": season,
            "week": week,
            "slate": slate_name,
            "request_kind": request_kind,
            "generated_at": _stored_iso(now),
            "requested_cutoff_at": _stored_iso(requested_cutoff),
            "cutoff_at": _stored_iso(effective_cutoff),
            "slate_lock_at": _stored_iso(slate_lock_at),
            "salary_rows": len(salary_rows),
            "games_expected": len(games),
            "games_resolved": identity_counts.get("resolved", 0),
            "state_counts": dict(sorted(state_counts.items())),
            "identity_counts": dict(sorted(identity_counts.items())),
            "quality_flags": sorted(report_flags),
            "games": games,
        }
