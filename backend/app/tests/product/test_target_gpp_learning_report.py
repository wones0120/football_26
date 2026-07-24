import unittest

from scripts.product.report_target_gpp_learning import recommend_gpp_rule


class TargetGppLearningReportTests(unittest.TestCase):
    def test_collects_more_data_for_small_samples(self):
        rec = recommend_gpp_rule(rows=12, top_decile_rate=0.5, value_4x_rate=0.5)

        self.assertEqual(rec.action, "collect_more_data")

    def test_increases_rules_finding_spikes_and_value(self):
        rec = recommend_gpp_rule(rows=100, top_decile_rate=0.2, value_4x_rate=0.25)

        self.assertEqual(rec.action, "consider_increase")

    def test_reduces_rules_without_spikes_or_value(self):
        rec = recommend_gpp_rule(rows=100, top_decile_rate=0.02, value_4x_rate=0.03)

        self.assertEqual(rec.action, "reduce_or_rework")


if __name__ == "__main__":
    unittest.main()
