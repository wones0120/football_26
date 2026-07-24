#!/usr/bin/env python3
"""Simulate week-by-week target rule policy evolution without mutating rules."""

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
from scripts.product.report_target_rule_learning import CONTEST_PROFILES, contest_profile_sql, report_rule_learning, validate_contest_profile
from scripts.product.replay_target_rule_evolution import previous_cutoff, target_weeks


POLICY_MULTIPLIERS = {
    "collect_more_data": 1.0,
    "keep_under_review": 1.0,
    "keep": 1.0,
    "reduce": 0.5,
    "consider_disable_or_reduce": 0.0,
    "consider_increase": 1.25,
}


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


def policy_multiplier(action: str) -> float:
    return POLICY_MULTIPLIERS.get(action, 1.0)


def adjusted_with_policy(base_mean: float, static_adjusted_mean: float, multiplier: float) -> float:
    return base_mean + ((static_adjusted_mean - base_mean) * multiplier)


def mae(rows: list[dict[str, float]], key: str) -> float:
    if not rows:
        return 0.0
    return sum(abs(row[key] - row["actual_points"]) for row in rows) / len(rows)


def load_week_applications(
    engine, target_schema: str, season: int, week: int, contest_profile: str = "all"
) -> list[dict[str, Any]]:
    profile_clause, profile_params = contest_profile_sql(contest_profile)
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT
                    app.rule_id,
                    adj.projection_run_id,
                    adj.game_id,
                    adj.player_id,
                    app.mean_before AS base_mean,
                    app.mean_after AS static_adjusted_mean,
                    actual.dk_points AS actual_points
                FROM {qident(target_schema)}.symbolic_rule_application app
                JOIN {qident(target_schema)}.symbolic_adjusted_projection adj
                  ON adj.rule_run_id = app.rule_run_id
                 AND adj.projection_run_id = app.projection_run_id
                 AND adj.player_id = app.player_id
                JOIN {qident(target_schema)}.fact_player_game_actual actual
                  ON actual.season = adj.season
                 AND actual.week = adj.week
                 AND actual.game_id = adj.game_id
                 AND actual.player_id = adj.player_id
                LEFT JOIN {qident(target_schema)}.symbolic_rule_version version
                  ON version.rule_id = app.rule_id
                 AND version.rule_version = app.rule_version
                WHERE adj.season = :season
                  AND adj.week = :week
                  AND actual.dk_points IS NOT NULL
                {profile_clause}
                """
            ),
            {"season": season, "week": week, **profile_params},
        ).mappings().all()
    return [
        {
            "rule_id": str(row["rule_id"]),
            "projection_run_id": str(row["projection_run_id"]),
            "game_id": str(row["game_id"]),
            "player_id": str(row["player_id"]),
            "base_mean": float(row["base_mean"] or 0.0),
            "static_adjusted_mean": float(row["static_adjusted_mean"] or 0.0),
            "actual_points": float(row["actual_points"] or 0.0),
        }
        for row in rows
    ]


def policies_from_report(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    policies = {}
    for rule in report.get("rules", []):
        action = rule.get("recommendation", {}).get("action", "keep_under_review")
        policies[str(rule["rule_id"])] = {
            "action": action,
            "multiplier": policy_multiplier(action),
            "rows": int(rule.get("rows", 0) or 0),
            "avg_delta_mae": float(rule.get("avg_delta_mae", 0.0) or 0.0),
            "hit_rate": float(rule.get("hit_rate", 0.0) or 0.0),
        }
    return policies


def simulate_policy_replay(
    engine, target_schema: str = "target", season: int = 2025, contest_profile: str = "all"
) -> dict[str, Any]:
    contest_profile = validate_contest_profile(contest_profile)
    steps = []
    all_rows: list[dict[str, float]] = []

    for week in target_weeks(engine, target_schema, season):
        cutoff_season, cutoff_week = previous_cutoff(season, week)
        report = report_rule_learning(
            engine=engine,
            target_schema=target_schema,
            through_season=cutoff_season,
            through_week=cutoff_week,
            contest_profile=contest_profile,
        )
        policies = policies_from_report(report)
        week_rows = []
        for row in load_week_applications(engine, target_schema, season, week, contest_profile=contest_profile):
            policy = policies.get(row["rule_id"], {"action": "collect_more_data", "multiplier": 1.0})
            evolving_mean = adjusted_with_policy(
                base_mean=row["base_mean"],
                static_adjusted_mean=row["static_adjusted_mean"],
                multiplier=float(policy["multiplier"]),
            )
            week_rows.append(
                {
                    "base_mean": row["base_mean"],
                    "static_adjusted_mean": row["static_adjusted_mean"],
                    "evolving_adjusted_mean": evolving_mean,
                    "actual_points": row["actual_points"],
                }
            )

        all_rows.extend(week_rows)
        steps.append(
            {
                "target_season": season,
                "target_week": week,
                "evidence_through": {"season": cutoff_season, "week": cutoff_week},
                "applications": len(week_rows),
                "base_mae": mae(week_rows, "base_mean"),
                "static_symbolic_mae": mae(week_rows, "static_adjusted_mean"),
                "evolving_symbolic_mae": mae(week_rows, "evolving_adjusted_mean"),
                "policies": policies,
            }
        )

    return {
        "target_schema": target_schema,
        "contest_profile": contest_profile,
        "season": season,
        "weeks": len(steps),
        "applications": len(all_rows),
        "overall": {
            "base_mae": mae(all_rows, "base_mean"),
            "static_symbolic_mae": mae(all_rows, "static_adjusted_mean"),
            "evolving_symbolic_mae": mae(all_rows, "evolving_adjusted_mean"),
            "static_delta_vs_base": mae(all_rows, "base_mean") - mae(all_rows, "static_adjusted_mean"),
            "evolving_delta_vs_base": mae(all_rows, "base_mean") - mae(all_rows, "evolving_adjusted_mean"),
            "evolving_delta_vs_static": mae(all_rows, "static_adjusted_mean") - mae(all_rows, "evolving_adjusted_mean"),
        },
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate target rule policy evolution by season/week.")
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
    report = simulate_policy_replay(
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
