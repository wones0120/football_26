from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import (
    Base,
    CuratedSalary,
    IngestRun,
    SourceSnapshot,
    SourceSnapshotIngestRun,
)
from backend.app.services.matching import create_player_master
from backend.app.services.source_capture import (
    SNAPSHOT_CONTRACT_ID,
    PostLockSnapshotError,
    SnapshotIntegrityError,
    SourceCaptureService,
    capture_nflreadpy_datasets,
    fetch_nflreadpy_dataset,
    verify_snapshot_artifact,
)


LICENSE = "Test fixture license"


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _salary_csv(path: Path, *, salary: int = 5500) -> None:
    pd.DataFrame(
        [
            {
                "ID": "dk-101",
                "Name": "Example Receiver",
                "TeamAbbrev": "BUF",
                "Position": "WR",
                "Roster Position": "WR/FLEX",
                "Salary": salary,
                "Game Info": "BUF@MIA 09/13/2026 01:00PM ET",
            }
        ]
    ).to_csv(path, index=False)


def test_capture_is_content_addressed_immutable_and_idempotent(tmp_path: Path) -> None:
    session = _session()
    source = tmp_path / "DKSalaries.csv"
    _salary_csv(source)
    observed_at = datetime(2026, 9, 13, 15, 0, tzinfo=UTC)
    lock_at = datetime(2026, 9, 13, 17, 0, tzinfo=UTC)
    service = SourceCaptureService(
        session,
        snapshot_root=tmp_path / "snapshots",
        clock=lambda: observed_at,
    )

    first = service.capture_file(
        source,
        source_system="draftkings",
        dataset="salary",
        season=2026,
        week=1,
        slate="sunday_main",
        source_license=LICENSE,
        slate_lock_at=lock_at,
        row_count=1,
        media_type="text/csv",
    )
    second = SourceCaptureService(
        session,
        snapshot_root=tmp_path / "snapshots",
        clock=lambda: datetime(2026, 9, 13, 16, 0, tzinfo=UTC),
    ).capture_file(
        source,
        source_system="draftkings",
        dataset="salary",
        season=2026,
        week=1,
        slate="sunday_main",
        source_license=LICENSE,
        slate_lock_at=lock_at,
        row_count=1,
        media_type="text/csv",
    )

    assert first.created is True
    assert first.pre_lock is True
    assert second.created is False
    assert second.snapshot.snapshot_id == first.snapshot.snapshot_id
    assert session.query(SourceSnapshot).count() == 1

    artifact = Path(first.snapshot.artifact_path)
    manifest_path = Path(first.snapshot.manifest_path)
    original_bytes = artifact.read_bytes()
    _salary_csv(source, salary=9900)

    assert artifact.read_bytes() == original_bytes
    assert hashlib.sha256(original_bytes).hexdigest() == first.snapshot.content_sha256
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["contract_id"] == SNAPSHOT_CONTRACT_ID
    assert manifest["snapshot_id"] == first.snapshot.snapshot_id
    assert manifest["observed_at"] == "2026-09-13T15:00:00Z"
    assert manifest["pre_lock"] is True
    verify_snapshot_artifact(first.snapshot)
    assert service.eligible_snapshots(
        cutoff_at=lock_at,
        source_system="draftkings",
        dataset="salary",
        season=2026,
        week=1,
        slate="sunday_main",
    ) == [first.snapshot]

    manifest["observed_at"] = "2026-09-13T18:00:00Z"
    manifest_path.chmod(0o644)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SnapshotIntegrityError):
        verify_snapshot_artifact(first.snapshot)


