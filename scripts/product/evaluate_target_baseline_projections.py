#!/usr/bin/env python3
"""Evaluate target.player_projection rows against target actuals."""

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

from scripts.product.apply_target_schema_adapters import create_target_schema_sql, qident


@dataclass
class EvaluationResult:
    status: str
    learning_runs: int = 0
    projection_evaluations: int = 0
    symbolic_learning_runs: int = 0
    rule_evaluations: int = 0
    message: str = ""


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


def filters_sql(season: int | None, week: int | None, alias: str = "proj") -> tuple[str, dict[str, Any]]:
    clauses = []
    params: dict[str, Any] = {}
    if season is not None:
        clauses.append(f"{alias}.season = :season")
        params["season"] = season
    if week is not None:
        clauses.append(f"{alias}.week = :week")
        params["week"] = week
    return (" AND " + " AND ".join(clauses) if clauses else ""), params


def count_evaluable_rows(conn, target_schema: str, season: int | None, week: int | None) -> int:
    extra_filter, params = filters_sql(season, week)
    return int(
        conn.execute(
            text(
                f"""
                SELECT COUNT(*)
                FROM {qident(target_schema)}.player_projection proj
                JOIN {qident(target_schema)}.fact_player_game_actual actual
                  ON actual.season = proj.season
                 AND actual.week = proj.week
                 AND actual.game_id = proj.game_id
                 AND actual.player_id = proj.player_id
                WHERE actual.dk_points IS NOT NULL
                  AND proj.mean IS NOT NULL
                {extra_filter}
                """
            ),
            params,
        ).scalar()
        or 0
    )


