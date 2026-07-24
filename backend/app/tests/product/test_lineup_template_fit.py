import unittest

from scripts.product.replay_lineup_template_fit import TemplateFitPolicy, classify_finish, score_classic_template


class LineupTemplateFitTests(unittest.TestCase):
    def test_scores_balanced_classic_template_as_strong(self):
        players = [
            {"roster_position": "QB", "bucket": "low", "ownership": 8},
            {"roster_position": "RB", "bucket": "mega_chalk", "ownership": 35},
            {"roster_position": "RB", "bucket": "chalk", "ownership": 22},
            {"roster_position": "WR", "bucket": "low", "ownership": 7},
            {"roster_position": "WR", "bucket": "dart", "ownership": 3},
            {"roster_position": "WR", "bucket": "mid", "ownership": 12},
            {"roster_position": "TE", "bucket": "mid", "ownership": 13},
            {"roster_position": "FLEX", "bucket": "popular", "ownership": 16},
            {"roster_position": "DST", "bucket": "dart", "ownership": 4},
        ]

        fit = score_classic_template(players)

        self.assertGreaterEqual(fit["score"], TemplateFitPolicy().strong_fit_score)
        self.assertEqual(fit["bucket_counts"]["dart"], 2)

    def test_scores_pure_chalk_template_as_not_strong(self):
        players = [
            {"roster_position": "QB", "bucket": "mega_chalk", "ownership": 40},
            {"roster_position": "RB", "bucket": "mega_chalk", "ownership": 35},
            {"roster_position": "RB", "bucket": "mega_chalk", "ownership": 33},
            {"roster_position": "WR", "bucket": "chalk", "ownership": 25},
            {"roster_position": "WR", "bucket": "chalk", "ownership": 22},
            {"roster_position": "WR", "bucket": "popular", "ownership": 18},
            {"roster_position": "TE", "bucket": "popular", "ownership": 17},
            {"roster_position": "FLEX", "bucket": "mid", "ownership": 12},
            {"roster_position": "DST", "bucket": "chalk", "ownership": 20},
        ]

        fit = score_classic_template(players)

        self.assertLess(fit["score"], TemplateFitPolicy().strong_fit_score)

    def test_classify_finish_uses_rank_percentile(self):
        finish = classify_finish(rank=10, total_entries=1000)

        self.assertFalse(finish["top_0_1_pct"])
        self.assertTrue(finish["top_1_pct"])
        self.assertTrue(finish["top_5_pct"])

    def test_classify_finish_does_not_treat_rank_ten_as_top_one_percent_in_large_contest(self):
        finish = classify_finish(rank=10, total_entries=100000)

        self.assertTrue(finish["top_0_1_pct"])
        self.assertTrue(finish["top_1_pct"])


if __name__ == "__main__":
    unittest.main()