def test_draftkings_capture_ingests_preserved_copy_with_canonical_identity(
    tmp_path: Path,
) -> None:
    session = _session()
    master = create_player_master(
        session,
        full_name="Example Receiver",
        team="BUF",
        position="WR",
    )
    session.commit()
    source = tmp_path / "DKSalaries.csv"
    _salary_csv(source)
    service = SourceCaptureService(
        session,
        snapshot_root=tmp_path / "snapshots",
        clock=lambda: datetime(2026, 9, 13, 15, 0, tzinfo=UTC),
    )

    first = service.capture_and_ingest_draftkings_salary(
        source,
        season=2026,
        week=1,
        slate="sunday_main",
        slate_lock_at=datetime(2026, 9, 13, 17, 0, tzinfo=UTC),
        source_license=LICENSE,
    )
    second = service.capture_and_ingest_draftkings_salary(
        source,
        season=2026,
        week=1,
        slate="sunday_main",
        slate_lock_at=datetime(2026, 9, 13, 17, 0, tzinfo=UTC),
        source_license=LICENSE,
    )

    assert first.ingest.status == "completed"
    assert first.ingest.rows_curated == 1
    assert first.ingest.rows_unresolved == 0
    assert second.capture.created is False
    assert second.ingest.ingest_run_id == first.ingest.ingest_run_id
    assert session.query(IngestRun).count() == 1
    assert session.query(SourceSnapshotIngestRun).count() == 1
    salary = session.query(CuratedSalary).one()
    assert salary.player_master_id == master.player_master_id
    run = session.get(IngestRun, first.ingest.ingest_run_id)
    assert run is not None
    assert run.source_path == first.capture.snapshot.artifact_path
    assert run.source_checksum == first.capture.snapshot.content_sha256


def test_post_lock_draftkings_capture_is_preserved_but_not_ingested(
    tmp_path: Path,
) -> None:
    session = _session()
    source = tmp_path / "DKSalaries.csv"
    _salary_csv(source)
    cutoff_at = datetime(2026, 9, 13, 17, 0, tzinfo=UTC)
    service = SourceCaptureService(
        session,
        snapshot_root=tmp_path / "snapshots",
        clock=lambda: datetime(2026, 9, 13, 17, 1, tzinfo=UTC),
    )

    with pytest.raises(PostLockSnapshotError) as exc_info:
        service.capture_and_ingest_draftkings_salary(
            source,
            season=2026,
            week=1,
            slate="sunday_main",
            slate_lock_at=cutoff_at,
            source_license=LICENSE,
        )

    capture = exc_info.value.capture
    assert capture.pre_lock is False
    assert Path(capture.snapshot.artifact_path).is_file()
    assert session.query(SourceSnapshot).count() == 1
    assert session.query(IngestRun).count() == 0
    assert service.eligible_snapshots(
        cutoff_at=cutoff_at,
        source_system="draftkings",
        dataset="salary",
        season=2026,
        week=1,
        slate="sunday_main",
    ) == []


def test_nflreadpy_capture_filters_week_and_records_version(tmp_path: Path) -> None:
    session = _session()
    fake_nflreadpy = SimpleNamespace(
        __version__="test-version",
        load_injuries=lambda seasons: pd.DataFrame(
            [
                {"season": seasons[0], "week": 1, "full_name": "Player One"},
                {"season": seasons[0], "week": 2, "full_name": "Player Two"},
            ]
        ),
    )
    frame, version = fetch_nflreadpy_dataset(
        "injuries",
        season=2026,
        week=1,
        nfl_module=fake_nflreadpy,
    )
    assert version == "test-version"
    assert frame["full_name"].tolist() == ["Player One"]

    service = SourceCaptureService(
        session,
        snapshot_root=tmp_path / "snapshots",
        clock=lambda: datetime(2026, 9, 9, 16, 0, tzinfo=UTC),
    )
    captures = capture_nflreadpy_datasets(
        service,
        ["injuries"],
        season=2026,
        week=1,
        slate="sunday_main",
        slate_lock_at=datetime(2026, 9, 13, 17, 0, tzinfo=UTC),
        source_license=LICENSE,
        nfl_module=fake_nflreadpy,
    )

    assert len(captures) == 1
    snapshot = captures[0].snapshot
    assert snapshot.row_count == 1
    assert snapshot.metadata_json["nflreadpy_version"] == "test-version"
    captured_frame = pd.read_csv(snapshot.artifact_path)
    assert captured_frame["full_name"].tolist() == ["Player One"]
