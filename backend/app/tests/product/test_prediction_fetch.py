import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from backend.app.product_services.predictions import PredictionsService


class _TargetInspector:
    def has_table(self, table_name, schema=None):
        if schema == "target":
            return table_name in {
                "active_projection_run",
                "dim_player",
                "fact_player_game_actual",
                "model_run",
                "player_projection",
                "snapshot_salary",
            }
        return False

    def get_columns(self, table_name, schema=None):
        if schema == "target" and table_name == "player_projection":
            return [
                {"name": name}
                for name in {
                    "projection_run_id",
                    "model_run_id",
                    "season",
                    "week",
                    "game_id",
                    "slate_id",
                    "player_id",
                    "mean",
                    "median",
                    "p10",
                    "p25",
                    "p75",
                    "p90",
                    "created_at",
                    "data_cutoff_at",
                }
            ]
        return []


class PredictionFetchTests(unittest.TestCase):
    def test_fetch_predictions_uses_target_schema_when_legacy_table_is_absent(self):
        service = PredictionsService.__new__(PredictionsService)
        service.engine = MagicMock()
        connection = service.engine.begin.return_value.__enter__.return_value
        active_result = MagicMock()
        active_result.mappings.return_value.first.return_value = {
            "projection_run_id": "projection-run-1"
        }
        connection.execute.return_value = active_result
        target_frame = pd.DataFrame(
            [
                {
                    "player_id": "player-1",
                    "player_display_name": "Example Runner",
                    "position": "RB",
                    "recent_team": "BUF",
                    "opponent_team": "MIA",
                    "salary": 7200,
                    "season": 2025,
                    "week": 11,
                    "predicted_mean": 18.0,
                    "predicted_p10": 8.0,
                    "predicted_p25": 12.0,
                    "predicted_p50": 17.0,
                    "predicted_p75": 23.0,
                    "predicted_p90": 29.0,
                    "model": "target.player_projection",
                    "feature_run_id": "feature-run-1",
                    "model_run_id": "model-run-1",
                    "projection_run_id": "projection-run-1",
                    "data_cutoff_at": None,
                    "game_id": "2025_11_BUF_MIA",
                    "calibration_method": "target_projection_fallback",
                    "calibration_position": "RB",
                    "calibration_role": "unknown",
                    "calibration_sample_size": 0,
                    "adj_mean": 18.0,
                    "adj_mean_base": 18.0,
                    "matchup_factor": 1.0,
                    "adj_mean_final": 18.0,
                }
            ]
        )

        observed_sql = []
        observed_params = []

        def read_sql(query, _connection, params=None):
            sql = str(query)
            observed_sql.append(sql)
            observed_params.append(params or {})
            if "WITH latest_projection" in sql:
                return target_frame
            if "dk_points AS dk_total_points" in sql:
                return pd.DataFrame(
                    [{"player_id": "player-1", "week": 10, "dk_total_points": 16.0}]
                )
            if "SUM(dk_points)" in sql:
                return pd.DataFrame(
                    [{"team": "BUF", "position": "RB", "total_points": 64.0, "games_played": 4}]
                )
            raise AssertionError(f"Unexpected prediction query: {sql}")

        with patch("backend.app.product_services.predictions.inspect", return_value=_TargetInspector()), patch(
            "backend.app.product_services.predictions.pd.read_sql", side_effect=read_sql
        ):
            rows = service.fetch_predictions(
                season=2025,
                week=11,
                limit=1000,
                slate="THURSDAY_NIGHT",
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["player_display_name"], "Example Runner")
        self.assertEqual(rows[0]["salary"], 7200)
        self.assertEqual(rows[0]["last3_points"], [16.0])
        self.assertEqual(rows[0]["team_pos_avg"], 16.0)
        self.assertTrue(any("target.player_projection" in sql for sql in observed_sql))
        self.assertFalse(any("FROM player_expected_points " in sql for sql in observed_sql))
        projection_params = next(
            params
            for sql, params in zip(observed_sql, observed_params, strict=True)
            if "WITH latest_projection" in sql
        )
        self.assertEqual(
            projection_params["selected_projection_run_id"],
            "projection-run-1",
        )


if __name__ == "__main__":
    unittest.main()
