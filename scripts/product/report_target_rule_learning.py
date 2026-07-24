#!/usr/bin/env python3
"""Report target-native symbolic rule performance and recommendations."""

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


MIN_ROWS_FOR_ACTION = 50
STRONG_DELTA = 0.25
WEAK_DELTA = 0.05
CONTEST_PROFILES = {"all", "cash", "gpp"}


@dataclass(frozen=True)
class RuleRecommendation:
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


def cutoff_sql(through_season: int | None, through_week: int | None, alias: str = "eval") -> tuple[str, dict[str, Any]]:
    if through_week is not None and through_season is None:
        raise ValueError("--through-week requires --through-season")
    if through_season is None:
        return "", {}
    if through_week is None:
        return f"AND {alias}.season <= :through_season", {"through_season": through_season}
    return (
        f"AND ({alias}.season < :through_season OR ({alias}.season = :through_season AND {alias}.week <= :through_week))",
        {"through_season": through_season, "through_week": through_week},
    )


def validate_contest_profile(contest_profile: str) -> str:
    normalized = contest_profile.lower().strip()
    if normalized not in CONTEST_PROFILES:
        raise ValueError(f"contest profile must be one of: {', '.join(sorted(CONTEST_PROFILES))}")
    return normalized


def contest_profile_sql(contest_profile: str, alias: str = "version") -> tuple[str, dict[str, Any]]:
    normalized = validate_contest_profile(contest_profile)
    if normalized == "all":
        return "", {}
    return f"AND {alias}.action_json->'contest_profiles' ? :contest_profile", {"contest_profile": normalized}


def recommend_rule(rows: int, avg_delta_mae: float, hit_rate: float) -> RuleRecommendation:
    if rows < MIN_ROWS_FOR_ACTION:
        return RuleRecommendation(
            action="collect_more_data",
            severity="info",
            rationale=f"Only {rows} evaluated applications; wait for at least {MIN_ROWS_FOR_ACTION}.",
        )
    if avg_delta_mae >= STRONG_DELTA and hit_rate >= 0.55:
        return RuleRecommendation(
            action="consider_increase",
            severity="positive",
            rationale="Rule has materially reduced error with a positive hit rate.",
        )
    if avg_delta_mae >= WEAK_DELTA:
        return RuleRecommendation(
            action="keep",
            severity="positive",
            rationale="Rule is modestly improving projection error.",
        )
    if avg_delta_mae <= -STRONG_DELTA and hit_rate <= 0.45:
        return RuleRecommendation(
            action="consider_disable_or_reduce",
            severity="negative",
            rationale="Rule has materially increased error with a poor hit rate.",
        )
    if avg_delta_mae < -WEAK_DELTA:
        return RuleRecommendation(
            action="reduce",
            severity="negative",
            rationale="Rule is modestly worsening projection error.",
        )
    return RuleRecommendation(
        action="keep_under_review",
        severity="neutral",
        rationale="Rule impact is near neutral.",
    )


