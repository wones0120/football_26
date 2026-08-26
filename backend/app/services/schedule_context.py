"""Resolve the next playable NFL week from locally ingested schedule evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import RawNflSchedule
from .historical_weather import schedule_kickoff_at


@dataclass(frozen=True)
class UpcomingScheduleContext:
    season: int
    week: int
    first_kickoff_at: datetime
    games_remaining: int


def next_upcoming_schedule_context(
    session: Session,
    *,
    as_of: datetime | None = None,
) -> UpcomingScheduleContext | None:
    """Return the earliest regular-season week with at least one future kickoff."""
    as_of = as_of or datetime.now(UTC)
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must include a timezone offset")
    as_of = as_of.astimezone(UTC)

    schedules = list(
        session.scalars(
            select(RawNflSchedule)
            .where(RawNflSchedule.game_type == "REG")
            .order_by(
                RawNflSchedule.created_at,
                RawNflSchedule.raw_nfl_schedule_id,
            )
        )
    )
    latest_by_game_id: dict[str, RawNflSchedule] = {}
    for schedule in schedules:
        if schedule.game_id and schedule.week is not None:
            latest_by_game_id[schedule.game_id] = schedule

    future_games: list[tuple[datetime, RawNflSchedule]] = []
    for schedule in latest_by_game_id.values():
        kickoff_at = schedule_kickoff_at(schedule)
        if kickoff_at is not None and kickoff_at >= as_of:
            future_games.append((kickoff_at, schedule))
    if not future_games:
        return None

    first_kickoff_at, first_schedule = min(
        future_games,
        key=lambda item: (item[0], item[1].season, item[1].week or 0),
    )
    selected_season = int(first_schedule.season)
    selected_week = int(first_schedule.week)
    games_remaining = sum(
        1
        for _, schedule in future_games
        if schedule.season == selected_season and schedule.week == selected_week
    )
    return UpcomingScheduleContext(
        season=selected_season,
        week=selected_week,
        first_kickoff_at=first_kickoff_at,
        games_remaining=games_remaining,
    )
