import unittest

import pandas as pd
import numpy as np

from backend.app.product_services.predictions import (
    TARGET_COL,
    apply_opportunity_point_adjustment,
    apply_residual_calibration,
    blend_point_predictions,
    build_position_calibration,
    derive_calibration_roles,
    estimate_team_market_elasticity,
    generate_walk_forward_residuals,
    kicker_point_estimates,
    historical_role_calibration,
    role_counterfactual_grid,
    reconcile_market_response,
)


class PredictionCalibrationTests(unittest.TestCase):
    def test_market_elasticity_requires_positive_later_holdout(self):
        rows = []
        for week in range(1, 31):
            for team in ("CHI", "PHI"):
                implied = 18.0 + week % 5
                for player in range(5):
                    rows.append({"season": 2025, "week": week, "team": team,
                                 "position": "RB", "player_id": f"{team}-{player}",
                                 "team_implied_total": implied,
                                 TARGET_COL: (implied * 2.0) / 5})
        result = estimate_team_market_elasticity(pd.DataFrame(rows))
        self.assertEqual(result["status"], "validated_positive_response")
        self.assertAlmostEqual(result["slope"], 2.0)

    def test_market_reconciliation_adds_only_response_missing_from_model(self):
        target = pd.DataFrame({
            "position": ["QB", "WR", "QB"],
            "recent_team": ["CHI", "CHI", "PHI"],
            "pregame_availability_probability": [1.0] * 3,
            "pregame_start_probability": [1.0] * 3,
        })
        adjusted, response, adjustments = reconcile_market_response(
            target, np.array([11.0, 10.0, 10.0]),
            np.array([10.0, 10.0, 10.0]),
            [{"team": "CHI", "changed_from_matrix": True,
              "implied_total_delta": -2.0}],
            {"slope": 2.0},
        )
        self.assertAlmostEqual(sum(adjusted[:2]), 16.0)
        self.assertAlmostEqual(adjusted[2], 10.0)
        self.assertAlmostEqual(sum(adjustments[:2]), -5.0)
        self.assertAlmostEqual(response[0]["model_offensive_projection_delta"], 1.0)
        self.assertAlmostEqual(response[0]["final_offensive_projection_delta"], -4.0)
        self.assertTrue(response[0]["direction_mismatch_before_reconciliation"])

    def test_role_counterfactual_varies_one_feature_without_mutating_target(self):
        class RoleModel:
            def predict(self, frame):
                return (10 + frame["offensive_role_importance"] * 10
                        + frame["offensive_role_completeness"] * 2).to_numpy()

        train = pd.DataFrame({"position": ["RB"], TARGET_COL: [12.0]})
        target = pd.DataFrame({"position": ["RB"], "offensive_role_importance": [0.6],
                               "offensive_role_completeness": [0.8],
                               "player_games_history": [4], "player_roll3_mean": [12.0],
                               "player_roll8_mean": [12.0]})
        before = target.copy(deep=True)
        grid = role_counterfactual_grid(RoleModel(), train, target,
            ["offensive_role_importance", "offensive_role_completeness"])[0]
        self.assertLess(grid["importance"][0]["delta"], 0)
        self.assertGreater(grid["importance"][-1]["delta"], 0)
        self.assertEqual(grid["importance"][2]["delta"], 0)
        pd.testing.assert_frame_equal(target, before)

    def test_historical_role_calibration_uses_prior_period_for_ceiling(self):
        rows = []
        for week in (1, 2):
            rows.extend({"season": 2025, "week": week, "position": "RB",
                         "offensive_role_class": "offensive centerpiece",
                         "actual": float(i), "point_prediction": 10.0,
                         "residual": float(i) - 10.0} for i in range(40))
        report = historical_role_calibration(pd.DataFrame(rows))
        bucket = report["by_position_and_role_class"]["RB|offensive centerpiece"]
        self.assertEqual(bucket["rows"], 80)
        self.assertEqual(bucket["ceiling_evaluable_rows"], 40)
        self.assertTrue(np.isfinite(bucket["ceiling_hit_rate"]))

    def test_role_counterfactual_does_not_extrapolate_above_training_support(self):
        class RoleModel:
            def predict(self, frame):
                return frame["offensive_role_importance"].to_numpy() * 10

        train = pd.DataFrame({"position": ["RB"] * 30,
                              "offensive_role_importance": [0.2 + i / 100 for i in range(30)],
                              TARGET_COL: [10.0] * 30})
        target = pd.DataFrame({"position": ["RB"], "offensive_role_importance": [0.8],
                               "offensive_role_completeness": [1.0]})
        grid = role_counterfactual_grid(RoleModel(), train, target,
            ["offensive_role_importance", "offensive_role_completeness"])[0]
        self.assertEqual(grid["importance"][-1]["input"], 0.8)
        self.assertEqual(grid["importance"][-1]["delta"], 0.0)

    def test_kicker_without_history_uses_current_slate_peer_history(self):
        target = pd.DataFrame(
            {
                "player_display_name": ["Veteran Kicker", "Rookie Kicker"],
                "kicker_role_eligible": [True, True],
                "kicker_role": ["primary", "primary"],
                "position": ["K", "K"],
                "player_games_history": [20, 0],
                "player_roll3_mean": [8.0, None],
                "player_roll8_mean": [10.0, None],
            }
        )

        estimates, metrics = kicker_point_estimates(target)

        self.assertAlmostEqual(estimates.iloc[0], 8.8)
        self.assertAlmostEqual(estimates.iloc[1], 8.8)
        self.assertEqual(metrics["peer_history_count"], 1)
        self.assertEqual(metrics["fallback_player_count"], 1)
        self.assertEqual(metrics["fallback_players"], ["Rookie Kicker"])

    def test_kicker_without_history_still_fails_without_peer_baseline(self):
        target = pd.DataFrame(
            {
                "player_display_name": ["Rookie Kicker"],
                "kicker_role_eligible": [True],
                "kicker_role": ["primary"],
                "position": ["K"],
                "player_games_history": [0],
                "player_roll3_mean": [None],
                "player_roll8_mean": [None],
            }
        )

        with self.assertRaisesRegex(
            ValueError,
            "current-slate peer history baseline; missing: Rookie Kicker",
        ):
            kicker_point_estimates(target)

    def test_current_opportunity_evidence_moves_veterans_and_rookies(self):
        train = pd.DataFrame(
            {
                "position": ["RB", "RB", "WR", "WR"],
                "carries_mean_3": [10.0, 12.0, 0.0, 0.0],
                "targets_mean_3": [2.0, 0.0, 5.0, 6.0],
                TARGET_COL: [13.5, 12.0, 10.0, 12.0],
            }
        )
        target = pd.DataFrame(
            {
                "position": ["RB", "WR", "WR"],
                "player_games_history": [0, 10, 10],
                "carries_mean_3": [10.0, 0.0, 0.0],
                "targets_mean_3": [2.0, 6.0, 6.0],
                "pregame_opportunity_context_applied": [True, True, False],
            }
        )

        adjusted, details = apply_opportunity_point_adjustment(
            base_predictions=pd.Series([5.0, 4.0, 4.0]).to_numpy(),
            train_df=train,
            target_df=target,
        )

        self.assertAlmostEqual(adjusted[0], 10.95)
        self.assertAlmostEqual(adjusted[1], 8.4)
        self.assertAlmostEqual(adjusted[2], 4.0)
        self.assertEqual(
            details["pregame_opportunity_point_weight"].tolist(),
            [0.70, 0.55, 0.0],
        )

    def test_point_prediction_blend_is_position_aware_for_every_supported_position(self):
        positions = ["QB", "RB", "WR", "TE", "DST"]
        train = pd.DataFrame(
            {
                "position": positions,
                TARGET_COL: [20.0, 12.0, 10.0, 8.0, 6.0],
            }
        )
        target = pd.DataFrame(
            {
                "position": positions,
                "player_games_history": [0, 0, 8, 0, 0],
                "player_roll3_mean": [0.0, 0.0, 18.0, 0.0, 0.0],
                "player_roll8_mean": [0.0, 0.0, 16.0, 0.0, 0.0],
            }
        )

        predictions = blend_point_predictions(
            raw_predictions=pd.Series([10.0] * 5).to_numpy(),
            train_df=train,
            target_df=target,
        )

        self.assertEqual(
            predictions.tolist(),
            [12.0, 10.4, 11.44, 9.6, 9.2],
        )

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

    def test_measured_opportunity_conditioned_ceiling_requires_sufficient_samples(self):
        residuals = pd.DataFrame({
            "position": ["RB"] * 12,
            "calibration_role": ["LEAD"] * 12,
            "offensive_role_importance": [0.2] * 6 + [0.8] * 6,
            "residual": [-3, -2, -1, 0, 1, 2, 0, 1, 2, 5, 8, 11],
        })
        train = pd.DataFrame({"position": ["RB"], TARGET_COL: [12.0]})
        profiles, metrics = build_position_calibration(
            residuals, train, min_position_rows=1, min_role_rows=4,
        )
        self.assertEqual(metrics["importance_splits_by_role"]["RB|LEAD"], 0.5)
        self.assertGreater(
            profiles["RB|LEAD|importance_high"].residual_quantiles["p90"],
            profiles["RB|LEAD|importance_low"].residual_quantiles["p90"],
        )
        _, sparse = build_position_calibration(
            residuals, train, min_position_rows=1, min_role_rows=7,
        )
        self.assertEqual(sparse["importance_splits_by_role"], {})


if __name__ == "__main__":
    unittest.main()
