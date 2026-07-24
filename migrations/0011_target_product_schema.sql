-- Consolidated product target schema imported from football_opt.
-- Canonical identities remain public.player_master.player_master_id.

CREATE SCHEMA IF NOT EXISTS "target";

CREATE TABLE IF NOT EXISTS "target".dim_player (
            player_id TEXT PRIMARY KEY,
            full_name TEXT,
            first_name TEXT,
            last_name TEXT,
            birth_date DATE,
            primary_position TEXT,
            normalized_name TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        );

CREATE TABLE IF NOT EXISTS "target".player_alias (
            alias_id TEXT PRIMARY KEY,
            player_id TEXT NOT NULL REFERENCES "target".dim_player(player_id),
            source TEXT,
            source_player_id TEXT,
            source_player_name TEXT,
            normalized_name TEXT,
            confidence DOUBLE PRECISION,
            created_at TIMESTAMPTZ DEFAULT now()
        );

CREATE TABLE IF NOT EXISTS "target".identity_quarantine (
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
        );

CREATE INDEX IF NOT EXISTS idx_identity_quarantine_slate
        ON "target".identity_quarantine (season, week, slate, status);

CREATE TABLE IF NOT EXISTS "target".dim_team (
            team_id TEXT NOT NULL,
            season INT NOT NULL,
            team_abbr TEXT,
            team_name TEXT,
            conference TEXT,
            division TEXT,
            PRIMARY KEY (team_id, season)
        );

CREATE TABLE IF NOT EXISTS "target".dim_game (
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
        );

CREATE TABLE IF NOT EXISTS "target".fact_player_game_actual (
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
        );

CREATE TABLE IF NOT EXISTS "target".fact_dst_game_actual (
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
        );

CREATE TABLE IF NOT EXISTS "target".snapshot_salary (
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
        );

CREATE TABLE IF NOT EXISTS "target".snapshot_injury_status (
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
        );

CREATE TABLE IF NOT EXISTS "target".feature_generation_run (
            feature_run_id TEXT PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT now(),
            training_cutoff TIMESTAMPTZ,
            source_versions_json JSONB DEFAULT '{}',
            feature_set_hash TEXT,
            status TEXT NOT NULL DEFAULT 'completed'
        );

CREATE TABLE IF NOT EXISTS "target".feature_player_game (
            feature_run_id TEXT NOT NULL REFERENCES "target".feature_generation_run(feature_run_id),
            season INT NOT NULL,
            week INT NOT NULL,
            game_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            feature_json JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ DEFAULT now(),
            PRIMARY KEY (feature_run_id, season, week, game_id, player_id)
        );

CREATE TABLE IF NOT EXISTS "target".model_registry (
            model_id TEXT PRIMARY KEY,
            model_name TEXT NOT NULL,
            model_version TEXT NOT NULL,
            trained_on_start TEXT,
            trained_on_end TEXT,
            feature_set_hash TEXT,
            metrics_json JSONB DEFAULT '{}',
            artifact_uri TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        );

CREATE TABLE IF NOT EXISTS "target".model_run (
            model_run_id TEXT PRIMARY KEY,
            model_id TEXT NOT NULL REFERENCES "target".model_registry(model_id),
            feature_run_id TEXT REFERENCES "target".feature_generation_run(feature_run_id),
            created_at TIMESTAMPTZ DEFAULT now(),
            data_cutoff_at TIMESTAMPTZ,
            params_json JSONB DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'completed'
        );

