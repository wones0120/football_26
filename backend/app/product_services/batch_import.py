"""Directory-level DraftKings import orchestration with durable per-file reports."""

from __future__ import annotations

import json
import hashlib
import os
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pandas as pd
from sqlalchemy import create_engine, inspect, text
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


@dataclass(frozen=True)
class SelectedWeeklyContestFile:
    path: str
    source_file_id: str
    season: int
    week: int
    slate: str


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
    staged: int = 0

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["files"] = [asdict(row) for row in self.files]
        return payload


class DraftKingsBatchImportService:
    SUPPORTED_SUFFIXES = {".csv", ".tsv", ".tab", ".zip"}
    WEEKLY_SLATES = (
        "WEDNESDAY_NIGHT", "THURSDAY_NIGHT", "FRIDAY_NIGHT", "SATURDAY_NIGHT",
        "SUNDAY_MORNING", "SUNDAY_MAIN", "SUNDAY_EARLY", "SUNDAY_LATE", "SUNDAY_NIGHT",
        "SUNDAY_MONDAY", "MONDAY_NIGHT", "TUESDAY_NIGHT",
    )

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
                "dk_contest_staged_file",
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
                    UNION ALL
                    SELECT 1 FROM target.dfs_contest
                    WHERE :file_type = 'contest_standings'
                      AND source_file_id = :source_file_id AND season = :season
                      AND week = :week AND upper(slate_id) = :slate
                )
            """), {"source_file_id": source_file_id, "file_type": file_type, "season": season, "week": week, "slate": slate}).scalar())

    @classmethod
    def _salary_slate_evidence(
        cls, path: Path, root: Path, *, season: int, week: int,
    ) -> tuple[str | None, str]:
        """Infer a slate only when every observed contest player matches one salary slate."""
        try:
            if path.suffix.lower() == ".zip":
                with ZipFile(path) as archive:
                    name = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
                    with archive.open(name) as source:
                        frame = pd.read_csv(source, usecols=["Player"], dtype=str)
            else:
                frame = pd.read_csv(path, usecols=["Player"], dtype=str)
        except (OSError, ValueError, KeyError, StopIteration) as exc:
            return None, f"Could not inspect contest players: {exc}"
        players = {
            " ".join(value.split()).casefold()
            for value in frame["Player"].dropna().astype(str)
            if value.strip()
        }
        if len(players) < 10:
            return None, "Too few distinct contest players to identify a slate automatically"

        matches: list[tuple[str, Path]] = []
        for salary_path in sorted(root.rglob(f"DKSalaries_{season}_{week}_*.csv")):
            if salary_path.relative_to(root).parts[0].casefold() == "processed":
                continue
            slate = salary_path.stem[len(f"DKSalaries_{season}_{week}_"):].upper()
            if not cls._valid_contest_slate(slate):
                continue
            try:
                salaries = pd.read_csv(salary_path, usecols=["Name"], dtype=str)
            except (OSError, ValueError):
                continue
            salary_players = {
                " ".join(value.split()).casefold()
                for value in salaries["Name"].dropna().astype(str)
                if value.strip()
            }
            if players <= salary_players:
                matches.append((slate, salary_path))
        slates = {slate for slate, _ in matches}
        if len(slates) == 1:
            slate = next(iter(slates))
            salary_path = next(path for candidate, path in matches if candidate == slate)
            salary_hash = hashlib.sha256(salary_path.read_bytes()).hexdigest()
            return slate, (
                f"Matched all {len(players)} contest players to {salary_path.name} "
                f"(SHA256 {salary_hash})"
            )
        if slates:
            return None, f"Contest players match multiple salary slates: {', '.join(sorted(slates))}"
        return None, "No complete match to one season/week salary slate; choose the correct scope"

    def _weekly_contest_scope(
        self, path: Path, *, root: Path, season: int, week: int,
        source_file_id: str, selected_slate: str | None = None,
    ) -> tuple[int | None, int | None, str | None, str | None]:
        """Resolve verified contest scope without assuming the selected UI week."""
        contest_match = re.search(r"contest-standings-(\d+)", path.stem, re.IGNORECASE)
        contest_id = contest_match.group(1) if contest_match else None
        filename_scope = re.search(r"(?:^|[^\d])(20\d{2})[-_](\d{1,2})(?:[-_]|$)", path.stem)
        explicit_week = (
            (int(filename_scope.group(1)), int(filename_scope.group(2)))
            if filename_scope else None
        )
        hints: set[str] = set()
        labeled_parts = [path.stem, *(parent.name for parent in path.parents if parent != root and root in parent.parents)]
        for part in labeled_parts:
            normalized = re.sub(r"[^A-Z0-9]+", "_", part.upper()).strip("_")
            # Match the explicitly assigned custom name before its built-in
            # prefix; retain independent labels from other folders as conflicts.
            selected_label = re.sub(r"[^A-Z0-9]+", "_", (selected_slate or "").upper()).strip("_")
            if selected_label and re.search(rf"(?:^|_){re.escape(selected_label)}(?:_|$)", normalized):
                hints.add(selected_slate.upper())
                continue
            for candidate in self.WEEKLY_SLATES:
                if re.search(rf"(?:^|_){candidate}(?:_|$)", normalized):
                    hints.add(candidate)
        with self.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT season, week, upper(slate_id) AS slate FROM target.dfs_contest
                WHERE source_file_id=:source_file_id OR contest_id=:contest_id
            """), {"source_file_id": source_file_id,
                   "contest_id": contest_id}).mappings().all()
            if contest_id and inspect(self.engine).has_table("saved_dk_contest", schema="target"):
                saved = conn.execute(text("""
                    SELECT season, week, upper(slate) AS slate FROM target.saved_dk_contest
                    WHERE contest_id=:contest_id
                """), {"contest_id": contest_id}).mappings().all()
                rows.extend(saved)
        known_weeks = {(int(row["season"]), int(row["week"])) for row in rows}
        if explicit_week:
            known_weeks.add(explicit_week)
        if selected_slate and known_weeks and (season, week) not in known_weeks:
            raise ValueError(f"Selected season/week conflicts with saved or filename evidence for {contest_id or path.name}")
        if len(known_weeks) > 1:
            raise ValueError(f"Conflicting season/week evidence for {contest_id or path.name}")
        hints.update(str(row["slate"]) for row in rows if row["slate"])
        if selected_slate:
            hints.add(selected_slate.upper())
        if len(hints) > 1:
            raise ValueError(f"Conflicting slate labels for {path.name}: {', '.join(sorted(hints))}")
        # A slate-labeled folder/file plus the selected week is an explicit
        # operator assignment when no saved contest week exists yet.
        verified_week = next(iter(known_weeks)) if known_weeks else (season, week) if hints else (None, None)
        return (*verified_week, next(iter(hints)) if hints else None, contest_id)

    def _stage_weekly_contest(self, path: Path, source_info: dict[str, Any], contest_id: str | None) -> None:
        self._register_source_file(source_info, "contest_standings")
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO target.dk_contest_staged_file
                    (source_file_id, contest_id, file_name, raw_file)
                VALUES (:source_file_id, :contest_id, :file_name, :raw_file)
                ON CONFLICT (source_file_id) DO NOTHING
            """), {
                "source_file_id": source_info["source_file_id"],
                "contest_id": contest_id,
                "file_name": path.name,
                "raw_file": path.read_bytes(),
            })

    def _mark_staged_contest_resolved(self, source_file_id: str, season: int, week: int, slate: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(text("""
                UPDATE target.dk_contest_staged_file
                SET resolved_at = now(), resolved_season = :season,
                    resolved_week = :week, resolved_slate = :slate
                WHERE source_file_id = :source_file_id
            """), {"source_file_id": source_file_id, "season": season, "week": week, "slate": slate})

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

    @staticmethod
    def _archive_weekly_contest(path: Path, root: Path) -> Path:
        """Move a loaded file without overwriting another archived download."""
        if path.is_symlink():
            raise ValueError("Symlinked contest files are not moved")
        relative = path.relative_to(root)
        destination_dir = root / "Processed" / relative.parent
        destination_dir.mkdir(parents=True, exist_ok=True)
        for number in range(1, 1001):
            suffix = "" if number == 1 else f"__{number}"
            destination = destination_dir / f"{path.stem}{suffix}{path.suffix}"
            try:
                os.link(path, destination)
            except FileExistsError:
                continue
            path.unlink()
            return destination
        raise FileExistsError(f"No available archive name for {path.name}")

    def get_batch_result(self, batch_id: str) -> BatchImportResult | None:
        self._ensure_schema()
        with self.engine.begin() as conn:
            batch = conn.execute(text("""
                SELECT batch_id, directory, dry_run, completed_at, discovered,
                       imported, deduplicated, staged, skipped, failed
                FROM target.import_batch WHERE batch_id = :batch_id
            """), {"batch_id": batch_id}).mappings().first()
            if not batch or batch["completed_at"] is None:
                return None
            files = conn.execute(text("""
                SELECT path, file_type, status, season, week, slate_id,
                       rows_written, source_file_id, contest_id, template_id, message
                FROM target.import_batch_file
                WHERE batch_id = :batch_id ORDER BY file_number
            """), {"batch_id": batch_id}).mappings().all()
        return BatchImportResult(
            batch_id=str(batch["batch_id"]),
            directory=str(batch["directory"]),
            discovered=int(batch["discovered"]),
            imported=int(batch["imported"]),
            deduplicated=int(batch["deduplicated"]),
            staged=int(batch["staged"]),
            skipped=int(batch["skipped"]),
            failed=int(batch["failed"]),
            dry_run=bool(batch["dry_run"]),
            files=[
                BatchFileResult(
                    path=str(row["path"]),
                    file_type=str(row["file_type"]),
                    status=str(row["status"]),
                    season=int(row["season"]),
                    week=int(row["week"]),
                    slate=str(row["slate_id"]),
                    rows_written=int(row["rows_written"]),
                    source_file_id=row["source_file_id"],
                    contest_id=row["contest_id"],
                    template_id=row["template_id"],
                    message=str(row["message"] or ""),
                )
                for row in files
            ],
        )

    @staticmethod
    def _valid_contest_slate(slate: str) -> bool:
        return bool(re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,63}", slate.upper())) and slate.upper() not in {
            "UNKNOWN", "DEFAULT", "UNRESOLVED",
        }

    def import_directory(
        self,
        directory: str,
        *,
        season: int,
        week: int,
        slate: str,
        recursive: bool = False,
        dry_run: bool = False,
        batch_id: str | None = None,
        weekly_contests_only: bool = False,
        selected_files: list[SelectedWeeklyContestFile] | None = None,
    ) -> BatchImportResult:
        root = Path(directory).expanduser()
        if not root.is_dir():
            raise ValueError(f"Batch import directory not found: {root}")
        selections: dict[Path, SelectedWeeklyContestFile] = {}
        if selected_files is not None:
            if not weekly_contests_only or not selected_files:
                raise ValueError("Select at least one contest standings file")
            for selected in selected_files:
                path = Path(selected.path).expanduser()
                if not path.is_absolute():
                    path = root / path
                try:
                    relative = path.relative_to(root)
                except ValueError as exc:
                    raise ValueError(f"Selected file is outside the contest folder: {path}") from exc
                if (not relative.parts or relative.parts[0].casefold() == "processed"
                        or not path.is_file() or path.is_symlink()
                        or not path.resolve().is_relative_to(root.resolve())
                        or path.suffix.lower() not in self.SUPPORTED_SUFFIXES):
                    raise ValueError(f"Selected contest file is unavailable: {path}")
                if path in selections:
                    raise ValueError(f"Contest file selected more than once: {path}")
                if not self._valid_contest_slate(selected.slate):
                    raise ValueError(f"Unsupported contest slate: {selected.slate}")
                selections[path] = selected
            paths = sorted(selections)
        else:
            pattern = "**/*" if recursive else "*"
            paths = sorted(
                path for path in root.glob(pattern)
                if path.is_file() and path.suffix.lower() in self.SUPPORTED_SUFFIXES
                and not (weekly_contests_only and path.relative_to(root).parts[0].casefold() == "processed")
            )
        batch_id = batch_id or str(uuid.uuid4())
        self._ensure_schema()
        existing = self.get_batch_result(batch_id)
        if existing is not None:
            return existing
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO target.import_batch
                    (batch_id, directory, dry_run, discovered)
                VALUES (:batch_id, :directory, :dry_run, :discovered)
                ON CONFLICT (batch_id) DO UPDATE SET
                    directory = EXCLUDED.directory,
                    dry_run = EXCLUDED.dry_run,
                    discovered = EXCLUDED.discovered,
                    completed_at = NULL,
                    imported = 0,
                    deduplicated = 0,
                    staged = 0,
                    skipped = 0,
                    failed = 0
            """), {"batch_id": batch_id, "directory": str(root),
                      "dry_run": dry_run, "discovered": len(paths)})
            conn.execute(
                text("DELETE FROM target.import_batch_file WHERE batch_id = :batch_id"),
                {"batch_id": batch_id},
            )
        results: list[BatchFileResult] = []
        for path in paths:
            selected = selections.get(path)
            file_type = self.classify_file(path)
            file_season, file_week, file_slate = (
                (selected.season, selected.week, selected.slate.upper()) if selected else
                self.infer_scope(path, season=season, week=week, slate=slate)
            )
            source_info: dict[str, Any] | None = None
            try:
                if file_type == "unrecognized" or (weekly_contests_only and file_type != "contest_standings"):
                    result = BatchFileResult(str(path), file_type, "failed" if selected else "skipped", file_season, file_week, file_slate, message="Not a DraftKings contest standings file")
                else:
                    source_info = self.ownership._source_file_info(path)
                    source_id = source_info["source_file_id"]
                    if selected and source_id != selected.source_file_id:
                        raise ValueError("File changed since preview; preview the folder again before loading")
                    detected_contest_id = None
                    scope_note = ""
                    if weekly_contests_only:
                        verified_season, verified_week, detected_slate, detected_contest_id = self._weekly_contest_scope(
                            path, root=root, season=file_season, week=file_week,
                            source_file_id=source_id,
                            **({"selected_slate": selected.slate} if selected else {}),
                        )
                        if selected is not None:
                            salary_slate, salary_note = self._salary_slate_evidence(
                                path, root, season=file_season, week=file_week,
                            )
                            if salary_slate and salary_slate != selected.slate.upper():
                                raise ValueError(
                                    f"Selected slate conflicts with salary-player evidence: {salary_slate}"
                                )
                            if salary_slate:
                                scope_note = salary_note
                        if detected_slate is None and selected is None:
                            inferred_slate, scope_note = self._salary_slate_evidence(
                                path, root, season=verified_season or file_season,
                                week=verified_week or file_week,
                            )
                            if inferred_slate:
                                detected_slate = inferred_slate
                                verified_season = verified_season or file_season
                                verified_week = verified_week or file_week
                        file_season = verified_season or season
                        file_week = verified_week or week
                        file_slate = detected_slate or "UNRESOLVED"
                        if verified_season is None or verified_week is None or detected_slate is None:
                            if not dry_run:
                                self._stage_weekly_contest(path, source_info, detected_contest_id)
                            result = BatchFileResult(
                                str(path), file_type, "would_stage" if dry_run else "staged",
                                file_season, file_week, file_slate, source_file_id=source_id,
                                contest_id=detected_contest_id,
                                message=(scope_note or "Choose this file's season, week, and slate before loading")
                                if dry_run else
                                f"Raw download staged; {scope_note or 'choose its season, week, and slate to load it'}",
                            )
                            results.append(result)
                            continue
                    already_imported = self._already_imported(
                        source_id, file_type, file_season, file_week, file_slate
                    )
                    template_id = (
                        self.entry_template_id(source_id, file_season, file_week, file_slate)
                        if file_type == "entry_template"
                        else None
                    )
                    if already_imported:
                        result = BatchFileResult(str(path), file_type, "deduplicated", file_season, file_week, file_slate, source_file_id=source_id, contest_id=detected_contest_id, message=f"Content already imported for this scope; {scope_note}" if scope_note else "Content already imported for this scope", template_id=template_id)
                        if weekly_contests_only and not dry_run:
                            self._mark_staged_contest_resolved(source_id, file_season, file_week, file_slate)
                    elif dry_run:
                        result = BatchFileResult(str(path), file_type, "would_import", file_season, file_week, file_slate, source_file_id=source_id, contest_id=detected_contest_id, template_id=template_id, message=scope_note)
                    else:
                        self._register_source_file(source_info, file_type)
                        if file_type == "contest_standings":
                            loaded = self.ownership.load_contest_standings(
                                file_season, file_week, file_slate, str(path),
                                contest_id=detected_contest_id,
                            )
                            result = BatchFileResult(
                                str(path), file_type,
                                "imported" if loaded.target_persisted else "failed",
                                file_season, file_week, file_slate, loaded.rows_written,
                                source_id, loaded.contest_id,
                                (f"{loaded.message}; {scope_note}" if scope_note else loaded.message)
                                if loaded.target_persisted else
                                f"{loaded.message}; normalized contest persistence failed",
                            )
                            if loaded.target_persisted and weekly_contests_only:
                                self._mark_staged_contest_resolved(source_id, file_season, file_week, file_slate)
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

        counts = {status: sum(row.status == status for row in results) for status in ("imported", "deduplicated", "staged", "skipped", "failed")}
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
                    deduplicated = :deduplicated, staged = :staged, skipped = :skipped, failed = :failed
                WHERE batch_id = :batch_id
            """), {"batch_id": batch_id, **counts})
        if weekly_contests_only and not dry_run:
            for number, row in enumerate(results, start=1):
                if row.status not in {"imported", "deduplicated"}:
                    continue
                try:
                    destination = self._archive_weekly_contest(Path(row.path), root)
                    detail = f"Moved to {destination}"
                except (OSError, ValueError) as exc:
                    detail = f"Could not move to Processed: {exc}"
                row.message = f"{row.message}; {detail}" if row.message else detail
                with self.engine.begin() as conn:
                    conn.execute(text("""
                        UPDATE target.import_batch_file SET message = :message
                        WHERE batch_id = :batch_id AND file_number = :file_number
                    """), {"message": row.message, "batch_id": batch_id, "file_number": number})
        return BatchImportResult(batch_id, str(root), len(paths), counts["imported"], counts["deduplicated"], counts["skipped"], counts["failed"], dry_run, results, staged=counts["staged"])
