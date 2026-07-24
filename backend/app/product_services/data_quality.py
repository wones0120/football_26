"""Durable data-quality runs and check history."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from Database.config import get_connection_string

from .target_schema import validate_target_schema


LOAD_QUALITY_CONTRACT_ID = "load_quality_v1"
STATUS_SEVERITY = {"pass": "info", "warn": "warning", "fail": "error"}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _value(row: object, name: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(name, default)
    return getattr(row, name, default)


def _score(statuses: Iterable[str]) -> int:
    values = [{"pass": 100, "warn": 60, "fail": 0}[status] for status in statuses]
    return round(sum(values) / len(values)) if values else 0


def build_load_quality_report(
    *,
    trigger: str,
    season: int,
    week: int | None,
    slate: str | None,
    summaries: Iterable[object],
    source_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a normalized quality report from one completed load operation."""
    checks: list[dict[str, Any]] = []
    normalized_slate = slate.upper() if slate else None
    for index, summary in enumerate(summaries, start=1):
        dataset = str(_value(summary, "dataset", _value(summary, "file_type", "unknown")))
        rows_written = int(_value(summary, "rows_written", 0) or 0)
        explicit_status = _value(summary, "status")
        status = str(explicit_status) if explicit_status in STATUS_SEVERITY else (
            "pass" if rows_written > 0 else "warn"
        )
        summary_season = int(_value(summary, "season", season) or season)
        summary_week = _value(summary, "week", week)
        summary_slate = _value(summary, "slate", _value(summary, "slate_id", normalized_slate))
        message = str(
            _value(summary, "message", "")
            or (
                f"{dataset} wrote {rows_written} rows."
                if rows_written
                else f"{dataset} completed without writing rows."
            )
        )
        checks.append(
            {
                "check_id": f"{dataset}:{index}:rows_written",
                "category": "load",
                "status": status,
                "table_name": dataset,
                "check_name": "rows_written",
                "message": message,
                "value": rows_written,
                "threshold": str(_value(summary, "threshold", "> 0 rows")),
                "affected_scope": {
                    "season": summary_season,
                    "week": int(summary_week) if summary_week is not None else None,
                    "slate": str(summary_slate).upper() if summary_slate else None,
                    "dataset": dataset,
                },
                "details": {
                    key: value
                    for key, value in {
                        "source_file_id": _value(summary, "source_file_id"),
                        "contest_id": _value(summary, "contest_id"),
                        "path": _value(summary, "path"),
                    }.items()
                    if value is not None
                },
            }
        )

    if not checks:
        checks.append(
            {
                "check_id": "load_operation:1:rows_written",
                "category": "load",
                "status": "warn",
                "table_name": "load_operation",
                "check_name": "rows_written",
                "message": "The load completed without reporting any dataset results.",
                "value": 0,
                "threshold": "> 0 reported datasets",
                "affected_scope": {
                    "season": season,
                    "week": week,
                    "slate": normalized_slate,
                    "dataset": "load_operation",
                },
                "details": {},
            }
        )

    counts = Counter(check["status"] for check in checks)
    overall = "fail" if counts["fail"] else "warn" if counts["warn"] else "pass"
    stable_payload = {
        "contract_id": LOAD_QUALITY_CONTRACT_ID,
        "trigger": trigger,
        "season": season,
        "week": week,
        "slate": normalized_slate,
        "checks": checks,
        "source_context": source_context or {},
    }
    report_hash = hashlib.sha256(_json(stable_payload).encode()).hexdigest()[:24]
    return {
        "report_id": f"load-quality:{report_hash}",
        "contract_id": LOAD_QUALITY_CONTRACT_ID,
        "season": season,
        "week": week,
        "slate": normalized_slate,
        "status": overall,
        "score": _score(check["status"] for check in checks),
        "summary": {"pass": counts["pass"], "warn": counts["warn"], "fail": counts["fail"]},
        "checks": checks,
        "source_context": source_context or {},
    }


