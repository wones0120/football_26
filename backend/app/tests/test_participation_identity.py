from __future__ import annotations

import pandas as pd
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import (
    Base,
    CuratedPlayerGameParticipation,
    IngestRun,
    PlayerAlias,
    RawNflSchedule,
    RawNflWeeklyRoster,
    UnresolvedPlayerQueue,
)
from backend.app.services.matching import create_player_master, upsert_alias
from backend.app.services.participation import ParticipationService
from backend.app.services.participation_identity import (
    apply_participation_identity_repairs,
    assess_participation_identities,
)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, future=True)()


def _add_ingest_run(session: Session, ingest_run_id: str = "run-1") -> IngestRun:
    run = IngestRun(
        ingest_run_id=ingest_run_id,
        source_system="nflreadpy",
        source_table="participation",
        status="completed",
    )
    session.add(run)
    session.flush()
    return run


def _add_queue_row(
    session: Session,
    *,
    unresolved_id: str,
    source_table: str,
    source_system: str,
    source_player_key: str | None,
    name: str,
    team: str,
    position: str,
    season: int = 2025,
    week: int = 1,
) -> None:
    session.add(
        UnresolvedPlayerQueue(
            unresolved_id=unresolved_id,
            ingest_run_id="run-1",
            source_system=source_system,
            source_table=source_table,
            source_player_key=source_player_key,
            season=season,
            week=week,
            raw_row_json={"player": name, "full_name": name},
            normalized_name=name.lower(),
            team=team,
            position=position,
            resolution_status="open",
        )
    )


def test_assessment_and_apply_resolve_native_and_exact_semantic_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    _add_ingest_run(session)
    registry_master = create_player_master(
        session,
        full_name="Registry Player",
        team="AAA",
        position="WR",
        player_master_id="registry-master",
    )
    roster_master = create_player_master(
        session,
        full_name="Roster Match",
        team="BBB",
        position="LB",
        player_master_id="roster-master",
    )
    upsert_alias(
        session,
        player_master_id=registry_master.player_master_id,
        source_system="nflreadpy",
        source_key="gsis-1",
        alias_name="Registry Player",
        team="AAA",
        position="WR",
        season=2025,
        week=1,
    )
    _add_queue_row(
        session,
        unresolved_id="snap-1",
        source_table="snap_counts",
        source_system="pfr",
        source_player_key="Pfr001",
        name="R. Player",
        team="AAA",
        position="WR",
    )
    _add_queue_row(
        session,
        unresolved_id="snap-2",
        source_table="snap_counts",
        source_system="pfr",
        source_player_key="Pfr001",
        name="R. Player",
        team="AAA",
        position="WR",
        week=2,
    )
    _add_queue_row(
        session,
        unresolved_id="roster-1",
        source_table="weekly_rosters",
        source_system="nflreadpy",
        source_player_key=None,
        name="Roster Match",
        team="BBB",
        position="LB",
    )
    session.commit()

    registry = pd.DataFrame(
        [{"pfr_id": "Pfr001", "gsis_id": "gsis-1", "display_name": "Registry Player"}]
    )
    assessment = assess_participation_identities(session, registry)

    assert assessment.open_rows_before == 3
    assert assessment.remaining_rows == 0
    assert assessment.conflicts == ()
    assert assessment.report()["decision_rows_by_reason"] == {
        "unique_name_team_position": 1,
        "unique_pfr_gsis_crosswalk": 2,
    }

    monkeypatch.setattr(
        ParticipationService,
        "rebuild",
        lambda self, *, season: {"participation_rows": season, "availability_rows": 0},
    )
    result = apply_participation_identity_repairs(
        session,
        assessment,
        registry_snapshot_id="snapshot-1",
    )

    assert result["queue_rows_resolved"] == 3
    assert result["open_rows_after"] == 0
    assert result["affected_seasons"] == [2025]
    pfr_alias = session.query(PlayerAlias).filter_by(
        source_system="pfr",
        source_key="Pfr001",
    ).one()
    assert pfr_alias.player_master_id == registry_master.player_master_id
    resolved_rows = session.query(UnresolvedPlayerQueue).all()
    assert {row.resolution_status for row in resolved_rows} == {"resolved"}
    assert all("registry_snapshot_id=snapshot-1" in (row.notes or "") for row in resolved_rows)
    assert session.get(UnresolvedPlayerQueue, "roster-1").resolved_player_master_id == (
        roster_master.player_master_id
    )


