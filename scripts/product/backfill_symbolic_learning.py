#!/usr/bin/env python3
"""Backfill symbolic learning evaluations across historical completed weeks."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Database.config import get_connection_string
from backend.app.product_services.agent import NewsMatchupAgent


REQUIRED_TABLES = {"nfl_weekly_data_with_scores", "player_expected_points"}


@dataclass
class WeekState:
    season: int
    week: int
    actual_rows: int = 0
    projection_rows: int = 0
    adjusted_rows: int = 0
    learning_rows: int = 0
    latest_rule_run_id: str | None = None


@dataclass
class WeekBackfillResult:
    season: int
    week: int
    status: str
    message: str
    rule_run_id: str | None = None
    adjusted_rows: int = 0
    learning_run_id: str | None = None
    projection_snapshots: int = 0
    rule_evaluations: int = 0


def existing_tables(engine) -> set[str]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                """
            )
        ).fetchall()
    return {str(row.tablename) for row in rows}


def validate_required_tables(engine) -> None:
    missing = sorted(REQUIRED_TABLES - existing_tables(engine))
    if missing:
        raise RuntimeError(
            "Missing required table(s): "
            + ", ".join(missing)
            + ". Load/build historical actuals and projections before running symbolic learning backfill."
        )


def _scalar(conn, query: str, params: dict) -> int:
    try:
        value = conn.execute(text(query), params).scalar()
    except SQLAlchemyError:
        return 0
    return int(value or 0)


def completed_weeks(engine, season: int | None = None, week: int | None = None, limit: int | None = None) -> list[WeekState]:
    where = []
    params: dict = {}
    if season is not None:
        where.append("season = :season")
        params["season"] = season
    if week is not None:
        where.append("week = :week")
        params["week"] = week
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""
    limit_clause = "LIMIT :limit" if limit else ""
    if limit:
        params["limit"] = limit
    query = f"""
        SELECT season, week, COUNT(*) AS actual_rows
        FROM nfl_weekly_data_with_scores
        {where_clause}
        GROUP BY season, week
        ORDER BY season, week
        {limit_clause}
    """
    try:
        with engine.begin() as conn:
            rows = conn.execute(text(query), params).fetchall()
    except SQLAlchemyError:
        return []
    return [WeekState(season=int(row.season), week=int(row.week), actual_rows=int(row.actual_rows or 0)) for row in rows]


def load_week_state(engine, season: int, week: int, slate: str | None = None) -> WeekState:
    params = {"season": season, "week": week, "slate": slate}
    slate_filter = "AND (slate = :slate OR slate IS NULL)" if slate else ""
    with engine.begin() as conn:
        actual_rows = _scalar(
            conn,
            "SELECT COUNT(*) FROM nfl_weekly_data_with_scores WHERE season = :season AND week = :week",
            params,
        )
        projection_rows = _scalar(
            conn,
            f"SELECT COUNT(*) FROM player_expected_points WHERE season = :season AND week = :week {slate_filter}",
            params,
        )
        adjusted_rows = _scalar(
            conn,
            f"SELECT COUNT(*) FROM player_expected_points_adjusted WHERE season = :season AND week = :week {slate_filter}",
            params,
        )
        try:
            latest_rule_run_id = conn.execute(
                text(
                    f"""
                    SELECT rule_run_id
                    FROM player_expected_points_adjusted
                    WHERE season = :season AND week = :week {slate_filter}
                    GROUP BY rule_run_id
                    ORDER BY MAX(created_at) DESC
                    LIMIT 1
                    """
                ),
                params,
            ).scalar()
        except SQLAlchemyError:
            latest_rule_run_id = None
        learning_rows = 0
        if latest_rule_run_id:
            learning_rows = _scalar(
                conn,
                """
                SELECT COUNT(*)
                FROM symbolic_learning_runs
                WHERE season = :season AND week = :week AND rule_run_id = :rule_run_id
                """,
                {**params, "rule_run_id": latest_rule_run_id},
            )
    return WeekState(
        season=season,
        week=week,
        actual_rows=actual_rows,
        projection_rows=projection_rows,
        adjusted_rows=adjusted_rows,
        learning_rows=learning_rows,
        latest_rule_run_id=str(latest_rule_run_id) if latest_rule_run_id else None,
    )


