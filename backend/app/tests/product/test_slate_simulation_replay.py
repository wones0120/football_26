import unittest

import pandas as pd

from scripts.product.evaluate_slate_simulation_leverage import evaluate_frame


class SlateSimulationReplayTests(unittest.TestCase):
    def test_replay_gate_requires_multiweek_top_lineup_lift(self):
        rows = []
        for week in (1, 2, 3):
            for index in range(10):
                rows.append(
                    {
                        "season": 2025,
                        "week": week,
                        "player_id": f"{week}-{index}",
                        "projection_mean": float(index),
                        "field_ownership": float(index),
                        "leverage_score": float(10 - index),
                        "actual_top_lineup_exposure": float(10 - index),
                    }
                )

        report = evaluate_frame(pd.DataFrame(rows), top_k=3)

        self.assertEqual(report["status"], "passed")
        self.assertTrue(report["performance_claim_eligible"])
        self.assertGreater(report["top_k_exposure_lift"], 0)

    def test_replay_gate_rejects_insufficient_weeks(self):
        frame = pd.DataFrame(
            [
                {
                    "season": 2025,
                    "week": 1,
                    "player_id": "player-1",
                    "projection_mean": 20.0,
                    "field_ownership": 10.0,
                    "leverage_score": 15.0,
                    "actual_top_lineup_exposure": 5.0,
                }
            ]
        )

        report = evaluate_frame(frame, top_k=1)

        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["performance_claim_eligible"])


if __name__ == "__main__":
    unittest.main()