def test_assessment_quarantines_conflicting_native_identity_chains() -> None:
    session = _session()
    _add_ingest_run(session)
    pfr_master = create_player_master(
        session,
        full_name="PFR Player",
        team="AAA",
        position="WR",
        player_master_id="pfr-master",
    )
    gsis_master = create_player_master(
        session,
        full_name="GSIS Player",
        team="AAA",
        position="WR",
        player_master_id="gsis-master",
    )
    for source_system, source_key, master in (
        ("pfr", "PfrConflict", pfr_master),
        ("nflreadpy", "gsis-conflict", gsis_master),
    ):
        upsert_alias(
            session,
            player_master_id=master.player_master_id,
            source_system=source_system,
            source_key=source_key,
            alias_name=master.full_name,
            team="AAA",
            position="WR",
            season=2025,
            week=1,
        )
    _add_queue_row(
        session,
        unresolved_id="snap-conflict",
        source_table="snap_counts",
        source_system="pfr",
        source_player_key="PfrConflict",
        name="Conflict Player",
        team="AAA",
        position="WR",
    )
    session.commit()

    assessment = assess_participation_identities(
        session,
        pd.DataFrame([{"pfr_id": "PfrConflict", "gsis_id": "gsis-conflict"}]),
    )

    assert len(assessment.conflicts) == 1
    assert assessment.decisions == ()
    assert assessment.remaining_rows == 1
    with pytest.raises(RuntimeError, match="conflicts"):
        apply_participation_identity_repairs(
            session,
            assessment,
            registry_snapshot_id="snapshot-conflict",
        )
    assert session.get(UnresolvedPlayerQueue, "snap-conflict").resolution_status == "open"


def test_existing_pfr_alias_resolves_without_registry_crosswalk() -> None:
    session = _session()
    _add_ingest_run(session)
    master = create_player_master(
        session,
        full_name="Known Player",
        team="AAA",
        position="RB",
        player_master_id="known-master",
    )
    upsert_alias(
        session,
        player_master_id=master.player_master_id,
        source_system="pfr",
        source_key="PfrKnown",
        alias_name="Known Player",
        team="AAA",
        position="RB",
        season=2024,
        week=1,
    )
    _add_queue_row(
        session,
        unresolved_id="snap-known",
        source_table="snap_counts",
        source_system="pfr",
        source_player_key="PfrKnown",
        name="Known Player",
        team="AAA",
        position="RB",
    )
    session.commit()

    assessment = assess_participation_identities(
        session,
        pd.DataFrame(columns=["pfr_id", "gsis_id"]),
    )

    assert len(assessment.decisions) == 1
    assert assessment.decisions[0].reason == "existing_pfr_alias"
    assert assessment.remaining_rows == 0


def test_participation_rebuild_uses_only_unique_name_team_position_fallback() -> None:
    session = _session()
    _add_ingest_run(session)
    create_player_master(
        session,
        full_name="No Native Id",
        team="AAA",
        position="LB",
        player_master_id="semantic-master-1",
    )
    session.add_all(
        [
            RawNflSchedule(
                ingest_run_id="run-1",
                source_system="nflreadpy",
                season=2025,
                week=1,
                game_id="game-1",
                home_team="AAA",
                away_team="BBB",
                game_type="REG",
                raw_row_json={"game_type": "REG"},
            ),
            RawNflWeeklyRoster(
                ingest_run_id="run-1",
                source_system="nflreadpy",
                season=2025,
                week=1,
                game_type="REG",
                team="AAA",
                position="LB",
                roster_status="ACT",
                player_name="No Native Id",
                gsis_id=None,
                pfr_id=None,
                raw_row_json={"full_name": "No Native Id"},
            ),
        ]
    )
    session.commit()

    result = ParticipationService(session).rebuild(season=2025)
    assert result["participation_rows"] == 1
    assert session.query(CuratedPlayerGameParticipation).one().player_master_id == (
        "semantic-master-1"
    )

    create_player_master(
        session,
        full_name="No Native Id",
        team="AAA",
        position="LB",
        player_master_id="semantic-master-2",
    )
    session.commit()

    ambiguous_result = ParticipationService(session).rebuild(season=2025)
    assert ambiguous_result["participation_rows"] == 0
    assert session.query(CuratedPlayerGameParticipation).count() == 0
