from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import (
    Base,
    CuratedInjury,
    CuratedSalary,
    IngestRun,
    PlayerAlias,
    RawSalaryRow,
    UnresolvedPlayerQueue,
)
from backend.app.schemas import InjuryIngestRequest, SalaryIngestRequest
from backend.app.services.ingest import (
    IngestService,
    _synthetic_source_key,
    _validate_ingest_dataframe,
)
from backend.app.services.matching import create_player_master, utcnow_naive


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


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def _salary_request(path: Path) -> SalaryIngestRequest:
    return SalaryIngestRequest(
        source_system="draftkings",
        season=2025,
        week=1,
        slate="main",
        path=str(path),
    )


def test_invalid_salary_file_preserves_existing_slice(tmp_path: Path) -> None:
    session = _session()
    service = IngestService(session)
    valid_path = tmp_path / "valid.csv"
    _write_csv(
        valid_path,
        [
            {
                "ID": "101",
                "Name": "Example Receiver",
                "TeamAbbrev": "BUF",
                "Position": "WR",
                "Salary": 5500,
            }
        ],
    )

    completed = service.ingest_salaries(_salary_request(valid_path))

    assert completed.status == "completed"
    assert completed.rows_raw == 1
    assert completed.rows_curated == 1
    assert session.query(CuratedSalary).count() == 1

    invalid_path = tmp_path / "missing_salary.csv"
    _write_csv(
        invalid_path,
        [
            {
                "ID": "202",
                "Name": "Replacement Receiver",
                "TeamAbbrev": "MIA",
                "Position": "WR",
            }
        ],
    )

    failed = service.ingest_salaries(_salary_request(invalid_path))

    assert failed.status == "failed"
    assert failed.rows_raw == 1
    assert failed.rows_curated == 0
    assert "missing required columns: salary" in (failed.error_message or "")
    assert session.query(CuratedSalary).count() == 1
    assert session.query(CuratedSalary).one().source_player_key == "101"
    assert session.query(RawSalaryRow).count() == 1


def test_salary_validation_reports_types_and_duplicate_identities(tmp_path: Path) -> None:
    session = _session()
    path = tmp_path / "invalid.csv"
    _write_csv(
        path,
        [
            {
                "ID": "301",
                "Name": "Example Runner",
                "TeamAbbrev": "DET",
                "Position": "RB",
                "Salary": "not-a-number",
            },
            {
                "ID": "301",
                "Name": "Example Runner",
                "TeamAbbrev": "",
                "Position": "RB",
                "Salary": 6200,
            },
        ],
    )

    failed = IngestService(session).ingest_salaries(_salary_request(path))

    assert failed.status == "failed"
    assert failed.rows_raw == 2
    assert failed.rows_curated == 0
    assert "invalid salary values" in (failed.error_message or "")
    assert "CSV rows 2" in (failed.error_message or "")
    assert "blank team values at CSV rows 3" in (failed.error_message or "")
    assert "duplicate player identities at CSV rows 2, 3" in (failed.error_message or "")
    assert session.query(RawSalaryRow).count() == 0


def test_fanduel_injury_validation_uses_semantic_identity_without_id(tmp_path: Path) -> None:
    session = _session()
    path = tmp_path / "injuries.csv"
    _write_csv(
        path,
        [
            {
                "Nickname": "Example Quarterback",
                "Team": "KC",
                "Position": "QB",
                "Injury Indicator": "Q",
                "Injury Details": "Ankle",
            },
            {
                "Nickname": "Healthy Receiver",
                "Team": "KC",
                "Position": "WR",
                "Injury Indicator": None,
                "Injury Details": None,
            },
        ],
    )
    request = InjuryIngestRequest(
        source_system="fanduel",
        season=2025,
        week=1,
        slate="main",
        path=str(path),
    )

    completed = IngestService(session).ingest_injuries(request)

    assert completed.status == "completed"
    assert completed.rows_raw == 2
    injuries = session.query(CuratedInjury).order_by(CuratedInjury.curated_injury_id).all()
    assert [injury.injury_status for injury in injuries] == ["Q", None]
    assert injuries[0].source_player_key == _synthetic_source_key(
        "Example Quarterback",
        "KC",
        "QB",
    )


def test_synthetic_source_key_is_stable_and_uses_full_semantic_identity() -> None:
    original = _synthetic_source_key("Example Quarterback", "KC", "QB")

    assert original == _synthetic_source_key("  Example Quarterback ", "KC", "QB")
    assert original != _synthetic_source_key("Example Quarterback", "LV", "QB")
    assert original != _synthetic_source_key("Example Quarterback", "KC", "WR")


def test_fanduel_salary_schema_aliases_are_supported() -> None:
    raw_df = pd.DataFrame(
        [
            {
                "Id": "fd-101",
                "Nickname": "Example Receiver",
                "Team": "BUF",
                "Position": "WR",
                "Salary": 6500,
            }
        ]
    )

    _validate_ingest_dataframe("fanduel", "salary", raw_df)


def test_draftkings_injury_schema_aliases_are_supported() -> None:
    raw_df = pd.DataFrame(
        [
            {
                "Name": "Example Receiver",
                "TeamAbbrev": "BUF",
                "Position": "WR",
                "Injury Indicator": "Q",
            }
        ]
    )

    _validate_ingest_dataframe("draftkings", "injury", raw_df)


