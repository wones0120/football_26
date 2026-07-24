import unittest

from scripts.product.replay_target_rule_evolution import ACTIONABLE_RECOMMENDATIONS, previous_cutoff, summarize_rule


class TargetRuleEvolutionReplayTests(unittest.TestCase):
    def test_week_one_uses_prior_season_as_cutoff(self):
        self.assertEqual(previous_cutoff(2025, 1), (2024, None))

    def test_later_week_uses_prior_week_as_cutoff(self):
        self.assertEqual(previous_cutoff(2025, 8), (2025, 7))

    def test_summarize_rule_extracts_recommendation(self):
        summary = summarize_rule(
            {
                "rule_id": "r1",
                "rule_name": "Rule One",
                "rows": 100,
                "avg_delta_mae": -0.2,
                "hit_rate": 0.3,
                "recommendation": {"action": "reduce", "severity": "negative", "rationale": "bad"},
            }
        )

        self.assertEqual(summary["action"], "reduce")
        self.assertIn("reduce", ACTIONABLE_RECOMMENDATIONS)


if __name__ == "__main__":
    unittest.main()