def backfill_week(
    agent: NewsMatchupAgent,
    season: int,
    week: int,
    slate: str | None = None,
    dry_run: bool = False,
    force_agent: bool = False,
    force_learning: bool = False,
) -> WeekBackfillResult:
    state = load_week_state(agent.engine, season=season, week=week, slate=slate)
    if state.actual_rows == 0:
        return WeekBackfillResult(season, week, "skipped", "No actuals found.")
    if state.projection_rows == 0:
        return WeekBackfillResult(season, week, "skipped", "No base projections found.")

    rule_run_id = state.latest_rule_run_id
    adjusted_rows = state.adjusted_rows
    if force_agent or adjusted_rows == 0:
        if dry_run:
            return WeekBackfillResult(
                season,
                week,
                "would_run_agent",
                "Would run symbolic agent, then learning evaluation.",
                rule_run_id=rule_run_id,
                adjusted_rows=adjusted_rows,
            )
        _, adjustments, config, _ = agent.run(season, week)
        rule_run_id = config.rule_run_id
        adjusted_rows = len(adjustments)

    if not rule_run_id:
        return WeekBackfillResult(season, week, "skipped", "No adjusted projection run available.")

    refreshed = load_week_state(agent.engine, season=season, week=week, slate=slate)
    if refreshed.learning_rows > 0 and not force_learning:
        return WeekBackfillResult(
            season,
            week,
            "skipped",
            "Learning run already exists for latest rule run.",
            rule_run_id=rule_run_id,
            adjusted_rows=refreshed.adjusted_rows,
        )

    if dry_run:
        return WeekBackfillResult(
            season,
            week,
            "would_evaluate",
            "Would persist symbolic learning evaluation.",
            rule_run_id=rule_run_id,
            adjusted_rows=refreshed.adjusted_rows,
        )

    evaluation = agent.evaluate_learning(season=season, week=week, rule_run_id=rule_run_id, slate=slate)
    rows_written = evaluation.get("rows_written", {})
    return WeekBackfillResult(
        season=season,
        week=week,
        status=str(evaluation.get("status", "completed")),
        message=str(evaluation.get("message", "Learning evaluation completed.")),
        rule_run_id=rule_run_id,
        adjusted_rows=refreshed.adjusted_rows,
        learning_run_id=evaluation.get("learning_run_id"),
        projection_snapshots=int(rows_written.get("projection_snapshots", 0) or 0),
        rule_evaluations=int(rows_written.get("rule_evaluations", 0) or 0),
    )


def backfill(
    agent: NewsMatchupAgent,
    weeks: Iterable[WeekState],
    slate: str | None = None,
    dry_run: bool = False,
    force_agent: bool = False,
    force_learning: bool = False,
) -> list[WeekBackfillResult]:
    results = []
    for item in weeks:
        try:
            results.append(
                backfill_week(
                    agent=agent,
                    season=item.season,
                    week=item.week,
                    slate=slate,
                    dry_run=dry_run,
                    force_agent=force_agent,
                    force_learning=force_learning,
                )
            )
        except Exception as exc:  # noqa: BLE001
            results.append(WeekBackfillResult(item.season, item.week, "failed", str(exc)))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill symbolic learning evaluations for historical weeks.")
    parser.add_argument("--season", type=int, help="Restrict to one season.")
    parser.add_argument("--week", type=int, help="Restrict to one week. Requires --season for clarity.")
    parser.add_argument("--slate", help="Optional slate filter for adjusted/evaluation reads.")
    parser.add_argument("--limit", type=int, help="Limit completed season/week pairs processed.")
    parser.add_argument("--dry-run", action="store_true", help="Report work without writing adjusted/evaluation rows.")
    parser.add_argument("--force-agent", action="store_true", help="Run symbolic agent even when adjusted rows exist.")
    parser.add_argument("--force-learning", action="store_true", help="Write a new learning run even if one already exists.")
    args = parser.parse_args()

    if args.week is not None and args.season is None:
        parser.error("--week requires --season")

    engine = create_engine(get_connection_string())
    agent = NewsMatchupAgent(engine=engine)
    agent._ensure_symbolic_schema()
    validate_required_tables(engine)
    weeks = completed_weeks(engine, season=args.season, week=args.week, limit=args.limit)
    results = backfill(
        agent=agent,
        weeks=weeks,
        slate=args.slate,
        dry_run=args.dry_run,
        force_agent=args.force_agent,
        force_learning=args.force_learning,
    )
    summary = {
        "dry_run": args.dry_run,
        "weeks_found": len(weeks),
        "processed": sum(1 for row in results if row.status == "completed"),
        "skipped": sum(1 for row in results if row.status == "skipped"),
        "failed": sum(1 for row in results if row.status == "failed"),
        "would_run_agent": sum(1 for row in results if row.status == "would_run_agent"),
        "would_evaluate": sum(1 for row in results if row.status == "would_evaluate"),
        "results": [asdict(row) for row in results],
    }
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
