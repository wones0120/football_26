#!/usr/bin/env python3
"""Create target-schema tables and adapt legacy football_26_dev data into them."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Database.dst import repair_dst_identities
from Database.player_identity import repair_salary_identities


IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class AdapterResult:
    name: str
    status: str
    rows: int = 0
    message: str = ""


def qident(identifier: str) -> str:
    if not IDENT_RE.match(identifier):
        raise ValueError(f"Unsafe SQL identifier: {identifier!r}")
    return f'"{identifier}"'


def canonical_team_sql(expression: str) -> str:
    """Render the shared modern-franchise normalization for trusted SQL expressions."""
    return (
        f"CASE upper(trim({expression})) "
        "WHEN 'LA' THEN 'LAR' WHEN 'STL' THEN 'LAR' "
        "WHEN 'SD' THEN 'LAC' WHEN 'JAC' THEN 'JAX' "
        "WHEN 'WSH' THEN 'WAS' WHEN 'OAK' THEN 'LV' "
        f"ELSE upper(trim({expression})) END"
    )


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


def table_exists(conn, schema: str, table_name: str) -> bool:
    return bool(
        conn.execute(
            text(
                """
                SELECT EXISTS (
                  SELECT 1
                  FROM information_schema.tables
                  WHERE table_schema = :schema AND table_name = :table_name
                )
                """
            ),
            {"schema": schema, "table_name": table_name},
        ).scalar()
    )


def create_target_schema_sql(target_schema: str) -> list[str]:
    s = qident(target_schema)
    return [
        f"CREATE SCHEMA IF NOT EXISTS {s}",
        f"""
        CREATE TABLE IF NOT EXISTS {s}.dim_player (
            player_id TEXT PRIMARY KEY,
            full_name TEXT,
            first_name TEXT,
            last_name TEXT,
            birth_date DATE,
            primary_position TEXT,
            normalized_name TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.player_alias (
            alias_id TEXT PRIMARY KEY,
            player_id TEXT NOT NULL REFERENCES {s}.dim_player(player_id),
            source TEXT,
            source_player_id TEXT,
            source_player_name TEXT,
            normalized_name TEXT,
            confidence DOUBLE PRECISION,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.identity_quarantine (
            identity_quarantine_id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            source_schema TEXT NOT NULL,
            source_table TEXT NOT NULL,
            source_record_key TEXT NOT NULL,
            source_system TEXT,
            season INT,
            week INT,
            slate TEXT,
            source_player_key TEXT,
            display_name TEXT,
            team_id TEXT,
            position TEXT,
            reason_code TEXT NOT NULL,
            candidate_player_ids JSONB NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'open',
            resolved_player_id TEXT,
            resolution_reason TEXT,
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            resolved_at TIMESTAMPTZ,
            UNIQUE (source_schema, source_table, source_record_key)
        )
        """,
        f"""
        CREATE INDEX IF NOT EXISTS idx_identity_quarantine_slate
        ON {s}.identity_quarantine (season, week, slate, status)
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.dim_team (
            team_id TEXT NOT NULL,
            season INT NOT NULL,
            team_abbr TEXT,
            team_name TEXT,
            conference TEXT,
            division TEXT,
            PRIMARY KEY (team_id, season)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.dim_game (
            game_id TEXT PRIMARY KEY,
            season INT NOT NULL,
            week INT NOT NULL,
            game_date DATE,
            kickoff_at TIMESTAMPTZ,
            home_team_id TEXT,
            away_team_id TEXT,
            roof TEXT,
            surface TEXT,
            neutral_site BOOLEAN DEFAULT FALSE
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.fact_player_game_actual (
            season INT NOT NULL,
            week INT NOT NULL,
            game_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            team_id TEXT,
            opponent_team_id TEXT,
            position TEXT,
            dk_points DOUBLE PRECISION,
            fd_points DOUBLE PRECISION,
            snaps DOUBLE PRECISION,
            snap_share DOUBLE PRECISION,
            routes DOUBLE PRECISION,
            targets DOUBLE PRECISION,
            carries DOUBLE PRECISION,
            receptions DOUBLE PRECISION,
            receiving_yards DOUBLE PRECISION,
            rushing_yards DOUBLE PRECISION,
            passing_yards DOUBLE PRECISION,
            tds DOUBLE PRECISION,
            turnovers DOUBLE PRECISION,
            created_at TIMESTAMPTZ DEFAULT now(),
            PRIMARY KEY (season, week, game_id, player_id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.fact_dst_game_actual (
            season INT NOT NULL,
            week INT NOT NULL,
            game_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            team_id TEXT NOT NULL,
            opponent_team_id TEXT NOT NULL,
            is_home BOOLEAN,
            sacks DOUBLE PRECISION NOT NULL DEFAULT 0,
            interceptions DOUBLE PRECISION NOT NULL DEFAULT 0,
            fumble_recoveries DOUBLE PRECISION NOT NULL DEFAULT 0,
            safeties DOUBLE PRECISION NOT NULL DEFAULT 0,
            interception_return_tds DOUBLE PRECISION NOT NULL DEFAULT 0,
            fumble_return_tds DOUBLE PRECISION NOT NULL DEFAULT 0,
            special_teams_tds DOUBLE PRECISION NOT NULL DEFAULT 0,
            blocked_kicks DOUBLE PRECISION NOT NULL DEFAULT 0,
            opponent_score DOUBLE PRECISION,
            charged_points_allowed DOUBLE PRECISION,
            points_allowed_score DOUBLE PRECISION,
            total_line DOUBLE PRECISION,
            spread_line DOUBLE PRECISION,
            opponent_implied_points DOUBLE PRECISION,
            reconstructed_dk_points DOUBLE PRECISION NOT NULL,
            observed_dk_points DOUBLE PRECISION,
            dk_points DOUBLE PRECISION NOT NULL,
            scoring_source TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            PRIMARY KEY (season, week, game_id, player_id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.snapshot_salary (
            snapshot_salary_id BIGSERIAL PRIMARY KEY,
            slate_id TEXT,
            season INT NOT NULL,
            week INT NOT NULL,
            slate TEXT,
            player_id TEXT NOT NULL,
            site TEXT,
            site_player_id TEXT,
            salary INT,
            roster_position TEXT,
            team_id TEXT,
            opponent_team_id TEXT,
            game_id TEXT,
            as_of TIMESTAMPTZ,
            source TEXT,
            UNIQUE (season, week, slate, player_id, site, roster_position)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.snapshot_injury_status (
            snapshot_injury_id BIGSERIAL PRIMARY KEY,
            season INT NOT NULL,
            week INT NOT NULL,
            slate TEXT,
            game_id TEXT,
            player_id TEXT NOT NULL,
            team_id TEXT,
            position TEXT,
            injury_status TEXT,
            injury_details TEXT,
            as_of TIMESTAMPTZ,
            source TEXT,
            UNIQUE (season, week, slate, player_id, source)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.feature_generation_run (
            feature_run_id TEXT PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT now(),
            training_cutoff TIMESTAMPTZ,
            source_versions_json JSONB DEFAULT '{{}}',
            feature_set_hash TEXT,
            status TEXT NOT NULL DEFAULT 'completed'
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.feature_player_game (
            feature_run_id TEXT NOT NULL REFERENCES {s}.feature_generation_run(feature_run_id),
            season INT NOT NULL,
            week INT NOT NULL,
            game_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            feature_json JSONB NOT NULL DEFAULT '{{}}',
            created_at TIMESTAMPTZ DEFAULT now(),
            PRIMARY KEY (feature_run_id, season, week, game_id, player_id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.model_registry (
            model_id TEXT PRIMARY KEY,
            model_name TEXT NOT NULL,
            model_version TEXT NOT NULL,
            trained_on_start TEXT,
            trained_on_end TEXT,
            feature_set_hash TEXT,
            metrics_json JSONB DEFAULT '{{}}',
            artifact_uri TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.model_run (
            model_run_id TEXT PRIMARY KEY,
            model_id TEXT NOT NULL REFERENCES {s}.model_registry(model_id),
            feature_run_id TEXT REFERENCES {s}.feature_generation_run(feature_run_id),
            created_at TIMESTAMPTZ DEFAULT now(),
            data_cutoff_at TIMESTAMPTZ,
            params_json JSONB DEFAULT '{{}}',
            status TEXT NOT NULL DEFAULT 'completed'
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.projection_run (
            projection_run_id TEXT PRIMARY KEY,
            model_run_id TEXT NOT NULL REFERENCES {s}.model_run(model_run_id),
            season INT NOT NULL,
            week INT NOT NULL,
            slate_id TEXT NOT NULL,
            row_count INT NOT NULL,
            data_cutoff_at TIMESTAMPTZ,
            status TEXT NOT NULL DEFAULT 'completed',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        f"""
        CREATE INDEX IF NOT EXISTS idx_projection_run_scope
        ON {s}.projection_run (season, week, slate_id, created_at DESC)
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.active_projection_run (
            season INT NOT NULL,
            week INT NOT NULL,
            slate_id TEXT NOT NULL,
            projection_run_id TEXT NOT NULL REFERENCES {s}.projection_run(projection_run_id),
            selection_reason TEXT NOT NULL DEFAULT 'prediction_run_completed',
            selected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (season, week, slate_id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.player_projection (
            projection_run_id TEXT NOT NULL,
            model_run_id TEXT NOT NULL REFERENCES {s}.model_run(model_run_id),
            season INT NOT NULL,
            week INT NOT NULL,
            game_id TEXT NOT NULL,
            slate_id TEXT,
            player_id TEXT NOT NULL,
            mean DOUBLE PRECISION,
            median DOUBLE PRECISION,
            p10 DOUBLE PRECISION,
            p25 DOUBLE PRECISION,
            p75 DOUBLE PRECISION,
            p90 DOUBLE PRECISION,
            stddev DOUBLE PRECISION,
            ceiling_prob DOUBLE PRECISION,
            created_at TIMESTAMPTZ DEFAULT now(),
            data_cutoff_at TIMESTAMPTZ,
            PRIMARY KEY (projection_run_id, game_id, player_id)
        )
        """,
        f"""
        INSERT INTO {s}.projection_run
            (projection_run_id, model_run_id, season, week, slate_id,
             row_count, data_cutoff_at, status, created_at)
        SELECT
            projection_run_id,
            MIN(model_run_id),
            MIN(season),
            MIN(week),
            COALESCE(MIN(slate_id), 'DEFAULT'),
            COUNT(*),
            MAX(data_cutoff_at),
            'completed',
            MAX(created_at)
        FROM {s}.player_projection
        GROUP BY projection_run_id
        ON CONFLICT (projection_run_id) DO NOTHING
        """,
        f"""
        INSERT INTO {s}.active_projection_run
            (season, week, slate_id, projection_run_id, selection_reason, selected_at)
        SELECT DISTINCT ON (season, week, slate_id)
            season, week, slate_id, projection_run_id,
            'schema_backfill_latest', created_at
        FROM {s}.projection_run
        WHERE status = 'completed'
        ORDER BY season, week, slate_id, created_at DESC, projection_run_id
        ON CONFLICT (season, week, slate_id) DO NOTHING
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.symbolic_rule (
            rule_id TEXT PRIMARY KEY,
            rule_name TEXT NOT NULL,
            rule_type TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.symbolic_rule_version (
            rule_id TEXT NOT NULL REFERENCES {s}.symbolic_rule(rule_id),
            rule_version INT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            priority INT NOT NULL DEFAULT 100,
            condition_json JSONB NOT NULL DEFAULT '{{}}',
            action_json JSONB NOT NULL DEFAULT '{{}}',
            created_at TIMESTAMPTZ DEFAULT now(),
            retired_at TIMESTAMPTZ,
            PRIMARY KEY (rule_id, rule_version)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.symbolic_rule_run (
            rule_run_id TEXT PRIMARY KEY,
            projection_run_id TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            rules_loaded INT NOT NULL DEFAULT 0,
            rules_applied INT NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'completed'
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.symbolic_rule_application (
            rule_application_id BIGSERIAL PRIMARY KEY,
            rule_run_id TEXT NOT NULL REFERENCES {s}.symbolic_rule_run(rule_run_id),
            rule_id TEXT NOT NULL,
            rule_version INT,
            projection_run_id TEXT,
            player_id TEXT NOT NULL,
            condition_context_json JSONB DEFAULT '{{}}',
            mean_before DOUBLE PRECISION,
            mean_after DOUBLE PRECISION,
            p90_before DOUBLE PRECISION,
            p90_after DOUBLE PRECISION,
            delta_mean DOUBLE PRECISION,
            delta_p90 DOUBLE PRECISION,
            reason TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.symbolic_adjusted_projection (
            rule_run_id TEXT NOT NULL REFERENCES {s}.symbolic_rule_run(rule_run_id),
            projection_run_id TEXT NOT NULL,
            season INT NOT NULL,
            week INT NOT NULL,
            game_id TEXT NOT NULL,
            slate_id TEXT,
            player_id TEXT NOT NULL,
            base_mean DOUBLE PRECISION,
            adjusted_mean DOUBLE PRECISION,
            base_p90 DOUBLE PRECISION,
            adjusted_p90 DOUBLE PRECISION,
            reason_json JSONB DEFAULT '[]',
            created_at TIMESTAMPTZ DEFAULT now(),
            PRIMARY KEY (rule_run_id, projection_run_id, game_id, player_id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.learning_run (
            learning_run_id TEXT PRIMARY KEY,
            projection_run_id TEXT,
            rule_run_id TEXT,
            season INT,
            week INT,
            status TEXT NOT NULL DEFAULT 'completed',
            projections_evaluated INT NOT NULL DEFAULT 0,
            rules_evaluated INT NOT NULL DEFAULT 0,
            metrics_json JSONB DEFAULT '{{}}',
            recommendations_json JSONB DEFAULT '[]',
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.data_quality_run (
            quality_run_id TEXT PRIMARY KEY,
            report_id TEXT,
            contract_id TEXT NOT NULL,
            trigger TEXT NOT NULL,
            season INT NOT NULL,
            week INT,
            slate TEXT,
            status TEXT NOT NULL CHECK (status IN ('pass', 'warn', 'fail')),
            score INT NOT NULL CHECK (score BETWEEN 0 AND 100),
            summary_json JSONB NOT NULL DEFAULT '{{}}',
            source_context_json JSONB NOT NULL DEFAULT '{{}}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        f"""
        CREATE INDEX IF NOT EXISTS idx_data_quality_run_scope
        ON {s}.data_quality_run (season, week, slate, created_at DESC)
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.data_quality_check (
            quality_check_id TEXT PRIMARY KEY,
            quality_run_id TEXT NOT NULL REFERENCES {s}.data_quality_run(quality_run_id) ON DELETE CASCADE,
            check_id TEXT NOT NULL,
            category TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pass', 'warn', 'fail')),
            severity TEXT NOT NULL,
            table_name TEXT,
            check_name TEXT NOT NULL,
            message TEXT NOT NULL,
            value_json JSONB,
            threshold TEXT,
            affected_scope_json JSONB NOT NULL DEFAULT '{{}}',
            details_json JSONB NOT NULL DEFAULT '{{}}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (quality_run_id, check_id)
        )
        """,
        f"""
        CREATE INDEX IF NOT EXISTS idx_data_quality_check_status
        ON {s}.data_quality_check (status, category, created_at DESC)
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.human_belief (
            belief_version_id TEXT PRIMARY KEY,
            belief_id TEXT NOT NULL,
            belief_version INT NOT NULL,
            supersedes_version_id TEXT REFERENCES {s}.human_belief(belief_version_id),
            operation TEXT NOT NULL CHECK (operation IN ('created', 'revised', 'deactivated', 'reactivated')),
            status TEXT NOT NULL CHECK (status IN ('active', 'inactive')),
            scope_type TEXT NOT NULL CHECK (scope_type IN ('global', 'contest_profile', 'season', 'weekly', 'game', 'player')),
            subject_label TEXT,
            subject_id TEXT,
            season INT,
            week INT,
            slate TEXT,
            contest_format TEXT,
            objective TEXT,
            direction TEXT NOT NULL CHECK (direction IN ('boost', 'fade', 'prefer', 'avoid', 'monitor', 'neutral')),
            strength INT NOT NULL CHECK (strength BETWEEN 1 AND 5),
            confidence INT NOT NULL CHECK (confidence BETWEEN 0 AND 100),
            thought_text TEXT NOT NULL,
            evidence_text TEXT,
            expires_at TIMESTAMPTZ,
            is_retrospective BOOLEAN NOT NULL DEFAULT FALSE,
            impact_status TEXT NOT NULL DEFAULT 'not_previewed',
            source TEXT NOT NULL DEFAULT 'manual',
            metadata_json JSONB NOT NULL DEFAULT '{{}}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (belief_id, belief_version)
        )
        """,
        f"""
        CREATE INDEX IF NOT EXISTS idx_human_belief_scope
        ON {s}.human_belief (scope_type, season, week, slate, created_at DESC)
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.raw_thought_capture (
            capture_id TEXT PRIMARY KEY,
            context_type TEXT NOT NULL CHECK (context_type IN ('auto', 'general', 'slate', 'player')),
            raw_text TEXT NOT NULL,
            subject_label TEXT,
            subject_id TEXT,
            season INT,
            week INT,
            slate TEXT,
            contest_format TEXT,
            objective TEXT,
            extraction_policy_id TEXT NOT NULL,
            notices_json JSONB NOT NULL DEFAULT '[]',
            source TEXT NOT NULL DEFAULT 'thought_inbox',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        f"""
        CREATE INDEX IF NOT EXISTS idx_raw_thought_capture_scope
        ON {s}.raw_thought_capture (season, week, slate, created_at DESC)
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.raw_thought_candidate (
            candidate_id TEXT PRIMARY KEY,
            capture_id TEXT NOT NULL REFERENCES {s}.raw_thought_capture(capture_id),
            ordinal INT NOT NULL,
            scope_type TEXT NOT NULL,
            subject_label TEXT,
            subject_id TEXT,
            season INT,
            week INT,
            slate TEXT,
            contest_format TEXT,
            objective TEXT,
            direction TEXT NOT NULL,
            strength INT NOT NULL,
            confidence INT NOT NULL,
            thought_text TEXT NOT NULL,
            extraction_reason TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (capture_id, ordinal)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.raw_thought_candidate_decision (
            decision_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL UNIQUE REFERENCES {s}.raw_thought_candidate(candidate_id),
            decision TEXT NOT NULL CHECK (decision IN ('accepted', 'rejected')),
            belief_id TEXT,
            belief_version_id TEXT REFERENCES {s}.human_belief(belief_version_id),
            reviewed_payload_json JSONB NOT NULL DEFAULT '{{}}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.belief_impact_preview (
            preview_id TEXT PRIMARY KEY,
            belief_version_id TEXT NOT NULL REFERENCES {s}.human_belief(belief_version_id),
            belief_id TEXT NOT NULL,
            policy_id TEXT NOT NULL,
            season INT NOT NULL,
            week INT NOT NULL,
            slate TEXT,
            contest_format TEXT,
            objective TEXT,
            target_player_id TEXT NOT NULL,
            target_label TEXT NOT NULL,
            adjustment_pct DOUBLE PRECISION NOT NULL,
            baseline_json JSONB NOT NULL,
            proposed_json JSONB NOT NULL,
            delta_json JSONB NOT NULL,
            modifier_json JSONB NOT NULL,
            lineage_json JSONB NOT NULL,
            notices_json JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        f"""
        CREATE INDEX IF NOT EXISTS idx_belief_impact_preview_scope
        ON {s}.belief_impact_preview (belief_id, season, week, slate, created_at DESC)
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.belief_impact_decision (
            decision_id TEXT PRIMARY KEY,
            preview_id TEXT NOT NULL UNIQUE REFERENCES {s}.belief_impact_preview(preview_id),
            decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
            note_text TEXT,
            approved_modifier_json JSONB NOT NULL DEFAULT '{{}}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.projection_evaluation (
            evaluation_id BIGSERIAL PRIMARY KEY,
            learning_run_id TEXT REFERENCES {s}.learning_run(learning_run_id),
            projection_run_id TEXT NOT NULL,
            season INT NOT NULL,
            week INT NOT NULL,
            game_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            projected_mean DOUBLE PRECISION,
            projected_p90 DOUBLE PRECISION,
            actual_points DOUBLE PRECISION,
            absolute_error DOUBLE PRECISION,
            squared_error DOUBLE PRECISION,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (learning_run_id, projection_run_id, game_id, player_id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.rule_evaluation (
            evaluation_id BIGSERIAL PRIMARY KEY,
            learning_run_id TEXT REFERENCES {s}.learning_run(learning_run_id),
            rule_run_id TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            rule_version INT,
            season INT NOT NULL,
            week INT NOT NULL,
            game_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            mean_before DOUBLE PRECISION,
            mean_after DOUBLE PRECISION,
            actual_points DOUBLE PRECISION,
            mae_before DOUBLE PRECISION,
            mae_after DOUBLE PRECISION,
            improved BOOLEAN,
            delta_mae DOUBLE PRECISION,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.source_file_import (
            source_file_id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            original_path TEXT,
            file_name TEXT,
            file_size_bytes BIGINT,
            first_ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata_json JSONB NOT NULL DEFAULT '{{}}'
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.dfs_contest (
            contest_id TEXT PRIMARY KEY,
            source_file_id TEXT REFERENCES {s}.source_file_import(source_file_id),
            site TEXT NOT NULL,
            slate_id TEXT NOT NULL,
            season INT NOT NULL,
            week INT NOT NULL,
            contest_name TEXT NOT NULL,
            contest_format TEXT NOT NULL,
            contest_type TEXT NOT NULL DEFAULT 'unknown',
            entry_fee NUMERIC(12, 2),
            field_size INT NOT NULL,
            max_entries_per_user INT,
            prize_pool NUMERIC(14, 2),
            metadata_json JSONB NOT NULL DEFAULT '{{}}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        f"""
        ALTER TABLE {s}.dfs_contest
        ADD COLUMN IF NOT EXISTS contest_type TEXT NOT NULL DEFAULT 'unknown'
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.dfs_contest_payout_tier (
            contest_id TEXT NOT NULL REFERENCES {s}.dfs_contest(contest_id) ON DELETE CASCADE,
            min_rank INT NOT NULL,
            max_rank INT NOT NULL,
            payout NUMERIC(14, 2),
            prize_description TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (contest_id, min_rank, max_rank)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.dfs_contest_entry_result (
            contest_id TEXT NOT NULL REFERENCES {s}.dfs_contest(contest_id) ON DELETE CASCADE,
            entry_id TEXT NOT NULL,
            source_file_id TEXT REFERENCES {s}.source_file_import(source_file_id),
            entry_name TEXT,
            rank INT,
            entry_points DOUBLE PRECISION,
            lineup_text TEXT,
            ingested_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (contest_id, entry_id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.import_batch (
            batch_id TEXT PRIMARY KEY,
            directory TEXT NOT NULL,
            dry_run BOOLEAN NOT NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ,
            discovered INT NOT NULL DEFAULT 0,
            imported INT NOT NULL DEFAULT 0,
            deduplicated INT NOT NULL DEFAULT 0,
            skipped INT NOT NULL DEFAULT 0,
            failed INT NOT NULL DEFAULT 0
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.import_batch_file (
            batch_id TEXT NOT NULL REFERENCES {s}.import_batch(batch_id) ON DELETE CASCADE,
            file_number INT NOT NULL,
            source_file_id TEXT,
            path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            status TEXT NOT NULL,
            season INT NOT NULL,
            week INT NOT NULL,
            slate_id TEXT NOT NULL,
            contest_id TEXT,
            template_id TEXT,
            rows_written INT NOT NULL DEFAULT 0,
            message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (batch_id, file_number)
        )
        """,
        f"""
        ALTER TABLE {s}.import_batch_file
        ADD COLUMN IF NOT EXISTS template_id TEXT
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.dk_entry_template_file (
            template_id TEXT PRIMARY KEY,
            source_file_id TEXT NOT NULL REFERENCES {s}.source_file_import(source_file_id),
            season INT NOT NULL,
            week INT NOT NULL,
            slate_id TEXT NOT NULL,
            columns_json JSONB NOT NULL DEFAULT '[]',
            row_count INT NOT NULL DEFAULT 0,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (source_file_id, season, week, slate_id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.dk_entry_template_row (
            template_id TEXT NOT NULL REFERENCES {s}.dk_entry_template_file(template_id) ON DELETE CASCADE,
            row_number INT NOT NULL,
            entry_id TEXT,
            contest_id TEXT,
            contest_name TEXT,
            entry_fee TEXT,
            row_json JSONB NOT NULL DEFAULT '{{}}',
            PRIMARY KEY (template_id, row_number)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.simulation_run (
            simulation_run_id TEXT PRIMARY KEY,
            simulation_model_id TEXT NOT NULL,
            projection_run_id TEXT NOT NULL,
            ownership_run_id TEXT,
            season INT NOT NULL,
            week INT NOT NULL,
            slate_id TEXT NOT NULL,
            contest_format TEXT NOT NULL,
            num_simulations INT NOT NULL,
            successful_simulations INT NOT NULL,
            seed BIGINT NOT NULL,
            salary_cap INT NOT NULL,
            roster_size INT NOT NULL,
            params_json JSONB NOT NULL DEFAULT '{{}}',
            data_cutoff_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            status TEXT NOT NULL,
            message TEXT
        )
        """,
        f"""
        CREATE INDEX IF NOT EXISTS idx_simulation_run_scope
        ON {s}.simulation_run
            (season, week, UPPER(slate_id), contest_format, created_at DESC)
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.player_simulation (
            simulation_run_id TEXT NOT NULL
                REFERENCES {s}.simulation_run(simulation_run_id) ON DELETE CASCADE,
            player_id TEXT NOT NULL,
            player_display_name TEXT NOT NULL,
            position TEXT NOT NULL,
            salary INT NOT NULL,
            projection_mean DOUBLE PRECISION NOT NULL,
            optimal_lineup_count INT NOT NULL,
            optimal_lineup_probability DOUBLE PRECISION NOT NULL,
            field_ownership DOUBLE PRECISION,
            leverage_score DOUBLE PRECISION,
            result_json JSONB NOT NULL DEFAULT '{{}}',
            PRIMARY KEY (simulation_run_id, player_id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.optimizer_run (
            optimizer_run_id TEXT PRIMARY KEY,
            projection_run_id TEXT,
            rule_run_id TEXT,
            slate_id TEXT,
            season INT NOT NULL,
            week INT NOT NULL,
            contest_format TEXT NOT NULL,
            objective TEXT NOT NULL,
            strategy TEXT NOT NULL,
            objective_config_json JSONB NOT NULL DEFAULT '{{}}',
            constraint_config_json JSONB NOT NULL DEFAULT '{{}}',
            data_cutoff_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            status TEXT NOT NULL,
            message TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.lineup (
            lineup_id TEXT PRIMARY KEY,
            optimizer_run_id TEXT NOT NULL REFERENCES {s}.optimizer_run(optimizer_run_id) ON DELETE CASCADE,
            lineup_number INT NOT NULL,
            salary_used DOUBLE PRECISION,
            projected_mean DOUBLE PRECISION,
            projected_p90 DOUBLE PRECISION,
            ownership_sum DOUBLE PRECISION,
            leverage_score DOUBLE PRECISION,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (optimizer_run_id, lineup_number)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.lineup_player (
            lineup_id TEXT NOT NULL REFERENCES {s}.lineup(lineup_id) ON DELETE CASCADE,
            slot_index INT NOT NULL,
            player_id TEXT NOT NULL,
            roster_position TEXT,
            salary DOUBLE PRECISION,
            projection DOUBLE PRECISION,
            projected_p90 DOUBLE PRECISION,
            ownership_projection DOUBLE PRECISION,
            player_json JSONB NOT NULL DEFAULT '{{}}',
            PRIMARY KEY (lineup_id, slot_index)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.lineup_constraint_explanation (
            explanation_id BIGSERIAL PRIMARY KEY,
            lineup_id TEXT NOT NULL REFERENCES {s}.lineup(lineup_id) ON DELETE CASCADE,
            constraint_name TEXT NOT NULL,
            constraint_status TEXT NOT NULL,
            explanation_json JSONB NOT NULL DEFAULT '{{}}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.lineup_portfolio (
            portfolio_id TEXT PRIMARY KEY,
            portfolio_name TEXT NOT NULL,
            optimizer_run_id TEXT NOT NULL REFERENCES {s}.optimizer_run(optimizer_run_id),
            template_id TEXT NOT NULL REFERENCES {s}.dk_entry_template_file(template_id),
            season INT NOT NULL,
            week INT NOT NULL,
            slate_id TEXT NOT NULL,
            contest_format TEXT NOT NULL,
            objective TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'assigned',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.portfolio_lineup (
            portfolio_id TEXT NOT NULL REFERENCES {s}.lineup_portfolio(portfolio_id) ON DELETE CASCADE,
            lineup_id TEXT NOT NULL REFERENCES {s}.lineup(lineup_id),
            portfolio_lineup_number INT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (portfolio_id, lineup_id),
            UNIQUE (portfolio_id, portfolio_lineup_number)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.contest_entry_assignment (
            assignment_id TEXT PRIMARY KEY,
            portfolio_id TEXT NOT NULL REFERENCES {s}.lineup_portfolio(portfolio_id) ON DELETE CASCADE,
            template_id TEXT NOT NULL,
            template_row_number INT NOT NULL,
            entry_id TEXT NOT NULL,
            contest_id TEXT NOT NULL,
            lineup_id TEXT NOT NULL REFERENCES {s}.lineup(lineup_id),
            status TEXT NOT NULL DEFAULT 'assigned',
            assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (template_id, template_row_number),
            UNIQUE (portfolio_id, lineup_id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.dk_export_validation (
            validation_id TEXT PRIMARY KEY,
            portfolio_id TEXT NOT NULL REFERENCES {s}.lineup_portfolio(portfolio_id),
            status TEXT NOT NULL,
            checks_run INT NOT NULL,
            errors_json JSONB NOT NULL DEFAULT '[]',
            warnings_json JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {s}.dk_upload_export (
            export_id TEXT PRIMARY KEY,
            portfolio_id TEXT NOT NULL REFERENCES {s}.lineup_portfolio(portfolio_id),
            validation_id TEXT REFERENCES {s}.dk_export_validation(validation_id),
            contest_format TEXT NOT NULL,
            file_name TEXT NOT NULL,
            row_count INT NOT NULL,
            content_sha256 TEXT NOT NULL,
            columns_json JSONB NOT NULL DEFAULT '[]',
            csv_content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        f"""
        ALTER TABLE {s}.dk_upload_export
        ADD COLUMN IF NOT EXISTS validation_id TEXT
        REFERENCES {s}.dk_export_validation(validation_id)
        """,
    ]


def adapter_sql(source_schema: str, target_schema: str) -> dict[str, str]:
    src = qident(source_schema)
    dst = qident(target_schema)
    return {
        "dim_player": f"""
            INSERT INTO {dst}.dim_player
            (player_id, full_name, first_name, last_name, birth_date, primary_position, normalized_name, created_at, updated_at)
            SELECT
                player_master_id,
                full_name,
                first_name,
                last_name,
                NULL::date,
                position,
                normalized_name,
                COALESCE(created_at, now()),
                COALESCE(updated_at, created_at, now())
            FROM {src}.player_master
            WHERE player_master_id IS NOT NULL
            ON CONFLICT (player_id) DO UPDATE SET
                full_name = EXCLUDED.full_name,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                primary_position = EXCLUDED.primary_position,
                normalized_name = EXCLUDED.normalized_name,
                updated_at = EXCLUDED.updated_at
        """,
        "player_alias": f"""
            INSERT INTO {dst}.player_alias
            (alias_id, player_id, source, source_player_id, source_player_name, normalized_name, confidence, created_at)
            SELECT
                'alias:' || alias_id::text,
                player_master_id,
                source_system,
                source_key,
                alias_name,
                normalized_alias,
                NULL::double precision,
                COALESCE(created_at, now())
            FROM {src}.player_alias
            WHERE player_master_id IS NOT NULL
            ON CONFLICT (alias_id) DO UPDATE SET
                player_id = EXCLUDED.player_id,
                source = EXCLUDED.source,
                source_player_id = EXCLUDED.source_player_id,
                source_player_name = EXCLUDED.source_player_name,
                normalized_name = EXCLUDED.normalized_name
        """,
        "player_mapping_rule_aliases": f"""
            INSERT INTO {dst}.player_alias
            (alias_id, player_id, source, source_player_id, source_player_name, normalized_name, confidence, created_at)
            SELECT
                'mapping_rule:' || rule_id::text,
                player_master_id,
                source_system,
                rule_id,
                rule_name,
                lower(regexp_replace(COALESCE(rule_name, ''), '[^a-zA-Z0-9]+', ' ', 'g')),
                confidence,
                COALESCE(created_at, now())
            FROM {src}.player_mapping_rule
            WHERE player_master_id IS NOT NULL
            ON CONFLICT (alias_id) DO UPDATE SET
                player_id = EXCLUDED.player_id,
                source = EXCLUDED.source,
                source_player_id = EXCLUDED.source_player_id,
                source_player_name = EXCLUDED.source_player_name,
                normalized_name = EXCLUDED.normalized_name,
                confidence = EXCLUDED.confidence
        """,
        "dim_team_from_schedules": f"""
            INSERT INTO {dst}.dim_team
            (team_id, season, team_abbr, team_name, conference, division)
            SELECT DISTINCT team_id, season, team_id, NULL::text, NULL::text, NULL::text
            FROM (
                SELECT season, {canonical_team_sql('home_team')} AS team_id FROM {src}.raw_nfl_schedule WHERE home_team IS NOT NULL
                UNION
                SELECT season, {canonical_team_sql('away_team')} AS team_id FROM {src}.raw_nfl_schedule WHERE away_team IS NOT NULL
            ) teams
            WHERE team_id IS NOT NULL
            ON CONFLICT (team_id, season) DO NOTHING
        """,
        "dim_game": f"""
            INSERT INTO {dst}.dim_game
            (game_id, season, week, game_date, kickoff_at, home_team_id, away_team_id, roof, surface, neutral_site)
            SELECT DISTINCT
                game_id,
                season,
                week,
                CASE
                    WHEN kickoff ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}' THEN left(kickoff, 10)::date
                    ELSE NULL::date
                END,
                CASE
                    WHEN kickoff ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}' THEN kickoff::timestamptz
                    ELSE NULL::timestamptz
                END,
                {canonical_team_sql('home_team')},
                {canonical_team_sql('away_team')},
                NULL::text,
                NULL::text,
                FALSE
            FROM {src}.raw_nfl_schedule
            WHERE game_id IS NOT NULL
            ON CONFLICT (game_id) DO UPDATE SET
                season = EXCLUDED.season,
                week = EXCLUDED.week,
                game_date = EXCLUDED.game_date,
                kickoff_at = EXCLUDED.kickoff_at,
                home_team_id = EXCLUDED.home_team_id,
                away_team_id = EXCLUDED.away_team_id
        """,
        "fact_player_game_actual": f"""
            INSERT INTO {dst}.fact_player_game_actual
            (season, week, game_id, player_id, team_id, opponent_team_id, position, dk_points, fd_points,
             snaps, snap_share, routes, targets, carries, receptions, receiving_yards, rushing_yards,
             passing_yards, tds, turnovers, created_at)
            SELECT DISTINCT ON (season, week, game_id, player_master_id)
                season,
                week,
                game_id,
                player_master_id AS player_id,
                team,
                opponent,
                position,
                dk_points,
                NULL::double precision,
                NULL::double precision,
                NULL::double precision,
                NULL::double precision,
                NULL::double precision,
                NULL::double precision,
                NULL::double precision,
                NULL::double precision,
                NULL::double precision,
                NULL::double precision,
                NULL::double precision,
                NULL::double precision,
                COALESCE(created_at, now())
            FROM {src}.player_game_feature_matrix
            WHERE game_id IS NOT NULL AND player_master_id IS NOT NULL
            ORDER BY season, week, game_id, player_master_id, created_at DESC
            ON CONFLICT (season, week, game_id, player_id) DO UPDATE SET
                team_id = EXCLUDED.team_id,
                opponent_team_id = EXCLUDED.opponent_team_id,
                position = EXCLUDED.position,
                dk_points = EXCLUDED.dk_points
        """,
        "fact_dst_game_actual": f"""
            WITH raw_rows AS (
                SELECT DISTINCT ON (season, week, team, COALESCE(player_id, player_name))
                    season, week, team, opponent, raw_row_json, created_at
                FROM {src}.raw_nfl_weekly_stat
                WHERE team IS NOT NULL AND opponent IS NOT NULL
                ORDER BY season, week, team, COALESCE(player_id, player_name), created_at DESC
            ),
            team_stats AS (
                SELECT
                    season,
                    week,
                    {canonical_team_sql('team')} AS team_id,
                    {canonical_team_sql('opponent')} AS opponent_team_id,
                    SUM(COALESCE(NULLIF(raw_row_json->>'def_sacks', '')::double precision, 0)) AS sacks,
                    SUM(COALESCE(NULLIF(raw_row_json->>'def_interceptions', '')::double precision, 0)) AS interceptions,
                    SUM(COALESCE(NULLIF(COALESCE(raw_row_json->>'def_fumble_recovery_opp', raw_row_json->>'fumble_recovery_opp'), '')::double precision, 0)) AS fumble_recoveries,
                    SUM(COALESCE(NULLIF(COALESCE(raw_row_json->>'def_safety', raw_row_json->>'def_safeties'), '')::double precision, 0)) AS safeties,
                    SUM(COALESCE(NULLIF(raw_row_json->>'def_tds', '')::double precision, 0)) AS interception_return_tds,
                    SUM(COALESCE(NULLIF(raw_row_json->>'fumble_recovery_tds', '')::double precision, 0)) AS fumble_return_tds,
                    SUM(COALESCE(NULLIF(raw_row_json->>'special_teams_tds', '')::double precision, 0)) AS special_teams_tds,
                    SUM(
                        COALESCE(NULLIF(raw_row_json->>'fg_blocked', '')::double precision, 0)
                        + COALESCE(NULLIF(raw_row_json->>'pat_blocked', '')::double precision, 0)
                    ) AS kicks_blocked_by_opponent
                FROM raw_rows
                GROUP BY season, week, {canonical_team_sql('team')}, {canonical_team_sql('opponent')}
            ),
            schedule_games AS (
                SELECT DISTINCT ON (season, week, game_id)
                    season,
                    week,
                    game_id,
                    {canonical_team_sql('home_team')} AS home_team_id,
                    {canonical_team_sql('away_team')} AS away_team_id,
                    NULLIF(raw_row_json->>'home_score', '')::double precision AS home_score,
                    NULLIF(raw_row_json->>'away_score', '')::double precision AS away_score,
                    NULLIF(raw_row_json->>'total_line', '')::double precision AS total_line,
                    NULLIF(raw_row_json->>'spread_line', '')::double precision AS spread_line
                FROM {src}.raw_nfl_schedule
                WHERE game_id IS NOT NULL
                ORDER BY season, week, game_id, created_at DESC
            ),
            dst_identity AS (
                SELECT DISTINCT ON ({canonical_team_sql('primary_team')})
                    {canonical_team_sql('primary_team')} AS team_id,
                    player_master_id::text AS player_id
                FROM {src}.player_master
                WHERE upper(trim(position)) IN ('D', 'DEF', 'DST')
                  AND NULLIF(trim(primary_team), '') IS NOT NULL
                ORDER BY {canonical_team_sql('primary_team')}, updated_at DESC NULLS LAST, created_at DESC NULLS LAST
            ),
            components AS (
                SELECT
                    stats.*,
                    schedule.game_id,
                    identity.player_id,
                    schedule.home_team_id = stats.team_id AS is_home,
                    opponent.kicks_blocked_by_opponent AS blocked_kicks,
                    opponent.interception_return_tds + opponent.fumble_return_tds AS opponent_defensive_touchdowns,
                    opponent.safeties AS opponent_defensive_safeties,
                    CASE WHEN schedule.home_team_id = stats.team_id THEN schedule.away_score ELSE schedule.home_score END AS opponent_score,
                    schedule.total_line,
                    schedule.spread_line,
                    CASE
                        WHEN schedule.total_line IS NULL OR schedule.spread_line IS NULL THEN NULL
                        WHEN schedule.home_team_id = stats.team_id THEN schedule.total_line / 2.0 - schedule.spread_line / 2.0
                        ELSE schedule.total_line / 2.0 + schedule.spread_line / 2.0
                    END AS opponent_implied_points
                FROM team_stats stats
                JOIN team_stats opponent
                  ON opponent.season = stats.season
                 AND opponent.week = stats.week
                 AND opponent.team_id = stats.opponent_team_id
                 AND opponent.opponent_team_id = stats.team_id
                JOIN schedule_games schedule
                  ON schedule.season = stats.season
                 AND schedule.week = stats.week
                 AND (
                    (schedule.home_team_id = stats.team_id AND schedule.away_team_id = stats.opponent_team_id)
                    OR (schedule.away_team_id = stats.team_id AND schedule.home_team_id = stats.opponent_team_id)
                 )
                JOIN dst_identity identity ON identity.team_id = stats.team_id
                WHERE schedule.home_score IS NOT NULL AND schedule.away_score IS NOT NULL
            ),
            charged AS (
                SELECT *,
                    GREATEST(
                        0,
                        opponent_score - 7 * opponent_defensive_touchdowns - 2 * opponent_defensive_safeties
                    ) AS charged_points_allowed
                FROM components
            ),
            scored AS (
                SELECT *,
                    CASE
                        WHEN charged_points_allowed = 0 THEN 10
                        WHEN charged_points_allowed <= 6 THEN 7
                        WHEN charged_points_allowed <= 13 THEN 4
                        WHEN charged_points_allowed <= 20 THEN 1
                        WHEN charged_points_allowed <= 27 THEN 0
                        WHEN charged_points_allowed <= 34 THEN -1
                        ELSE -4
                    END::double precision AS points_allowed_score
                FROM charged
            ),
            projected AS (
                SELECT *,
                    sacks
                    + 2 * interceptions
                    + 2 * fumble_recoveries
                    + 2 * safeties
                    + 6 * (interception_return_tds + fumble_return_tds + special_teams_tds)
                    + 2 * blocked_kicks
                    + points_allowed_score AS reconstructed_dk_points
                FROM scored
            )
            INSERT INTO {dst}.fact_dst_game_actual AS existing
            (season, week, game_id, player_id, team_id, opponent_team_id, is_home,
             sacks, interceptions, fumble_recoveries, safeties, interception_return_tds,
             fumble_return_tds, special_teams_tds, blocked_kicks, opponent_score,
             charged_points_allowed, points_allowed_score, total_line, spread_line,
             opponent_implied_points, reconstructed_dk_points, observed_dk_points,
             dk_points, scoring_source, created_at)
            SELECT
                season, week, game_id, player_id, team_id, opponent_team_id, is_home,
                sacks, interceptions, fumble_recoveries, safeties, interception_return_tds,
                fumble_return_tds, special_teams_tds, blocked_kicks, opponent_score,
                charged_points_allowed, points_allowed_score, total_line, spread_line,
                opponent_implied_points, reconstructed_dk_points, NULL::double precision,
                reconstructed_dk_points, 'nflverse_reconstructed', now()
            FROM projected
            ON CONFLICT (season, week, game_id, player_id) DO UPDATE SET
                team_id = EXCLUDED.team_id,
                opponent_team_id = EXCLUDED.opponent_team_id,
                is_home = EXCLUDED.is_home,
                sacks = EXCLUDED.sacks,
                interceptions = EXCLUDED.interceptions,
                fumble_recoveries = EXCLUDED.fumble_recoveries,
                safeties = EXCLUDED.safeties,
                interception_return_tds = EXCLUDED.interception_return_tds,
                fumble_return_tds = EXCLUDED.fumble_return_tds,
                special_teams_tds = EXCLUDED.special_teams_tds,
                blocked_kicks = EXCLUDED.blocked_kicks,
                opponent_score = EXCLUDED.opponent_score,
                charged_points_allowed = EXCLUDED.charged_points_allowed,
                points_allowed_score = EXCLUDED.points_allowed_score,
                total_line = EXCLUDED.total_line,
                spread_line = EXCLUDED.spread_line,
                opponent_implied_points = EXCLUDED.opponent_implied_points,
                reconstructed_dk_points = EXCLUDED.reconstructed_dk_points,
                dk_points = COALESCE(existing.observed_dk_points, EXCLUDED.dk_points),
                scoring_source = CASE
                    WHEN existing.observed_dk_points IS NOT NULL THEN 'draftkings_contest'
                    ELSE EXCLUDED.scoring_source
                END,
                created_at = now()
        """,
        "fact_dst_game_actual_observed_override": f"""
            WITH observed AS (
                SELECT
                    salary.season,
                    salary.week,
                    {canonical_team_sql('salary.team')} AS team_id,
                    MAX(standings.fpts)::double precision AS observed_dk_points
                FROM {src}.curated_salary salary
                JOIN {src}.dk_contest_standings_rows standings
                  ON standings.season = salary.season
                 AND standings.week = salary.week
                 AND lower(trim(standings.slate)) = lower(trim(salary.slate))
                 AND lower(trim(standings.player_display_name)) = lower(trim(salary.player_name))
                WHERE upper(trim(salary.position)) IN ('D', 'DEF', 'DST')
                  AND standings.fpts IS NOT NULL
                GROUP BY salary.season, salary.week, {canonical_team_sql('salary.team')}
            )
            UPDATE {dst}.fact_dst_game_actual actual
            SET observed_dk_points = observed.observed_dk_points,
                dk_points = observed.observed_dk_points,
                scoring_source = 'draftkings_contest',
                created_at = now()
            FROM observed
            WHERE observed.season = actual.season
              AND observed.week = actual.week
              AND observed.team_id = actual.team_id
        """,
        "fact_dst_game_actual_stale_identity_cleanup": f"""
            WITH active_identity AS (
                SELECT DISTINCT ON ({canonical_team_sql('team')})
                    {canonical_team_sql('team')} AS team_id,
                    player_master_id::text AS player_id
                FROM {src}.curated_salary
                WHERE upper(trim(position)) IN ('D', 'DEF', 'DST')
                  AND player_master_id IS NOT NULL
                ORDER BY {canonical_team_sql('team')}, created_at DESC
            )
            DELETE FROM {dst}.fact_dst_game_actual actual
            USING active_identity
            WHERE active_identity.team_id = actual.team_id
              AND active_identity.player_id <> actual.player_id
        """,
        "fact_dst_game_actual_compat": f"""
            INSERT INTO {dst}.fact_player_game_actual
            (season, week, game_id, player_id, team_id, opponent_team_id, position, dk_points, fd_points,
             snaps, snap_share, routes, targets, carries, receptions, receiving_yards, rushing_yards,
             passing_yards, tds, turnovers, created_at)
            SELECT
                season,
                week,
                game_id,
                player_id,
                team_id,
                opponent_team_id,
                'DST',
                dk_points,
                NULL::double precision,
                NULL::double precision,
                NULL::double precision,
                NULL::double precision,
                NULL::double precision,
                NULL::double precision,
                NULL::double precision,
                NULL::double precision,
                NULL::double precision,
                NULL::double precision,
                interception_return_tds + fumble_return_tds + special_teams_tds,
                interceptions + fumble_recoveries,
                created_at
            FROM {dst}.fact_dst_game_actual
            ON CONFLICT (season, week, game_id, player_id) DO UPDATE SET
                team_id = EXCLUDED.team_id,
                opponent_team_id = EXCLUDED.opponent_team_id,
                position = EXCLUDED.position,
                dk_points = EXCLUDED.dk_points,
                tds = EXCLUDED.tds,
                turnovers = EXCLUDED.turnovers,
                created_at = EXCLUDED.created_at
        """,
        "fact_dst_game_actual_compat_cleanup": f"""
            DELETE FROM {dst}.fact_player_game_actual actual
            WHERE upper(trim(actual.position)) IN ('D', 'DEF', 'DST')
              AND NOT EXISTS (
                  SELECT 1
                  FROM {dst}.fact_dst_game_actual dst_actual
                  WHERE dst_actual.season = actual.season
                    AND dst_actual.week = actual.week
                    AND dst_actual.game_id = actual.game_id
                    AND dst_actual.player_id = actual.player_id
              )
        """,
        "fact_player_game_actual_orphan_cleanup": f"""
            DELETE FROM {dst}.fact_player_game_actual actual
            WHERE NOT EXISTS (
                SELECT 1
                FROM {dst}.dim_player player
                WHERE player.player_id = actual.player_id
            )
        """,
        "snapshot_salary": f"""
            INSERT INTO {dst}.snapshot_salary
            (slate_id, season, week, slate, player_id, site, site_player_id, salary, roster_position,
             team_id, opponent_team_id, game_id, as_of, source)
            WITH schedule_games AS (
                SELECT DISTINCT ON (season, week, home_team, away_team)
                    season,
                    week,
                    {canonical_team_sql('home_team')} AS home_team,
                    {canonical_team_sql('away_team')} AS away_team,
                    game_id
                FROM {src}.raw_nfl_schedule
                WHERE game_id IS NOT NULL
                ORDER BY season, week, home_team, away_team, created_at DESC
            )
            SELECT DISTINCT ON (season, week, slate, player_master_id, source_system, roster_position)
                salary.season::text || ':' || salary.week::text || ':' || COALESCE(salary.slate, 'UNKNOWN') AS slate_id,
                salary.season,
                salary.week,
                salary.slate,
                salary.player_master_id,
                salary.source_system,
                salary.source_player_key,
                salary.salary,
                salary.roster_position,
                {canonical_team_sql('salary.team')},
                {canonical_team_sql('salary.opponent')},
                schedule_games.game_id,
                COALESCE(salary.created_at, now()),
                salary.source_system
            FROM {src}.curated_salary salary
            LEFT JOIN schedule_games ON schedule_games.season = salary.season
                AND schedule_games.week = salary.week
                AND (
                    (schedule_games.home_team = {canonical_team_sql('salary.team')} AND schedule_games.away_team = {canonical_team_sql('salary.opponent')})
                    OR (schedule_games.home_team = {canonical_team_sql('salary.opponent')} AND schedule_games.away_team = {canonical_team_sql('salary.team')})
                )
            WHERE salary.player_master_id IS NOT NULL
            ORDER BY salary.season, salary.week, salary.slate, salary.player_master_id, salary.source_system, salary.roster_position, salary.created_at DESC
            ON CONFLICT (season, week, slate, player_id, site, roster_position) DO UPDATE SET
                site_player_id = EXCLUDED.site_player_id,
                salary = EXCLUDED.salary,
                team_id = EXCLUDED.team_id,
                opponent_team_id = EXCLUDED.opponent_team_id,
                game_id = EXCLUDED.game_id,
                as_of = EXCLUDED.as_of
        """,
        "snapshot_injury_status": f"""
            INSERT INTO {dst}.snapshot_injury_status
            (season, week, slate, game_id, player_id, team_id, position, injury_status, injury_details, as_of, source)
            WITH schedule_games AS (
                SELECT DISTINCT ON (season, week, home_team, away_team)
                    season,
                    week,
                    home_team,
                    away_team,
                    game_id
                FROM {src}.raw_nfl_schedule
                WHERE game_id IS NOT NULL
                ORDER BY season, week, home_team, away_team, created_at DESC
            )
            SELECT DISTINCT ON (season, week, slate, player_master_id, source_system)
                injury.season,
                injury.week,
                injury.slate,
                schedule_games.game_id,
                injury.player_master_id,
                injury.team,
                injury.position,
                injury.injury_status,
                injury.injury_details,
                COALESCE(injury.created_at, now()),
                injury.source_system
            FROM {src}.curated_injury injury
            LEFT JOIN schedule_games ON schedule_games.season = injury.season
                AND schedule_games.week = injury.week
                AND (schedule_games.home_team = injury.team OR schedule_games.away_team = injury.team)
            WHERE injury.player_master_id IS NOT NULL
            ORDER BY injury.season, injury.week, injury.slate, injury.player_master_id, injury.source_system, injury.created_at DESC
            ON CONFLICT (season, week, slate, player_id, source) DO UPDATE SET
                team_id = EXCLUDED.team_id,
                position = EXCLUDED.position,
                game_id = EXCLUDED.game_id,
                injury_status = EXCLUDED.injury_status,
                injury_details = EXCLUDED.injury_details,
                as_of = EXCLUDED.as_of
        """,
        "dfs_contest_entry_result": f"""
            INSERT INTO {dst}.dfs_contest_entry_result
                (contest_id, entry_id, source_file_id, entry_name, rank,
                 entry_points, lineup_text, ingested_at)
            SELECT DISTINCT ON (contest.contest_id, entry.entry_id)
                contest.contest_id,
                entry.entry_id,
                contest.source_file_id,
                entry.entry_name,
                entry.rank,
                entry.entry_points,
                entry.lineup_text,
                entry.ingested_at
            FROM {src}.dk_contest_entries entry
            JOIN {dst}.dfs_contest contest
              ON contest.season = entry.season
             AND contest.week = entry.week
             AND UPPER(contest.slate_id) = UPPER(entry.slate)
            JOIN {dst}.source_file_import source
              ON source.source_file_id = contest.source_file_id
             AND source.original_path = entry.source_file
            WHERE entry.entry_id IS NOT NULL
            ORDER BY contest.contest_id, entry.entry_id, entry.ingested_at DESC
            ON CONFLICT (contest_id, entry_id) DO UPDATE SET
                source_file_id = EXCLUDED.source_file_id,
                entry_name = EXCLUDED.entry_name,
                rank = EXCLUDED.rank,
                entry_points = EXCLUDED.entry_points,
                lineup_text = EXCLUDED.lineup_text,
                ingested_at = EXCLUDED.ingested_at
        """,
    }


def required_source_tables() -> dict[str, list[str]]:
    return {
        "dim_player": ["player_master"],
        "player_alias": ["player_alias"],
        "player_mapping_rule_aliases": ["player_mapping_rule"],
        "dim_team_from_schedules": ["raw_nfl_schedule"],
        "dim_game": ["raw_nfl_schedule"],
        "fact_player_game_actual": ["player_game_feature_matrix"],
        "fact_dst_game_actual": ["raw_nfl_weekly_stat", "raw_nfl_schedule", "player_master"],
        "fact_dst_game_actual_observed_override": ["curated_salary", "dk_contest_standings_rows"],
        "fact_dst_game_actual_stale_identity_cleanup": ["curated_salary"],
        "fact_dst_game_actual_compat": [],
        "fact_dst_game_actual_compat_cleanup": [],
        "fact_player_game_actual_orphan_cleanup": [],
        "snapshot_salary": ["curated_salary", "raw_nfl_schedule"],
        "snapshot_injury_status": ["curated_injury", "raw_nfl_schedule"],
        "dfs_contest_entry_result": ["dk_contest_entries"],
    }


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


def apply_adapters(engine, source_schema: str, target_schema: str, dry_run: bool = False) -> list[AdapterResult]:
    results: list[AdapterResult] = []
    sql_by_adapter = adapter_sql(source_schema=source_schema, target_schema=target_schema)
    with engine.begin() as conn:
        available = existing_tables(conn, source_schema)
        if not dry_run:
            for statement in create_target_schema_sql(target_schema):
                conn.execute(text(statement))

    if not dry_run and {"curated_salary", "player_master"}.issubset(available):
        try:
            repair = repair_dst_identities(engine, schema=source_schema)
            results.append(
                AdapterResult(
                    name="dst_identity_repair",
                    status="applied",
                    rows=repair.salary_rows_resolved,
                    message=(
                        f"teams={repair.teams_seen}, created={repair.masters_created}, "
                        f"updated={repair.masters_updated}"
                    ),
                )
            )
        except SQLAlchemyError as exc:
            results.append(
                AdapterResult(
                    name="dst_identity_repair",
                    status="failed",
                    message=str(exc).splitlines()[0],
                )
            )

        try:
            repair = repair_salary_identities(
                engine,
                source_schema=source_schema,
                target_schema=target_schema,
            )
            results.append(
                AdapterResult(
                    name="salary_identity_repair",
                    status="applied",
                    rows=repair.salary_rows_resolved,
                    message=(
                        f"seen={repair.salary_rows_seen}, quarantined={repair.salary_rows_quarantined}, "
                        f"no_match={repair.no_match_rows}, ambiguous={repair.ambiguous_rows}, "
                        f"masters_updated={repair.masters_updated}"
                    ),
                )
            )
        except (RuntimeError, SQLAlchemyError) as exc:
            results.append(
                AdapterResult(
                    name="salary_identity_repair",
                    status="failed",
                    message=str(exc).splitlines()[0],
                )
            )

    missing_by_adapter = {
        name: [table for table in tables if table not in available]
        for name, tables in required_source_tables().items()
    }

    for name, statement in sql_by_adapter.items():
        missing = missing_by_adapter.get(name, [])
        if missing:
            results.append(
                AdapterResult(
                    name=name,
                    status="skipped",
                    message=f"Missing source table(s): {', '.join(missing)}",
                )
            )
            continue
        if dry_run:
            results.append(AdapterResult(name=name, status="would_apply"))
            continue
        try:
            with engine.begin() as conn:
                result = conn.execute(text(statement))
            results.append(AdapterResult(name=name, status="applied", rows=int(result.rowcount or 0)))
        except SQLAlchemyError as exc:
            results.append(AdapterResult(name=name, status="failed", message=str(exc).splitlines()[0]))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply initial legacy-to-target schema adapters.")
    parser.add_argument("--database", help="Postgres database name. Defaults to PGDATABASE.")
    parser.add_argument("--host", help="Postgres host. Defaults to PGHOST or localhost.")
    parser.add_argument("--port", help="Postgres port. Defaults to PGPORT or 5432.")
    parser.add_argument("--user", help="Postgres user. Defaults to PGUSER.")
    parser.add_argument("--password", help="Postgres password. Defaults to PGPASSWORD.")
    parser.add_argument("--source-schema", default="public")
    parser.add_argument("--target-schema", default="target")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    engine = create_engine(build_connection_url(args))
    results = apply_adapters(
        engine=engine,
        source_schema=args.source_schema,
        target_schema=args.target_schema,
        dry_run=args.dry_run,
    )
    payload = {
        "database": args.database or os.getenv("PGDATABASE"),
        "source_schema": args.source_schema,
        "target_schema": args.target_schema,
        "dry_run": args.dry_run,
        "applied": sum(1 for row in results if row.status == "applied"),
        "failed": sum(1 for row in results if row.status == "failed"),
        "skipped": sum(1 for row in results if row.status == "skipped"),
        "would_apply": sum(1 for row in results if row.status == "would_apply"),
        "results": [asdict(row) for row in results],
    }
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
    return 1 if (payload["failed"] or payload["skipped"]) and not args.dry_run else 0


if __name__ == "__main__":
    raise SystemExit(main())
