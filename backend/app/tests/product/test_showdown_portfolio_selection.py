import unittest

import pandas as pd

from backend.app.product_services.optimizer import OptimizerService, add_showdown_lineup_chalk_metrics
from backend.app.product_services.showdown_portfolio_selection import (
    candidate_metrics,
    select_showdown_portfolio,
)


def lineup(captain: str, flex: list[str], mean: float, p90: float, selector: float,
           missing_ownership: str | None = None) -> list[dict]:
    rows = []
    for index, player_id in enumerate([captain, *flex]):
        rows.append({
            "player_id": player_id,
            "name": player_id,
            "roster_position": "CPT" if index == 0 else "FLEX",
            "salary": 10000 if index == 0 else 5000,
            "projection": mean / 6,
            "p90": p90 / 6,
            "ownership": None if player_id == missing_ownership else 10.0,
        })
    rows[0]["solver_objective_value"] = selector
    return rows


class ShowdownPortfolioSelectionTests(unittest.TestCase):
    def test_family_candidate_competes_with_normal_candidates(self):
        normal = lineup("Smith", ["a", "b", "c", "d", "e"], 76, 142, 100)
        hurts = lineup("Hurts", ["a", "b", "c", "d", "f"], 75, 141, 99)
        weak = lineup("Raymond", ["a", "b", "c", "d", "g"], 69, 130, 90)
        selected, report = select_showdown_portfolio(
            [normal, hurts, weak, normal], requested=3,
            player_limits={pid: 3 for pid in "abcdefg"} | {"Smith": 3, "Hurts": 3, "Raymond": 3},
            captain_limit=2,
        )
        self.assertEqual(report["candidate_count"], 3)
        self.assertEqual(report["quality_eligible_count"], 2)
        self.assertEqual([row[0]["player_id"] for row in selected], ["Smith", "Hurts"])
        self.assertEqual(report["selected"], 2)
        self.assertIn("Joint quality screen", report["omission_reasons"][3])
        self.assertEqual(selected[1][0]["showdown_selection_diagnostic"]["global_candidate_rank"], 2)

    def test_exposure_rejection_names_the_binding_player(self):
        candidates = [
            lineup("C1", ["core", "a", "b", "c", "d"], 80, 140, 100),
            lineup("C2", ["core", "e", "f", "g", "h"], 79, 139, 99),
            lineup("C3", ["i", "j", "k", "l", "m"], 78, 138, 98),
        ]
        limits = {pid: 3 for row in candidates for pid in [player["player_id"] for player in row]}
        limits["core"] = 1
        selected, report = select_showdown_portfolio(
            candidates, requested=2, player_limits=limits, captain_limit=2,
        )
        self.assertEqual([row[0]["player_id"] for row in selected], ["C1", "C3"])
        self.assertIn("selector points", report["omission_reasons"][2])
        skipped = selected[1][0]["showdown_selection_diagnostic"]["higher_ranked_skipped"]
        self.assertIn("player exposure: core", skipped[0]["blockers"])

    def test_partial_ownership_is_unavailable_and_never_zero_filled(self):
        candidate = lineup("C1", ["a", "b", "c", "d", "e"], 80, 140, 100, "e")
        self.assertFalse(candidate_metrics(candidate)["ownership_complete"])
        self.assertIsNone(candidate_metrics(candidate)["lineup_ownership"])
        summary = add_showdown_lineup_chalk_metrics([candidate])[0]
        self.assertFalse(summary["ownership_available"])
        self.assertIsNone(summary["probability_product"])
        self.assertEqual(summary["missing_ownership_players"], ["e"])
        self.assertEqual(summary["salary_left_unused"], 15000)

    def test_direct_solver_rejects_partial_role_ownership_scoring(self):
        pool = pd.DataFrame([
            {"player_id": "c", "name": "Captain", "position": "RB", "player_team": "A",
             "salary": 5000, "projection": 10, "p90": 20, "captain_ownership": None,
             "flex_ownership": 12},
        ])
        service = OptimizerService.__new__(OptimizerService)
        with self.assertRaisesRegex(ValueError, "complete finite CPT/FLEX ownership"):
            service._solve_lineup(
                pool, score_col="projection", contest_type="captain",
                stack_params={"use_role_ownership": True},
            )


if __name__ == "__main__":
    unittest.main()
