"""Directory-level DraftKings import orchestration with durable per-file reports."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from Database.config import get_connection_string
from Database.curated_ingest import curate_salaries
from Database.raw_ingest import load_raw_salaries
from .ownership import OwnershipService
from .target_schema import validate_target_schema


@dataclass
class BatchFileResult:
    path: str
    file_type: str
    status: str
    season: int
    week: int
    slate: str
    rows_written: int = 0
    source_file_id: str | None = None
    contest_id: str | None = None
    message: str = ""
    template_id: str | None = None


@dataclass
class BatchImportResult:
    batch_id: str
    directory: str
    discovered: int
    imported: int
    deduplicated: int
    skipped: int
    failed: int
    dry_run: bool
    files: list[BatchFileResult]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["files"] = [asdict(row) for row in self.files]
        return payload


class DraftKingsBatchImportService:
    SUPPORTED_SUFFIXES = {".csv", ".tsv", ".tab", ".zip"}

    def __init__(self, connection_string: str | None = None, engine: Engine | None = None) -> None:
        self.connection_string = connection_string or get_connection_string()
        self.engine = engine or create_engine(self.connection_string)
        self.ownership = OwnershipService(connection_string=self.connection_string, engine=self.engine)

    @staticmethod
    def _read_preview(path: Path) -> pd.DataFrame:
        if path.suffix.lower() == ".zip":
            with ZipFile(path) as archive:
                names = [name for name in archive.namelist() if name.lower().endswith((".csv", ".tsv"))]
                if not names:
                    return pd.DataFrame()
                with archive.open(names[0]) as handle:
                    return pd.read_csv(handle, nrows=8, encoding="utf-8-sig", low_memory=False)
        separator = "\t" if path.suffix.lower() in {".tsv", ".tab"} else ","
        return pd.read_csv(path, nrows=8, encoding="utf-8-sig", sep=separator, low_memory=False)

    @classmethod
    def classify_file(cls, path: Path) -> str:
        try:
            preview = cls._read_preview(path)
        except Exception:  # noqa: BLE001 - malformed/unrelated files are reported as unrecognized
            return "unrecognized"
        columns = {str(column).strip().lower() for column in preview.columns}
        if {"entryid", "player", "roster position", "%drafted"}.issubset(columns):
            return "contest_standings"
        if {"position", "name + id", "id", "salary", "game info"}.issubset(columns):
            return "salary"
        normalized = {column.replace("_", " ") for column in columns}
        if "entry id" in normalized and ("contest id" in normalized or "contest name" in normalized):
            return "entry_template"
        roster_headers = {"qb", "rb", "wr", "te", "flex", "dst", "cpt"}
        if len(columns.intersection(roster_headers)) >= 4 and "instructions" in columns:
            return "entry_template"
        return "unrecognized"

    @staticmethod
    def infer_scope(path: Path, *, season: int, week: int, slate: str) -> tuple[int, int, str]:
        stem = re.sub(r"[^A-Za-z0-9]+", "_", path.stem).strip("_")
        match = re.search(r"(?:^|_)(20\d{2})_(\d{1,2})(?:_|$)", stem)
        if not match:
            return season, week, slate
        inferred_season = int(match.group(1))
        inferred_week = int(match.group(2))
        suffix = stem[match.end():].strip("_")
        inferred_slate = suffix.upper() if suffix else slate
        return inferred_season, inferred_week, inferred_slate

    def _ensure_schema(self) -> None:
        validate_target_schema(
            self.engine,
            consumer=type(self).__name__,
            required_tables=(
                "source_file_import",
                "import_batch",
                "import_batch_file",
                "dk_entry_template_file",
                "dk_entry_template_row",
            ),
        )

    def _register_source_file(self, source_info: dict[str, Any], file_type: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO target.source_file_import
                    (source_file_id, source_type, content_sha256, original_path,
                     file_name, file_size_bytes, metadata_json)
                VALUES (:source_file_id, :source_type, :content_sha256, :original_path,
                        :file_name, :file_size_bytes, '{}'::jsonb)
                ON CONFLICT (source_file_id) DO UPDATE SET
                    original_path = EXCLUDED.original_path, file_name = EXCLUDED.file_name,
                    file_size_bytes = EXCLUDED.file_size_bytes, last_ingested_at = now()
            """), {**source_info, "source_type": f"draftkings_{file_type}"})

    def _already_imported(self, source_file_id: str, file_type: str, season: int, week: int, slate: str) -> bool:
        with self.engine.begin() as conn:
            return bool(conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM target.import_batch_file
                    WHERE source_file_id = :source_file_id AND file_type = :file_type
                      AND season = :season AND week = :week AND slate_id = :slate
                      AND status = 'imported'
                )
            """), {"source_file_id": source_file_id, "file_type": file_type, "season": season, "week": week, "slate": slate}).scalar())

    def _import_entry_template(self, path: Path, source_file_id: str, season: int, week: int, slate: str) -> int:
        if path.suffix.lower() == ".zip":
            with ZipFile(path) as archive:
                names = [name for name in archive.namelist() if name.lower().endswith((".csv", ".tsv"))]
                with archive.open(names[0]) as handle:
                    frame = pd.read_csv(handle, encoding="utf-8-sig", low_memory=False)
        else:
            separator = "\t" if path.suffix.lower() in {".tsv", ".tab"} else ","
            frame = pd.read_csv(path, encoding="utf-8-sig", sep=separator, low_memory=False)
        template_id = self.entry_template_id(source_file_id, season, week, slate)
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO target.dk_entry_template_file
                    (template_id, source_file_id, season, week, slate_id, columns_json, row_count)
                VALUES (:template_id, :source_file_id, :season, :week, :slate,
                        CAST(:columns_json AS JSONB), :row_count)
                ON CONFLICT (source_file_id, season, week, slate_id) DO UPDATE SET
                    columns_json = EXCLUDED.columns_json, row_count = EXCLUDED.row_count,
                    imported_at = now()
            """), {"template_id": template_id, "source_file_id": source_file_id, "season": season,
                    "week": week, "slate": slate, "columns_json": json.dumps(list(frame.columns)),
                    "row_count": len(frame)})
            conn.execute(
                text("DELETE FROM target.dk_entry_template_row WHERE template_id = :template_id"),
                {"template_id": template_id},
            )
            rows = []
            for row_number, row in enumerate(
                frame.where(pd.notna(frame), None).to_dict(orient="records"),
                start=1,
            ):
                rows.append(
                    {
                        "template_id": template_id,
                        "row_number": row_number,
                        "entry_id": row.get("Entry ID", row.get("EntryId")),
                        "contest_id": row.get("Contest ID", row.get("ContestId")),
                        "contest_name": row.get("Contest Name", row.get("ContestName")),
                        "entry_fee": row.get("Entry Fee", row.get("EntryFee")),
                        "row_json": json.dumps(row, default=str),
                    }
                )
            if rows:
                conn.execute(text("""
                    INSERT INTO target.dk_entry_template_row
                        (template_id, row_number, entry_id, contest_id, contest_name,
                         entry_fee, row_json)
                    VALUES (:template_id, :row_number, :entry_id, :contest_id,
                            :contest_name, :entry_fee, CAST(:row_json AS JSONB))
                """), rows)
        return len(frame)

    @staticmethod
    def entry_template_id(source_file_id: str, season: int, week: int, slate: str) -> str:
        return f"template_{uuid.uuid5(uuid.NAMESPACE_URL, f'{source_file_id}|{season}|{week}|{slate}')}"

    def import_directory(self, directory: str, *, season: int, week: int, slate: str, recursive: bool = False, dry_run: bool = False) -> BatchImportResult:
        root = Path(directory).expanduser()
        if not root.is_dir():
            raise ValueError(f"Batch import directory not found: {root}")
        pattern = "**/*" if recursive else "*"
        paths = sorted(path for path in root.glob(pattern) if path.is_file() and path.suffix.lower() in self.SUPPORTED_SUFFIXES)
        batch_id = str(uuid.uuid4())
        self._ensure_schema()
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO target.import_batch (batch_id, directory, dry_run, discovered) VALUES (:batch_id, :directory, :dry_run, :discovered)"),
                         {"batch_id": batch_id, "directory": str(root), "dry_run": dry_run, "discovered": len(paths)})
        results: list[BatchFileResult] = []
        for path in paths:
            file_type = self.classify_file(path)
            file_season, file_week, file_slate = self.infer_scope(path, season=season, week=week, slate=slate)
            source_info: dict[str, Any] | None = None
            try:
                if file_type == "unrecognized":
                    result = BatchFileResult(str(path), file_type, "skipped", file_season, file_week, file_slate, message="Unrecognized DraftKings file")
                else:
                    source_info = self.ownership._source_file_info(path)
                    source_id = source_info["source_file_id"]
                    already_imported = self._already_imported(
                        source_id, file_type, file_season, file_week, file_slate
                    )
                    template_id = (
                        self.entry_template_id(source_id, file_season, file_week, file_slate)
                        if file_type == "entry_template"
                        else None
                    )
                    if already_imported:
                        result = BatchFileResult(str(path), file_type, "deduplicated", file_season, file_week, file_slate, source_file_id=source_id, message="Content already imported for this scope", template_id=template_id)
                    elif dry_run:
                        result = BatchFileResult(str(path), file_type, "would_import", file_season, file_week, file_slate, source_file_id=source_id, template_id=template_id)
                    else:
                        self._register_source_file(source_info, file_type)
                        if file_type == "contest_standings":
                            loaded = self.ownership.load_contest_standings(file_season, file_week, file_slate, str(path))
                            result = BatchFileResult(str(path), file_type, "imported", file_season, file_week, file_slate, loaded.rows_written, source_id, loaded.contest_id, loaded.message)
                        elif file_type == "salary":
                            raw_rows = load_raw_salaries(path, file_season, file_week, file_slate, self.connection_string)
                            curated_rows = curate_salaries(file_season, file_week, file_slate, self.connection_string)
                            result = BatchFileResult(str(path), file_type, "imported", file_season, file_week, file_slate, curated_rows or raw_rows, source_id, message=f"Loaded {raw_rows} raw and {curated_rows} curated salary rows")
                        else:
                            rows = self._import_entry_template(path, source_id, file_season, file_week, file_slate)
                            result = BatchFileResult(
                                str(path), file_type, "imported", file_season, file_week,
                                file_slate, rows, source_id,
                                message=f"Registered entry template with {rows} rows",
                                template_id=self.entry_template_id(
                                    source_id, file_season, file_week, file_slate
                                ),
                            )
            except Exception as exc:  # noqa: BLE001 - one bad file must not abort the batch
                result = BatchFileResult(str(path), file_type, "failed", file_season, file_week, file_slate, source_file_id=(source_info or {}).get("source_file_id"), message=str(exc))
            results.append(result)

        counts = {status: sum(row.status == status for row in results) for status in ("imported", "deduplicated", "skipped", "failed")}
        with self.engine.begin() as conn:
            for number, row in enumerate(results, start=1):
                conn.execute(text("""
                    INSERT INTO target.import_batch_file
                        (batch_id, file_number, source_file_id, path, file_type, status,
                         season, week, slate_id, contest_id, template_id, rows_written, message)
                    VALUES (:batch_id, :file_number, :source_file_id, :path, :file_type,
                            :status, :season, :week, :slate, :contest_id, :template_id,
                            :rows_written, :message)
                """), {"batch_id": batch_id, "file_number": number, **asdict(row)})
            conn.execute(text("""
                UPDATE target.import_batch SET completed_at = now(), imported = :imported,
                    deduplicated = :deduplicated, skipped = :skipped, failed = :failed
                WHERE batch_id = :batch_id
            """), {"batch_id": batch_id, **counts})
        return BatchImportResult(batch_id, str(root), len(paths), counts["imported"], counts["deduplicated"], counts["skipped"], counts["failed"], dry_run, results)
