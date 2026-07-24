import unittest

from scripts.product.build_target_baseline_projections import MODEL_ID, filters_sql


class TargetBaselineProjectionTests(unittest.TestCase):
    def test_model_id_is_versioned_baseline(self):
        self.assertEqual(MODEL_ID, "baseline_rolling_dk_v0")

    def test_filters_require_prior_season_when_week_is_supplied(self):
        clause, params = filters_sql(season=2025, week=3)

        self.assertIn("actual.season = :season", clause)
        self.assertIn("actual.week = :week", clause)
        self.assertEqual(params, {"season": 2025, "week": 3})


if __name__ == "__main__":
    unittest.main()
