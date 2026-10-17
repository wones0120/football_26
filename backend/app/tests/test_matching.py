from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import Base, PlayerAlias
from backend.app.services.matching import (
    create_player_master,
    find_player_master_id,
    normalize_name,
    normalize_position,
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


def test_normalize_position_canonicalizes_team_defense_variants() -> None:
    for position in ("D", "DEF", "Defense", "DST", "D/ST"):
        assert normalize_position(position) == "DST"
    assert normalize_position("RB/FLEX") == "RB"


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


def test_master_fallback_requires_exact_name_team_and_position() -> None:
    session = _session()
    receiver = create_player_master(
        session,
        full_name="Shared Player",
        team="BUF",
        position="WR",
    )
    session.commit()

    found_id, reason = find_player_master_id(
        session=session,
        source_system="draftkings",
        source_key="new-source-key",
        name="Shared Player",
        team="BUF",
        position="WR",
    )
    wrong_position_id, wrong_position_reason = find_player_master_id(
        session=session,
        source_system="draftkings",
        source_key="other-source-key",
        name="Shared Player",
        team="BUF",
        position="RB",
    )
    wrong_team_id, wrong_team_reason = find_player_master_id(
        session=session,
        source_system="draftkings",
        source_key="third-source-key",
        name="Shared Player",
        team="MIA",
        position="WR",
    )

    assert found_id == receiver.player_master_id
    assert reason == "master_name_team_position"
    assert wrong_position_id is None
    assert wrong_position_reason == "unresolved"
    assert wrong_team_id is None
    assert wrong_team_reason == "unresolved"


def test_same_source_exact_alias_allows_multiple_keys_for_one_player() -> None:
    session = _session()
    player = create_player_master(session, full_name="Traded Player", team="OLD", position="WR")
    for source_key in ("old-slate", "new-slate"):
        upsert_alias(
            session=session,
            player_master_id=player.player_master_id,
            source_system="fanduel",
            source_key=source_key,
            alias_name="Traded Player",
            team="NEW",
            position="WR",
            season=2026,
            week=2,
        )
    session.commit()

    found_id, reason = find_player_master_id(
        session=session,
        source_system="fanduel",
        source_key="third-slate",
        name="Traded Player",
        team="NEW",
        position="WR",
    )

    assert found_id == player.player_master_id
    assert reason == "alias_name_team_position"


def test_cross_source_exact_alias_resolves_traded_player() -> None:
    session = _session()
    player = create_player_master(session, full_name="Traded Player", team="OLD", position="WR")
    upsert_alias(
        session=session,
        player_master_id=player.player_master_id,
        source_system="draftkings",
        source_key="dk-current",
        alias_name="Traded Player",
        team="NEW",
        position="WR",
        season=2026,
        week=2,
    )
    session.commit()

    found_id, reason = find_player_master_id(
        session=session,
        source_system="fanduel",
        source_key="fd-current",
        name="Traded Player",
        team="NEW",
        position="WR",
    )

    assert found_id == player.player_master_id
    assert reason == "alias_cross_source_name_team_position"


def test_cross_source_exact_alias_refuses_ambiguous_identity() -> None:
    session = _session()
    first = create_player_master(session, full_name="Shared Player", team="OLD", position="WR")
    second = create_player_master(session, full_name="Shared Player", team="OTHER", position="WR")
    for source_system, source_key, player_id in (
        ("draftkings", "dk-key", first.player_master_id),
        ("nflreadpy", "nfl-key", second.player_master_id),
    ):
        upsert_alias(
            session=session,
            player_master_id=player_id,
            source_system=source_system,
            source_key=source_key,
            alias_name="Shared Player",
            team="NEW",
            position="WR",
            season=2026,
            week=2,
        )
    session.commit()

    found_id, reason = find_player_master_id(
        session=session,
        source_system="fanduel",
        source_key="fd-key",
        name="Shared Player",
        team="NEW",
        position="WR",
    )

    assert found_id is None
    assert reason == "ambiguous_cross_source_name_team_position"


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


def test_dst_matches_unique_source_team_alias_without_using_name() -> None:
    session = _session()
    defense = create_player_master(session, full_name="Bills", team="BUF", position="DST")
    upsert_alias(
        session=session,
        player_master_id=defense.player_master_id,
        source_system="draftkings",
        source_key="buf-week-1",
        alias_name="Buffalo Bills",
        team="BUF",
        position="DST",
        season=2025,
        week=1,
    )
    session.commit()

    found_id, reason = find_player_master_id(
        session=session,
        source_system="draftkings",
        source_key="buf-week-2",
        name="Completely Different Defense Label",
        team="BUF",
        position="D/ST",
    )

    assert found_id == defense.player_master_id
    assert reason == "alias_dst_team"


def test_dst_matches_unique_team_master_without_using_name() -> None:
    session = _session()
    defense = create_player_master(session, full_name="Bills", team="BUF", position="DST")
    session.commit()

    found_id, reason = find_player_master_id(
        session=session,
        source_system="fanduel",
        source_key="fd-buf-new",
        name="Buffalo Defense",
        team="BUF",
        position="DEF",
    )

    assert found_id == defense.player_master_id
    assert reason == "master_dst_team"


def test_dst_never_falls_back_to_player_name_matching() -> None:
    session = _session()
    create_player_master(session, full_name="Bills", team="BUF", position="DST")
    session.commit()

    wrong_team_id, wrong_team_reason = find_player_master_id(
        session=session,
        source_system="draftkings",
        source_key="mia-defense",
        name="Bills",
        team="MIA",
        position="DST",
    )
    missing_team_id, missing_team_reason = find_player_master_id(
        session=session,
        source_system="draftkings",
        source_key="unknown-defense",
        name="Bills",
        team=None,
        position="DST",
    )

    assert wrong_team_id is None
    assert wrong_team_reason == "unresolved_dst_team"
    assert missing_team_id is None
    assert missing_team_reason == "dst_team_required"


def test_dst_ambiguous_team_masters_remain_unresolved() -> None:
    session = _session()
    create_player_master(session, full_name="Titans", team="TEN", position="DST")
    create_player_master(session, full_name="Tennessee Titans", team="TEN", position="DST")
    session.commit()

    found_id, reason = find_player_master_id(
        session=session,
        source_system="draftkings",
        source_key="ten-new",
        name="Titans",
        team="TEN",
        position="DST",
    )

    assert found_id is None
    assert reason == "ambiguous_dst_team_master"


def test_dst_prefers_canonical_master_over_legacy_position_variant() -> None:
    session = _session()
    canonical = create_player_master(session, full_name="Titans", team="TEN", position="DST")
    legacy = create_player_master(
        session,
        full_name="Tennessee Titans",
        team="TEN",
        position="DST",
    )
    legacy.position = "D"
    session.add(legacy)
    session.commit()

    found_id, reason = find_player_master_id(
        session=session,
        source_system="draftkings",
        source_key="ten-new",
        name="Titans",
        team="TEN",
        position="DST",
    )

    assert found_id == canonical.player_master_id
    assert reason == "master_dst_team"


def test_normalized_roster_alias_beats_duplicate_master_and_survives_next_source_id():
    session = _session()
    canonical = create_player_master(session, "A.J. Example", "MIA", "WR")
    duplicate = create_player_master(session, "AJ Example", "MIA", "WR")
    upsert_alias(session, canonical.player_master_id, "nflreadpy", "native-gsis", "A.J. Example", "MIA", "WR", 2026, 5)
    session.commit()
    for key in ("salary-week-five", "salary-week-six"):
        pid, reason = find_player_master_id(session, "draftkings", key, "AJ Example", "MIA", "WR")
        assert pid == canonical.player_master_id
        assert pid != duplicate.player_master_id
        upsert_alias(session, pid, "draftkings", key, "AJ Example", "MIA", "WR", 2026, 5)
        session.commit()
        assert find_player_master_id(session, "draftkings", key, "AJ Example", "MIA", "WR")[1] == "alias_source_key"


def test_accented_alias_uses_current_sourced_team_and_preserves_football_position():
    session = _session()
    canonical = create_player_master(session, "Audric Example", "NO", "RB")
    upsert_alias(session, canonical.player_master_id, "nflreadpy", "native", "Audric Examplé", "MIN", "RB", 2026, 5)
    session.commit()
    assert find_player_master_id(session, "draftkings", "new", "Audric Example", "MIN", "RB")[0] == canonical.player_master_id
    specialist = create_player_master(session, "Specialist Example", "NO", "LS")
    upsert_alias(session, specialist.player_master_id, "draftkings", "verified-native", "Specialist Example", "NO", "TE", 2026, 5)
    session.commit()
    assert find_player_master_id(session, "draftkings", "verified-native", "Specialist Example", "NO", "TE")[0] == specialist.player_master_id
    assert specialist.position == "LS"


def test_conflicting_vendor_alias_needs_corroboration_from_two_roster_sources():
    session = _session()
    native = create_player_master(session, "Roster Player", "ARI", "RB")
    duplicate = create_player_master(session, "Roster Player", "ARI", "RB")
    for source, key, pid in [("draftkings", "old", duplicate.player_master_id),
                             ("draftkings", "recent", native.player_master_id),
                             ("nflreadpy", "native", native.player_master_id)]:
        upsert_alias(session, pid, source, key, "Roster Player", "ARI", "RB", 2026, 5)
    session.commit()
    assert find_player_master_id(session, "draftkings", "next", "Roster Player", "ARI", "RB")[0] is None
    upsert_alias(session, native.player_master_id, "nfl_official", "profile", "Roster Player", "ARI", "RB", 2026, 5)
    session.commit()
    assert find_player_master_id(session, "draftkings", "next", "Roster Player", "ARI", "RB")[0] == native.player_master_id


def test_nickname_vendor_conflict_requires_unique_roster_corroboration():
    session = _session()
    canonical = create_player_master(session, "Marquise Brown", "KC", "WR")
    duplicate = create_player_master(session, "Hollywood Brown", "KC", "WR")
    for key, pid in (("old-salary", duplicate.player_master_id),
                     ("recent-salary", canonical.player_master_id)):
        upsert_alias(session, pid, "draftkings", key, "Hollywood Brown", "PHI", "WR", 2026, 5)
    upsert_alias(session, canonical.player_master_id, "nflreadpy", "gsis", "Marquise Brown", "PHI", "WR", 2026, 5)
    session.commit()

    assert find_player_master_id(session, "draftkings", "next-salary", "Hollywood Brown", "PHI", "WR")[0] is None
    upsert_alias(session, canonical.player_master_id, "pfr", "pfr-id", "Marquise Brown", "PHI", "WR", 2026, 5)
    session.commit()
    pid, reason = find_player_master_id(session, "draftkings", "next-salary", "Hollywood Brown", "PHI", "WR")
    assert pid == canonical.player_master_id
    assert reason == "source_backed_alias_conflict_resolved"
    assert canonical.primary_team == "KC"
    assert duplicate.full_name == "Hollywood Brown"

    upsert_alias(session, pid, "draftkings", "next-salary", "Hollywood Brown", "PHI", "WR", 2026, 6)
    session.commit()
    assert find_player_master_id(session, "draftkings", "next-salary", "Hollywood Brown", "PHI", "WR") == (pid, "alias_source_key")

    upsert_alias(session, duplicate.player_master_id, "nfl_official", "conflicting-roster", "Hollywood Brown", "PHI", "WR", 2026, 6)
    session.commit()
    assert find_player_master_id(session, "draftkings", "future-salary", "Hollywood Brown", "PHI", "WR")[0] is None


def test_nickname_alias_requires_matching_team_and_position():
    session = _session()
    canonical = create_player_master(session, "Marquise Brown", "KC", "WR")
    upsert_alias(session, canonical.player_master_id, "nflreadpy", "gsis", "Marquise Brown", "PHI", "WR", 2026, 6)
    session.commit()

    assert find_player_master_id(session, "draftkings", "new", "Hollywood Brown", "PHI", "WR") == (canonical.player_master_id, "alias_normalized_name_team_position")
    for name, team, position in (("Hollywood Brown", "BUF", "WR"),
                                 ("Hollywood Brown", "PHI", "RB"),
                                 ("Hollywood Brown", None, "WR"),
                                 ("Hollywood Brown", "PHI", None),
                                 ("Other Hollywood Brown", "PHI", "WR")):
        assert find_player_master_id(session, "draftkings", "new", name, team, position)[0] is None
