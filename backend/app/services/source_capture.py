"""Prospective, content-addressed source capture and ingest lineage."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import IngestRun, SourceSnapshot, SourceSnapshotIngestRun
from ..product_services.point_in_time import snapshot_visible_at_cutoff
from ..schemas import IngestResultResponse, SalaryIngestRequest
from .ingest import IngestService


SNAPSHOT_CONTRACT_ID = "prospective_source_snapshot_v1"
SNAPSHOT_UUID_NAMESPACE = uuid.UUID("bdf6c542-738d-4c36-8b82-6b46c899f2e6")
REPO_ROOT = Path(__file__).resolve().parents[3]
SAFE_COMPONENT_RE = re.compile(r"[^a-zA-Z0-9._-]+")
NFLREADPY_DATASETS = (
    "schedules",
    "weekly_rosters",
    "injuries",
    "snap_counts",
)
NFLREADPY_LOADERS = {
    "schedules": "load_schedules",
    "weekly_rosters": "load_rosters_weekly",
    "injuries": "load_injuries",
    "snap_counts": "load_snap_counts",
}


class SnapshotIntegrityError(RuntimeError):
    """An immutable artifact or manifest no longer matches its recorded digest."""


class PostLockSnapshotError(RuntimeError):
    """A captured artifact is valid evidence but cannot enter the pre-lock pipeline."""

    def __init__(self, capture: SnapshotCaptureResult) -> None:
        self.capture = capture
        super().__init__(
            f"Snapshot {capture.snapshot.snapshot_id} was observed after slate lock and was not ingested"
        )


@dataclass(frozen=True)
class SnapshotCaptureResult:
    snapshot: SourceSnapshot
    created: bool
    pre_lock: bool | None


@dataclass(frozen=True)
class DraftKingsCaptureIngestResult:
    capture: SnapshotCaptureResult
    ingest: IngestResultResponse


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset")
    return value.astimezone(UTC)


def _optional_aware_utc(value: datetime | None, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _aware_utc(value, field_name=field_name)


def _stored_utc(value: datetime | None) -> datetime | None:
    """Normalize DB timestamps; SQLite drops timezone metadata in tests/local use."""
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _aware_utc(value, field_name="timestamp").isoformat().replace("+00:00", "Z")


def _stored_iso(value: datetime | None) -> str | None:
    return _iso(_stored_utc(value))


def _safe_component(value: str | None, fallback: str) -> str:
    cleaned = SAFE_COMPONENT_RE.sub("_", (value or "").strip()).strip("._-")
    return cleaned[:96] or fallback


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            byte_count += len(chunk)
    return digest.hexdigest(), byte_count


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _snapshot_id(
    *,
    source_system: str,
    dataset: str,
    season: int,
    week: int | None,
    slate: str | None,
    content_sha256: str,
) -> str:
    identity = "|".join(
        (
            source_system,
            dataset,
            str(season),
            str(week or ""),
            slate or "",
            content_sha256,
        )
    )
    return str(uuid.uuid5(SNAPSHOT_UUID_NAMESPACE, identity))


def _ingest_run_id(snapshot_id: str) -> str:
    return str(uuid.uuid5(SNAPSHOT_UUID_NAMESPACE, f"ingest|{snapshot_id}"))


def _resolve_root(root: str | Path | None) -> Path:
    configured = Path(root or get_settings().source_snapshot_root).expanduser()
    if not configured.is_absolute():
        configured = REPO_ROOT / configured
    return configured.resolve()


def _write_new_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        path.chmod(0o444)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise SnapshotIntegrityError(
                f"Immutable snapshot path already exists with different content: {path}"
            ) from None


def _copy_new_file(source: Path, target: Path, expected_sha256: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source.open("rb") as source_handle, target.open("xb") as target_handle:
            while chunk := source_handle.read(1024 * 1024):
                target_handle.write(chunk)
            target_handle.flush()
            os.fsync(target_handle.fileno())
        target.chmod(0o444)
    except FileExistsError:
        pass
    actual_sha256, _byte_count = _sha256_file(target)
    if actual_sha256 != expected_sha256:
        raise SnapshotIntegrityError(
            f"Immutable artifact checksum mismatch at {target}: "
            f"expected {expected_sha256}, received {actual_sha256}"
        )


def _csv_row_count(path: Path) -> int | None:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return max(sum(1 for _row in csv.reader(handle)) - 1, 0)
    except (OSError, UnicodeError, csv.Error):
        return None


def snapshot_pre_lock(snapshot: SourceSnapshot) -> bool | None:
    if snapshot.slate_lock_at is None:
        return None
    return snapshot_visible_at_cutoff(snapshot.observed_at, snapshot.slate_lock_at)


def verify_snapshot_artifact(snapshot: SourceSnapshot) -> None:
    artifact_path = Path(snapshot.artifact_path)
    manifest_path = Path(snapshot.manifest_path)
    if not artifact_path.is_file():
        raise SnapshotIntegrityError(f"Snapshot artifact is missing: {artifact_path}")
    actual_sha256, byte_count = _sha256_file(artifact_path)
    if actual_sha256 != snapshot.content_sha256 or byte_count != snapshot.byte_count:
        raise SnapshotIntegrityError(
            f"Snapshot artifact no longer matches recorded evidence: {artifact_path}"
        )
    if not manifest_path.is_file():
        raise SnapshotIntegrityError(f"Snapshot manifest is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotIntegrityError(f"Snapshot manifest is invalid: {manifest_path}") from exc
    expected_manifest_values = {
        "contract_id": SNAPSHOT_CONTRACT_ID,
        "snapshot_id": snapshot.snapshot_id,
        "source_system": snapshot.source_system,
        "dataset": snapshot.dataset,
        "season": snapshot.season,
        "week": snapshot.week,
        "slate": snapshot.slate,
        "observed_at": _stored_iso(snapshot.observed_at),
        "effective_at": _stored_iso(snapshot.effective_at),
        "captured_at": _stored_iso(snapshot.captured_at),
        "slate_lock_at": _stored_iso(snapshot.slate_lock_at),
        "observation_basis": snapshot.observation_basis,
        "pre_lock": snapshot_pre_lock(snapshot),
        "content_sha256": snapshot.content_sha256,
        "byte_count": snapshot.byte_count,
        "row_count": snapshot.row_count,
        "media_type": snapshot.media_type,
        "original_path": snapshot.original_path,
        "source_uri": snapshot.source_uri,
        "source_license": snapshot.source_license,
        "metadata": snapshot.metadata_json,
    }
    if any(manifest.get(key) != value for key, value in expected_manifest_values.items()):
        raise SnapshotIntegrityError(
            f"Snapshot manifest no longer matches recorded evidence: {manifest_path}"
        )
    manifest_artifact = Path(str(manifest.get("artifact_path") or ""))
    manifest_manifest = Path(str(manifest.get("manifest_path") or ""))
    if (
        manifest_artifact.name != artifact_path.name
        or snapshot.snapshot_id not in manifest_artifact.parts
        or manifest_manifest.name != manifest_path.name
        or snapshot.snapshot_id not in manifest_manifest.parts
    ):
        raise SnapshotIntegrityError(
            f"Snapshot manifest paths no longer match recorded evidence: {manifest_path}"
        )


class SourceCaptureService:
    def __init__(
        self,
        session: Session,
        *,
        snapshot_root: str | Path | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.session = session
        self.snapshot_root = _resolve_root(snapshot_root)
        self.clock = clock

    def capture_file(
        self,
        path: str | Path,
        *,
        source_system: str,
        dataset: str,
        season: int,
        week: int | None,
        slate: str | None,
        source_license: str,
        source_uri: str | None = None,
        effective_at: datetime | None = None,
        slate_lock_at: datetime | None = None,
        observation_basis: str = "capture_clock",
        row_count: int | None = None,
        media_type: str = "application/octet-stream",
        metadata: dict[str, Any] | None = None,
    ) -> SnapshotCaptureResult:
        source_path = Path(path).expanduser().resolve()
        if not source_path.is_file():
            raise ValueError(f"Source file not found: {source_path}")
        content_sha256, byte_count = _sha256_file(source_path)
        return self._capture(
            payload_path=source_path,
            payload=None,
            artifact_name=source_path.name,
            source_system=source_system,
            dataset=dataset,
            season=season,
            week=week,
            slate=slate,
            source_license=source_license,
            source_uri=source_uri,
            effective_at=effective_at,
            slate_lock_at=slate_lock_at,
            observation_basis=observation_basis,
            row_count=row_count,
            media_type=media_type,
            metadata=metadata,
            original_path=str(source_path),
            content_sha256=content_sha256,
            byte_count=byte_count,
        )

    def capture_dataframe(
        self,
        frame: pd.DataFrame,
        *,
        artifact_name: str,
        source_system: str,
        dataset: str,
        season: int,
        week: int | None,
        slate: str | None,
        source_license: str,
        source_uri: str | None = None,
        effective_at: datetime | None = None,
        slate_lock_at: datetime | None = None,
        observation_basis: str = "capture_clock",
        metadata: dict[str, Any] | None = None,
    ) -> SnapshotCaptureResult:
        buffer = io.StringIO(newline="")
        frame.to_csv(buffer, index=False, lineterminator="\n")
        payload = buffer.getvalue().encode("utf-8")
        return self._capture(
            payload_path=None,
            payload=payload,
            artifact_name=artifact_name,
            source_system=source_system,
            dataset=dataset,
            season=season,
            week=week,
            slate=slate,
            source_license=source_license,
            source_uri=source_uri,
            effective_at=effective_at,
            slate_lock_at=slate_lock_at,
            observation_basis=observation_basis,
            row_count=len(frame),
            media_type="text/csv",
            metadata=metadata,
            original_path=None,
            content_sha256=_sha256_bytes(payload),
            byte_count=len(payload),
        )

    def _capture(
        self,
        *,
        payload_path: Path | None,
        payload: bytes | None,
        artifact_name: str,
        source_system: str,
        dataset: str,
        season: int,
        week: int | None,
        slate: str | None,
        source_license: str,
        source_uri: str | None,
        effective_at: datetime | None,
        slate_lock_at: datetime | None,
        observation_basis: str,
        row_count: int | None,
        media_type: str,
        metadata: dict[str, Any] | None,
        original_path: str | None,
        content_sha256: str,
        byte_count: int,
    ) -> SnapshotCaptureResult:
        source_system = source_system.strip().lower()
        dataset = dataset.strip().lower()
        slate = slate.strip().lower() if slate else None
        source_license = source_license.strip()
        observation_basis = observation_basis.strip().lower()
        if not source_system or not dataset:
            raise ValueError("source_system and dataset are required")
        if season < 2000 or week is not None and not 1 <= week <= 25:
            raise ValueError("season/week scope is invalid")
        if not source_license:
            raise ValueError("source_license is required for every captured snapshot")
        if not observation_basis:
            raise ValueError("observation_basis is required")

        captured_at = _aware_utc(self.clock(), field_name="capture clock")
        observed_at = captured_at
        requested_effective_at = _optional_aware_utc(
            effective_at,
            field_name="effective_at",
        )
        effective_at = requested_effective_at or observed_at
        slate_lock_at = _optional_aware_utc(slate_lock_at, field_name="slate_lock_at")
        snapshot_id = _snapshot_id(
            source_system=source_system,
            dataset=dataset,
            season=season,
            week=week,
            slate=slate,
            content_sha256=content_sha256,
        )

        existing = self.session.get(SourceSnapshot, snapshot_id)
        if existing is not None:
            verify_snapshot_artifact(existing)
            if existing.source_license != source_license:
                raise SnapshotIntegrityError(
                    "The same scoped content was already captured with different license metadata"
                )
            if _stored_utc(existing.slate_lock_at) != slate_lock_at:
                raise SnapshotIntegrityError(
                    "The same scoped content was already captured with a different slate lock"
                )
            if (
                requested_effective_at is not None
                and _stored_utc(existing.effective_at) != requested_effective_at
            ):
                raise SnapshotIntegrityError(
                    "The same scoped content was already captured with a different effective time"
                )
            if existing.source_uri != source_uri:
                raise SnapshotIntegrityError(
                    "The same scoped content was already captured with a different source URI"
                )
            return SnapshotCaptureResult(
                snapshot=existing,
                created=False,
                pre_lock=snapshot_pre_lock(existing),
            )

        scope_path = (
            self.snapshot_root
            / _safe_component(source_system, "source")
            / _safe_component(dataset, "dataset")
            / f"season={season}"
        )
        if week is not None:
            scope_path /= f"week={week:02d}"
        if slate:
            scope_path /= f"slate={_safe_component(slate, 'slate')}"
        snapshot_path = scope_path / snapshot_id
        safe_artifact_name = _safe_component(Path(artifact_name).name, "snapshot.bin")
        artifact_path = snapshot_path / safe_artifact_name
        manifest_path = snapshot_path / "manifest.json"

        if payload_path is not None:
            _copy_new_file(payload_path, artifact_path, content_sha256)
        elif payload is not None:
            _write_new_bytes(artifact_path, payload)
        else:  # pragma: no cover - protected by the two public capture methods
            raise RuntimeError("Snapshot payload is missing")

        artifact_relative_path = artifact_path.relative_to(self.snapshot_root).as_posix()
        manifest_relative_path = manifest_path.relative_to(self.snapshot_root).as_posix()
        manifest = {
            "contract_id": SNAPSHOT_CONTRACT_ID,
            "snapshot_id": snapshot_id,
            "source_system": source_system,
            "dataset": dataset,
            "season": season,
            "week": week,
            "slate": slate,
            "observed_at": _iso(observed_at),
            "effective_at": _iso(effective_at),
            "captured_at": _iso(captured_at),
            "slate_lock_at": _iso(slate_lock_at),
            "observation_basis": observation_basis,
            "pre_lock": (
                snapshot_visible_at_cutoff(observed_at, slate_lock_at)
                if slate_lock_at is not None
                else None
            ),
            "content_sha256": content_sha256,
            "byte_count": byte_count,
            "row_count": row_count,
            "media_type": media_type,
            "artifact_path": artifact_relative_path,
            "manifest_path": manifest_relative_path,
            "original_path": original_path,
            "source_uri": source_uri,
            "source_license": source_license,
            "metadata": metadata or {},
        }
        manifest_bytes = (
            json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n"
        ).encode("utf-8")
        _write_new_bytes(manifest_path, manifest_bytes)

        snapshot = SourceSnapshot(
            snapshot_id=snapshot_id,
            source_system=source_system,
            dataset=dataset,
            season=season,
            week=week,
            slate=slate,
            observed_at=observed_at,
            effective_at=effective_at,
            captured_at=captured_at,
            slate_lock_at=slate_lock_at,
            observation_basis=observation_basis,
            content_sha256=content_sha256,
            byte_count=byte_count,
            row_count=row_count,
            media_type=media_type,
            artifact_path=str(artifact_path),
            manifest_path=str(manifest_path),
            original_path=original_path,
            source_uri=source_uri,
            source_license=source_license,
            metadata_json=metadata or {},
        )
        self.session.add(snapshot)
        try:
            self.session.commit()
            self.session.refresh(snapshot)
        except IntegrityError:
            self.session.rollback()
            concurrent = self.session.get(SourceSnapshot, snapshot_id)
            if concurrent is None:
                raise
            verify_snapshot_artifact(concurrent)
            return SnapshotCaptureResult(
                snapshot=concurrent,
                created=False,
                pre_lock=snapshot_pre_lock(concurrent),
            )
        return SnapshotCaptureResult(
            snapshot=snapshot,
            created=True,
            pre_lock=snapshot_pre_lock(snapshot),
        )

    def link_ingest_run(self, snapshot_id: str, ingest_run_id: str) -> None:
        if self.session.get(SourceSnapshot, snapshot_id) is None:
            raise ValueError(f"Snapshot not found: {snapshot_id}")
        if self.session.get(IngestRun, ingest_run_id) is None:
            raise ValueError(f"Ingest run not found: {ingest_run_id}")
        key = {"snapshot_id": snapshot_id, "ingest_run_id": ingest_run_id}
        if self.session.get(SourceSnapshotIngestRun, key) is None:
            self.session.add(SourceSnapshotIngestRun(**key))
            self.session.commit()

    def capture_and_ingest_draftkings_salary(
        self,
        path: str | Path,
        *,
        season: int,
        week: int,
        slate: str,
        slate_lock_at: datetime,
        source_license: str,
        source_uri: str | None = None,
    ) -> DraftKingsCaptureIngestResult:
        source_path = Path(path).expanduser().resolve()
        capture = self.capture_file(
            source_path,
            source_system="draftkings",
            dataset="salary",
            season=season,
            week=week,
            slate=slate,
            source_license=source_license,
            source_uri=source_uri,
            slate_lock_at=slate_lock_at,
            effective_at=slate_lock_at,
            row_count=_csv_row_count(source_path),
            media_type="text/csv",
            metadata={"capture_mode": "manual_download"},
        )
        if capture.pre_lock is not True:
            raise PostLockSnapshotError(capture)
        ingest = IngestService(self.session).ingest_salaries(
            SalaryIngestRequest(
                source_system="draftkings",
                season=season,
                week=week,
                slate=slate,
                path=capture.snapshot.artifact_path,
            ),
            ingest_run_id=_ingest_run_id(capture.snapshot.snapshot_id),
        )
        self.link_ingest_run(capture.snapshot.snapshot_id, ingest.ingest_run_id)
        return DraftKingsCaptureIngestResult(capture=capture, ingest=ingest)

    def eligible_snapshots(
        self,
        *,
        cutoff_at: datetime,
        source_system: str | None = None,
        dataset: str | None = None,
        season: int | None = None,
        week: int | None = None,
        slate: str | None = None,
    ) -> list[SourceSnapshot]:
        cutoff_at = _aware_utc(cutoff_at, field_name="cutoff_at")
        query = select(SourceSnapshot)
        if source_system:
            query = query.where(SourceSnapshot.source_system == source_system.strip().lower())
        if dataset:
            query = query.where(SourceSnapshot.dataset == dataset.strip().lower())
        if season is not None:
            query = query.where(SourceSnapshot.season == season)
        if week is not None:
            query = query.where(SourceSnapshot.week == week)
        if slate:
            query = query.where(SourceSnapshot.slate == slate.strip().lower())
        rows = list(self.session.scalars(query.order_by(SourceSnapshot.observed_at)))
        return [
            row
            for row in rows
            if snapshot_visible_at_cutoff(row.observed_at, cutoff_at)
        ]


def _coerce_dataframe(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value
    if hasattr(value, "to_pandas"):
        return value.to_pandas()  # type: ignore[no-any-return]
    raise RuntimeError(f"Expected tabular nflreadpy data, received {type(value).__name__}")


def fetch_nflreadpy_dataset(
    dataset: str,
    *,
    season: int,
    week: int | None,
    nfl_module: Any | None = None,
) -> tuple[pd.DataFrame, str]:
    if dataset not in NFLREADPY_LOADERS:
        raise ValueError(
            f"Unsupported nflreadpy dataset {dataset!r}; choose from {NFLREADPY_DATASETS}"
        )
    if nfl_module is None:
        try:
            import nflreadpy as nfl_module  # type: ignore[no-redef]
        except ModuleNotFoundError as exc:  # pragma: no cover - environment-specific
            raise RuntimeError(
                "nflreadpy is not installed; install the repository requirements first"
            ) from exc
    loader_name = NFLREADPY_LOADERS[dataset]
    loader = getattr(nfl_module, loader_name, None)
    if loader is None:
        raise RuntimeError(f"Installed nflreadpy does not provide {loader_name}")
    frame = _coerce_dataframe(loader(seasons=[season]))
    season_column = "season" if "season" in frame.columns else None
    if season_column:
        frame = frame[pd.to_numeric(frame[season_column], errors="coerce") == season]
    if week is not None:
        if "week" not in frame.columns:
            raise RuntimeError(f"nflreadpy {dataset} output has no week column")
        frame = frame[pd.to_numeric(frame["week"], errors="coerce") == week]
    version = str(getattr(nfl_module, "__version__", "unknown"))
    return frame.reset_index(drop=True), version


def capture_nflreadpy_datasets(
    service: SourceCaptureService,
    datasets: Iterable[str],
    *,
    season: int,
    week: int | None,
    slate: str | None,
    slate_lock_at: datetime | None,
    source_license: str,
    nfl_module: Any | None = None,
) -> list[SnapshotCaptureResult]:
    results: list[SnapshotCaptureResult] = []
    for dataset in datasets:
        frame, version = fetch_nflreadpy_dataset(
            dataset,
            season=season,
            week=week,
            nfl_module=nfl_module,
        )
        artifact_name = f"nflreadpy_{dataset}_{season}"
        if week is not None:
            artifact_name += f"_week_{week:02d}"
        artifact_name += ".csv"
        results.append(
            service.capture_dataframe(
                frame,
                artifact_name=artifact_name,
                source_system="nflreadpy",
                dataset=dataset,
                season=season,
                week=week,
                slate=slate,
                source_license=source_license,
                source_uri=f"nflreadpy://{dataset}/{season}",
                slate_lock_at=slate_lock_at,
                metadata={
                    "capture_mode": "nflreadpy_fetch",
                    "nflreadpy_version": version,
                },
            )
        )
    return results
