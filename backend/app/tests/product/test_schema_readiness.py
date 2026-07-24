import unittest

from scripts.product.inspect_schema_readiness import inspect_schema


class SchemaReadinessTests(unittest.TestCase):
    def test_classifies_present_target_tables(self):
        report = inspect_schema(
            {"dim_player", "player_alias", "dim_game", "fact_player_game_actual", "fact_dst_game_actual"}
        )
        rows = {row["name"]: row for row in report["tables"]}

        self.assertEqual(rows["dim_player"]["status"], "present")
        self.assertEqual(rows["fact_player_game_actual"]["status"], "present")
        self.assertEqual(rows["fact_dst_game_actual"]["status"], "present")

    def test_classifies_legacy_mappable_tables(self):
        report = inspect_schema({"player_master", "raw_nfl_weekly_stat", "player_expected_points"})
        rows = {row["name"]: row for row in report["tables"]}

        self.assertEqual(rows["dim_player"]["status"], "mappable_from_legacy")
        self.assertEqual(rows["fact_player_game_actual"]["status"], "mappable_from_legacy")
        self.assertEqual(rows["fact_dst_game_actual"]["status"], "mappable_from_legacy")
        self.assertEqual(rows["player_projection"]["status"], "mappable_from_legacy")
        self.assertIn("player_master", rows["dim_player"]["legacy_candidates_present"])

    def test_reports_required_learning_blockers(self):
        report = inspect_schema({"player_master"})

        missing = report["required_for_learning"]["missing"]
        self.assertIn("dim_game", missing)
        self.assertIn("fact_player_game_actual", missing)
        self.assertIn("fact_dst_game_actual", missing)
        self.assertGreater(report["counts"]["missing"], 0)


if __name__ == "__main__":
    unittest.main()