def test_injury_validation_rejects_duplicate_semantic_identities(tmp_path: Path) -> None:
    session = _session()
    path = tmp_path / "duplicate_injuries.csv"
    _write_csv(
        path,
        [
            {
                "Nickname": "Example Tight End",
                "Team": "SF",
                "Position": "TE",
                "Injury Indicator": "Q",
            },
            {
                "Nickname": "Example Tight End",
                "Team": "SF",
                "Position": "TE",
                "Injury Indicator": "OUT",
            },
        ],
    )
    request = InjuryIngestRequest(
        source_system="fanduel",
        season=2025,
        week=1,
        slate="main",
        path=str(path),
    )

    failed = IngestService(session).ingest_injuries(request)

    assert failed.status == "failed"
    assert failed.rows_raw == 2
    assert "duplicate player identities at CSV rows 2, 3" in (failed.error_message or "")
    assert session.query(CuratedInjury).count() == 0


def test_injury_validation_requires_status_column(tmp_path: Path) -> None:
    session = _session()
    path = tmp_path / "missing_status.csv"
    _write_csv(
        path,
        [
            {
                "Nickname": "Example Defender",
                "Team": "BAL",
                "Position": "LB",
            }
        ],
    )
    request = InjuryIngestRequest(
        source_system="fanduel",
        season=2025,
        week=1,
        slate="main",
        path=str(path),
    )

    failed = IngestService(session).ingest_injuries(request)

    assert failed.status == "failed"
    assert "missing required columns: injury_status" in (failed.error_message or "")
    assert session.query(CuratedInjury).count() == 0


def test_salary_validation_rejects_empty_file(tmp_path: Path) -> None:
    session = _session()
    path = tmp_path / "empty.csv"
    pd.DataFrame(
        columns=["ID", "Name", "TeamAbbrev", "Position", "Salary"]
    ).to_csv(path, index=False)

    failed = IngestService(session).ingest_salaries(_salary_request(path))

    assert failed.status == "failed"
    assert failed.rows_raw == 0
    assert "file contains no data rows" in (failed.error_message or "")
    assert session.query(RawSalaryRow).count() == 0


def test_salary_ingest_resolves_dst_by_team_and_persists_source_alias(tmp_path: Path) -> None:
    session = _session()
    defense = create_player_master(session, full_name="Bills", team="BUF", position="DST")
    session.commit()
    path = tmp_path / "fanduel_dst.csv"
    _write_csv(
        path,
        [
            {
                "Id": "fd-buf-defense",
                "Nickname": "Buffalo Defense",
                "Team": "BUF",
                "Position": "D",
                "Salary": 4200,
            }
        ],
    )
    request = SalaryIngestRequest(
        source_system="fanduel",
        season=2025,
        week=1,
        slate="main",
        path=str(path),
    )

    completed = IngestService(session).ingest_salaries(request)

    assert completed.status == "completed"
    assert completed.rows_unresolved == 0
    salary = session.query(CuratedSalary).one()
    assert salary.player_master_id == defense.player_master_id
    assert salary.position == "DST"
    alias = session.query(PlayerAlias).one()
    assert alias.player_master_id == defense.player_master_id
    assert alias.team == "BUF"
    assert alias.position == "DST"


def test_unresolved_triage_groups_open_and_recent_rows() -> None:
    session = _session()
    now = utcnow_naive()
    run = IngestRun(
        ingest_run_id="triage-run",
        source_system="draftkings",
        source_table="salary",
        season=2025,
        week=1,
        slate="main",
        status="completed",
        started_at=now - timedelta(days=3),
        completed_at=now - timedelta(days=3),
    )
    session.add(run)

    def unresolved(
        unresolved_id: str,
        *,
        source_system: str,
        source_table: str,
        season: int,
        week: int,
        slate: str,
        created_at_offset: timedelta,
        resolution_status: str = "open",
    ) -> UnresolvedPlayerQueue:
        return UnresolvedPlayerQueue(
            unresolved_id=unresolved_id,
            ingest_run_id=run.ingest_run_id,
            source_system=source_system,
            source_table=source_table,
            source_player_key=unresolved_id,
            season=season,
            week=week,
            slate=slate,
            raw_row_json={"Name": unresolved_id},
            normalized_name=unresolved_id,
            team="BUF",
            position="WR",
            resolution_status=resolution_status,
            created_at=now - created_at_offset,
        )

    session.add_all(
        [
            unresolved(
                "dk-new",
                source_system="draftkings",
                source_table="salary",
                season=2025,
                week=1,
                slate="main",
                created_at_offset=timedelta(hours=1),
            ),
            unresolved(
                "dk-old",
                source_system="draftkings",
                source_table="salary",
                season=2025,
                week=1,
                slate="main",
                created_at_offset=timedelta(hours=48),
            ),
            unresolved(
                "fd-new",
                source_system="fanduel",
                source_table="injury",
                season=2024,
                week=17,
                slate="sunday_main",
                created_at_offset=timedelta(minutes=30),
            ),
            unresolved(
                "resolved-new",
                source_system="draftkings",
                source_table="salary",
                season=2025,
                week=2,
                slate="main",
                created_at_offset=timedelta(minutes=15),
                resolution_status="resolved",
            ),
        ]
    )
    session.commit()

    report = IngestService(session).unresolved_triage(lookback_hours=24)

    assert report.open_total == 3
    assert report.new_total == 2
    assert report.groups_returned == 2
    assert [
        (row.source_system, row.source_table, row.season, row.week, row.slate)
        for row in report.rows
    ] == [
        ("draftkings", "salary", 2025, 1, "main"),
        ("fanduel", "injury", 2024, 17, "sunday_main"),
    ]
    assert [(row.open_count, row.new_count) for row in report.rows] == [(2, 1), (1, 1)]

    draftkings_report = IngestService(session).unresolved_triage(
        lookback_hours=24,
        source_system="draftkings",
    )
    assert draftkings_report.open_total == 2
    assert draftkings_report.new_total == 1
    assert draftkings_report.groups_returned == 1
