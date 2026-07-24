import unittest
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pandas as pd

from backend.app.product_services.ownership import (
    OWNERSHIP_NUMERIC_FEATURES,
    OwnershipService,
    build_slate_aware_ownership_frame,
    generate_walk_forward_ownership_predictions,
    ownership_model_metrics,
)


def synthetic_ownership_rows() -> pd.DataFrame:
    rows = []
    positions = ["QB", "RB", "WR", "TE", "DST"]
    for week in range(1, 5):
        for index in range(40):
            position = positions[index % len(positions)]
            salary = 3000 + index * 150
            projection = 5 + ((index * 3 + week * 7) % 24)
            ownership = 2 + 0.003 * salary + 0.9 * projection + (4 if position == "RB" else 0)
            rows.append(
                {
                    "season": 2025,
                    "week": week,
                    "slate": "SUNDAY_MAIN",
                    "player_id": f"player-{index}",
                    "player_display_name": f"Player {index}",
                    "roster_position": position,
                    "position": position,
                    "actual_ownership": ownership,
                    "salary": salary,
                    "projection_mean": projection,
                    "projection_p90": projection + 8,
                }
            )
    return pd.DataFrame(rows)


class SlateAwareOwnershipModelTests(unittest.TestCase):
    def test_captain_slate_marks_captain_and_flex_rows_as_showdown(self):
        rows = pd.DataFrame(
            [
                {
                    "season": 2025,
                    "week": 8,
                    "slate": "THURSDAY_NIGHT",
                    "player_id": f"player-{slot.lower()}",
                    "player_display_name": f"Player {slot}",
                    "roster_position": slot,
                    "position": "WR",
                    "actual_ownership": 10.0,
                    "salary": 6000,
                    "projection_mean": 15,
                    "projection_p90": 24,
                }
                for slot in ("CPT", "FLEX")
            ]
        )

        features = build_slate_aware_ownership_frame(rows)

        self.assertEqual(set(features["contest_format"]), {"showdown"})
        self.assertEqual(set(features["roster_slot"]), {"CPT", "FLEX"})

    def test_prior_player_feature_uses_only_earlier_slates(self):
        rows = pd.DataFrame(
            [
                {
                    "season": 2025,
                    "week": week,
                    "slate": "SUNDAY_MAIN",
                    "player_id": "p1",
                    "player_display_name": "Player One",
                    "roster_position": "WR",
                    "position": "WR",
                    "actual_ownership": ownership,
                    "salary": 6000,
                    "projection_mean": 15,
                    "projection_p90": 24,
                }
                for week, ownership in [(1, 10.0), (2, 30.0), (3, None)]
            ]
        )

        features = build_slate_aware_ownership_frame(rows)

        self.assertFalse(pd.isna(features.loc[features["week"] == 1, "prior_player_ownership"].iloc[0]))
        self.assertEqual(features.loc[features["week"] == 2, "prior_player_ownership"].iloc[0], 10.0)
        self.assertEqual(features.loc[features["week"] == 3, "prior_player_ownership"].iloc[0], 20.0)

    def test_prior_player_feature_cannot_see_another_slate_in_same_week(self):
        rows = pd.DataFrame(
            [
                {
                    "season": 2025,
                    "week": week,
                    "slate": slate,
                    "player_id": "p1",
                    "player_display_name": "Player One",
                    "roster_position": "WR",
                    "position": "WR",
                    "actual_ownership": ownership,
                    "salary": 6000,
                    "projection_mean": 15,
                    "projection_p90": 24,
                }
                for week, slate, ownership in [
                    (1, "SUNDAY_EARLY", 10.0),
                    (1, "SUNDAY_MAIN", 90.0),
                    (2, "SUNDAY_MAIN", None),
                ]
            ]
        )

        features = build_slate_aware_ownership_frame(rows)
        week_one = features.loc[features["week"] == 1, "prior_player_ownership"]

        self.assertEqual(week_one.nunique(), 1)
        self.assertEqual(features.loc[features["week"] == 2, "prior_player_ownership"].iloc[0], 50.0)

    def test_walk_forward_folds_never_train_on_validation_week(self):
        features = build_slate_aware_ownership_frame(synthetic_ownership_rows())

        predictions = generate_walk_forward_ownership_predictions(
            features,
            min_train_rows=40,
        )

        self.assertEqual(sorted(predictions["week"].unique().tolist()), [2, 3, 4])
        for row in predictions.itertuples(index=False):
            self.assertLess(
                (row.training_through_season, row.training_through_week),
                (row.season, row.week),
            )
        self.assertTrue(predictions["predicted_ownership"].between(0, 100).all())

    def test_metrics_include_format_slot_calibration_and_baseline(self):
        features = build_slate_aware_ownership_frame(synthetic_ownership_rows())
        predictions = generate_walk_forward_ownership_predictions(features, min_train_rows=40)

        metrics = ownership_model_metrics(predictions)

        self.assertGreater(metrics["walk_forward_rows"], 0)
        self.assertIsInstance(metrics["mae"], float)
        self.assertIsInstance(metrics["baseline_mae"], float)
        self.assertIn("classic|QB", metrics["calibration_by_format_slot"])
        self.assertIn(metrics["promotion_gate"]["status"], {"passed", "blocked"})

    def test_target_persistence_writes_run_and_projection_lineage(self):
        service = OwnershipService.__new__(OwnershipService)
        service.engine = MagicMock()
        projection = pd.DataFrame(
            [
                {
                    "player_id": "player-1",
                    "roster_position": "WR",
                    "projected_ownership": 18.5,
                    **{feature: 1.0 for feature in OWNERSHIP_NUMERIC_FEATURES},
                    "position": "WR",
                    "contest_format": "classic",
                    "roster_slot": "WR",
                }
            ]
        )
        cutoff = datetime(2025, 11, 16, 13, 0, tzinfo=UTC)

        persisted = service._persist_target_ownership_run(
            ownership_run_id="ownership-run-1",
            season=2025,
            week=11,
            slate="SUNDAY_MAIN",
            data_cutoff_at=cutoff,
            training_rows=1000,
            metrics={"mae": 3.2},
            projections=projection,
        )

        self.assertTrue(persisted)
        connection = service.engine.begin.return_value.__enter__.return_value
        payload = next(
            call.args[1]
            for call in connection.execute.call_args_list
            if len(call.args) > 1
            and isinstance(call.args[1], list)
            and call.args[1]
            and "projected_ownership" in call.args[1][0]
        )
        self.assertEqual(payload[0]["ownership_run_id"], "ownership-run-1")
        self.assertEqual(payload[0]["projected_ownership"], 18.5)


if __name__ == "__main__":
    unittest.main()
