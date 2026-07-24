#!/usr/bin/env python3
"""Report GPP-specific target rule performance using spike and value metrics."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.product.apply_target_schema_adapters import qident
from scripts.product.report_target_rule_learning import cutoff_sql


MIN_GPP_ROWS_FOR_ACTION = 50


@dataclass(frozen=True)
class GppRecommendation:
    action: str
    severity: str
    rationale: str


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


def recommend_gpp_rule(rows: int, top_decile_rate: float, value_4x_rate: float) -> GppRecommendation:
    if rows < MIN_GPP_ROWS_FOR_ACTION:
        return GppRecommendation(
            action="collect_more_data",
            severity="info",
            rationale=f"Only {rows} GPP applications; wait for at least {MIN_GPP_ROWS_FOR_ACTION}.",
        )
    if top_decile_rate >= 0.15 and value_4x_rate >= 0.20:
        return GppRecommendation(
            action="consider_increase",
            severity="positive",
            rationale="Rule is finding both top-decile outcomes and strong salary value.",
        )
    if top_decile_rate >= 0.10 or value_4x_rate >= 0.15:
        return GppRecommendation(
            action="keep",
            severity="neutral",
            rationale="Rule is finding some useful GPP spike/value outcomes.",
        )
    return GppRecommendation(
        action="reduce_or_rework",
        severity="negative",
        rationale="Rule is not finding enough spike or salary-value outcomes for GPP use.",
    )


def report_gpp_learning(
    engine,
    target_schema: str = "target",
    through_season: int | None = None,
    through_week: int | None = None,
) -> dict[str, Any]:
    s = qident(target_schema)
    cutoff_clause, params = cutoff_sql(through_season, through_week, alias="adj")
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                WITH actual_distribution AS (
                    SELECT
                        actual.season,
                        actual.week,
                        actual.game_id,
                        actual.player_id,
                        actual.dk_points,
                        percent_rank() OVER (
                            PARTITION BY actual.season, actual.week
                            ORDER BY actual.dk_points
                        ) AS week_percentile
                    FROM {s}.fact_player_game_actual actual
                    WHERE actual.dk_points IS NOT NULL
                ),
                scored AS (
                    SELECT
                        app.rule_id,
                        COALESCE(rule.rule_name, app.rule_id) AS rule_name,
                        adj.season,
                        adj.week,
                        adj.base_p90,
                        adj.adjusted_p90,
                        dist.dk_points AS actual_points,
                        dist.week_percentile,
                        salary.salary
                    FROM {s}.symbolic_rule_application app
                    JOIN {s}.symbolic_adjusted_projection adj
                      ON adj.rule_run_id = app.rule_run_id
                     AND adj.projection_run_id = app.projection_run_id
                     AND adj.player_id = app.player_id
                    JOIN actual_distribution dist
                      ON dist.season = adj.season
                     AND dist.week = adj.week
                     AND dist.game_id = adj.game_id
                     AND dist.player_id = adj.player_id
                    JOIN {s}.symbolic_rule_version version
                      ON version.rule_id = app.rule_id
                     AND version.rule_version = app.rule_version
                    LEFT JOIN {s}.symbolic_rule rule ON rule.rule_id = app.rule_id
                    LEFT JOIN LATERAL (
                        SELECT salary
                        FROM {s}.snapshot_salary salary
                        WHERE salary.season = adj.season
                          AND salary.week = adj.week
                          AND salary.player_id = adj.player_id
                        ORDER BY salary.as_of DESC NULLS LAST
                        LIMIT 1
                    ) salary ON TRUE
                    WHERE version.action_json->'contest_profiles' ? 'gpp'
                    {cutoff_clause}
                )
                SELECT
                    rule_id,
                    rule_name,
                    COUNT(*) AS rows,
                    COUNT(DISTINCT season::text || ':' || week::text) AS weeks,
                    AVG(actual_points) AS avg_actual_points,
                    AVG(salary) AS avg_salary,
                    AVG(CASE WHEN actual_points >= 20 THEN 1.0 ELSE 0.0 END) AS spike_20_rate,
                    AVG(CASE WHEN week_percentile >= 0.80 THEN 1.0 ELSE 0.0 END) AS top_quintile_rate,
                    AVG(CASE WHEN week_percentile >= 0.90 THEN 1.0 ELSE 0.0 END) AS top_decile_rate,
                    AVG(CASE WHEN salary > 0 AND actual_points >= (salary / 1000.0) * 3.0 THEN 1.0 ELSE 0.0 END) AS value_3x_rate,
                    AVG(CASE WHEN salary > 0 AND actual_points >= (salary / 1000.0) * 4.0 THEN 1.0 ELSE 0.0 END) AS value_4x_rate,
                    AVG(CASE WHEN actual_points >= base_p90 THEN 1.0 ELSE 0.0 END) AS base_p90_hit_rate,
                    AVG(CASE WHEN actual_points >= adjusted_p90 THEN 1.0 ELSE 0.0 END) AS adjusted_p90_hit_rate
                FROM scored
                GROUP BY rule_id, rule_name
                ORDER BY top_decile_rate DESC, value_4x_rate DESC, rows DESC
                """
            ),
            params,
        ).fetchall()

    rules = []
    for row in rows:
        count = int(row.rows or 0)
        top_decile_rate = float(row.top_decile_rate or 0.0)
        value_4x_rate = float(row.value_4x_rate or 0.0)
        recommendation = recommend_gpp_rule(count, top_decile_rate, value_4x_rate)
        rules.append(
            {
                "rule_id": str(row.rule_id),
                "rule_name": str(row.rule_name),
                "rows": count,
                "weeks": int(row.weeks or 0),
                "avg_actual_points": float(row.avg_actual_points or 0.0),
                "avg_salary": float(row.avg_salary or 0.0),
                "spike_20_rate": float(row.spike_20_rate or 0.0),
                "top_quintile_rate": float(row.top_quintile_rate or 0.0),
                "top_decile_rate": top_decile_rate,
                "value_3x_rate": float(row.value_3x_rate or 0.0),
                "value_4x_rate": value_4x_rate,
                "base_p90_hit_rate": float(row.base_p90_hit_rate or 0.0),
                "adjusted_p90_hit_rate": float(row.adjusted_p90_hit_rate or 0.0),
                "recommendation": asdict(recommendation),
            }
        )

    return {
        "target_schema": target_schema,
        "contest_profile": "gpp",
        "cutoff": {"through_season": through_season, "through_week": through_week},
        "rules_evaluated": len(rules),
        "applications_evaluated": sum(row["rows"] for row in rules),
        "rules": rules,
        "data_gaps": [
            "ownership projections are not loaded, so leverage cannot be scored yet",
            "lineup portfolio results are not loaded, so top-percentile lineup outcomes cannot be scored yet",
            "correlation/stack outcomes are not loaded, so game-stack quality cannot be scored yet",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Report GPP-specific target symbolic rule learning.")
    parser.add_argument("--database", help="Postgres database name. Defaults to PGDATABASE.")
    parser.add_argument("--host", help="Postgres host. Defaults to PGHOST or localhost.")
    parser.add_argument("--port", help="Postgres port. Defaults to PGPORT or 5432.")
    parser.add_argument("--user", help="Postgres user. Defaults to PGUSER.")
    parser.add_argument("--password", help="Postgres password. Defaults to PGPASSWORD.")
    parser.add_argument("--target-schema", default="target")
    parser.add_argument("--through-season", type=int)
    parser.add_argument("--through-week", type=int)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    engine = create_engine(build_connection_url(args))
    report = report_gpp_learning(
        engine=engine,
        target_schema=args.target_schema,
        through_season=args.through_season,
        through_week=args.through_week,
    )
    report["database"] = args.database or os.getenv("PGDATABASE")
    print(json.dumps(report, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
