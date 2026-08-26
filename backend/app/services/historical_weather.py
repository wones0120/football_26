"""Curate retrospective game weather from versioned nflverse schedules."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import CuratedGameWeather, RawNflSchedule
from .matching import normalize_team


HISTORICAL_GAME_WEATHER_CONTRACT_ID = "historical_game_weather_actual_v1"
HISTORICAL_GAME_WEATHER_DATA_KIND = "retrospective_game_observation"
HISTORICAL_GAME_WEATHER_OBSERVATION_BASIS = "nflverse_schedule_result_context"
EASTERN = ZoneInfo("America/New_York")
INDOOR_ROOFS = {"closed", "dome"}
EXPOSED_ROOFS = {"open", "outdoors"}


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _safe_float(value: Any) -> float | None:
    text = _safe_text(value)
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _parse_date(value: Any) -> date | None:
    text = _safe_text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _parse_time(value: Any) -> time | None:
    text = _safe_text(value)
    if not text or "-" in text[:10]:
        return None
    try:
        return time.fromisoformat(text)
    except ValueError:
        return None


def schedule_kickoff_at(schedule: RawNflSchedule) -> datetime | None:
    """Build a UTC kickoff from nflverse's Eastern-date/Eastern-time contract."""
    raw = schedule.raw_row_json or {}
    game_date = _parse_date(raw.get("gameday") or raw.get("game_date"))
    game_time = _parse_time(raw.get("gametime") or raw.get("kickoff"))
    if game_time is None:
        game_time = _parse_time(schedule.kickoff)
    if game_date is None or game_time is None:
        return None
    return datetime.combine(game_date, game_time, tzinfo=EASTERN).astimezone(UTC)


def _weather_status(
    *,
    roof: str | None,
    temperature_f: float | None,
    wind_mph: float | None,
) -> str:
    if temperature_f is not None and wind_mph is not None:
        return "observed"
    if roof in INDOOR_ROOFS and temperature_f is None and wind_mph is None:
        return "indoor_not_applicable"
    if temperature_f is not None or wind_mph is not None:
        return "partial"
    if roof in EXPOSED_ROOFS:
        return "missing_exposed"
    return "missing_unknown_roof"


def _quality_flags(
    *,
    roof: str | None,
    kickoff_at: datetime | None,
    temperature_f: float | None,
    wind_mph: float | None,
    weather_status: str,
) -> list[str]:
    flags: list[str] = []
    if kickoff_at is None:
        flags.append("missing_kickoff")
    if not roof:
        flags.append("missing_roof")
    elif roof not in INDOOR_ROOFS | EXPOSED_ROOFS:
        flags.append("unknown_roof")
    if temperature_f is not None and not -80.0 <= temperature_f <= 140.0:
        flags.append("temperature_out_of_range")
    if wind_mph is not None and not 0.0 <= wind_mph <= 150.0:
        flags.append("wind_out_of_range")
    elif wind_mph is not None and wind_mph > 45.0:
        flags.append("extreme_wind_review")
    if roof in INDOOR_ROOFS and (temperature_f is not None or wind_mph is not None):
        flags.append("indoor_weather_present")
    if weather_status in {"partial", "missing_exposed"}:
        flags.append("exposed_weather_incomplete")
    return flags


