import unittest

from Database.dst import (
    charged_points_allowed,
    deterministic_dst_player_id,
    dk_dst_points,
    dk_points_allowed_score,
    is_dst_position,
    normalize_team,
    team_aliases,
)


class DstModelingTests(unittest.TestCase):
    def test_team_aliases_share_one_franchise_identity(self):
        self.assertEqual(normalize_team("la"), "LAR")
        self.assertEqual(normalize_team("STL"), "LAR")
        self.assertEqual(normalize_team("JAC"), "JAX")
        self.assertEqual(deterministic_dst_player_id("LA"), deterministic_dst_player_id("LAR"))
        self.assertEqual(team_aliases("LAR"), ("LA", "LAR", "STL"))

    def test_dst_position_matching_is_exact(self):
        self.assertTrue(is_dst_position("DST"))
        self.assertTrue(is_dst_position(" d "))
        self.assertFalse(is_dst_position("DL"))
        self.assertFalse(is_dst_position(""))

    def test_points_allowed_buckets_match_draftkings_contract(self):
        expected = {
            0: 10,
            1: 7,
            6: 7,
            7: 4,
            13: 4,
            14: 1,
            20: 1,
            21: 0,
            27: 0,
            28: -1,
            34: -1,
            35: -4,
        }
        for points_allowed, score in expected.items():
            with self.subTest(points_allowed=points_allowed):
                self.assertEqual(dk_points_allowed_score(points_allowed), score)

    def test_charged_points_remove_opponent_defensive_scores(self):
        self.assertEqual(charged_points_allowed(16, opponent_defensive_touchdowns=1), 9)
        self.assertEqual(charged_points_allowed(6, opponent_defensive_touchdowns=1), 0)

    def test_complete_dst_score_includes_returns_and_blocks(self):
        score = dk_dst_points(
            sacks=5,
            interceptions=2,
            fumble_recoveries=1,
            safeties=1,
            defensive_touchdowns=2,
            special_teams_touchdowns=1,
            blocked_kicks=1,
            points_allowed=13,
        )
        self.assertEqual(score, 37)


if __name__ == "__main__":
    unittest.main()
