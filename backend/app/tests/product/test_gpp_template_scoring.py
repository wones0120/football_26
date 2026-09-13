import unittest
from datetime import timedelta

from backend.app.product_services.gpp_optimizer import (
    Player,
    TagThresholds,
    build_large_gpp_config,
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
        self.assertEqual(result.created_at.utcoffset(), timedelta(0))
        self.assertEqual(result.updated_at.utcoffset(), timedelta(0))
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

    def test_large_gpp_honors_requested_minimum_exposure(self):
        players = [
            Player("qb-a", "QB A", "A", "B", "QB", 5000, 20, 30, 0, game_id="A-B"),
            Player("rb-a", "RB A", "A", "B", "RB", 5000, 18, 28, 0, game_id="A-B"),
            Player("rb-b", "RB B", "B", "A", "RB", 5000, 17, 27, 0, game_id="A-B"),
            Player("rb-c", "RB C", "C", "D", "RB", 5000, 16, 26, 0, game_id="C-D"),
            Player("wr-a", "WR A", "A", "B", "WR", 5000, 15, 25, 0, game_id="A-B"),
            Player("wr-b", "WR B", "B", "A", "WR", 5000, 14, 24, 0, game_id="A-B"),
            Player("wr-c", "WR C", "C", "D", "WR", 5000, 13, 23, 0, game_id="C-D"),
            Player("wr-d", "WR D", "D", "C", "WR", 5000, 12, 22, 0, game_id="C-D"),
            Player("te-a", "TE A", "A", "B", "TE", 5000, 11, 21, 0, game_id="A-B"),
            Player("te-b", "TE B", "B", "A", "TE", 4000, 5, 10, 0, game_id="A-B"),
            Player("dst-c", "DST C", "C", "D", "DST", 3000, 9, 19, 0, game_id="C-D"),
        ]

        result = generate_portfolio(
            season=2026,
            week=1,
            slate="SUNDAY_MAIN",
            num_lineups=1,
            engine=object(),
            config_builder=build_large_gpp_config,
            players=players,
            ownership_available=False,
            max_exposure=1.0,
            minimum_exposure_by_player={"te-b": 1.0},
        )

        self.assertEqual(result.status, "completed")
        self.assertIn("te-b", {player.player_id for player in result.lineups[0]})

    def test_large_gpp_objective_consumes_context_adjustment_without_mutating_projection(self):
        fixed_players = [
            Player("qb-a", "QB A", "A", "B", "QB", 5000, 20, 30, 0, game_id="A-B"),
            Player("rb-a", "RB A", "A", "B", "RB", 5000, 18, 28, 0, game_id="A-B"),
            Player("rb-b", "RB B", "B", "A", "RB", 5000, 17, 27, 0, game_id="A-B"),
            Player("rb-c", "RB C", "C", "D", "RB", 5000, 16, 26, 0, game_id="C-D"),
            Player("wr-a", "WR A", "A", "B", "WR", 5000, 15, 25, 0, game_id="A-B"),
            Player("wr-b", "WR B", "B", "A", "WR", 5000, 14, 24, 0, game_id="A-B"),
            Player("wr-c", "WR C", "C", "D", "WR", 5000, 13, 23, 0, game_id="C-D"),
            Player("dst-d", "DST D", "D", "C", "DST", 3000, 9, 19, 0, game_id="C-D"),
        ]
        raw_te = Player(
            "te-raw", "TE Raw", "B", "A", "TE", 5000, 11.0, 21.0, 0, game_id="A-B"
        )
        contextual_te = Player(
            "te-context",
            "TE Context",
            "B",
            "A",
            "TE",
            5000,
            10.9,
            20.9,
            0,
            game_id="A-B",
            optimizer_context_adjustment=1.0,
        )

        result = generate_portfolio(
            season=2026,
            week=1,
            slate="SUNDAY_MAIN",
            num_lineups=1,
            engine=object(),
            config_builder=build_large_gpp_config,
            players=[*fixed_players, raw_te, contextual_te],
            ownership_available=False,
            max_exposure=1.0,
        )

        selected_ids = {player.player_id for player in result.lineups[0]}
        self.assertIn("te-context", selected_ids)
        self.assertNotIn("te-raw", selected_ids)
        self.assertEqual(contextual_te.projection, 10.9)
        self.assertEqual(contextual_te.ceiling, 20.9)

    def test_large_gpp_objective_consumes_shared_correlation_rules(self):
        fixed_players = [
            Player("qb-a", "QB A", "A", "B", "QB", 5000, 20, 30, 0, game_id="A-B"),
            Player("rb-a", "RB A", "A", "B", "RB", 5000, 18, 28, 0, game_id="A-B"),
            Player("rb-b", "RB B", "B", "A", "RB", 5000, 17, 27, 0, game_id="A-B"),
            Player("rb-c", "RB C", "C", "D", "RB", 5000, 16, 26, 0, game_id="C-D"),
            Player("wr-a", "WR A", "A", "B", "WR", 5000, 15, 25, 0, game_id="A-B"),
            Player("wr-b", "WR B", "B", "A", "WR", 5000, 14, 24, 0, game_id="A-B"),
            Player("wr-c", "WR C", "C", "D", "WR", 5000, 13, 23, 0, game_id="C-D"),
            Player("dst-d", "DST D", "D", "C", "DST", 3000, 9, 19, 0, game_id="C-D"),
        ]
        raw_te = Player(
            "te-raw", "TE Raw", "B", "A", "TE", 5000, 11.0, 21.0, 0, game_id="A-B"
        )
        stack_te = Player(
            "te-stack", "TE Stack", "A", "B", "TE", 5000, 10.9, 20.9, 0, game_id="A-B"
        )

        result = generate_portfolio(
            season=2026,
            week=1,
            slate="SUNDAY_MAIN",
            num_lineups=1,
            engine=object(),
            config_builder=build_large_gpp_config,
            players=[*fixed_players, raw_te, stack_te],
            ownership_available=False,
            max_exposure=1.0,
        )

        selected_ids = {player.player_id for player in result.lineups[0]}
        self.assertIn("te-stack", selected_ids)
        self.assertNotIn("te-raw", selected_ids)

    def test_large_gpp_rejects_exposure_for_player_outside_candidate_pool(self):
        players = [
            Player("qb-a", "QB A", "A", "B", "QB", 5000, 20, 30, 0),
        ]

        with self.assertRaisesRegex(ValueError, "outside the candidate pool"):
            generate_portfolio(
                season=2026,
                week=1,
                slate="SUNDAY_MAIN",
                num_lineups=1,
                engine=object(),
                config_builder=build_large_gpp_config,
                players=players,
                ownership_available=False,
                minimum_exposure_by_player={"missing-player": 1.0},
            )


if __name__ == "__main__":
    unittest.main()
