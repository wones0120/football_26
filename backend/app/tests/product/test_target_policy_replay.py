import unittest

from scripts.product.simulate_target_policy_replay import adjusted_with_policy, policies_from_report, policy_multiplier


class TargetPolicyReplayTests(unittest.TestCase):
    def test_policy_multiplier_reduces_bad_rule(self):
        self.assertEqual(policy_multiplier("reduce"), 0.5)
        self.assertEqual(policy_multiplier("consider_disable_or_reduce"), 0.0)
        self.assertEqual(policy_multiplier("consider_increase"), 1.25)

    def test_adjusted_with_policy_scales_delta_from_base(self):
        self.assertEqual(adjusted_with_policy(base_mean=10.0, static_adjusted_mean=13.0, multiplier=0.5), 11.5)
        self.assertEqual(adjusted_with_policy(base_mean=10.0, static_adjusted_mean=13.0, multiplier=0.0), 10.0)

    def test_policies_from_report_extracts_rule_actions(self):
        policies = policies_from_report(
            {
                "rules": [
                    {
                        "rule_id": "r1",
                        "rows": 100,
                        "avg_delta_mae": -0.2,
                        "hit_rate": 0.3,
                        "recommendation": {"action": "reduce"},
                    }
                ]
            }
        )

        self.assertEqual(policies["r1"]["action"], "reduce")
        self.assertEqual(policies["r1"]["multiplier"], 0.5)


if __name__ == "__main__":
    unittest.main()
