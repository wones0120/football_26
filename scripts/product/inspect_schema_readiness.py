#!/usr/bin/env python3
"""Inspect database readiness against the target neuro-symbolic schema."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


@dataclass(frozen=True)
class TargetTable:
    name: str
    layer: str
    priority: int
    required_for_learning: bool
    purpose: str


TARGET_TABLES: list[TargetTable] = [
    TargetTable("dim_player", "canonical", 1, True, "Canonical player identity"),
    TargetTable("player_alias", "canonical", 1, True, "Provider ID/name mapping"),
    TargetTable("identity_quarantine", "canonical", 1, True, "Audited unresolved source identities"),
    TargetTable("dim_team", "canonical", 1, False, "Canonical team identity"),
    TargetTable("dim_game", "canonical", 1, True, "Canonical NFL game identity"),
    TargetTable("dim_slate", "canonical", 2, False, "DFS slate identity"),
    TargetTable("slate_game", "canonical", 2, False, "Games included in slates"),
    TargetTable("slate_player_eligibility", "canonical", 2, False, "Salary and roster eligibility"),
    TargetTable("fact_player_game_actual", "facts", 1, True, "Actual player fantasy outcomes"),
    TargetTable("fact_dst_game_actual", "facts", 1, True, "Auditable DST components and fantasy outcomes"),
    TargetTable("fact_team_game_actual", "facts", 2, False, "Actual team game context"),
    TargetTable("fact_game_actual", "facts", 2, False, "Actual game outcome"),
    TargetTable("snapshot_salary", "snapshots", 2, True, "Point-in-time salary data"),
    TargetTable("snapshot_injury_status", "snapshots", 2, True, "Point-in-time injury data"),
    TargetTable("snapshot_ownership_projection", "snapshots", 3, False, "Pregame ownership projections"),
    TargetTable("snapshot_vegas_market", "snapshots", 2, True, "Point-in-time betting market"),
    TargetTable("snapshot_player_props", "snapshots", 3, False, "Point-in-time player props"),
    TargetTable("snapshot_weather", "snapshots", 3, False, "Point-in-time weather"),
    TargetTable("snapshot_depth_chart", "snapshots", 3, False, "Point-in-time role assumptions"),
    TargetTable("feature_generation_run", "features", 3, True, "Feature build metadata"),
    TargetTable("feature_player_game", "features", 3, True, "Player-game feature rows"),
    TargetTable("feature_team_game", "features", 3, False, "Team-game feature rows"),
    TargetTable("feature_slate_player", "features", 3, False, "Slate-player feature rows"),
    TargetTable("model_registry", "predictions", 3, True, "Model metadata"),
    TargetTable("model_run", "predictions", 3, True, "One model execution"),
    TargetTable("player_projection", "predictions", 3, True, "Base projection output"),
    TargetTable("symbolic_rule", "symbolic", 4, True, "Logical symbolic rule"),
    TargetTable("symbolic_rule_version", "symbolic", 4, True, "Versioned rule condition/action"),
    TargetTable("symbolic_rule_run", "symbolic", 4, True, "One symbolic execution"),
    TargetTable("symbolic_rule_application", "symbolic", 4, True, "Rule applied to one context"),
    TargetTable("symbolic_adjusted_projection", "symbolic", 4, True, "Final adjusted projections"),
    TargetTable("learning_run", "learning", 5, True, "Postgame evaluation batch"),
    TargetTable("projection_evaluation", "learning", 5, True, "Projection vs actual evaluation"),
    TargetTable("rule_evaluation", "learning", 5, True, "Rule before/after evaluation"),
    TargetTable("optimizer_evaluation", "learning", 6, False, "Lineup/portfolio evaluation"),
    TargetTable("data_quality_run", "learning", 5, False, "Versioned data quality execution"),
    TargetTable("data_quality_check", "learning", 5, False, "Data quality warnings"),
    TargetTable("human_belief", "human", 7, False, "Versioned user decision beliefs"),
    TargetTable("raw_thought_capture", "human", 7, False, "Verbatim user brain dumps"),
    TargetTable("raw_thought_candidate", "human", 7, False, "Extracted review-only belief drafts"),
    TargetTable("raw_thought_candidate_decision", "human", 7, False, "Immutable draft acceptance and rejection"),
    TargetTable("belief_impact_preview", "human", 7, False, "Guarded belief before/after proposals"),
    TargetTable("belief_impact_decision", "human", 7, False, "Immutable preview approvals and rejections"),
    TargetTable("optimizer_run", "optimization", 6, False, "One optimizer execution"),
    TargetTable("lineup", "optimization", 6, False, "Generated lineup"),
    TargetTable("lineup_player", "optimization", 6, False, "Lineup membership"),
    TargetTable("lineup_constraint_explanation", "optimization", 6, False, "Lineup explainability"),
]


LEGACY_MAPPINGS: dict[str, list[str]] = {
    "dim_player": ["player_master"],
    "player_alias": ["player_alias", "player_mapping_rule"],
    "identity_quarantine": ["curated_salary"],
    "dim_team": ["teams", "raw_nfl_team", "raw_roster_row"],
    "dim_game": ["raw_nfl_schedule", "raw_schedules", "schedules"],
    "dim_slate": ["slates", "ingest_run"],
    "slate_game": ["slate_games"],
    "slate_player_eligibility": ["curated_salary", "curated_salaries", "raw_salary_row", "raw_salaries"],
    "fact_player_game_actual": [
        "nfl_weekly_data_with_scores",
        "raw_nfl_weekly_stat",
        "raw_weekly_stats",
        "player_game_feature_matrix",
    ],
    "fact_dst_game_actual": ["raw_nfl_weekly_stat", "raw_nfl_schedule", "dk_contest_standings_rows"],
    "fact_team_game_actual": ["team_weekly_aggregations", "raw_nfl_weekly_team_stat"],
    "fact_game_actual": ["raw_nfl_schedule", "raw_schedules"],
    "snapshot_salary": ["curated_salary", "curated_salaries", "raw_salary_row", "raw_salaries"],
    "snapshot_injury_status": ["curated_injury", "weekly_injuries", "raw_injury_row", "raw_injuries"],
    "snapshot_ownership_projection": ["ownership_predictions", "raw_ownership", "ownership"],
    "snapshot_vegas_market": ["raw_vegas_lines", "vegas_lines", "team_implied_totals"],
    "snapshot_player_props": ["raw_player_props", "player_props"],
    "snapshot_weather": ["raw_weather", "weather"],
    "snapshot_depth_chart": ["starting_qbs", "depth_chart", "raw_depth_chart"],
    "feature_generation_run": ["feature_runs"],
    "feature_player_game": ["player_game_feature_matrix", "predictive_features"],
    "feature_team_game": ["team_weekly_aggregations", "predictive_features"],
    "feature_slate_player": ["predictive_features", "curated_salary", "curated_salaries"],
    "model_registry": ["model_registry"],
    "model_run": ["model_runs"],
    "player_projection": ["player_expected_points"],
    "symbolic_rule": ["symbolic_rules"],
    "symbolic_rule_version": ["symbolic_rules"],
    "symbolic_rule_run": ["symbolic_rule_runs"],
    "symbolic_rule_application": ["symbolic_adjustments"],
    "symbolic_adjusted_projection": ["player_expected_points_adjusted"],
    "learning_run": ["symbolic_learning_runs"],
    "projection_evaluation": ["symbolic_projection_snapshots"],
    "rule_evaluation": ["symbolic_rule_evaluations"],
    "optimizer_evaluation": ["contest_result", "simulation_run"],
    "data_quality_run": ["data_quality_runs"],
    "data_quality_check": ["data_quality_checks"],
    "human_belief": [],
    "raw_thought_capture": [],
    "raw_thought_candidate": [],
    "raw_thought_candidate_decision": [],
    "belief_impact_preview": [],
    "belief_impact_decision": [],
    "optimizer_run": ["optimizer_runs", "simulation_run"],
    "lineup": ["lineups", "actual_top_lineup"],
    "lineup_player": ["lineup_players", "actual_top_lineup_player"],
    "lineup_constraint_explanation": ["lineup_explanations"],
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


def fetch_existing_tables(engine, schema: str = "public") -> set[str]:
    with engine.begin() as conn:
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


def inspect_schema(existing_tables: set[str]) -> dict[str, Any]:
    table_results = []
    for target in TARGET_TABLES:
        candidates = LEGACY_MAPPINGS.get(target.name, [])
        present_candidates = [candidate for candidate in candidates if candidate in existing_tables]
        if target.name in existing_tables:
            status = "present"
        elif present_candidates:
            status = "mappable_from_legacy"
        else:
            status = "missing"
        table_results.append(
            {
                **asdict(target),
                "status": status,
                "legacy_candidates_present": present_candidates,
                "legacy_candidates_considered": candidates,
            }
        )

    counts = {
        "present": sum(1 for row in table_results if row["status"] == "present"),
        "mappable_from_legacy": sum(1 for row in table_results if row["status"] == "mappable_from_legacy"),
        "missing": sum(1 for row in table_results if row["status"] == "missing"),
    }
    required_rows = [row for row in table_results if row["required_for_learning"]]
    required_blockers = [
        row["name"]
        for row in required_rows
        if row["status"] == "missing"
    ]
    return {
        "target_tables": len(TARGET_TABLES),
        "counts": counts,
        "required_for_learning": {
            "total": len(required_rows),
            "ready_or_mappable": len(required_rows) - len(required_blockers),
            "missing": required_blockers,
        },
        "tables": table_results,
        "legacy_tables_seen": sorted(existing_tables),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect DB readiness against the target neuro-symbolic schema.")
    parser.add_argument("--database", help="Postgres database name. Defaults to PGDATABASE.")
    parser.add_argument("--host", help="Postgres host. Defaults to PGHOST or localhost.")
    parser.add_argument("--port", help="Postgres port. Defaults to PGPORT or 5432.")
    parser.add_argument("--user", help="Postgres user. Defaults to PGUSER.")
    parser.add_argument("--password", help="Postgres password. Defaults to PGPASSWORD.")
    parser.add_argument("--schema", default="public", help="Postgres schema to inspect. Defaults to public.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    engine = create_engine(build_connection_url(args))
    existing = fetch_existing_tables(engine, schema=args.schema)
    report = inspect_schema(existing)
    report["database"] = args.database or os.getenv("PGDATABASE")
    report["schema"] = args.schema
    print(json.dumps(report, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
