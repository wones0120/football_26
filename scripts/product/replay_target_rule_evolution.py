#!/usr/bin/env python3
"""Replay how target symbolic rule recommendations evolve week by week."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.product.apply_target_schema_adapters import qident
from scripts.product.report_target_rule_learning import CONTEST_PROFILES, report_rule_learning, validate_contest_profile


ACTIONABLE_RECOMMENDATIONS = {"consider_increase", "reduce", "consider_disable_or_reduce"}


def build_connection_url(args: argparse.Namespace) -> URL:
    database = args.database or os.getenv("PGDATABASE")
    if not database:
        raise RuntimeError("Database is required. Pass --database or set PGDATABASE.")
    return URL.create(
        drivername="postgresql",
        username=args.user or os.getenv("PGUSER"),
        password=args.password or os.getenv("PGPASSWORD"),
        host=args.host or os.getenv("PGHOST", "localhost"),
        port=int(args.port or os.getenv("PGPORT", "5432")),
        database=database,
    )


def previous_cutoff(season: int, week: int) -> tuple[int, int | None]:
    if week <= 1:
        return season - 1, None
    return season, week - 1


def target_weeks(engine, target_schema: str, season: int) -> list[int]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT DISTINCT week
                FROM {qident(target_schema)}.player_projection
                WHERE season = :season
                ORDER BY week
                """
            ),
            {"season": season},
        ).fetchall()
    return [int(row.week) for row in rows]


def summarize_rule(rule: dict[str, Any]) -> dict[str, Any]:
    recommendation = rule.get("recommendation", {})
    return {
        "rule_id": rule.get("rule_id"),
        "rule_name": rule.get("rule_name"),
        "rows": rule.get("rows", 0),
        "avg_delta_mae": rule.get("avg_delta_mae", 0.0),
        "hit_rate": rule.get("hit_rate", 0.0),
        "action": recommendation.get("action", "unknown"),
        "severity": recommendation.get("severity", "unknown"),
        "rationale": recommendation.get("rationale", ""),
    }


def replay_rule_evolution(
    engine, target_schema: str = "target", season: int = 2025, contest_profile: str = "all"
) -> dict[str, Any]:
    contest_profile = validate_contest_profile(contest_profile)
    weeks = target_weeks(engine, target_schema, season)
    steps = []
    for week in weeks:
        cutoff_season, cutoff_week = previous_cutoff(season, week)
        report = report_rule_learning(
            engine=engine,
            target_schema=target_schema,
            through_season=cutoff_season,
            through_week=cutoff_week,
            contest_profile=contest_profile,
        )
        rules = [summarize_rule(rule) for rule in report["rules"]]
        actionable = [rule for rule in rules if rule["action"] in ACTIONABLE_RECOMMENDATIONS]
        steps.append(
            {
                "target_season": season,
                "target_week": week,
                "evidence_through": {"season": cutoff_season, "week": cutoff_week},
                "applications_evaluated": report["applications_evaluated"],
                "rules_evaluated": report["rules_evaluated"],
                "actionable_recommendations": len(actionable),
                "rules": rules,
            }
        )

    return {
        "target_schema": target_schema,
        "contest_profile": contest_profile,
        "season": season,
        "weeks": len(steps),
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay target symbolic rule recommendations week by week.")
    parser.add_argument("--database", help="Postgres database name. Defaults to PGDATABASE.")
    parser.add_argument("--host", help="Postgres host. Defaults to PGHOST or localhost.")
    parser.add_argument("--port", help="Postgres port. Defaults to PGPORT or 5432.")
    parser.add_argument("--user", help="Postgres user. Defaults to PGUSER.")
    parser.add_argument("--password", help="Postgres password. Defaults to PGPASSWORD.")
    parser.add_argument("--target-schema", default="target")
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--contest-profile", default="all", choices=sorted(CONTEST_PROFILES))
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    engine = create_engine(build_connection_url(args))
    report = replay_rule_evolution(
        engine=engine,
        target_schema=args.target_schema,
        season=args.season,
        contest_profile=args.contest_profile,
    )
    report["database"] = args.database or os.getenv("PGDATABASE")
    print(json.dumps(report, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
