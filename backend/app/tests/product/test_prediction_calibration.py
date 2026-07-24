import unittest

import pandas as pd

from backend.app.product_services.predictions import (
    TARGET_COL,
    apply_residual_calibration,
    build_position_calibration,
    derive_calibration_roles,
    generate_walk_forward_residuals,
)


class PredictionCalibrationTests(unittest.TestCase):
    def test_role_groups_use_lagged_usage_features(self):
        rows = pd.DataFrame(
            [
                {"position": "QB", "carries_mean_3": 6.0},
                {"position": "RB", "carry_share_mean_3": 0.7},
                {"position": "RB", "target_share_mean_3": 0.15},
                {"position": "WR", "target_share_mean_3": 0.26},
                {"position": "TE", "snap_share_mean_3": 0.35},
                {"position": "DST"},
            ]
        )

        roles = derive_calibration_roles(rows)

        self.assertEqual(
            roles.tolist(),
            ["MOBILE", "LEAD", "RECEIVING", "PRIMARY", "ROTATION", "DEFENSE"],
        )

    def test_walk_forward_residuals_train_only_on_prior_periods(self):
        rows = []
        for week in (1, 2, 3):
            for index, position in enumerate(("QB", "RB", "WR"), start=1):
                rows.append(
                    {
                        "player_id": f"{week}-{position}",
                        "season": 2025,
                        "week": week,
                        "position": position,
                        "feature_value": float(week * index),
                        TARGET_COL: float(week * 2 + index),
                    }
                )

        residuals = generate_walk_forward_residuals(
            pd.DataFrame(rows),
            ["feature_value"],
            min_train_rows=3,
        )

        self.assertEqual(sorted(residuals["week"].unique().tolist()), [2, 3])
        for row in residuals.itertuples(index=False):
            training_cutoff = (row.training_through_season, row.training_through_week)
            validation_period = (row.season, row.week)
            self.assertLess(training_cutoff, validation_period)

    def test_position_profiles_create_distinct_monotonic_distributions(self):
        residuals = pd.DataFrame(
            {
                "position": ["QB"] * 5 + ["RB"] * 5,
                "residual": [-10.0, -5.0, 0.0, 5.0, 10.0, -2.0, -1.0, 0.0, 1.0, 2.0],
            }
        )
        train_df = pd.DataFrame(
            {
                "position": ["QB", "RB"],
                TARGET_COL: [20.0, 12.0],
            }
        )

        profiles, metrics = build_position_calibration(
            residuals,
            train_df,
            min_position_rows=1,
        )
        qb = apply_residual_calibration(20.0, profiles["QB"])
        rb = apply_residual_calibration(20.0, profiles["RB"])

        self.assertLess(qb["p10"], rb["p10"])
        self.assertGreater(qb["p90"], rb["p90"])
        self.assertEqual(list(qb.values()), sorted(qb.values()))
        self.assertEqual(metrics["method"], "walk_forward_residual_quantiles")
        self.assertIn("p10_p90_coverage", metrics["coverage_by_position"]["QB"])
        self.assertEqual(metrics["promotion_gate"]["status"], "blocked")

    def test_role_profiles_refine_their_position_parent(self):
        residuals = pd.DataFrame(
            {
                "position": ["QB"] * 10,
                "calibration_role": ["MOBILE"] * 5 + ["POCKET"] * 5,
                "residual": [-12.0, -6.0, 0.0, 6.0, 12.0, -3.0, -1.0, 0.0, 1.0, 3.0],
            }
        )
        train_df = pd.DataFrame(
            {"position": ["QB"], "carries_mean_3": [5.0], TARGET_COL: [20.0]}
        )

        profiles, metrics = build_position_calibration(
            residuals,
            train_df,
            min_position_rows=1,
            min_role_rows=1,
        )

        mobile = apply_residual_calibration(20.0, profiles["QB|MOBILE"])
        pocket = apply_residual_calibration(20.0, profiles["QB|POCKET"])
        self.assertLess(mobile["p10"], pocket["p10"])
        self.assertGreater(mobile["p90"], pocket["p90"])
        self.assertIn("QB|MOBILE", metrics["coverage_by_role"])

    def test_sparse_position_profile_shrinks_toward_global_distribution(self):
        residuals = pd.DataFrame(
            {
                "position": ["QB", "QB", "QB", "RB"],
                "residual": [-6.0, 0.0, 6.0, 20.0],
            }
        )
        train_df = pd.DataFrame(
            {"position": ["QB", "RB"], TARGET_COL: [20.0, 10.0]}
        )

        profiles, _ = build_position_calibration(
            residuals,
            train_df,
            min_position_rows=10,
        )

        self.assertEqual(profiles["RB"].sample_size, 1)
        self.assertIn("shrunk_to_global", profiles["RB"].source)
        self.assertLess(profiles["RB"].residual_quantiles["p50"], 20.0)

    def test_fallback_distribution_is_non_negative_and_monotonic(self):
        train_df = pd.DataFrame(
            {
                "position": ["TE", "TE", "TE"],
                TARGET_COL: [0.0, 5.0, 15.0],
            }
        )

        profiles, metrics = build_position_calibration(pd.DataFrame(), train_df)
        distribution = apply_residual_calibration(1.0, profiles["TE"])

        self.assertEqual(list(distribution.values()), sorted(distribution.values()))
        self.assertGreaterEqual(distribution["p10"], 0.0)
        self.assertEqual(metrics["method"], "historical_position_dispersion_fallback")


if __name__ == "__main__":
    unittest.main()
