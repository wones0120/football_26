import unittest

from scripts.product.evaluate_target_baseline_projections import EvaluationResult, filters_sql


class TargetProjectionEvaluationTests(unittest.TestCase):
    def test_filters_can_scope_to_completed_week(self):
        clause, params = filters_sql(season=2025, week=18)

        self.assertIn("proj.season = :season", clause)
        self.assertIn("proj.week = :week", clause)
        self.assertEqual(params, {"season": 2025, "week": 18})

    def test_result_tracks_symbolic_evaluation_counts(self):
        result = EvaluationResult(status="completed", symbolic_learning_runs=2, rule_evaluations=9)

        self.assertEqual(result.symbolic_learning_runs, 2)
        self.assertEqual(result.rule_evaluations, 9)


if __name__ == "__main__":
    unittest.main()
