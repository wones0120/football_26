"""Persistent DFS portfolios and DraftKings contest-entry assignments."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from Database.config import get_connection_string

from .target_schema import validate_target_schema


@dataclass
class EntryAssignment:
    assignment_id: str
    portfolio_id: str
    template_id: str
    template_row_number: int
    entry_id: str
    contest_id: str
    lineup_id: str
    portfolio_lineup_number: int


@dataclass
class PortfolioResult:
    portfolio_id: str
    portfolio_name: str
    optimizer_run_id: str
    template_id: str
    season: int
    week: int
    slate: str
    contest_format: str
    objective: str
    status: str
    lineup_count: int
    assignment_count: int
    assignments: list[EntryAssignment]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["assignments"] = [asdict(row) for row in self.assignments]
        return payload


class PortfolioService:
    def __init__(self, connection_string: str | None = None, engine: Engine | None = None) -> None:
        self.connection_string = connection_string or get_connection_string()
        self.engine = engine or create_engine(self.connection_string)

    def _ensure_schema(self) -> None:
        validate_target_schema(
            self.engine,
            consumer=type(self).__name__,
            required_tables=(
                "lineup_portfolio",
                "portfolio_lineup",
                "contest_entry_assignment",
            ),
        )

    @staticmethod
    def _build_assignment_plan(
        *,
        portfolio_id: str,
        template_id: str,
        template_rows: list[dict[str, Any]],
        lineup_ids: list[str],
        default_contest_id: str | None = None,
    ) -> list[EntryAssignment]:
        if not template_rows:
            raise ValueError("Entry template has no rows")
        if len(lineup_ids) != len(template_rows):
            raise ValueError(
                f"Optimizer run has {len(lineup_ids)} lineups for {len(template_rows)} entries"
            )
        if len(set(lineup_ids)) != len(lineup_ids):
            raise ValueError("lineup_ids must be unique")
        assignments: list[EntryAssignment] = []
        seen_entry_ids: set[str] = set()
        for index, (template_row, lineup_id) in enumerate(
            zip(template_rows, lineup_ids, strict=False),
            start=1,
        ):
            entry_id = str(template_row.get("entry_id") or "").strip()
            contest_id = str(template_row.get("contest_id") or default_contest_id or "").strip()
            if not entry_id:
                raise ValueError(f"Entry template row {template_row.get('row_number')} has no entry_id")
            if entry_id in seen_entry_ids:
                raise ValueError(f"Entry template contains duplicate entry_id: {entry_id}")
            seen_entry_ids.add(entry_id)
            if not contest_id:
                raise ValueError(
                    f"Entry template row {template_row.get('row_number')} has no contest_id"
                )
            assignments.append(
                EntryAssignment(
                    assignment_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{portfolio_id}|{template_id}|{template_row['row_number']}")),
                    portfolio_id=portfolio_id,
                    template_id=template_id,
                    template_row_number=int(template_row["row_number"]),
                    entry_id=entry_id,
                    contest_id=contest_id,
                    lineup_id=lineup_id,
                    portfolio_lineup_number=index,
                )
            )
        return assignments

    def create_portfolio(
        self,
        *,
        portfolio_name: str,
        optimizer_run_id: str,
        template_id: str,
        lineup_ids: list[str] | None = None,
        default_contest_id: str | None = None,
    ) -> PortfolioResult:
        self._ensure_schema()
        with self.engine.begin() as conn:
            optimizer = conn.execute(text("""
                SELECT optimizer_run_id, season, week, slate_id, contest_format, objective, status
                FROM target.optimizer_run WHERE optimizer_run_id = :optimizer_run_id
            """), {"optimizer_run_id": optimizer_run_id}).mappings().first()
            if not optimizer:
                raise ValueError(f"Optimizer run not found: {optimizer_run_id}")
            if optimizer["status"] != "completed":
                raise ValueError("Portfolio requires a completed optimizer run")
            template = conn.execute(text("""
                SELECT template_id, season, week, slate_id
                FROM target.dk_entry_template_file WHERE template_id = :template_id
            """), {"template_id": template_id}).mappings().first()
            if not template:
                raise ValueError(f"Entry template not found: {template_id}")
            optimizer_scope = (int(optimizer["season"]), int(optimizer["week"]), str(optimizer["slate_id"]))
            template_scope = (int(template["season"]), int(template["week"]), str(template["slate_id"]))
            if optimizer_scope != template_scope:
                raise ValueError(
                    f"Optimizer scope {optimizer_scope} does not match template scope {template_scope}"
                )
            template_rows = [dict(row) for row in conn.execute(text("""
                SELECT row_number, entry_id, contest_id
                FROM target.dk_entry_template_row
                WHERE template_id = :template_id ORDER BY row_number
            """), {"template_id": template_id}).mappings().all()]
            available_lineups = [str(row["lineup_id"]) for row in conn.execute(text("""
                SELECT lineup_id FROM target.lineup
                WHERE optimizer_run_id = :optimizer_run_id ORDER BY lineup_number
            """), {"optimizer_run_id": optimizer_run_id}).mappings().all()]

        selected_lineups = lineup_ids or available_lineups[: len(template_rows)]
        unavailable = sorted(set(selected_lineups).difference(available_lineups))
        if unavailable:
            raise ValueError(f"Lineups do not belong to optimizer run: {', '.join(unavailable)}")
        portfolio_id = str(uuid.uuid4())
        assignments = self._build_assignment_plan(
            portfolio_id=portfolio_id,
            template_id=template_id,
            template_rows=template_rows,
            lineup_ids=selected_lineups,
            default_contest_id=default_contest_id,
        )
        name = portfolio_name.strip()
        if not name:
            raise ValueError("portfolio_name is required")

        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO target.lineup_portfolio
                    (portfolio_id, portfolio_name, optimizer_run_id, template_id,
                     season, week, slate_id, contest_format, objective, status)
                VALUES (:portfolio_id, :portfolio_name, :optimizer_run_id, :template_id,
                        :season, :week, :slate, :contest_format, :objective, 'assigned')
            """), {"portfolio_id": portfolio_id, "portfolio_name": name,
                    "optimizer_run_id": optimizer_run_id, "template_id": template_id,
                    "season": optimizer_scope[0], "week": optimizer_scope[1],
                    "slate": optimizer_scope[2], "contest_format": optimizer["contest_format"],
                    "objective": optimizer["objective"]})
            conn.execute(text("""
                INSERT INTO target.portfolio_lineup
                    (portfolio_id, lineup_id, portfolio_lineup_number)
                VALUES (:portfolio_id, :lineup_id, :portfolio_lineup_number)
            """), [{"portfolio_id": portfolio_id, "lineup_id": row.lineup_id,
                     "portfolio_lineup_number": row.portfolio_lineup_number} for row in assignments])
            conn.execute(text("""
                INSERT INTO target.contest_entry_assignment
                    (assignment_id, portfolio_id, template_id, template_row_number,
                     entry_id, contest_id, lineup_id, status)
                VALUES (:assignment_id, :portfolio_id, :template_id, :template_row_number,
                        :entry_id, :contest_id, :lineup_id, 'assigned')
            """), [asdict(row) for row in assignments])

        return PortfolioResult(
            portfolio_id=portfolio_id,
            portfolio_name=name,
            optimizer_run_id=optimizer_run_id,
            template_id=template_id,
            season=optimizer_scope[0],
            week=optimizer_scope[1],
            slate=optimizer_scope[2],
            contest_format=str(optimizer["contest_format"]),
            objective=str(optimizer["objective"]),
            status="assigned",
            lineup_count=len(assignments),
            assignment_count=len(assignments),
            assignments=assignments,
        )

    def get_portfolio(self, portfolio_id: str) -> PortfolioResult | None:
        self._ensure_schema()
        with self.engine.begin() as conn:
            portfolio = conn.execute(text("""
                SELECT portfolio_id, portfolio_name, optimizer_run_id, template_id,
                       season, week, slate_id, contest_format, objective, status
                FROM target.lineup_portfolio WHERE portfolio_id = :portfolio_id
            """), {"portfolio_id": portfolio_id}).mappings().first()
            if not portfolio:
                return None
            rows = conn.execute(text("""
                SELECT assignment.assignment_id, assignment.portfolio_id,
                       assignment.template_id, assignment.template_row_number,
                       assignment.entry_id, assignment.contest_id, assignment.lineup_id,
                       portfolio_lineup.portfolio_lineup_number
                FROM target.contest_entry_assignment assignment
                JOIN target.portfolio_lineup portfolio_lineup
                  ON portfolio_lineup.portfolio_id = assignment.portfolio_id
                 AND portfolio_lineup.lineup_id = assignment.lineup_id
                WHERE assignment.portfolio_id = :portfolio_id
                ORDER BY assignment.template_row_number
            """), {"portfolio_id": portfolio_id}).mappings().all()
        assignments = [
            EntryAssignment(
                assignment_id=str(row["assignment_id"]),
                portfolio_id=str(row["portfolio_id"]),
                template_id=str(row["template_id"]),
                template_row_number=int(row["template_row_number"]),
                entry_id=str(row["entry_id"]),
                contest_id=str(row["contest_id"]),
                lineup_id=str(row["lineup_id"]),
                portfolio_lineup_number=int(row["portfolio_lineup_number"]),
            )
            for row in rows
        ]
        return PortfolioResult(
            portfolio_id=str(portfolio["portfolio_id"]),
            portfolio_name=str(portfolio["portfolio_name"]),
            optimizer_run_id=str(portfolio["optimizer_run_id"]),
            template_id=str(portfolio["template_id"]),
            season=int(portfolio["season"]),
            week=int(portfolio["week"]),
            slate=str(portfolio["slate_id"]),
            contest_format=str(portfolio["contest_format"]),
            objective=str(portfolio["objective"]),
            status=str(portfolio["status"]),
            lineup_count=len(assignments),
            assignment_count=len(assignments),
            assignments=assignments,
        )
