from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import Base, IngestRun, RawNflSchedule
from backend.app.services.schedule_context import next_upcoming_schedule_context


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, future=True)()


def _schedule(
    *,
    game_id: str,
    week: int,
    gameday: str,
    gametime: str,
) -> RawNflSchedule:
    return RawNflSchedule(
        ingest_run_id="schedule-run",
        source_system="nflreadpy",
        season=2026,
        week=week,
        game_id=game_id,
        home_team="PHI",
        away_team="DAL",
        game_type="REG",
        kickoff=gametime,
        raw_row_json={"gameday": gameday, "gametime": gametime},
    )


def _seed_schedule(session: Session) -> None:
    session.add(
        IngestRun(
            ingest_run_id="schedule-run",
            source_system="nflreadpy",
            source_table="nfl_schedule",
            season=2026,
            status="completed",
        )
    )
    session.add_all(
        [
            _schedule(
                game_id="2026_01_NE_SEA",
                week=1,
                gameday="2026-09-09",
                gametime="20:20",
            ),
            _schedule(
                game_id="2026_01_DAL_PHI",
                week=1,
                gameday="2026-09-13",
                gametime="13:00",
            ),
            _schedule(
                game_id="2026_02_PHI_DAL",
                week=2,
                gameday="2026-09-20",
                gametime="13:00",
            ),
        ]
    )
    session.commit()


def test_next_upcoming_schedule_context_selects_earliest_future_week() -> None:
    session = _session()
    _seed_schedule(session)

    context = next_upcoming_schedule_context(
        session,
        as_of=datetime(2026, 8, 22, 12, 0, tzinfo=UTC),
    )

    assert context is not None
    assert (context.season, context.week) == (2026, 1)
    assert context.first_kickoff_at == datetime(2026, 9, 10, 0, 20, tzinfo=UTC)
    assert context.games_remaining == 2


def test_next_upcoming_schedule_context_keeps_week_until_its_last_game() -> None:
    session = _session()
    _seed_schedule(session)

    context = next_upcoming_schedule_context(
        session,
        as_of=datetime(2026, 9, 10, 1, 0, tzinfo=UTC),
    )

    assert context is not None
    assert (context.season, context.week) == (2026, 1)
    assert context.first_kickoff_at == datetime(2026, 9, 13, 17, 0, tzinfo=UTC)
    assert context.games_remaining == 1


def test_next_upcoming_schedule_context_advances_and_then_exhausts_schedule() -> None:
    session = _session()
    _seed_schedule(session)

    context = next_upcoming_schedule_context(
        session,
        as_of=datetime(2026, 9, 14, 0, 0, tzinfo=UTC),
    )
    exhausted = next_upcoming_schedule_context(
        session,
        as_of=datetime(2026, 9, 21, 0, 0, tzinfo=UTC),
    )

    assert context is not None
    assert (context.season, context.week) == (2026, 2)
    assert exhausted is None
