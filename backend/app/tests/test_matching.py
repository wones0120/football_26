from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import Base, PlayerAlias
from backend.app.services.matching import (
    create_player_master,
    find_player_master_id,
    normalize_name,
    parse_opponent_from_game_info,
    upsert_alias,
)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()


def test_normalize_name() -> None:
    assert normalize_name("  DJ   Moore ") == "dj moore"
    assert normalize_name("D.J. Moore") == "d j moore"


def test_parse_opponent() -> None:
    assert parse_opponent_from_game_info("BUF@KC", "KC") == "BUF"
    assert parse_opponent_from_game_info("BUF@KC", "BUF") == "KC"


def test_find_by_source_key_alias() -> None:
    session = _session()
    player = create_player_master(session, full_name="Amon-Ra St. Brown", team="DET", position="WR")
    session.flush()
    upsert_alias(
        session=session,
        player_master_id=player.player_master_id,
        source_system="draftkings",
        source_key="12345",
        alias_name="Amon-Ra St. Brown",
        team="DET",
        position="WR",
        season=2025,
        week=1,
    )
    session.commit()
    found_id, reason = find_player_master_id(
        session=session,
        source_system="draftkings",
        source_key="12345",
        name="Amon-Ra St. Brown",
        team="DET",
        position="WR",
    )
    assert found_id == player.player_master_id
    assert reason == "alias_source_key"


def test_create_master_then_alias_with_fk_enforced() -> None:
    session = _session()
    player = create_player_master(session, full_name="Aaron Rodgers", team="PIT", position="QB")
    upsert_alias(
        session=session,
        player_master_id=player.player_master_id,
        source_system="nflreadpy",
        source_key="00-0023459",
        alias_name="Aaron Rodgers",
        team="PIT",
        position="QB",
        season=2025,
        week=None,
    )
    session.commit()


def test_upsert_alias_same_source_key_twice_same_transaction() -> None:
    session = _session()
    player = create_player_master(session, full_name="Tez Johnson", team="TB", position="WR")
    upsert_alias(
        session=session,
        player_master_id=player.player_master_id,
        source_system="nflreadpy",
        source_key="00-0040237",
        alias_name="Tez Johnson",
        team="TB",
        position="WR",
        season=2025,
        week=None,
    )
    upsert_alias(
        session=session,
        player_master_id=player.player_master_id,
        source_system="nflreadpy",
        source_key="00-0040237",
        alias_name="Tez J.",
        team="TB",
        position="WR",
        season=2025,
        week=None,
    )
    session.commit()

    aliases = session.query(PlayerAlias).filter_by(
        source_system="nflreadpy",
        source_key="00-0040237",
    ).all()
    assert len(aliases) == 1
    assert aliases[0].alias_name == "Tez J."
