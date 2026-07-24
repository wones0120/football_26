import unittest

from scripts.product.profile_target_schema import assess_readiness


class TargetSchemaProfileTests(unittest.TestCase):
    def test_reports_loaded_foundation_but_missing_learning_layer(self):
        target_tables = {
            "dim_player",
            "player_alias",
            "identity_quarantine",
            "dim_team",
            "dim_game",
            "fact_player_game_actual",
            "fact_dst_game_actual",
            "snapshot_salary",
            "snapshot_injury_status",
        }
        row_counts = {table_name: 1 for table_name in target_tables}

        report = assess_readiness(
            target_tables=target_tables,
            source_tables={"nfl_weekly_data_with_scores", "player_expected_points"},
            row_counts=row_counts,
        )

        self.assertTrue(report["target_foundation_ready"])
        self.assertFalse(report["target_native_learning_ready"])
        self.assertTrue(report["legacy_backfill_ready"])
        self.assertIn("player_projection", report["missing_target_learning_tables"])
        self.assertEqual(report["empty_target_learning_tables"], [])

    def test_empty_foundation_table_blocks_target_readiness(self):
        target_tables = {
            "dim_player",
            "player_alias",
            "identity_quarantine",
            "dim_team",
            "dim_game",
            "fact_player_game_actual",
            "fact_dst_game_actual",
            "snapshot_salary",
            "snapshot_injury_status",
        }
        row_counts = {table_name: 1 for table_name in target_tables}
        row_counts["fact_player_game_actual"] = 0

        report = assess_readiness(target_tables=target_tables, source_tables=set(), row_counts=row_counts)

        self.assertFalse(report["target_foundation_ready"])
        self.assertIn("fact_player_game_actual", report["empty_target_foundation_tables"])
        self.assertFalse(report["legacy_backfill_ready"])

    def test_empty_projection_layer_blocks_target_learning(self):
        target_tables = {
            "dim_player",
            "player_alias",
            "identity_quarantine",
            "dim_team",
            "dim_game",
            "fact_player_game_actual",
            "fact_dst_game_actual",
            "snapshot_salary",
            "snapshot_injury_status",
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
        }
        row_counts = {table_name: 1 for table_name in target_tables}
        row_counts["player_projection"] = 0

        report = assess_readiness(target_tables=target_tables, source_tables=set(), row_counts=row_counts)

        self.assertFalse(report["target_native_learning_ready"])
        self.assertIn("player_projection", report["empty_target_learning_tables"])


if __name__ == "__main__":
    unittest.main()
