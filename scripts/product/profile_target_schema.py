#!/usr/bin/env python3
"""Profile loaded target-schema data quality and learning readiness."""

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
from sqlalchemy.exc import SQLAlchemyError

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.product.apply_target_schema_adapters import qident


FOUNDATION_TABLES = [
    "dim_player",
    "player_alias",
    "identity_quarantine",
    "dim_team",
    "dim_game",
    "fact_player_game_actual",
    "fact_dst_game_actual",
    "snapshot_salary",
    "snapshot_injury_status",
]

TARGET_LEARNING_TABLES = [
    "feature_generation_run",
    "feature_player_game",
    "model_registry",
    "model_run",
    "player_projection",
    "symbolic_rule",
    "symbolic_rule_version",
    "symbolic_rule_run",
    "symbolic_rule_application",
    "symbolic_adjusted_projection",
    "learning_run",
    "projection_evaluation",
    "rule_evaluation",
]

LEGACY_BACKFILL_TABLES = ["nfl_weekly_data_with_scores", "player_expected_points"]


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    value: int | None = None
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


def existing_tables(conn, schema: str) -> set[str]:
    rows = conn.execute(
        text(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = :schema
            """
        ),
        {"schema": schema},
    ).fetchall()
    return {str(row.tablename) for row in rows}


def scalar_int(conn, sql: str) -> int:
    return int(conn.execute(text(sql)).scalar() or 0)


def safe_count(conn, schema: str, table_name: str, tables: set[str]) -> int | None:
    if table_name not in tables:
        return None
    return scalar_int(conn, f"SELECT COUNT(*) FROM {qident(schema)}.{qident(table_name)}")


def coverage_by_week(conn, schema: str, table_name: str, tables: set[str], limit: int) -> list[dict[str, int]]:
    if table_name not in tables:
        return []
    try:
        rows = conn.execute(
            text(
                f"""
                SELECT season, week, COUNT(*) AS rows
                FROM {qident(schema)}.{qident(table_name)}
                GROUP BY season, week
                ORDER BY season DESC, week DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).fetchall()
    except SQLAlchemyError:
        return []
    return [{"season": int(row.season), "week": int(row.week), "rows": int(row.rows or 0)} for row in rows]


def check_count(
    conn,
    name: str,
    sql: str,
    ok_when_zero: bool = True,
    missing_message: str = "Check could not be run.",
) -> CheckResult:
    try:
        value = scalar_int(conn, sql)
    except SQLAlchemyError as exc:
        return CheckResult(name=name, status="skipped", message=f"{missing_message} {str(exc).splitlines()[0]}")
    status = "ok" if (value == 0 if ok_when_zero else value > 0) else "warn"
    return CheckResult(name=name, status=status, value=value)


def assess_readiness(target_tables: set[str], source_tables: set[str], row_counts: dict[str, int | None]) -> dict[str, Any]:
    target_missing = [table for table in TARGET_LEARNING_TABLES if table not in target_tables]
    target_empty_learning = [
        table
        for table in ["feature_generation_run", "feature_player_game", "model_registry", "model_run", "player_projection"]
        if table in target_tables and row_counts.get(table) == 0
    ]
    legacy_missing = [table for table in LEGACY_BACKFILL_TABLES if table not in source_tables]
    foundation_missing = [table for table in FOUNDATION_TABLES if table not in target_tables]
    foundation_empty = [table for table in FOUNDATION_TABLES if row_counts.get(table) == 0]

    recommendations = []
    if foundation_missing or foundation_empty:
        recommendations.append("Repair target foundation adapters before building target-native learning.")
    else:
        recommendations.append("Target foundation tables are loaded and can support feature/projection adapter work.")
    if target_missing:
        recommendations.append("Add target prediction, symbolic, and learning tables before target-native learning runs.")
    elif target_empty_learning:
        recommendations.append("Build target-native baseline projections before target-native learning runs.")
    if legacy_missing:
        recommendations.append("Current legacy backfill script cannot run in this database until legacy actual/projection tables exist.")
    else:
        recommendations.append("Legacy backfill prerequisites exist; run a dry-run by season/week before writing evaluations.")

    return {
        "target_foundation_ready": not foundation_missing and not foundation_empty,
        "target_native_learning_ready": (
            not foundation_missing and not foundation_empty and not target_missing and not target_empty_learning
        ),
        "legacy_backfill_ready": not legacy_missing,
        "missing_target_foundation_tables": foundation_missing,
        "empty_target_foundation_tables": foundation_empty,
        "missing_target_learning_tables": target_missing,
        "empty_target_learning_tables": target_empty_learning,
        "missing_legacy_backfill_tables": legacy_missing,
        "recommendations": recommendations,
    }


def profile_database(engine, source_schema: str, target_schema: str, top_weeks: int = 12) -> dict[str, Any]:
    with engine.begin() as conn:
        source_tables = existing_tables(conn, source_schema)
        target_tables = existing_tables(conn, target_schema)

        row_counts = {
            table_name: safe_count(conn, target_schema, table_name, target_tables)
            for table_name in FOUNDATION_TABLES + TARGET_LEARNING_TABLES
        }
        legacy_counts = {
            table_name: safe_count(conn, source_schema, table_name, source_tables)
            for table_name in LEGACY_BACKFILL_TABLES
        }

        target_coverage = {
            table_name: coverage_by_week(conn, target_schema, table_name, target_tables, top_weeks)
            for table_name in [
                "dim_game",
                "fact_player_game_actual",
                "fact_dst_game_actual",
                "snapshot_salary",
                "snapshot_injury_status",
            ]
        }
        legacy_coverage = {
            table_name: coverage_by_week(conn, source_schema, table_name, source_tables, top_weeks)
            for table_name in LEGACY_BACKFILL_TABLES
        }

        quality_checks = [
            check_count(
                conn,
                "fact_player_game_actual_player_orphans",
                f"""
                SELECT COUNT(*)
                FROM {qident(target_schema)}.fact_player_game_actual actual
                LEFT JOIN {qident(target_schema)}.dim_player player ON player.player_id = actual.player_id
                WHERE player.player_id IS NULL
                """,
            ),
            check_count(
                conn,
                "fact_player_game_actual_game_orphans",
                f"""
                SELECT COUNT(*)
                FROM {qident(target_schema)}.fact_player_game_actual actual
                LEFT JOIN {qident(target_schema)}.dim_game game ON game.game_id = actual.game_id
                WHERE game.game_id IS NULL
                """,
            ),
            check_count(
                conn,
                "fact_dst_game_actual_player_orphans",
                f"""
                SELECT COUNT(*)
                FROM {qident(target_schema)}.fact_dst_game_actual actual
                LEFT JOIN {qident(target_schema)}.dim_player player ON player.player_id = actual.player_id
                WHERE player.player_id IS NULL
                """,
            ),
            check_count(
                conn,
                "fact_dst_game_actual_game_orphans",
                f"""
                SELECT COUNT(*)
                FROM {qident(target_schema)}.fact_dst_game_actual actual
                LEFT JOIN {qident(target_schema)}.dim_game game ON game.game_id = actual.game_id
                WHERE game.game_id IS NULL
                """,
            ),
            check_count(
                conn,
                "snapshot_salary_player_orphans",
                f"""
                SELECT COUNT(*)
                FROM {qident(target_schema)}.snapshot_salary salary
                LEFT JOIN {qident(target_schema)}.dim_player player ON player.player_id = salary.player_id
                WHERE player.player_id IS NULL
                """,
            ),
            check_count(
                conn,
                "snapshot_injury_status_player_orphans",
                f"""
                SELECT COUNT(*)
                FROM {qident(target_schema)}.snapshot_injury_status injury
                LEFT JOIN {qident(target_schema)}.dim_player player ON player.player_id = injury.player_id
                WHERE player.player_id IS NULL
                """,
            ),
            check_count(
                conn,
                "snapshot_salary_missing_game_id",
                f"SELECT COUNT(*) FROM {qident(target_schema)}.snapshot_salary WHERE game_id IS NULL",
            ),
            check_count(
                conn,
                "snapshot_injury_status_missing_game_id",
                f"SELECT COUNT(*) FROM {qident(target_schema)}.snapshot_injury_status WHERE game_id IS NULL",
            ),
            check_count(
                conn,
                "fact_player_game_actual_missing_dk_points",
                f"SELECT COUNT(*) FROM {qident(target_schema)}.fact_player_game_actual WHERE dk_points IS NULL",
            ),
            check_count(
                conn,
                "fact_dst_game_actual_missing_dk_points",
                f"SELECT COUNT(*) FROM {qident(target_schema)}.fact_dst_game_actual WHERE dk_points IS NULL",
            ),
            check_count(
                conn,
                "legacy_feature_rows_without_player_master_id",
                f"""
                SELECT COUNT(*)
                FROM {qident(source_schema)}.player_game_feature_matrix
                WHERE COALESCE(player_master_id, player_id) IS NULL
                """,
            ),
            check_count(
                conn,
                "legacy_salary_rows_without_identity_or_quarantine",
                f"""
                SELECT COUNT(*)
                FROM {qident(source_schema)}.curated_salary salary
                LEFT JOIN {qident(target_schema)}.identity_quarantine quarantine
                  ON quarantine.source_schema = '{source_schema}'
                 AND quarantine.source_table = 'curated_salary'
                 AND quarantine.source_record_key = salary.curated_salary_id::text
                 AND quarantine.status = 'open'
                WHERE salary.player_master_id IS NULL
                  AND quarantine.identity_quarantine_id IS NULL
                """,
            ),
            check_count(
                conn,
                "open_salary_identity_quarantine",
                f"""
                SELECT COUNT(*)
                FROM {qident(target_schema)}.identity_quarantine
                WHERE source_schema = '{source_schema}'
                  AND source_table = 'curated_salary'
                  AND status = 'open'
                """,
            ),
            check_count(
                conn,
                "legacy_injury_rows_without_player_master_id",
                f"SELECT COUNT(*) FROM {qident(source_schema)}.curated_injury WHERE player_master_id IS NULL",
            ),
        ]

    return {
        "source_schema": source_schema,
        "target_schema": target_schema,
        "target_row_counts": row_counts,
        "legacy_row_counts": legacy_counts,
        "target_coverage_by_week": target_coverage,
        "legacy_coverage_by_week": legacy_coverage,
        "quality_checks": [asdict(check) for check in quality_checks],
        "readiness": assess_readiness(target_tables, source_tables, row_counts),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile target-schema data quality and learning readiness.")
    parser.add_argument("--database", help="Postgres database name. Defaults to PGDATABASE.")
    parser.add_argument("--host", help="Postgres host. Defaults to PGHOST or localhost.")
    parser.add_argument("--port", help="Postgres port. Defaults to PGPORT or 5432.")
    parser.add_argument("--user", help="Postgres user. Defaults to PGUSER.")
    parser.add_argument("--password", help="Postgres password. Defaults to PGPASSWORD.")
    parser.add_argument("--source-schema", default="public")
    parser.add_argument("--target-schema", default="target")
    parser.add_argument("--top-weeks", type=int, default=12)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    engine = create_engine(build_connection_url(args))
    report = profile_database(
        engine=engine,
        source_schema=args.source_schema,
        target_schema=args.target_schema,
        top_weeks=args.top_weeks,
    )
    report["database"] = args.database or os.getenv("PGDATABASE")
    print(json.dumps(report, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