class DataQualityService:
    """Persist and query versioned data-quality reports."""

    def __init__(self, connection_string: str | None = None, engine: Engine | None = None) -> None:
        self.connection_string = connection_string or (
            str(engine.url) if engine is not None else get_connection_string()
        )
        self.engine = engine or create_engine(self.connection_string)

    def _ensure_schema(self) -> None:
        validate_target_schema(
            self.engine,
            consumer=type(self).__name__,
            required_tables=("data_quality_run", "data_quality_check"),
        )

    def record_report(self, report: Mapping[str, Any], *, trigger: str) -> str:
        """Persist one normalized report and return its unique run ID."""
        self._ensure_schema()
        quality_run_id = f"quality-{uuid.uuid4()}"
        checks = list(report.get("checks") or [])
        season = int(report["season"])
        week = report.get("week")
        slate = str(report["slate"]).upper() if report.get("slate") else None
        source_context = dict(report.get("source_context") or {})
        if report.get("gates"):
            source_context["gates"] = report["gates"]

        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO target.data_quality_run
                        (quality_run_id, report_id, contract_id, trigger, season, week, slate,
                         status, score, summary_json, source_context_json)
                    VALUES
                        (:quality_run_id, :report_id, :contract_id, :trigger, :season, :week, :slate,
                         :status, :score, CAST(:summary_json AS JSONB), CAST(:source_context_json AS JSONB))
                    """
                ),
                {
                    "quality_run_id": quality_run_id,
                    "report_id": report.get("report_id"),
                    "contract_id": report.get("contract_id", "unknown"),
                    "trigger": trigger,
                    "season": season,
                    "week": int(week) if week is not None else None,
                    "slate": slate,
                    "status": report.get("status", "warn"),
                    "score": int(report.get("score", 0)),
                    "summary_json": _json(report.get("summary") or {}),
                    "source_context_json": _json(source_context),
                },
            )
            if checks:
                check_rows = []
                for index, check in enumerate(checks, start=1):
                    logical_id = str(check.get("check_id") or f"check-{index}")
                    affected_scope = dict(check.get("affected_scope") or {})
                    affected_scope.setdefault("season", season)
                    affected_scope.setdefault("week", int(week) if week is not None else None)
                    affected_scope.setdefault("slate", slate)
                    if check.get("applies_to"):
                        affected_scope["applies_to"] = check["applies_to"]
                    if check.get("blocks"):
                        affected_scope["blocks"] = check["blocks"]
                    status = str(check.get("status", "warn"))
                    check_rows.append(
                        {
                            "quality_check_id": str(
                                uuid.uuid5(uuid.NAMESPACE_URL, f"{quality_run_id}|{logical_id}")
                            ),
                            "quality_run_id": quality_run_id,
                            "check_id": logical_id,
                            "category": str(check.get("category", "unknown")),
                            "status": status,
                            "severity": STATUS_SEVERITY[status],
                            "table_name": check.get("table_name") or check.get("category"),
                            "check_name": str(check.get("check_name") or logical_id),
                            "message": str(check.get("message") or logical_id),
                            "value_json": _json(check.get("value")),
                            "threshold": check.get("threshold"),
                            "affected_scope_json": _json(affected_scope),
                            "details_json": _json(check.get("details") or {}),
                        }
                    )
                connection.execute(
                    text(
                        """
                        INSERT INTO target.data_quality_check
                            (quality_check_id, quality_run_id, check_id, category, status, severity,
                             table_name, check_name, message, value_json, threshold,
                             affected_scope_json, details_json)
                        VALUES
                            (:quality_check_id, :quality_run_id, :check_id, :category, :status, :severity,
                             :table_name, :check_name, :message, CAST(:value_json AS JSONB), :threshold,
                             CAST(:affected_scope_json AS JSONB), CAST(:details_json AS JSONB))
                        """
                    ),
                    check_rows,
                )
        return quality_run_id

    def record_load(
        self,
        *,
        trigger: str,
        season: int,
        week: int | None,
        slate: str | None,
        summaries: Iterable[object],
        source_context: dict[str, Any] | None = None,
    ) -> str:
        report = build_load_quality_report(
            trigger=trigger,
            season=season,
            week=week,
            slate=slate,
            summaries=summaries,
            source_context=source_context,
        )
        return self.record_report(report, trigger=trigger)

    def record_readiness(self, report: Mapping[str, Any], *, trigger: str = "readiness_check") -> str:
        return self.record_report(report, trigger=trigger)

    def history(
        self,
        *,
        season: int,
        week: int | None = None,
        slate: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Return newest-first quality runs, including broader season/week checks."""
        self._ensure_schema()
        conditions = ["season = :season"]
        params: dict[str, Any] = {"season": season, "limit": max(1, min(int(limit), 100))}
        if week is not None:
            conditions.append("(week IS NULL OR week = :week)")
            params["week"] = week
        if slate:
            conditions.append("(slate IS NULL OR UPPER(slate) = UPPER(:slate))")
            params["slate"] = slate
        where_clause = " AND ".join(conditions)

        with self.engine.begin() as connection:
            run_rows = connection.execute(
                text(
                    f"""
                    SELECT quality_run_id, report_id, contract_id, trigger, season, week, slate,
                           status, score, summary_json, source_context_json, created_at
                    FROM target.data_quality_run
                    WHERE {where_clause}
                    ORDER BY created_at DESC, quality_run_id DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
            run_ids = [str(row["quality_run_id"]) for row in run_rows]
            check_rows = (
                connection.execute(
                    text(
                        """
                        SELECT quality_check_id, quality_run_id, check_id, category, status, severity,
                               table_name, check_name, message, value_json, threshold,
                               affected_scope_json, details_json, created_at
                        FROM target.data_quality_check
                        WHERE quality_run_id = ANY(:run_ids)
                        ORDER BY created_at, check_id
                        """
                    ),
                    {"run_ids": run_ids},
                ).mappings().all()
                if run_ids
                else []
            )

        checks_by_run: dict[str, list[dict[str, Any]]] = {run_id: [] for run_id in run_ids}
        for row in check_rows:
            payload = dict(row)
            payload["value"] = payload.pop("value_json")
            payload["affected_scope"] = payload.pop("affected_scope_json") or {}
            payload["details"] = payload.pop("details_json") or {}
            checks_by_run[str(row["quality_run_id"])].append(payload)

        runs = []
        for row in run_rows:
            payload = dict(row)
            payload["summary"] = payload.pop("summary_json") or {}
            payload["source_context"] = payload.pop("source_context_json") or {}
            payload["checks"] = checks_by_run[str(row["quality_run_id"])]
            runs.append(payload)
        return {
            "season": season,
            "week": week,
            "slate": slate.upper() if slate else None,
            "runs": runs,
        }
