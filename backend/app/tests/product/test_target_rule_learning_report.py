import unittest

from scripts.product.report_target_rule_learning import contest_profile_sql, cutoff_sql, recommend_rule, validate_contest_profile


class TargetRuleLearningReportTests(unittest.TestCase):
    def test_cutoff_requires_season_for_week(self):
        with self.assertRaises(ValueError):
            cutoff_sql(None, 3)

    def test_cutoff_can_scope_replay_through_week(self):
        clause, params = cutoff_sql(2025, 8)

        self.assertIn("eval.season < :through_season", clause)
        self.assertIn("eval.week <= :through_week", clause)
        self.assertEqual(params, {"through_season": 2025, "through_week": 8})

    def test_recommends_collect_more_data_for_small_sample(self):
        rec = recommend_rule(rows=12, avg_delta_mae=1.0, hit_rate=0.9)

        self.assertEqual(rec.action, "collect_more_data")

    def test_recommends_reduce_for_bad_rule(self):
        rec = recommend_rule(rows=120, avg_delta_mae=-0.4, hit_rate=0.3)

        self.assertEqual(rec.action, "consider_disable_or_reduce")

    def test_recommends_increase_for_strong_rule(self):
        rec = recommend_rule(rows=120, avg_delta_mae=0.4, hit_rate=0.7)

        self.assertEqual(rec.action, "consider_increase")

    def test_contest_profile_sql_filters_cash_rules(self):
        clause, params = contest_profile_sql("cash")

        self.assertIn("contest_profiles", clause)
        self.assertEqual(params, {"contest_profile": "cash"})

    def test_invalid_contest_profile_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_contest_profile("single-entry")


if __name__ == "__main__":
    unittest.main()
