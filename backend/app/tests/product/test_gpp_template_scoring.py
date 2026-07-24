import unittest

from backend.app.product_services.gpp_optimizer import (
    Player,
    TagThresholds,
    classic_template_score,
    ownership_bucket,
    tag_players,
    template_score_bucket,
)


def player(position: str, ownership: float) -> Player:
    return Player(
        player_id=f"{position}-{ownership}",
        name=f"{position} {ownership}",
        team="A",
        opponent="B",
        position=position,
        salary=5000,
        projection=10.0,
        ceiling=20.0,
        ownership=ownership,
    )


class GppTemplateScoringTests(unittest.TestCase):
    def test_ownership_bucket(self):
        self.assertEqual(ownership_bucket(35), "mega_chalk")
        self.assertEqual(ownership_bucket(22), "chalk")
        self.assertEqual(ownership_bucket(16), "popular")
        self.assertEqual(ownership_bucket(12), "mid")
        self.assertEqual(ownership_bucket(7), "low")
        self.assertEqual(ownership_bucket(2), "dart")

    def test_leverage_compares_optimal_probability_to_ownership(self):
        candidate = player("WR", 18.0)
        candidate.optimal_lineup_probability = 24.5

        tag_players([candidate], TagThresholds())

        self.assertEqual(candidate.leverage, 6.5)
        self.assertIn("leverage", candidate.tags)

    def test_leverage_is_not_fabricated_without_simulation(self):
        candidate = player("WR", 18.0)

        tag_players([candidate], TagThresholds())

        self.assertEqual(candidate.leverage, 0.0)
        self.assertNotIn("leverage", candidate.tags)

    def test_balanced_lineup_scores_strong(self):
        lineup = [
            player("QB", 8),
            player("RB", 35),
            player("RB", 22),
            player("WR", 7),
            player("WR", 3),
            player("WR", 12),
            player("TE", 13),
            player("FLEX", 16),
            player("DST", 4),
        ]

        score = classic_template_score(lineup)

        self.assertGreaterEqual(score, 8)
        self.assertEqual(template_score_bucket(score), "strong")

    def test_pure_chalk_lineup_scores_lower(self):
        lineup = [
            player("QB", 40),
            player("RB", 35),
            player("RB", 33),
            player("WR", 25),
            player("WR", 22),
            player("WR", 18),
            player("TE", 17),
            player("FLEX", 12),
            player("DST", 20),
        ]

        score = classic_template_score(lineup)

        self.assertLess(score, 8)


if __name__ == "__main__":
    unittest.main()
