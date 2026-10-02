import unittest

import pandas as pd

from backend.app.product_services.showdown_game_scenarios import (
    condition_player_pool, define_game_scenarios,
)
from backend.app.product_services.showdown_portfolio_selection import select_showdown_portfolio
from backend.app.product_services.optimizer import OptimizerService


def player(pid, team, position, role=""):
    implied = 25 if team == "A" else 22
    return {
        "player_id": pid, "name": pid, "player_team": team,
        "position": position, "role_label": role,
        "projection": 10.0, "p90": 18.0,
        "optimizer_context_ceiling_score": 19.0,
        "game_total_line": 47, "team_spread_line": -3 if team == "A" else 3,
        "team_implied_total": implied,
    }


def lineup(captain, other, scenario, selector, mean=80, p90=140):
    rows = []
    for index, pid in enumerate([captain, *other]):
        rows.append({
            "player_id": pid, "name": pid, "player_team": "A" if index < 3 else "B",
            "roster_position": "CPT" if index == 0 else "FLEX",
            "salary": 5000, "projection": mean / 6, "p90": p90 / 6,
            "showdown_scenario_id": scenario,
        })
    rows[0]["solver_objective_value"] = selector
    return rows


class ShowdownGameScenarioTests(unittest.TestCase):
    def test_market_conditioning_keeps_two_sided_roles_and_baseline(self):
        pool = pd.DataFrame([
            player("a_rb", "A", "RB"), player("a_qb", "A", "QB"),
            player("a_dst", "A", "DST"), player("b_rb", "B", "RB"),
            player("b_wr", "B", "WR"), player("b_qb", "B", "QB"),
        ])
        baseline, a_win, b_win = define_game_scenarios(pool)
        self.assertEqual([baseline.scenario_id, a_win.scenario_id, b_win.scenario_id], [
            "baseline", "team_a_decisive_win", "team_b_decisive_win",
        ])
        self.assertGreaterEqual(a_win.conditioned_implied_by_team["A"] - a_win.conditioned_implied_by_team["B"], 14)
        conditioned = condition_player_pool(pool, a_win).set_index("player_id")
        self.assertGreater(conditioned.loc["a_rb", "projection"], 10)
        self.assertGreater(conditioned.loc["a_dst", "projection"], 10)
        self.assertLess(conditioned.loc["a_qb", "projection"], conditioned.loc["a_rb", "projection"])
        self.assertLess(conditioned.loc["b_rb", "projection"], 10)
        self.assertGreater(conditioned.loc["b_wr", "projection"], conditioned.loc["b_rb", "projection"])
        self.assertTrue((conditioned["projection"] >= conditioned["baseline_projection"] * 0.78).all())
        self.assertTrue((conditioned["projection"] <= conditioned["baseline_projection"] * 1.22).all())
        self.assertEqual(pool.loc[0, "projection"], 10)
        self.assertEqual(condition_player_pool(pool, baseline)["projection"].tolist(), pool["projection"].tolist())

    def test_missing_market_does_not_make_up_decisive_scenarios(self):
        pool = pd.DataFrame([player("a", "A", "QB"), player("b", "B", "QB")])
        pool["game_total_line"] = None
        pool["team_implied_total"] = None
        self.assertEqual([item.scenario_id for item in define_game_scenarios(pool)], ["baseline"])
        unsafe = pd.DataFrame([player("a", "A", "QB"), player("b", "B", "QB")])
        unsafe["market_context_point_in_time_safe"] = False
        self.assertEqual([item.scenario_id for item in define_game_scenarios(unsafe)], ["baseline"])
        with self.assertRaisesRegex(ValueError, "between 7 and 35"):
            define_game_scenarios(pool, margin=50)

    def test_conditioned_solver_can_produce_three_three(self):
        rows = []
        for team in ("A", "B"):
            for index, position in enumerate(("QB", "RB", "WR", "WR", "TE", "DST", "K")):
                row = player(f"{team}{index}", team, position)
                row["salary"] = 6500
                rows.append(row)
        pool = pd.DataFrame(rows)
        scenario = define_game_scenarios(pool)[1]
        service = OptimizerService.__new__(OptimizerService)
        selected = service._solve_lineup(
            condition_player_pool(pool, scenario),
            score_col="optimizer_context_ceiling_score", contest_type="captain",
            stack_params={"use_role_ownership": False},
            portfolio_script={"kind": "scenario_construction", "team": "A", "team_players": 3},
            include_control_comparison=False,
        )
        self.assertIsNotNone(selected)
        self.assertEqual(sum(row["player_team"] == "A" for row in selected), 3)
        captain = next(row for row in selected if row["roster_position"] == "CPT")
        baseline = pool.loc[pool["player_id"] == captain["player_id"], "projection"].iloc[0]
        self.assertEqual(captain["baseline_projection"], baseline * 1.5)

    def test_diversity_cannot_bypass_quality_and_keeps_rosters_unique(self):
        a = lineup("A1", ["a", "b", "c", "d", "e"], "baseline", 100)
        b = lineup("B1", ["f", "g", "h", "i", "j"], "team_a_decisive_win", 99)
        c = lineup("C1", ["k", "l", "m", "n", "o"], "team_b_decisive_win", 98)
        weak = lineup("W1", ["p", "q", "r", "s", "t"], "team_b_decisive_win", 97, mean=60, p90=100)
        same_roster = lineup("A1", ["a", "b", "c", "d", "e"], "team_b_decisive_win", 101)
        limits = {row["player_id"]: 3 for candidate in (a, b, c, weak) for row in candidate}
        selected, report = select_showdown_portfolio(
            [a, b, c, weak, same_roster], requested=3,
            player_limits=limits, captain_limit=3, require_scenario_diversity=True,
        )
        self.assertEqual(len(selected), 3)
        self.assertEqual({row[0]["showdown_scenario_id"] for row in selected}, {
            "baseline", "team_a_decisive_win", "team_b_decisive_win",
        })
        self.assertEqual(len({frozenset(player["player_id"] for player in row) for row in selected}), 3)
        self.assertEqual(report["quality_eligible_count"], 4)
        self.assertEqual(report["scenario_family_coverage"][2]["selected"], True)

    def test_scenario_discovery_does_not_force_weak_family(self):
        baseline = lineup("A1", ["a", "b", "c", "d", "e"], "baseline", 100)
        strong = lineup("B1", ["f", "g", "h", "i", "j"], "team_a_decisive_win", 99)
        weak = lineup("C1", ["k", "l", "m", "n", "o"], "team_b_decisive_win", 98, mean=65, p90=110)
        limits = {row["player_id"]: 2 for candidate in (baseline, strong, weak) for row in candidate}
        for diversity in (False, True):
            selected, report = select_showdown_portfolio(
                [baseline, strong, weak], requested=2, player_limits=limits,
                captain_limit=2, require_scenario_diversity=diversity,
            )
            self.assertEqual([row[0]["showdown_scenario_id"] for row in selected], [
                "baseline", "team_a_decisive_win",
            ])
            missing = next(row for row in report["scenario_family_coverage"]
                           if row["scenario_id"] == "team_b_decisive_win")
            self.assertEqual(missing["qualifying_count"], 0)
            self.assertIn("mean/P90 floor", missing["reason"])


if __name__ == "__main__":
    unittest.main()
