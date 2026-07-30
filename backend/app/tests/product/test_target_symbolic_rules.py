import unittest

from backend.app.product_services.point_in_time import injury_snapshot_cutoff_sql
from scripts.product.apply_target_symbolic_rules import RULES_LOADED, RULE_SET_ID, filters_sql


class TargetSymbolicRulesTests(unittest.TestCase):
    def test_rule_set_id_is_versioned(self):
        self.assertEqual(RULE_SET_ID, "injury_symbolic_v0")
        self.assertEqual(RULES_LOADED, 4)

    def test_filters_scope_projection_alias(self):
        clause, params = filters_sql(season=2025, week=18)

        self.assertIn("proj.season = :season", clause)
        self.assertIn("proj.week = :week", clause)
        self.assertEqual(params, {"season": 2025, "week": 18})

    def test_injury_rules_require_snapshot_before_projection_cutoff(self):
        predicate = injury_snapshot_cutoff_sql(
            injury_alias="injury",
            projection_alias="proj",
        )

        self.assertIn("injury.as_of <= proj.data_cutoff_at", predicate)


if __name__ == "__main__":
    unittest.main()
