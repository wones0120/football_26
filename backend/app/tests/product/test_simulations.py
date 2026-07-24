import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import numpy as np
import pandas as pd

from backend.app.product_services.simulations import (
    SimulationResult,
    SimulationService,
    build_simulation_rows,
    sample_independent_outcomes,
    simulate_optimal_lineups,
)


def classic_pool() -> pd.DataFrame:
    positions = ["QB", "RB", "RB", "RB", "WR", "WR", "WR", "WR", "TE", "DST"]
    rows = []
    for index, position in enumerate(positions):
        mean = 24.0 - index
        rows.append(
            {
                "player_id": f"player-{index}",
                "player_display_name": f"Player {index}",
                "position": position,
                "salary": 5_000,
                "projection_mean": mean,
                "projection_p10": mean - 6,
                "projection_p25": mean - 3,
                "projection_p50": mean,
                "projection_p75": mean + 3,
                "projection_p90": mean + 6,
                "field_ownership": 12.5,
            }
        )
    return pd.DataFrame(rows)


class SlateSimulationTests(unittest.TestCase):
    def test_sampling_is_seeded_non_negative_and_preserves_shape(self):
        pool = classic_pool()

        first = sample_independent_outcomes(pool, num_simulations=12, seed=502)
        second = sample_independent_outcomes(pool, num_simulations=12, seed=502)

        self.assertEqual(first.shape, (12, len(pool)))
        self.assertTrue(np.array_equal(first, second))
        self.assertTrue(np.all(first >= 0))

    def test_every_successful_classic_simulation_selects_nine_players(self):
        pool = classic_pool()

        counts, successful = simulate_optimal_lineups(
            pool,
            num_simulations=10,
            seed=502,
        )

        self.assertEqual(successful, 10)
        self.assertEqual(int(counts.sum()), successful * 9)

    def test_player_leverage_uses_percentage_points(self):
        pool = classic_pool().iloc[:2].copy()

        rows = build_simulation_rows(
            pool,
            np.asarray([3, 1]),
            successful_simulations=4,
        )
        by_id = {row["player_id"]: row for row in rows}

        self.assertEqual(by_id["player-0"]["optimal_lineup_probability"], 75.0)
        self.assertEqual(by_id["player-0"]["leverage_score"], 62.5)
        self.assertEqual(by_id["player-1"]["optimal_lineup_probability"], 25.0)
        self.assertEqual(by_id["player-1"]["leverage_score"], 12.5)
        self.assertEqual(by_id["player-0"]["sampling_index"], 0)
        self.assertEqual(by_id["player-1"]["sampling_index"], 1)

    def test_illegal_pool_fails_with_position_evidence(self):
        pool = classic_pool()
        pool = pool[pool["position"] != "DST"].reset_index(drop=True)

        with self.assertRaisesRegex(ValueError, "DST"):
            simulate_optimal_lineups(pool, num_simulations=1, seed=502)

    def test_belief_replay_reuses_persisted_salary_cap(self):
        service = SimulationService.__new__(SimulationService)
        result = SimulationResult(
            simulation_run_id="simulation-run-1",
            simulation_model_id="independent_quantile_lineup_v1",
            season=2025,
            week=11,
            slate="SUNDAY_MAIN",
            contest_format="classic",
            projection_run_id="projection-run-1",
            ownership_run_id=None,
            num_simulations=1,
            successful_simulations=1,
            seed=502,
            salary_cap=43_000,
            status="completed",
            message="completed",
            data_cutoff_at=None,
            created_at=datetime.now(timezone.utc),
            rows=[
                {
                    "player_id": "player-0",
                    "optimal_lineup_probability": 100.0,
                }
            ],
        )
        service.fetch_latest = lambda **_kwargs: result
        service._load_persisted_pool = lambda _run_id: classic_pool()

        with patch(
            "backend.app.product_services.simulations.simulate_optimal_lineups",
            return_value=(np.asarray([1] + [0] * 9), 1),
        ) as simulate:
            impact = service.estimate_player_modifier(
                season=2025,
                week=11,
                slate="SUNDAY_MAIN",
                player_id="player-0",
                projection_multiplier=1.05,
                projection_run_id="projection-run-1",
            )

        self.assertIsNotNone(impact)
        self.assertEqual(simulate.call_args.kwargs["salary_cap"], 43_000)


if __name__ == "__main__":
    unittest.main()
