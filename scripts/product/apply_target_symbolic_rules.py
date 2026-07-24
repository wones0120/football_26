#!/usr/bin/env python3
"""Apply target-native symbolic rules to target.player_projection rows."""

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


RULE_SET_ID = "injury_symbolic_v0"
RULES_LOADED = 4


@dataclass
class SymbolicRunResult:
    status: str
    rule_rows: int = 0
    rule_version_rows: int = 0
    rule_runs: int = 0
    rule_applications: int = 0
    adjusted_projection_rows: int = 0
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


def count_projection_rows(conn, target_schema: str, season: int | None, week: int | None) -> int:
    extra_filter, params = filters_sql(season, week)
    return int(
        conn.execute(
            text(
                f"""
                SELECT COUNT(*)
                FROM {qident(target_schema)}.player_projection proj
                WHERE proj.mean IS NOT NULL
                {extra_filter}
                """
            ),
            params,
        ).scalar()
        or 0
    )


def apply_symbolic_rules(
    engine,
    target_schema: str = "target",
    season: int | None = None,
    week: int | None = None,
    dry_run: bool = False,
) -> SymbolicRunResult:
    s = qident(target_schema)
    extra_filter, params = filters_sql(season, week)

    with engine.begin() as conn:
        for statement in create_target_schema_sql(target_schema):
            conn.execute(text(statement))

        candidate_rows = count_projection_rows(conn, target_schema, season, week)
        if dry_run:
            return SymbolicRunResult(status="would_apply", adjusted_projection_rows=candidate_rows)

        rule_rows = conn.execute(
            text(
                f"""
                INSERT INTO {s}.symbolic_rule (rule_id, rule_name, rule_type)
                VALUES
                    ('target_injury_negative', 'Target Injury Downgrade', 'injury'),
                    ('target_injury_positive', 'Target Positive Injury Note', 'injury'),
                    ('target_salary_value_boost', 'Target Salary Value Boost', 'salary_value'),
                    ('target_expensive_low_projection_penalty', 'Target Expensive Low Projection Penalty', 'salary_value')
                ON CONFLICT (rule_id) DO UPDATE SET
                    rule_name = EXCLUDED.rule_name,
                    rule_type = EXCLUDED.rule_type
                """
            )
        ).rowcount or 0

        rule_version_rows = conn.execute(
            text(
                f"""
                INSERT INTO {s}.symbolic_rule_version
                (rule_id, rule_version, enabled, priority, condition_json, action_json)
                VALUES
                    (
                        'target_injury_negative',
                        1,
                        TRUE,
                        10,
                        jsonb_build_object('status_tokens', ARRAY['Q', 'D', 'O', 'OUT', 'IR', 'DOUBTFUL']),
                        jsonb_build_object(
                            'mean_multiplier', 0.92,
                            'p90_multiplier', 0.92,
                            'reason', 'Target injury downgrade',
                            'contest_profiles', ARRAY['cash', 'gpp']
                        )
                    ),
                    (
                        'target_injury_positive',
                        1,
                        TRUE,
                        20,
                        jsonb_build_object('status_tokens', ARRAY['P', 'ACTIVE', 'PROBABLE']),
                        jsonb_build_object(
                            'mean_multiplier', 1.05,
                            'p90_multiplier', 1.05,
                            'reason', 'Target positive injury note',
                            'contest_profiles', ARRAY['cash', 'gpp']
                        )
                    ),
                    (
                        'target_salary_value_boost',
                        1,
                        TRUE,
                        30,
                        jsonb_build_object('salary_lte', 4000, 'mean_gte', 8.0),
                        jsonb_build_object(
                            'mean_multiplier', 1.03,
                            'p90_multiplier', 1.03,
                            'reason', 'Low salary value boost',
                            'contest_profiles', ARRAY['gpp']
                        )
                    ),
                    (
                        'target_expensive_low_projection_penalty',
                        1,
                        TRUE,
                        40,
                        jsonb_build_object('salary_gte', 8000, 'mean_lt', 15.0),
                        jsonb_build_object(
                            'mean_multiplier', 0.97,
                            'p90_multiplier', 0.97,
                            'reason', 'Expensive low-projection penalty',
                            'contest_profiles', ARRAY['cash']
                        )
                    )
                ON CONFLICT (rule_id, rule_version) DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    priority = EXCLUDED.priority,
                    condition_json = EXCLUDED.condition_json,
                    action_json = EXCLUDED.action_json,
                    retired_at = NULL
                """
            )
        ).rowcount or 0

        conn.execute(
            text(
                f"""
                WITH scoped_runs AS (
                    SELECT DISTINCT
                        :rule_set_id || ':' || projection_run_id AS rule_run_id,
                        projection_run_id
                    FROM {s}.player_projection proj
                    WHERE proj.mean IS NOT NULL
                    {extra_filter}
                )
                DELETE FROM {s}.symbolic_rule_application app
                USING scoped_runs
                WHERE app.rule_run_id = scoped_runs.rule_run_id
                """
            ),
            {**params, "rule_set_id": RULE_SET_ID},
        )
        conn.execute(
            text(
                f"""
                WITH scoped_runs AS (
                    SELECT DISTINCT
                        :rule_set_id || ':' || projection_run_id AS rule_run_id,
                        projection_run_id
                    FROM {s}.player_projection proj
                    WHERE proj.mean IS NOT NULL
                    {extra_filter}
                )
                DELETE FROM {s}.symbolic_adjusted_projection adj
                USING scoped_runs
                WHERE adj.rule_run_id = scoped_runs.rule_run_id
                """
            ),
            {**params, "rule_set_id": RULE_SET_ID},
        )

        rule_runs = conn.execute(
            text(
                f"""
                WITH scoped_runs AS (
                    SELECT
                        projection_run_id,
                        COUNT(*) AS projections_seen
                    FROM {s}.player_projection proj
                    WHERE proj.mean IS NOT NULL
                    {extra_filter}
                    GROUP BY projection_run_id
                )
                INSERT INTO {s}.symbolic_rule_run
                (rule_run_id, projection_run_id, rules_loaded, rules_applied, status)
                SELECT
                    :rule_set_id || ':' || projection_run_id,
                    projection_run_id,
                    :rules_loaded,
                    0,
                    'completed'
                FROM scoped_runs
                ON CONFLICT (rule_run_id) DO UPDATE SET
                    rules_loaded = EXCLUDED.rules_loaded,
                    rules_applied = 0,
                    status = EXCLUDED.status
                """
            ),
            {**params, "rule_set_id": RULE_SET_ID, "rules_loaded": RULES_LOADED},
        ).rowcount or 0

        rule_applications = conn.execute(
            text(
                f"""
                WITH projection_context AS (
                    SELECT
                        proj.*,
                        :rule_set_id || ':' || proj.projection_run_id AS rule_run_id,
                        upper(COALESCE(injury.injury_status, injury.injury_details, '')) AS injury_status,
                        salary.salary
                    FROM {s}.player_projection proj
                    LEFT JOIN LATERAL (
                        SELECT injury_status, injury_details
                        FROM {s}.snapshot_injury_status injury
                        WHERE injury.season = proj.season
                          AND injury.week = proj.week
                          AND injury.player_id = proj.player_id
                        ORDER BY injury.as_of DESC NULLS LAST
                        LIMIT 1
                    ) injury ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT salary
                        FROM {s}.snapshot_salary salary
                        WHERE salary.season = proj.season
                          AND salary.week = proj.week
                          AND salary.player_id = proj.player_id
                        ORDER BY salary.as_of DESC NULLS LAST
                        LIMIT 1
                    ) salary ON TRUE
                    WHERE proj.mean IS NOT NULL
                    {extra_filter}
                ),
                matched_rules AS (
                    SELECT
                        ctx.rule_run_id,
                        rule.rule_id,
                        version.rule_version,
                        ctx.projection_run_id,
                        ctx.player_id,
                        ctx.injury_status,
                        ctx.salary,
                        ctx.mean AS mean_before,
                        ctx.p90 AS p90_before,
                        (version.action_json->>'mean_multiplier')::double precision AS mean_multiplier,
                        (version.action_json->>'p90_multiplier')::double precision AS p90_multiplier,
                        version.action_json->>'reason' AS reason
                    FROM projection_context ctx
                    JOIN {s}.symbolic_rule_version version ON version.enabled
                    JOIN {s}.symbolic_rule rule ON rule.rule_id = version.rule_id
                    WHERE (
                        rule.rule_id = 'target_injury_negative'
                        AND (
                            ctx.injury_status IN ('Q', 'D', 'O', 'OUT', 'IR', 'DOUBTFUL')
                            OR ctx.injury_status LIKE 'Q%'
                            OR ctx.injury_status LIKE 'D%'
                            OR ctx.injury_status LIKE 'O%'
                        )
                    )
                    OR (
                        rule.rule_id = 'target_injury_positive'
                        AND ctx.injury_status IN ('P', 'ACTIVE', 'PROBABLE')
                    )
                    OR (
                        rule.rule_id = 'target_salary_value_boost'
                        AND ctx.salary <= (version.condition_json->>'salary_lte')::integer
                        AND ctx.mean >= (version.condition_json->>'mean_gte')::double precision
                    )
                    OR (
                        rule.rule_id = 'target_expensive_low_projection_penalty'
                        AND ctx.salary >= (version.condition_json->>'salary_gte')::integer
                        AND ctx.mean < (version.condition_json->>'mean_lt')::double precision
                    )
                )
                INSERT INTO {s}.symbolic_rule_application
                (rule_run_id, rule_id, rule_version, projection_run_id, player_id, condition_context_json,
                 mean_before, mean_after, p90_before, p90_after, delta_mean, delta_p90, reason)
                SELECT
                    rule_run_id,
                    rule_id,
                    rule_version,
                    projection_run_id,
                    player_id,
                    jsonb_build_object('injury_status', injury_status, 'salary', salary),
                    mean_before,
                    mean_before * mean_multiplier,
                    p90_before,
                    p90_before * p90_multiplier,
                    (mean_before * mean_multiplier) - mean_before,
                    (p90_before * p90_multiplier) - p90_before,
                    reason
                FROM matched_rules
                """
            ),
            {**params, "rule_set_id": RULE_SET_ID},
        ).rowcount or 0

        adjusted_projection_rows = conn.execute(
            text(
                f"""
                WITH projection_context AS (
                    SELECT
                        proj.*,
                        :rule_set_id || ':' || proj.projection_run_id AS rule_run_id
                    FROM {s}.player_projection proj
                    WHERE proj.mean IS NOT NULL
                    {extra_filter}
                ),
                application_rollup AS (
                    SELECT
                        rule_run_id,
                        projection_run_id,
                        player_id,
                        exp(sum(ln(CASE WHEN mean_before = 0 THEN 1.0 ELSE NULLIF(mean_after / mean_before, 0.0) END))) AS mean_multiplier,
                        exp(sum(ln(CASE WHEN p90_before = 0 THEN 1.0 ELSE NULLIF(p90_after / p90_before, 0.0) END))) AS p90_multiplier,
                        jsonb_agg(jsonb_build_object('rule_id', rule_id, 'rule_version', rule_version, 'reason', reason) ORDER BY rule_id) AS reasons
                    FROM {s}.symbolic_rule_application
                    GROUP BY rule_run_id, projection_run_id, player_id
                )
                INSERT INTO {s}.symbolic_adjusted_projection
                (rule_run_id, projection_run_id, season, week, game_id, slate_id, player_id,
                 base_mean, adjusted_mean, base_p90, adjusted_p90, reason_json)
                SELECT
                    ctx.rule_run_id,
                    ctx.projection_run_id,
                    ctx.season,
                    ctx.week,
                    ctx.game_id,
                    ctx.slate_id,
                    ctx.player_id,
                    ctx.mean,
                    ctx.mean * COALESCE(rollup.mean_multiplier, 1.0),
                    ctx.p90,
                    ctx.p90 * COALESCE(rollup.p90_multiplier, 1.0),
                    COALESCE(rollup.reasons, '[]'::jsonb)
                FROM projection_context ctx
                LEFT JOIN application_rollup rollup
                  ON rollup.rule_run_id = ctx.rule_run_id
                 AND rollup.projection_run_id = ctx.projection_run_id
                 AND rollup.player_id = ctx.player_id
                ON CONFLICT (rule_run_id, projection_run_id, game_id, player_id) DO UPDATE SET
                    base_mean = EXCLUDED.base_mean,
                    adjusted_mean = EXCLUDED.adjusted_mean,
                    base_p90 = EXCLUDED.base_p90,
                    adjusted_p90 = EXCLUDED.adjusted_p90,
                    reason_json = EXCLUDED.reason_json
                """
            ),
            {**params, "rule_set_id": RULE_SET_ID},
        ).rowcount or 0

        conn.execute(
            text(
                f"""
                WITH counts AS (
                    SELECT rule_run_id, COUNT(DISTINCT rule_id) AS rules_applied
                    FROM {s}.symbolic_rule_application
                    GROUP BY rule_run_id
                )
                UPDATE {s}.symbolic_rule_run run
                SET rules_applied = COALESCE(counts.rules_applied, 0)
                FROM counts
                WHERE run.rule_run_id = counts.rule_run_id
                  AND run.rule_run_id LIKE :rule_run_prefix
                """
            ),
            {"rule_run_prefix": f"{RULE_SET_ID}:%"},
        )

    return SymbolicRunResult(
        status="completed",
        rule_rows=int(rule_rows),
        rule_version_rows=int(rule_version_rows),
        rule_runs=int(rule_runs),
        rule_applications=int(rule_applications),
        adjusted_projection_rows=int(adjusted_projection_rows),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply target-native symbolic rules to target projections.")
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
    result = apply_symbolic_rules(
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