@dataclass(frozen=True)
class HistoricalWeatherAssessment:
    generated_at: str
    season_start: int
    season_end: int
    source_rows: int
    latest_games: int
    skipped_without_game_key: int
    rows: tuple[dict[str, Any], ...]

    def report(self) -> dict[str, Any]:
        by_status: dict[str, int] = defaultdict(int)
        flagged_rows = 0
        flag_counts: dict[str, int] = defaultdict(int)
        for row in self.rows:
            by_status[row["weather_status"]] += 1
            flags = row["quality_flags_json"]
            if flags:
                flagged_rows += 1
            for flag in flags:
                flag_counts[flag] += 1
        return {
            "contract_id": HISTORICAL_GAME_WEATHER_CONTRACT_ID,
            "generated_at": self.generated_at,
            "season_start": self.season_start,
            "season_end": self.season_end,
            "source_rows": self.source_rows,
            "latest_games": self.latest_games,
            "rows_ready": len(self.rows),
            "skipped_without_game_key": self.skipped_without_game_key,
            "weather_status_counts": dict(sorted(by_status.items())),
            "quality_flagged_rows": flagged_rows,
            "quality_flag_counts": dict(sorted(flag_counts.items())),
            "replay_eligible_rows": 0,
            "data_kind": HISTORICAL_GAME_WEATHER_DATA_KIND,
            "observation_basis": HISTORICAL_GAME_WEATHER_OBSERVATION_BASIS,
        }


def assess_historical_game_weather(
    session: Session,
    *,
    season_start: int,
    season_end: int,
) -> HistoricalWeatherAssessment:
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
    skipped_without_game_key = 0
    for schedule in source_rows:
        if not schedule.game_id or schedule.week is None:
            skipped_without_game_key += 1
            continue
        latest_by_game[schedule.game_id] = schedule

    rows: list[dict[str, Any]] = []
    for game_id, schedule in sorted(latest_by_game.items()):
        raw = schedule.raw_row_json or {}
        roof = _safe_text(raw.get("roof")).lower() or None
        surface = _safe_text(raw.get("surface")).lower() or None
        temperature_f = _safe_float(raw.get("temp"))
        wind_mph = _safe_float(raw.get("wind"))
        kickoff_at = schedule_kickoff_at(schedule)
        weather_status = _weather_status(
            roof=roof,
            temperature_f=temperature_f,
            wind_mph=wind_mph,
        )
        flags = _quality_flags(
            roof=roof,
            kickoff_at=kickoff_at,
            temperature_f=temperature_f,
            wind_mph=wind_mph,
            weather_status=weather_status,
        )
        rows.append(
            {
                "game_id": game_id,
                "season": schedule.season,
                "week": int(schedule.week),
                "game_type": _safe_text(schedule.game_type).upper() or None,
                "kickoff_at": kickoff_at,
                "home_team": normalize_team(schedule.home_team),
                "away_team": normalize_team(schedule.away_team),
                "stadium": _safe_text(schedule.stadium) or None,
                "roof": roof,
                "surface": surface,
                "temperature_f": temperature_f,
                "wind_mph": wind_mph,
                "weather_status": weather_status,
                "data_kind": HISTORICAL_GAME_WEATHER_DATA_KIND,
                "observation_basis": HISTORICAL_GAME_WEATHER_OBSERVATION_BASIS,
                "observed_at": None,
                "effective_at": kickoff_at,
                "replay_eligible": False,
                "quality_flags_json": flags,
                "source_system": schedule.source_system,
                "source_ingest_run_id": schedule.ingest_run_id,
                "raw_nfl_schedule_id": schedule.raw_nfl_schedule_id,
            }
        )

    return HistoricalWeatherAssessment(
        generated_at=datetime.now(UTC).isoformat(),
        season_start=season_start,
        season_end=season_end,
        source_rows=len(source_rows),
        latest_games=len(latest_by_game),
        skipped_without_game_key=skipped_without_game_key,
        rows=tuple(rows),
    )


def apply_historical_weather_rebuild(
    session: Session,
    assessment: HistoricalWeatherAssessment,
) -> dict[str, Any]:
    session.execute(
        delete(CuratedGameWeather).where(
            CuratedGameWeather.season >= assessment.season_start,
            CuratedGameWeather.season <= assessment.season_end,
        )
    )
    if assessment.rows:
        session.bulk_insert_mappings(CuratedGameWeather, assessment.rows)
    session.flush()
    return {
        "contract_id": HISTORICAL_GAME_WEATHER_CONTRACT_ID,
        "season_start": assessment.season_start,
        "season_end": assessment.season_end,
        "rows_written": len(assessment.rows),
        "replay_eligible_rows": 0,
    }
