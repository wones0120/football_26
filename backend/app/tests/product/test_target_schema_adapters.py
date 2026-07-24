import unittest

from scripts.product.apply_target_schema_adapters import (
    adapter_sql,
    canonical_team_sql,
    create_target_schema_sql,
    qident,
    required_source_tables,
)


class TargetSchemaAdapterTests(unittest.TestCase):
    def test_rejects_unsafe_identifier(self):
        with self.assertRaises(ValueError):
            qident("public;drop schema public")

    def test_ddl_uses_target_schema_not_public_table_collision(self):
        ddl = "\n".join(create_target_schema_sql("target"))

        self.assertIn('CREATE SCHEMA IF NOT EXISTS "target"', ddl)
        self.assertIn('"target".player_alias', ddl)
        self.assertIn('"target".identity_quarantine', ddl)
        self.assertIn("candidate_player_ids JSONB", ddl)
        self.assertIn('"target".dfs_contest_entry_result', ddl)
        self.assertIn("contest_type TEXT NOT NULL DEFAULT 'unknown'", ddl)
        self.assertIn('"target".player_projection', ddl)
        self.assertIn('"target".projection_run', ddl)
        self.assertIn('"target".active_projection_run', ddl)
        self.assertIn("schema_backfill_latest", ddl)
        self.assertIn('"target".symbolic_adjusted_projection', ddl)
        self.assertIn('"target".projection_evaluation', ddl)
        self.assertIn('"target".human_belief', ddl)
        self.assertIn("impact_status TEXT NOT NULL DEFAULT 'not_previewed'", ddl)
        self.assertIn('"target".raw_thought_capture', ddl)
        self.assertIn('"target".raw_thought_candidate', ddl)
        self.assertIn('"target".raw_thought_candidate_decision', ddl)
        self.assertIn("extraction_policy_id TEXT NOT NULL", ddl)
        self.assertIn('"target".belief_impact_preview', ddl)
        self.assertIn('"target".belief_impact_decision', ddl)
        self.assertIn("approved_modifier_json JSONB", ddl)
        self.assertIn('"target".optimizer_run', ddl)
        self.assertIn('"target".lineup', ddl)
        self.assertIn('"target".lineup_player', ddl)
        self.assertIn('"target".lineup_constraint_explanation', ddl)
        self.assertIn("contest_format TEXT NOT NULL", ddl)
        self.assertIn("objective TEXT NOT NULL", ddl)
        self.assertNotIn("public.player_alias", ddl)

    def test_adapter_sql_maps_core_legacy_tables(self):
        sql = adapter_sql("public", "target")

        self.assertIn('"public".player_master', sql["dim_player"])
        self.assertIn('"target".dim_player', sql["dim_player"])
        self.assertIn('"public".player_game_feature_matrix', sql["fact_player_game_actual"])
        self.assertIn('"target".fact_player_game_actual', sql["fact_player_game_actual"])
        self.assertIn("WHEN kickoff ~", sql["dim_game"])
        self.assertIn("ELSE NULL::date", sql["dim_game"])
        self.assertEqual(sql["fact_player_game_actual"].count("NULL::double precision"), 12)
        self.assertIn("player_master_id AS player_id", sql["fact_player_game_actual"])
        self.assertIn("fact_player_game_actual_orphan_cleanup", sql)
        self.assertIn('"public".raw_nfl_weekly_stat', sql["fact_dst_game_actual"])
        self.assertIn('"target".fact_dst_game_actual', sql["fact_dst_game_actual"])
        self.assertIn("fumble_recovery_tds", sql["fact_dst_game_actual"])
        self.assertIn("kicks_blocked_by_opponent", sql["fact_dst_game_actual"])
        self.assertIn("draftkings_contest", sql["fact_dst_game_actual_observed_override"])
        self.assertIn("active_identity", sql["fact_dst_game_actual_stale_identity_cleanup"])
        self.assertIn("'DST'", sql["fact_dst_game_actual_compat"])
        self.assertIn("NOT EXISTS", sql["fact_dst_game_actual_compat_cleanup"])
        self.assertIn("schedule_games.game_id", sql["snapshot_salary"])
        self.assertIn("schedule_games.game_id", sql["snapshot_injury_status"])
        self.assertIn('"public".dk_contest_entries', sql["dfs_contest_entry_result"])
        self.assertIn('"target".dfs_contest_entry_result', sql["dfs_contest_entry_result"])

    def test_required_sources_are_declared_for_all_initial_adapters(self):
        sources = required_source_tables()
        sql = adapter_sql("public", "target")

        self.assertEqual(set(sources), set(sql))
        self.assertEqual(sources["snapshot_salary"], ["curated_salary", "raw_nfl_schedule"])
        self.assertEqual(sources["dfs_contest_entry_result"], ["dk_contest_entries"])

    def test_team_sql_normalizes_cross_source_aliases(self):
        expression = canonical_team_sql("salary.team")

        self.assertIn("WHEN 'LA' THEN 'LAR'", expression)
        self.assertIn("WHEN 'JAC' THEN 'JAX'", expression)
        self.assertIn("upper(trim(salary.team))", expression)


if __name__ == "__main__":
    unittest.main()