def evaluate_projections(
    engine,
    target_schema: str = "target",
    season: int | None = None,
    week: int | None = None,
    dry_run: bool = False,
) -> EvaluationResult:
    s = qident(target_schema)
    extra_filter, params = filters_sql(season, week)

    with engine.begin() as conn:
        for statement in create_target_schema_sql(target_schema):
            conn.execute(text(statement))
        evaluable_rows = count_evaluable_rows(conn, target_schema, season, week)
        if dry_run:
            return EvaluationResult(status="would_evaluate", projection_evaluations=evaluable_rows)

        learning_runs = conn.execute(
            text(
                f"""
                WITH scored AS (
                    SELECT
                        proj.projection_run_id,
                        proj.season,
                        proj.week,
                        proj.mean,
                        proj.p90,
                        actual.dk_points AS actual_points,
                        ABS(proj.mean - actual.dk_points) AS absolute_error,
                        POWER(proj.mean - actual.dk_points, 2) AS squared_error
                    FROM {s}.player_projection proj
                    JOIN {s}.fact_player_game_actual actual
                      ON actual.season = proj.season
                     AND actual.week = proj.week
                     AND actual.game_id = proj.game_id
                     AND actual.player_id = proj.player_id
                    WHERE actual.dk_points IS NOT NULL
                      AND proj.mean IS NOT NULL
                    {extra_filter}
                ),
                grouped AS (
                    SELECT
                        projection_run_id,
                        season,
                        week,
                        COUNT(*) AS rows,
                        AVG(absolute_error) AS mae,
                        SQRT(AVG(squared_error)) AS rmse,
                        AVG(CASE WHEN actual_points <= p90 THEN 1.0 ELSE 0.0 END) AS p90_coverage
                    FROM scored
                    GROUP BY projection_run_id, season, week
                )
                INSERT INTO {s}.learning_run
                (learning_run_id, projection_run_id, rule_run_id, season, week, status,
                 projections_evaluated, rules_evaluated, metrics_json, recommendations_json)
                SELECT
                    'projection_eval:' || projection_run_id,
                    projection_run_id,
                    NULL::text,
                    season,
                    week,
                    'completed',
                    rows,
                    0,
                    jsonb_build_object('mae', mae, 'rmse', rmse, 'p90_coverage', p90_coverage),
                    '[]'::jsonb
                FROM grouped
                ON CONFLICT (learning_run_id) DO UPDATE SET
                    projections_evaluated = EXCLUDED.projections_evaluated,
                    metrics_json = EXCLUDED.metrics_json,
                    recommendations_json = EXCLUDED.recommendations_json,
                    status = EXCLUDED.status
                """
            ),
            params,
        ).rowcount or 0

        projection_evaluations = conn.execute(
            text(
                f"""
                INSERT INTO {s}.projection_evaluation
                (learning_run_id, projection_run_id, season, week, game_id, player_id,
                 projected_mean, projected_p90, actual_points, absolute_error, squared_error)
                SELECT
                    'projection_eval:' || proj.projection_run_id,
                    proj.projection_run_id,
                    proj.season,
                    proj.week,
                    proj.game_id,
                    proj.player_id,
                    proj.mean,
                    proj.p90,
                    actual.dk_points,
                    ABS(proj.mean - actual.dk_points),
                    POWER(proj.mean - actual.dk_points, 2)
                FROM {s}.player_projection proj
                JOIN {s}.fact_player_game_actual actual
                  ON actual.season = proj.season
                 AND actual.week = proj.week
                 AND actual.game_id = proj.game_id
                 AND actual.player_id = proj.player_id
                WHERE actual.dk_points IS NOT NULL
                  AND proj.mean IS NOT NULL
                {extra_filter}
                ON CONFLICT (learning_run_id, projection_run_id, game_id, player_id) DO UPDATE SET
                    projected_mean = EXCLUDED.projected_mean,
                    projected_p90 = EXCLUDED.projected_p90,
                    actual_points = EXCLUDED.actual_points,
                    absolute_error = EXCLUDED.absolute_error,
                    squared_error = EXCLUDED.squared_error
                """
            ),
            params,
        ).rowcount or 0

        symbolic_learning_runs = conn.execute(
            text(
                f"""
                WITH scored AS (
                    SELECT
                        adj.rule_run_id,
                        adj.projection_run_id,
                        adj.season,
                        adj.week,
                        adj.base_mean,
                        adj.adjusted_mean,
                        adj.adjusted_p90,
                        actual.dk_points AS actual_points,
                        ABS(adj.base_mean - actual.dk_points) AS base_absolute_error,
                        ABS(adj.adjusted_mean - actual.dk_points) AS adjusted_absolute_error
                    FROM {s}.symbolic_adjusted_projection adj
                    JOIN {s}.fact_player_game_actual actual
                      ON actual.season = adj.season
                     AND actual.week = adj.week
                     AND actual.game_id = adj.game_id
                     AND actual.player_id = adj.player_id
                    WHERE actual.dk_points IS NOT NULL
                      AND adj.adjusted_mean IS NOT NULL
                    {extra_filter.replace("proj.", "adj.")}
                ),
                grouped AS (
                    SELECT
                        rule_run_id,
                        projection_run_id,
                        season,
                        week,
                        COUNT(*) AS rows,
                        AVG(base_absolute_error) AS base_mae,
                        AVG(adjusted_absolute_error) AS adjusted_mae,
                        AVG(base_absolute_error - adjusted_absolute_error) AS mae_delta,
                        AVG(CASE WHEN actual_points <= adjusted_p90 THEN 1.0 ELSE 0.0 END) AS adjusted_p90_coverage
                    FROM scored
                    GROUP BY rule_run_id, projection_run_id, season, week
                )
                INSERT INTO {s}.learning_run
                (learning_run_id, projection_run_id, rule_run_id, season, week, status,
                 projections_evaluated, rules_evaluated, metrics_json, recommendations_json)
                SELECT
                    'symbolic_eval:' || rule_run_id,
                    projection_run_id,
                    rule_run_id,
                    season,
                    week,
                    'completed',
                    rows,
                    0,
                    jsonb_build_object(
                        'base_mae', base_mae,
                        'adjusted_mae', adjusted_mae,
                        'mae_delta', mae_delta,
                        'adjusted_p90_coverage', adjusted_p90_coverage
                    ),
                    '[]'::jsonb
                FROM grouped
                ON CONFLICT (learning_run_id) DO UPDATE SET
                    projections_evaluated = EXCLUDED.projections_evaluated,
                    metrics_json = EXCLUDED.metrics_json,
                    recommendations_json = EXCLUDED.recommendations_json,
                    status = EXCLUDED.status
                """
            ),
            params,
        ).rowcount or 0

        rule_evaluations = conn.execute(
            text(
                f"""
                INSERT INTO {s}.rule_evaluation
                (learning_run_id, rule_run_id, rule_id, rule_version, season, week, game_id, player_id,
                 mean_before, mean_after, actual_points, mae_before, mae_after, improved, delta_mae)
                SELECT
                    'symbolic_eval:' || app.rule_run_id,
                    app.rule_run_id,
                    app.rule_id,
                    app.rule_version,
                    adj.season,
                    adj.week,
                    adj.game_id,
                    app.player_id,
                    app.mean_before,
                    app.mean_after,
                    actual.dk_points,
                    ABS(app.mean_before - actual.dk_points),
                    ABS(app.mean_after - actual.dk_points),
                    ABS(app.mean_after - actual.dk_points) < ABS(app.mean_before - actual.dk_points),
                    ABS(app.mean_before - actual.dk_points) - ABS(app.mean_after - actual.dk_points)
                FROM {s}.symbolic_rule_application app
                JOIN {s}.symbolic_adjusted_projection adj
                  ON adj.rule_run_id = app.rule_run_id
                 AND adj.projection_run_id = app.projection_run_id
                 AND adj.player_id = app.player_id
                JOIN {s}.fact_player_game_actual actual
                  ON actual.season = adj.season
                 AND actual.week = adj.week
                 AND actual.game_id = adj.game_id
                 AND actual.player_id = adj.player_id
                WHERE actual.dk_points IS NOT NULL
                {extra_filter.replace("proj.", "adj.")}
                """
            ),
            params,
        ).rowcount or 0

        conn.execute(
            text(
                f"""
                WITH rule_counts AS (
                    SELECT learning_run_id, COUNT(DISTINCT rule_id) AS rules_evaluated
                    FROM {s}.rule_evaluation
                    GROUP BY learning_run_id
                )
                UPDATE {s}.learning_run run
                SET rules_evaluated = rule_counts.rules_evaluated
                FROM rule_counts
                WHERE run.learning_run_id = rule_counts.learning_run_id
                """
            )
        )

    return EvaluationResult(
        status="completed",
        learning_runs=int(learning_runs),
        projection_evaluations=int(projection_evaluations),
        symbolic_learning_runs=int(symbolic_learning_runs),
        rule_evaluations=int(rule_evaluations),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate target-native player projections.")
    parser.add_argument("--database", help="Postgres database name. Defaults to PGDATABASE.")
    parser.add_argument("--host", help="Postgres host. Defaults to PGHOST or localhost.")
    parser.add_argument("--port", help="Postgres port. Defaults to PGPORT or 5432.")
    parser.add_argument("--user", help="Postgres user. Defaults to PGUSER.")
    parser.add_argument("--password", help="Postgres password. Defaults to PGPASSWORD.")
    parser.add_argument("--target-schema", default="target")
    parser.add_argument("--season", type=int)
    parser.add_argument("--week", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    if args.week is not None and args.season is None:
        parser.error("--week requires --season")

    engine = create_engine(build_connection_url(args))
    result = evaluate_projections(
        engine=engine,
        target_schema=args.target_schema,
        season=args.season,
        week=args.week,
        dry_run=args.dry_run,
    )
    payload = {
        "database": args.database or os.getenv("PGDATABASE"),
        "target_schema": args.target_schema,
        "season": args.season,
        "week": args.week,
        "dry_run": args.dry_run,
        **asdict(result),
    }
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