CREATE TABLE IF NOT EXISTS "target".projection_run (
            projection_run_id TEXT PRIMARY KEY,
            model_run_id TEXT NOT NULL REFERENCES "target".model_run(model_run_id),
            season INT NOT NULL,
            week INT NOT NULL,
            slate_id TEXT NOT NULL,
            row_count INT NOT NULL,
            data_cutoff_at TIMESTAMPTZ,
            status TEXT NOT NULL DEFAULT 'completed',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

CREATE INDEX IF NOT EXISTS idx_projection_run_scope
        ON "target".projection_run (season, week, slate_id, created_at DESC);

CREATE TABLE IF NOT EXISTS "target".active_projection_run (
            season INT NOT NULL,
            week INT NOT NULL,
            slate_id TEXT NOT NULL,
            projection_run_id TEXT NOT NULL REFERENCES "target".projection_run(projection_run_id),
            selection_reason TEXT NOT NULL DEFAULT 'prediction_run_completed',
            selected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (season, week, slate_id)
        );

CREATE TABLE IF NOT EXISTS "target".player_projection (
            projection_run_id TEXT NOT NULL,
            model_run_id TEXT NOT NULL REFERENCES "target".model_run(model_run_id),
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
        );

INSERT INTO "target".projection_run
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
        FROM "target".player_projection
        GROUP BY projection_run_id
        ON CONFLICT (projection_run_id) DO NOTHING;

INSERT INTO "target".active_projection_run
            (season, week, slate_id, projection_run_id, selection_reason, selected_at)
        SELECT DISTINCT ON (season, week, slate_id)
            season, week, slate_id, projection_run_id,
            'schema_backfill_latest', created_at
        FROM "target".projection_run
        WHERE status = 'completed'
        ORDER BY season, week, slate_id, created_at DESC, projection_run_id
        ON CONFLICT (season, week, slate_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS "target".symbolic_rule (
            rule_id TEXT PRIMARY KEY,
            rule_name TEXT NOT NULL,
            rule_type TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now()
        );

CREATE TABLE IF NOT EXISTS "target".symbolic_rule_version (
            rule_id TEXT NOT NULL REFERENCES "target".symbolic_rule(rule_id),
            rule_version INT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            priority INT NOT NULL DEFAULT 100,
            condition_json JSONB NOT NULL DEFAULT '{}',
            action_json JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ DEFAULT now(),
            retired_at TIMESTAMPTZ,
            PRIMARY KEY (rule_id, rule_version)
        );

CREATE TABLE IF NOT EXISTS "target".symbolic_rule_run (
            rule_run_id TEXT PRIMARY KEY,
            projection_run_id TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            rules_loaded INT NOT NULL DEFAULT 0,
            rules_applied INT NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'completed'
        );

CREATE TABLE IF NOT EXISTS "target".symbolic_rule_application (
            rule_application_id BIGSERIAL PRIMARY KEY,
            rule_run_id TEXT NOT NULL REFERENCES "target".symbolic_rule_run(rule_run_id),
            rule_id TEXT NOT NULL,
            rule_version INT,
            projection_run_id TEXT,
            player_id TEXT NOT NULL,
            condition_context_json JSONB DEFAULT '{}',
            mean_before DOUBLE PRECISION,
            mean_after DOUBLE PRECISION,
            p90_before DOUBLE PRECISION,
            p90_after DOUBLE PRECISION,
            delta_mean DOUBLE PRECISION,
            delta_p90 DOUBLE PRECISION,
            reason TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        );

CREATE TABLE IF NOT EXISTS "target".symbolic_adjusted_projection (
            rule_run_id TEXT NOT NULL REFERENCES "target".symbolic_rule_run(rule_run_id),
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
        );

CREATE TABLE IF NOT EXISTS "target".learning_run (
            learning_run_id TEXT PRIMARY KEY,
            projection_run_id TEXT,
            rule_run_id TEXT,
            season INT,
            week INT,
            status TEXT NOT NULL DEFAULT 'completed',
            projections_evaluated INT NOT NULL DEFAULT 0,
            rules_evaluated INT NOT NULL DEFAULT 0,
            metrics_json JSONB DEFAULT '{}',
            recommendations_json JSONB DEFAULT '[]',
            created_at TIMESTAMPTZ DEFAULT now()
        );

CREATE TABLE IF NOT EXISTS "target".data_quality_run (
            quality_run_id TEXT PRIMARY KEY,
            report_id TEXT,
            contract_id TEXT NOT NULL,
            trigger TEXT NOT NULL,
            season INT NOT NULL,
            week INT,
            slate TEXT,
            status TEXT NOT NULL CHECK (status IN ('pass', 'warn', 'fail')),
            score INT NOT NULL CHECK (score BETWEEN 0 AND 100),
            summary_json JSONB NOT NULL DEFAULT '{}',
            source_context_json JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

CREATE INDEX IF NOT EXISTS idx_data_quality_run_scope
        ON "target".data_quality_run (season, week, slate, created_at DESC);

CREATE TABLE IF NOT EXISTS "target".data_quality_check (
            quality_check_id TEXT PRIMARY KEY,
            quality_run_id TEXT NOT NULL REFERENCES "target".data_quality_run(quality_run_id) ON DELETE CASCADE,
            check_id TEXT NOT NULL,
            category TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pass', 'warn', 'fail')),
            severity TEXT NOT NULL,
            table_name TEXT,
            check_name TEXT NOT NULL,
            message TEXT NOT NULL,
            value_json JSONB,
            threshold TEXT,
            affected_scope_json JSONB NOT NULL DEFAULT '{}',
            details_json JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (quality_run_id, check_id)
        );

CREATE INDEX IF NOT EXISTS idx_data_quality_check_status
        ON "target".data_quality_check (status, category, created_at DESC);

CREATE TABLE IF NOT EXISTS "target".human_belief (
            belief_version_id TEXT PRIMARY KEY,
            belief_id TEXT NOT NULL,
            belief_version INT NOT NULL,
            supersedes_version_id TEXT REFERENCES "target".human_belief(belief_version_id),
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
            metadata_json JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (belief_id, belief_version)
        );

CREATE INDEX IF NOT EXISTS idx_human_belief_scope
        ON "target".human_belief (scope_type, season, week, slate, created_at DESC);

CREATE TABLE IF NOT EXISTS "target".raw_thought_capture (
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
        );

CREATE INDEX IF NOT EXISTS idx_raw_thought_capture_scope
        ON "target".raw_thought_capture (season, week, slate, created_at DESC);

CREATE TABLE IF NOT EXISTS "target".raw_thought_candidate (
            candidate_id TEXT PRIMARY KEY,
            capture_id TEXT NOT NULL REFERENCES "target".raw_thought_capture(capture_id),
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
        );

CREATE TABLE IF NOT EXISTS "target".raw_thought_candidate_decision (
            decision_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL UNIQUE REFERENCES "target".raw_thought_candidate(candidate_id),
            decision TEXT NOT NULL CHECK (decision IN ('accepted', 'rejected')),
            belief_id TEXT,
            belief_version_id TEXT REFERENCES "target".human_belief(belief_version_id),
            reviewed_payload_json JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

CREATE TABLE IF NOT EXISTS "target".belief_impact_preview (
            preview_id TEXT PRIMARY KEY,
            belief_version_id TEXT NOT NULL REFERENCES "target".human_belief(belief_version_id),
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
        );

CREATE INDEX IF NOT EXISTS idx_belief_impact_preview_scope
        ON "target".belief_impact_preview (belief_id, season, week, slate, created_at DESC);

CREATE TABLE IF NOT EXISTS "target".belief_impact_decision (
            decision_id TEXT PRIMARY KEY,
            preview_id TEXT NOT NULL UNIQUE REFERENCES "target".belief_impact_preview(preview_id),
            decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
            note_text TEXT,
            approved_modifier_json JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

CREATE TABLE IF NOT EXISTS "target".projection_evaluation (
            evaluation_id BIGSERIAL PRIMARY KEY,
            learning_run_id TEXT REFERENCES "target".learning_run(learning_run_id),
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
        );

CREATE TABLE IF NOT EXISTS "target".rule_evaluation (
            evaluation_id BIGSERIAL PRIMARY KEY,
            learning_run_id TEXT REFERENCES "target".learning_run(learning_run_id),
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
        );

CREATE TABLE IF NOT EXISTS "target".source_file_import (
            source_file_id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            original_path TEXT,
            file_name TEXT,
            file_size_bytes BIGINT,
            first_ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata_json JSONB NOT NULL DEFAULT '{}'
        );

CREATE TABLE IF NOT EXISTS "target".dfs_contest (
            contest_id TEXT PRIMARY KEY,
            source_file_id TEXT REFERENCES "target".source_file_import(source_file_id),
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
            metadata_json JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

ALTER TABLE "target".dfs_contest
        ADD COLUMN IF NOT EXISTS contest_type TEXT NOT NULL DEFAULT 'unknown';

CREATE TABLE IF NOT EXISTS "target".dfs_contest_payout_tier (
            contest_id TEXT NOT NULL REFERENCES "target".dfs_contest(contest_id) ON DELETE CASCADE,
            min_rank INT NOT NULL,
            max_rank INT NOT NULL,
            payout NUMERIC(14, 2),
            prize_description TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (contest_id, min_rank, max_rank)
        );

CREATE TABLE IF NOT EXISTS "target".dfs_contest_entry_result (
            contest_id TEXT NOT NULL REFERENCES "target".dfs_contest(contest_id) ON DELETE CASCADE,
            entry_id TEXT NOT NULL,
            source_file_id TEXT REFERENCES "target".source_file_import(source_file_id),
            entry_name TEXT,
            rank INT,
            entry_points DOUBLE PRECISION,
            lineup_text TEXT,
            ingested_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (contest_id, entry_id)
        );

CREATE TABLE IF NOT EXISTS "target".import_batch (
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
        );

CREATE TABLE IF NOT EXISTS "target".import_batch_file (
            batch_id TEXT NOT NULL REFERENCES "target".import_batch(batch_id) ON DELETE CASCADE,
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
        );

ALTER TABLE "target".import_batch_file
        ADD COLUMN IF NOT EXISTS template_id TEXT;

CREATE TABLE IF NOT EXISTS "target".dk_entry_template_file (
            template_id TEXT PRIMARY KEY,
            source_file_id TEXT NOT NULL REFERENCES "target".source_file_import(source_file_id),
            season INT NOT NULL,
            week INT NOT NULL,
            slate_id TEXT NOT NULL,
            columns_json JSONB NOT NULL DEFAULT '[]',
            row_count INT NOT NULL DEFAULT 0,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (source_file_id, season, week, slate_id)
        );

CREATE TABLE IF NOT EXISTS "target".dk_entry_template_row (
            template_id TEXT NOT NULL REFERENCES "target".dk_entry_template_file(template_id) ON DELETE CASCADE,
            row_number INT NOT NULL,
            entry_id TEXT,
            contest_id TEXT,
            contest_name TEXT,
            entry_fee TEXT,
            row_json JSONB NOT NULL DEFAULT '{}',
            PRIMARY KEY (template_id, row_number)
        );

CREATE TABLE IF NOT EXISTS "target".simulation_run (
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
            params_json JSONB NOT NULL DEFAULT '{}',
            data_cutoff_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            status TEXT NOT NULL,
            message TEXT
        );

CREATE INDEX IF NOT EXISTS idx_simulation_run_scope
        ON "target".simulation_run
            (season, week, UPPER(slate_id), contest_format, created_at DESC);

CREATE TABLE IF NOT EXISTS "target".player_simulation (
            simulation_run_id TEXT NOT NULL
                REFERENCES "target".simulation_run(simulation_run_id) ON DELETE CASCADE,
            player_id TEXT NOT NULL,
            player_display_name TEXT NOT NULL,
            position TEXT NOT NULL,
            salary INT NOT NULL,
            projection_mean DOUBLE PRECISION NOT NULL,
            optimal_lineup_count INT NOT NULL,
            optimal_lineup_probability DOUBLE PRECISION NOT NULL,
            field_ownership DOUBLE PRECISION,
            leverage_score DOUBLE PRECISION,
            result_json JSONB NOT NULL DEFAULT '{}',
            PRIMARY KEY (simulation_run_id, player_id)
        );

CREATE TABLE IF NOT EXISTS "target".optimizer_run (
            optimizer_run_id TEXT PRIMARY KEY,
            projection_run_id TEXT,
            rule_run_id TEXT,
            slate_id TEXT,
            season INT NOT NULL,
            week INT NOT NULL,
            contest_format TEXT NOT NULL,
            objective TEXT NOT NULL,
            strategy TEXT NOT NULL,
            objective_config_json JSONB NOT NULL DEFAULT '{}',
            constraint_config_json JSONB NOT NULL DEFAULT '{}',
            data_cutoff_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            status TEXT NOT NULL,
            message TEXT
        );

CREATE TABLE IF NOT EXISTS "target".lineup (
            lineup_id TEXT PRIMARY KEY,
            optimizer_run_id TEXT NOT NULL REFERENCES "target".optimizer_run(optimizer_run_id) ON DELETE CASCADE,
            lineup_number INT NOT NULL,
            salary_used DOUBLE PRECISION,
            projected_mean DOUBLE PRECISION,
            projected_p90 DOUBLE PRECISION,
            ownership_sum DOUBLE PRECISION,
            leverage_score DOUBLE PRECISION,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (optimizer_run_id, lineup_number)
        );

CREATE TABLE IF NOT EXISTS "target".lineup_player (
            lineup_id TEXT NOT NULL REFERENCES "target".lineup(lineup_id) ON DELETE CASCADE,
            slot_index INT NOT NULL,
            player_id TEXT NOT NULL,
            roster_position TEXT,
            salary DOUBLE PRECISION,
            projection DOUBLE PRECISION,
            projected_p90 DOUBLE PRECISION,
            ownership_projection DOUBLE PRECISION,
            player_json JSONB NOT NULL DEFAULT '{}',
            PRIMARY KEY (lineup_id, slot_index)
        );

CREATE TABLE IF NOT EXISTS "target".lineup_constraint_explanation (
            explanation_id BIGSERIAL PRIMARY KEY,
            lineup_id TEXT NOT NULL REFERENCES "target".lineup(lineup_id) ON DELETE CASCADE,
            constraint_name TEXT NOT NULL,
            constraint_status TEXT NOT NULL,
            explanation_json JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

CREATE TABLE IF NOT EXISTS "target".lineup_portfolio (
            portfolio_id TEXT PRIMARY KEY,
            portfolio_name TEXT NOT NULL,
            optimizer_run_id TEXT NOT NULL REFERENCES "target".optimizer_run(optimizer_run_id),
            template_id TEXT NOT NULL REFERENCES "target".dk_entry_template_file(template_id),
            season INT NOT NULL,
            week INT NOT NULL,
            slate_id TEXT NOT NULL,
            contest_format TEXT NOT NULL,
            objective TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'assigned',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

CREATE TABLE IF NOT EXISTS "target".portfolio_lineup (
            portfolio_id TEXT NOT NULL REFERENCES "target".lineup_portfolio(portfolio_id) ON DELETE CASCADE,
            lineup_id TEXT NOT NULL REFERENCES "target".lineup(lineup_id),
            portfolio_lineup_number INT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (portfolio_id, lineup_id),
            UNIQUE (portfolio_id, portfolio_lineup_number)
        );

CREATE TABLE IF NOT EXISTS "target".contest_entry_assignment (
            assignment_id TEXT PRIMARY KEY,
            portfolio_id TEXT NOT NULL REFERENCES "target".lineup_portfolio(portfolio_id) ON DELETE CASCADE,
            template_id TEXT NOT NULL,
            template_row_number INT NOT NULL,
            entry_id TEXT NOT NULL,
            contest_id TEXT NOT NULL,
            lineup_id TEXT NOT NULL REFERENCES "target".lineup(lineup_id),
            status TEXT NOT NULL DEFAULT 'assigned',
            assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (template_id, template_row_number),
            UNIQUE (portfolio_id, lineup_id)
        );

CREATE TABLE IF NOT EXISTS "target".dk_export_validation (
            validation_id TEXT PRIMARY KEY,
            portfolio_id TEXT NOT NULL REFERENCES "target".lineup_portfolio(portfolio_id),
            status TEXT NOT NULL,
            checks_run INT NOT NULL,
            errors_json JSONB NOT NULL DEFAULT '[]',
            warnings_json JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

CREATE TABLE IF NOT EXISTS "target".dk_upload_export (
            export_id TEXT PRIMARY KEY,
            portfolio_id TEXT NOT NULL REFERENCES "target".lineup_portfolio(portfolio_id),
            validation_id TEXT REFERENCES "target".dk_export_validation(validation_id),
            contest_format TEXT NOT NULL,
            file_name TEXT NOT NULL,
            row_count INT NOT NULL,
            content_sha256 TEXT NOT NULL,
            columns_json JSONB NOT NULL DEFAULT '[]',
            csv_content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

ALTER TABLE "target".dk_upload_export
        ADD COLUMN IF NOT EXISTS validation_id TEXT
        REFERENCES "target".dk_export_validation(validation_id);
