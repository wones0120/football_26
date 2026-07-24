"""DraftKings upload CSV generation from persisted DFS portfolios."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from Database.config import get_connection_string

from .target_schema import validate_target_schema


CLASSIC_SLOTS = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]
SHOWDOWN_SLOTS = ["CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"]


@dataclass
class DraftKingsExportResult:
    export_id: str
    portfolio_id: str
    contest_format: str
    file_name: str
    row_count: int
    content_sha256: str
    csv_content: str
    validation_id: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExportValidationIssue:
    code: str
    message: str
    lineup_number: int | None = None
    player_id: str | None = None


@dataclass
class ExportValidationResult:
    validation_id: str
    portfolio_id: str
    status: str
    checks_run: int
    errors: list[ExportValidationIssue]
    warnings: list[ExportValidationIssue]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class DraftKingsExportService:
    def __init__(self, connection_string: str | None = None, engine: Engine | None = None) -> None:
        self.connection_string = connection_string or get_connection_string()
        self.engine = engine or create_engine(self.connection_string)

    @staticmethod
    def _base_column(column: str) -> str:
        return re.sub(r"\.\d+$", "", str(column)).strip()

    @staticmethod
    def _id_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()

    @classmethod
    def _site_player_id(cls, player: dict[str, Any]) -> str:
        payload = player.get("player_json") or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        for key in ("dk_player_id", "site_player_id", "ID", "id"):
            value = cls._id_text(payload.get(key))
            if value:
                return value
        fallback = cls._id_text(player.get("player_id"))
        if fallback.isdigit():
            return fallback
        raise ValueError(f"Lineup player {fallback or '<unknown>'} has no DraftKings site ID")

    @staticmethod
    def _position(player: dict[str, Any]) -> str:
        payload = player.get("player_json") or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        persisted_role = str(player.get("roster_position") or "").upper()
        if persisted_role in {"CPT", "FLEX"}:
            return persisted_role
        position = str(payload.get("position") or persisted_role).upper()
        return "DST" if position in {"D", "DEF", "DST"} else position

    @classmethod
    def _assign_players(cls, contest_format: str, players: list[dict[str, Any]]) -> list[str]:
        if contest_format == "showdown":
            captain = [player for player in players if cls._position(player) == "CPT"]
            flex = [player for player in players if cls._position(player) == "FLEX"]
            if len(captain) != 1 or len(flex) != 5:
                raise ValueError("Showdown lineup must contain exactly one CPT and five FLEX players")
            return [cls._site_player_id(captain[0]), *[cls._site_player_id(player) for player in flex]]

        buckets: dict[str, list[dict[str, Any]]] = {key: [] for key in ("QB", "RB", "WR", "TE", "DST")}
        for player in players:
            position = cls._position(player)
            if position not in buckets:
                raise ValueError(f"Unsupported classic position: {position or '<missing>'}")
            buckets[position].append(player)
        required = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1}
        for position, count in required.items():
            if len(buckets[position]) < count:
                raise ValueError(f"Classic lineup requires at least {count} {position} player(s)")
        dedicated: list[dict[str, Any]] = [
            buckets["QB"].pop(0),
            buckets["RB"].pop(0), buckets["RB"].pop(0),
            buckets["WR"].pop(0), buckets["WR"].pop(0), buckets["WR"].pop(0),
            buckets["TE"].pop(0),
        ]
        flex_candidates = buckets["RB"] + buckets["WR"] + buckets["TE"]
        if len(flex_candidates) != 1 or len(buckets["DST"]) != 1:
            raise ValueError("Classic lineup must contain one FLEX-eligible remainder and one DST")
        ordered = [*dedicated, flex_candidates[0], buckets["DST"][0]]
        return [cls._site_player_id(player) for player in ordered]

    @classmethod
    def build_csv(
        cls,
        *,
        contest_format: str,
        template_columns: list[str],
        rows: list[dict[str, Any]],
    ) -> str:
        expected_slots = SHOWDOWN_SLOTS if contest_format == "showdown" else CLASSIC_SLOTS
        roster_indexes = [
            index
            for index, column in enumerate(template_columns)
            if cls._base_column(column).upper() in {"QB", "RB", "WR", "TE", "FLEX", "DST", "CPT"}
        ]
        template_slots = [cls._base_column(template_columns[index]).upper() for index in roster_indexes]
        if template_slots != expected_slots:
            raise ValueError(
                f"Entry template roster columns {template_slots} do not match {contest_format} {expected_slots}"
            )
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow([cls._base_column(column) for column in template_columns])
        for row in rows:
            original = row.get("row_json") or {}
            if isinstance(original, str):
                original = json.loads(original)
            values = [cls._id_text(original.get(column)) for column in template_columns]
            player_ids = cls._assign_players(contest_format, row["players"])
            for column_index, player_id in zip(roster_indexes, player_ids, strict=True):
                values[column_index] = player_id
            writer.writerow(values)
        return output.getvalue()

    @staticmethod
    def _number(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def validate_rows(
        cls,
        *,
        portfolio_id: str,
        contest_format: str,
        template_columns: list[str],
        rows: list[dict[str, Any]],
        expected_entry_count: int,
        max_exposure: float = 1.0,
    ) -> ExportValidationResult:
        validation_id = str(uuid.uuid4())
        errors: list[ExportValidationIssue] = []
        warnings: list[ExportValidationIssue] = []
        if len(rows) != expected_entry_count:
            errors.append(ExportValidationIssue(
                "entry_count_mismatch",
                f"Portfolio has {len(rows)} assignments for {expected_entry_count} template entries",
            ))
        try:
            cls.build_csv(contest_format=contest_format, template_columns=template_columns, rows=[])
        except ValueError as exc:
            errors.append(ExportValidationIssue("template_slot_shape", str(exc)))

        seen_signatures: dict[tuple[str, ...], int] = {}
        exposure_counts: dict[str, int] = {}
        for lineup_number, row in enumerate(rows, start=1):
            entry_id = cls._id_text(row.get("entry_id"))
            contest_id = cls._id_text(row.get("contest_id"))
            if not entry_id or not contest_id:
                errors.append(ExportValidationIssue(
                    "entry_mapping",
                    "Entry assignment requires both entry_id and contest_id",
                    lineup_number=lineup_number,
                ))
            players = row.get("players") or []
            expected_players = 6 if contest_format == "showdown" else 9
            if len(players) != expected_players:
                errors.append(ExportValidationIssue(
                    "roster_size",
                    f"{contest_format} lineup has {len(players)} players; expected {expected_players}",
                    lineup_number=lineup_number,
                ))
            site_ids: list[str] = []
            for player in players:
                try:
                    site_id = cls._site_player_id(player)
                    site_ids.append(site_id)
                    exposure_counts[site_id] = exposure_counts.get(site_id, 0) + 1
                except ValueError as exc:
                    errors.append(ExportValidationIssue(
                        "site_player_id",
                        str(exc),
                        lineup_number=lineup_number,
                        player_id=cls._id_text(player.get("player_id")) or None,
                    ))
            if len(site_ids) != len(set(site_ids)):
                errors.append(ExportValidationIssue(
                    "duplicate_player",
                    "Lineup contains the same DraftKings player more than once",
                    lineup_number=lineup_number,
                ))
            if contest_format == "showdown":
                signature = tuple(sorted(
                    f"{site_id}:{cls._position(player)}"
                    for site_id, player in zip(site_ids, players, strict=False)
                ))
            else:
                signature = tuple(sorted(site_ids))
            if signature in seen_signatures:
                errors.append(ExportValidationIssue(
                    "duplicate_lineup",
                    f"Lineup duplicates portfolio lineup {seen_signatures[signature]}",
                    lineup_number=lineup_number,
                ))
            elif signature:
                seen_signatures[signature] = lineup_number
            salary = sum(cls._number(player.get("salary")) for player in players)
            if any(cls._number(player.get("salary")) <= 0 for player in players):
                errors.append(ExportValidationIssue(
                    "invalid_salary",
                    "Every lineup player must have a positive salary",
                    lineup_number=lineup_number,
                ))
            if salary > 50000.0 + 1e-6:
                errors.append(ExportValidationIssue(
                    "salary_cap",
                    f"Lineup salary {salary:.0f} exceeds the DraftKings 50000 cap",
                    lineup_number=lineup_number,
                ))
            try:
                cls._assign_players(contest_format, players)
            except ValueError as exc:
                errors.append(ExportValidationIssue(
                    "roster_eligibility",
                    str(exc),
                    lineup_number=lineup_number,
                ))

        normalized_exposure = max_exposure / 100.0 if max_exposure > 1.0 else max_exposure
        normalized_exposure = max(0.0, min(1.0, normalized_exposure))
        allowed_count = math.ceil(len(rows) * normalized_exposure)
        for site_id, count in sorted(exposure_counts.items()):
            if count > allowed_count:
                errors.append(ExportValidationIssue(
                    "exposure_limit",
                    f"Player exposure {count}/{len(rows)} exceeds max_exposure {normalized_exposure:.2%}",
                    player_id=site_id,
                ))
        return ExportValidationResult(
            validation_id=validation_id,
            portfolio_id=portfolio_id,
            status="failed" if errors else "passed",
            checks_run=8,
            errors=errors,
            warnings=warnings,
        )

    def _ensure_schema(self) -> None:
        validate_target_schema(
            self.engine,
            consumer=type(self).__name__,
            required_tables=("dk_export_validation", "dk_upload_export"),
        )

    def validate_portfolio(self, portfolio_id: str) -> ExportValidationResult:
        self._ensure_schema()
        with self.engine.begin() as conn:
            context = conn.execute(text("""
                SELECT portfolio.portfolio_id, portfolio.template_id,
                       portfolio.contest_format, template.columns_json,
                       template.row_count, optimizer.constraint_config_json
                FROM target.lineup_portfolio portfolio
                JOIN target.dk_entry_template_file template
                  ON template.template_id = portfolio.template_id
                JOIN target.optimizer_run optimizer
                  ON optimizer.optimizer_run_id = portfolio.optimizer_run_id
                WHERE portfolio.portfolio_id = :portfolio_id
            """), {"portfolio_id": portfolio_id}).mappings().first()
            if not context:
                raise ValueError(f"Portfolio not found: {portfolio_id}")
            assignments = conn.execute(text("""
                SELECT assignment.template_row_number, assignment.entry_id,
                       assignment.contest_id, assignment.lineup_id,
                       template_row.row_json
                FROM target.contest_entry_assignment assignment
                JOIN target.dk_entry_template_row template_row
                  ON template_row.template_id = assignment.template_id
                 AND template_row.row_number = assignment.template_row_number
                WHERE assignment.portfolio_id = :portfolio_id
                ORDER BY assignment.template_row_number
            """), {"portfolio_id": portfolio_id}).mappings().all()
            rows = []
            for assignment in assignments:
                players = conn.execute(text("""
                    SELECT player_id, roster_position, salary, player_json
                    FROM target.lineup_player
                    WHERE lineup_id = :lineup_id ORDER BY slot_index
                """), {"lineup_id": assignment["lineup_id"]}).mappings().all()
                rows.append({
                    "entry_id": assignment["entry_id"],
                    "contest_id": assignment["contest_id"],
                    "row_json": assignment["row_json"],
                    "players": [dict(player) for player in players],
                })
        columns = context["columns_json"] or []
        if isinstance(columns, str):
            columns = json.loads(columns)
        config = context["constraint_config_json"] or {}
        if isinstance(config, str):
            config = json.loads(config)
        try:
            max_exposure = float(config.get("max_exposure", 1.0))
        except (TypeError, ValueError):
            max_exposure = 1.0
        result = self.validate_rows(
            portfolio_id=portfolio_id,
            contest_format=str(context["contest_format"]),
            template_columns=list(columns),
            rows=rows,
            expected_entry_count=int(context["row_count"]),
            max_exposure=max_exposure,
        )
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO target.dk_export_validation
                    (validation_id, portfolio_id, status, checks_run,
                     errors_json, warnings_json)
                VALUES (:validation_id, :portfolio_id, :status, :checks_run,
                        CAST(:errors_json AS JSONB), CAST(:warnings_json AS JSONB))
            """), {
                "validation_id": result.validation_id,
                "portfolio_id": portfolio_id,
                "status": result.status,
                "checks_run": result.checks_run,
                "errors_json": json.dumps([asdict(issue) for issue in result.errors]),
                "warnings_json": json.dumps([asdict(issue) for issue in result.warnings]),
            })
        return result

    def generate_export(self, portfolio_id: str) -> DraftKingsExportResult:
        validation = self.validate_portfolio(portfolio_id)
        if validation.status != "passed":
            summary = "; ".join(issue.message for issue in validation.errors[:5])
            raise ValueError(f"Export validation failed: {summary}")
        with self.engine.begin() as conn:
            portfolio = conn.execute(text("""
                SELECT portfolio_id, portfolio_name, template_id, contest_format
                FROM target.lineup_portfolio WHERE portfolio_id = :portfolio_id
            """), {"portfolio_id": portfolio_id}).mappings().first()
            if not portfolio:
                raise ValueError(f"Portfolio not found: {portfolio_id}")
            template = conn.execute(text("""
                SELECT columns_json FROM target.dk_entry_template_file
                WHERE template_id = :template_id
            """), {"template_id": portfolio["template_id"]}).mappings().first()
            assignments = conn.execute(text("""
                SELECT assignment.template_row_number, assignment.lineup_id,
                       template_row.row_json
                FROM target.contest_entry_assignment assignment
                JOIN target.dk_entry_template_row template_row
                  ON template_row.template_id = assignment.template_id
                 AND template_row.row_number = assignment.template_row_number
                WHERE assignment.portfolio_id = :portfolio_id
                ORDER BY assignment.template_row_number
            """), {"portfolio_id": portfolio_id}).mappings().all()
            if not assignments:
                raise ValueError("Portfolio has no contest-entry assignments")
            rows = []
            for assignment in assignments:
                players = conn.execute(text("""
                    SELECT player_id, roster_position, player_json
                    FROM target.lineup_player WHERE lineup_id = :lineup_id ORDER BY slot_index
                """), {"lineup_id": assignment["lineup_id"]}).mappings().all()
                rows.append({"row_json": assignment["row_json"], "players": [dict(player) for player in players]})

        columns = template["columns_json"] if template else []
        if isinstance(columns, str):
            columns = json.loads(columns)
        csv_content = self.build_csv(
            contest_format=str(portfolio["contest_format"]),
            template_columns=list(columns),
            rows=rows,
        )
        digest = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()
        export_id = str(uuid.uuid4())
        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", str(portfolio["portfolio_name"])).strip("_") or "portfolio"
        file_name = f"draftkings_{safe_name}_{export_id[:8]}.csv"
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO target.dk_upload_export
                    (export_id, portfolio_id, validation_id, contest_format, file_name, row_count,
                     content_sha256, columns_json, csv_content)
                VALUES (:export_id, :portfolio_id, :validation_id, :contest_format, :file_name,
                        :row_count, :content_sha256, CAST(:columns_json AS JSONB), :csv_content)
            """), {"export_id": export_id, "portfolio_id": portfolio_id,
                    "validation_id": validation.validation_id,
                    "contest_format": portfolio["contest_format"], "file_name": file_name,
                    "row_count": len(rows), "content_sha256": digest,
                    "columns_json": json.dumps(columns), "csv_content": csv_content})
        return DraftKingsExportResult(export_id, portfolio_id, str(portfolio["contest_format"]), file_name, len(rows), digest, csv_content, validation.validation_id)

    def get_export(self, export_id: str) -> DraftKingsExportResult | None:
        self._ensure_schema()
        with self.engine.begin() as conn:
            row = conn.execute(text("""
                SELECT export.export_id, export.portfolio_id, export.contest_format,
                       export.file_name, export.row_count, export.content_sha256,
                       export.csv_content, export.validation_id
                FROM target.dk_upload_export export
                JOIN target.dk_export_validation validation
                  ON validation.validation_id = export.validation_id
                 AND validation.status = 'passed'
                WHERE export.export_id = :export_id
            """), {"export_id": export_id}).mappings().first()
        return DraftKingsExportResult(**dict(row)) if row else None
