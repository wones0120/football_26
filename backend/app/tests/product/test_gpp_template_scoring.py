import unittest

from backend.app.product_services.gpp_optimizer import (
    Player,
    TagThresholds,
    classic_template_score,
    generate_portfolio,
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

    def test_live_pool_generation_uses_supplied_players_and_live_constraints(self):
        players = [
            Player("qb-a", "QB A", "A", "B", "QB", 5000, 20, 30, 5, game_id="A-B"),
            Player("rb-a", "RB A", "A", "B", "RB", 5000, 18, 28, 5, game_id="A-B"),
            Player("rb-b", "RB B", "B", "A", "RB", 5000, 17, 27, 5, game_id="A-B"),
            Player("rb-c", "RB C", "C", "D", "RB", 5000, 16, 26, 5, game_id="C-D"),
            Player("wr-a1", "WR A1", "A", "B", "WR", 5000, 15, 25, 5, game_id="A-B"),
            Player("wr-a2", "WR A2", "A", "B", "WR", 5000, 14, 24, 5, game_id="A-B"),
            Player("wr-b", "WR B", "B", "A", "WR", 5000, 13, 23, 5, game_id="A-B"),
            Player("wr-c", "WR C", "C", "D", "WR", 5000, 12, 22, 5, game_id="C-D"),
            Player("te-a", "TE A", "A", "B", "TE", 5000, 11, 21, 5, game_id="A-B"),
            Player("te-b", "TE B", "B", "A", "TE", 5000, 10, 20, 5, game_id="A-B"),
            Player("dst-c", "DST C", "C", "D", "DST", 3000, 9, 19, 5, game_id="C-D"),
        ]

        result = generate_portfolio(
            season=2025,
            week=11,
            slate="SUNDAY_MAIN",
            num_lineups=1,
            engine=object(),
            players=players,
            ownership_available=True,
            max_exposure=1.0,
            enforce_single_te=True,
            avoid_dst_opponents=True,
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.lineups), 1)
        team_counts = {
            team: sum(player.team == team for player in result.lineups[0])
            for team in {player.team for player in result.lineups[0]}
        }
        self.assertLessEqual(max(team_counts.values()), 4)
        self.assertLessEqual(
            sum(player.position == "TE" for player in result.lineups[0]),
            1,
        )
        self.assertTrue(
            {player.player_id for player in result.lineups[0]}
            <= {player.player_id for player in players}
        )


if __name__ == "__main__":
    unittest.main()