def report_rule_learning(
    engine,
    target_schema: str = "target",
    through_season: int | None = None,
    through_week: int | None = None,
    contest_profile: str = "all",
) -> dict[str, Any]:
    s = qident(target_schema)
    cutoff_clause, params = cutoff_sql(through_season, through_week)
    profile_clause, profile_params = contest_profile_sql(contest_profile)
    params = {**params, **profile_params}
    with engine.begin() as conn:
        rule_rows = conn.execute(
            text(
                f"""
                SELECT
                    eval.rule_id,
                    COALESCE(rule.rule_name, eval.rule_id) AS rule_name,
                    COALESCE(rule.rule_type, 'unknown') AS rule_type,
                    COUNT(*) AS rows,
                    COUNT(DISTINCT eval.season::text || ':' || eval.week::text) AS weeks,
                    AVG(eval.mae_before) AS mae_before,
                    AVG(eval.mae_after) AS mae_after,
                    AVG(eval.delta_mae) AS avg_delta_mae,
                    AVG(CASE WHEN eval.improved THEN 1.0 ELSE 0.0 END) AS hit_rate
                FROM {s}.rule_evaluation eval
                LEFT JOIN {s}.symbolic_rule rule ON rule.rule_id = eval.rule_id
                LEFT JOIN {s}.symbolic_rule_version version
                  ON version.rule_id = eval.rule_id
                 AND version.rule_version = eval.rule_version
                WHERE 1 = 1
                {cutoff_clause}
                {profile_clause}
                GROUP BY eval.rule_id, rule.rule_name, rule.rule_type
                ORDER BY avg_delta_mae DESC NULLS LAST, rows DESC
                """
            ),
            params,
        ).fetchall()
        week_rows = conn.execute(
            text(
                f"""
                SELECT
                    eval.season,
                    eval.week,
                    COUNT(*) AS rows,
                    AVG(eval.mae_before) AS mae_before,
                    AVG(eval.mae_after) AS mae_after,
                    AVG(eval.delta_mae) AS avg_delta_mae,
                    AVG(CASE WHEN eval.improved THEN 1.0 ELSE 0.0 END) AS hit_rate
                FROM {s}.rule_evaluation eval
                LEFT JOIN {s}.symbolic_rule_version version
                  ON version.rule_id = eval.rule_id
                 AND version.rule_version = eval.rule_version
                WHERE 1 = 1
                {cutoff_clause}
                {profile_clause}
                GROUP BY eval.season, eval.week
                ORDER BY eval.season, eval.week
                """
            ),
            params,
        ).fetchall()

    rules = []
    for row in rule_rows:
        rows = int(row.rows or 0)
        avg_delta = float(row.avg_delta_mae or 0.0)
        hit_rate = float(row.hit_rate or 0.0)
        recommendation = recommend_rule(rows=rows, avg_delta_mae=avg_delta, hit_rate=hit_rate)
        rules.append(
            {
                "rule_id": str(row.rule_id),
                "rule_name": str(row.rule_name),
                "rule_type": str(row.rule_type),
                "rows": rows,
                "weeks": int(row.weeks or 0),
                "mae_before": float(row.mae_before or 0.0),
                "mae_after": float(row.mae_after or 0.0),
                "avg_delta_mae": avg_delta,
                "hit_rate": hit_rate,
                "recommendation": asdict(recommendation),
            }
        )

    by_week = [
        {
            "season": int(row.season),
            "week": int(row.week),
            "rows": int(row.rows or 0),
            "mae_before": float(row.mae_before or 0.0),
            "mae_after": float(row.mae_after or 0.0),
            "avg_delta_mae": float(row.avg_delta_mae or 0.0),
            "hit_rate": float(row.hit_rate or 0.0),
        }
        for row in week_rows
    ]

    return {
        "target_schema": target_schema,
        "contest_profile": validate_contest_profile(contest_profile),
        "cutoff": {"through_season": through_season, "through_week": through_week},
        "rules_evaluated": len(rules),
        "applications_evaluated": sum(row["rows"] for row in rules),
        "rules": rules,
        "by_week": by_week,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Report target-native symbolic rule learning results.")
    parser.add_argument("--database", help="Postgres database name. Defaults to PGDATABASE.")
    parser.add_argument("--host", help="Postgres host. Defaults to PGHOST or localhost.")
    parser.add_argument("--port", help="Postgres port. Defaults to PGPORT or 5432.")
    parser.add_argument("--user", help="Postgres user. Defaults to PGUSER.")
    parser.add_argument("--password", help="Postgres password. Defaults to PGPASSWORD.")
    parser.add_argument("--target-schema", default="target")
    parser.add_argument("--through-season", type=int)
    parser.add_argument("--through-week", type=int)
    parser.add_argument("--contest-profile", default="all", choices=sorted(CONTEST_PROFILES))
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    try:
        engine = create_engine(build_connection_url(args))
        report = report_rule_learning(
            engine=engine,
            target_schema=args.target_schema,
            through_season=args.through_season,
            through_week=args.through_week,
            contest_profile=args.contest_profile,
        )
    except ValueError as exc:
        parser.error(str(exc))
    report["database"] = args.database or os.getenv("PGDATABASE")
    print(json.dumps(report, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
