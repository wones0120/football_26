import unittest

import pandas as pd

from backend.app.product_services.predictions import TARGET_COL, select_training_rows_before_cutoff


class PredictionTrainingCutoffTests(unittest.TestCase):
    def test_keeps_only_labeled_rows_before_target_week(self):
        rows = pd.DataFrame(
            [
                {"player_id": "prior-season", "season": 2024, "week": 18, TARGET_COL: 10.0},
                {"player_id": "prior-week", "season": 2025, "week": 5, TARGET_COL: 11.0},
                {"player_id": "target-week", "season": 2025, "week": 6, TARGET_COL: 12.0},
                {"player_id": "future-week", "season": 2025, "week": 7, TARGET_COL: 13.0},
                {"player_id": "future-season", "season": 2026, "week": 1, TARGET_COL: 14.0},
                {"player_id": "unlabeled", "season": 2025, "week": 4, TARGET_COL: None},
            ]
        )

        selected = select_training_rows_before_cutoff(
            rows,
            target_season=2025,
            target_week=6,
        )

        self.assertEqual(selected["player_id"].tolist(), ["prior-season", "prior-week"])

    def test_coerces_string_season_week_and_label_values(self):
        rows = pd.DataFrame(
            [
                {"player_id": "valid", "season": "2025", "week": "3", TARGET_COL: "8.5"},
                {"player_id": "bad-label", "season": "2025", "week": "2", TARGET_COL: "unknown"},
            ]
        )

        selected = select_training_rows_before_cutoff(
            rows,
            target_season=2025,
            target_week=4,
        )

        self.assertEqual(selected["player_id"].tolist(), ["valid"])
        self.assertEqual(selected.iloc[0][TARGET_COL], 8.5)

    def test_rejects_missing_cutoff_columns(self):
        with self.assertRaisesRegex(ValueError, "missing required columns: week"):
            select_training_rows_before_cutoff(
                pd.DataFrame([{"season": 2025, TARGET_COL: 5.0}]),
                target_season=2025,
                target_week=1,
            )


if __name__ == "__main__":
    unittest.main()
