import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd

from backend.app.product_services.predictions import (
    PredictionsService,
    create_prediction_run_context,
    prediction_game_id,
)


class PredictionLineageTests(unittest.TestCase):
    def test_run_context_uses_stable_feature_hash_and_unique_run_ids(self):
        cutoff = datetime(2025, 11, 16, 13, 0, 0)

        first = create_prediction_run_context(["salary", "target_share"], data_cutoff_at=cutoff)
        second = create_prediction_run_context(["target_share", "salary"], data_cutoff_at=cutoff)

        self.assertEqual(first.feature_set_hash, second.feature_set_hash)
        self.assertNotEqual(first.feature_run_id, second.feature_run_id)
        self.assertNotEqual(first.model_run_id, second.model_run_id)
        self.assertNotEqual(first.projection_run_id, second.projection_run_id)
        self.assertEqual(first.data_cutoff_at.tzinfo, timezone.utc)

    def test_prediction_game_id_is_stable_across_team_order(self):
        first = prediction_game_id(
            {"player_id": "one", "recent_team": "BUF", "opponent_team": "MIA"},
            season=2025,
            week=11,
        )
        second = prediction_game_id(
            {"player_id": "two", "recent_team": "MIA", "opponent_team": "BUF"},
            season=2025,
            week=11,
        )

        self.assertEqual(first, "2025_11_BUF_MIA")
        self.assertEqual(first, second)

    def test_prediction_game_id_handles_nullable_legacy_fields(self):
        game_id = prediction_game_id(
            {
                "game_id": pd.NA,
                "recent_team": pd.NA,
                "opponent_team": pd.NA,
                "player_id": "player-1",
            },
            season=2025,
            week=11,
        )

        self.assertEqual(game_id, "2025_11_unknown_player-1")

    def test_target_persistence_writes_projection_and_feature_run_ids(self):
        service = PredictionsService.__new__(PredictionsService)
        service.engine = MagicMock()
        connection = service.engine.begin.return_value.__enter__.return_value
        context = create_prediction_run_context(
            ["salary", "target_share"],
            data_cutoff_at=datetime(2025, 11, 16, 13, 0, tzinfo=timezone.utc),
        )
        train_df = pd.DataFrame(
            [{"season": 2025, "week": 10, "label_dk_total_points": 12.0}]
        )
        source_features = pd.DataFrame([{"salary": 6000, "target_share": 0.25}])
        projections = pd.DataFrame(
            [
                {
                    "player_id": "player-1",
                    "game_id": "2025_11_BUF_MIA",
                    "predicted_mean": 18.0,
                    "adj_mean_final": 19.0,
                    "predicted_p10": 8.0,
                    "predicted_p25": 13.0,
                    "predicted_p50": 18.0,
                    "predicted_p75": 24.0,
                    "predicted_p90": 30.0,
                    "calibration_method": "position_role_walk_forward",
                    "calibration_position": "RB",
                    "calibration_role": "LEAD",
                    "calibration_sample_size": 250,
                }
            ]
        )

        persisted = service._persist_target_prediction_run(
            context=context,
            season=2025,
            week=11,
            slate="SUNDAY_MAIN",
            feature_cols=["salary", "target_share"],
            train_df=train_df,
            source_features=source_features,
            projections=projections,
        )

        self.assertTrue(persisted)
        projection_payload = next(
            call.args[1]
            for call in connection.execute.call_args_list
            if len(call.args) > 1
            and isinstance(call.args[1], list)
            and call.args[1]
            and "projection_run_id" in call.args[1][0]
        )
        self.assertEqual(projection_payload[0]["projection_run_id"], context.projection_run_id)
        self.assertEqual(projection_payload[0]["model_run_id"], context.model_run_id)
        self.assertEqual(projection_payload[0]["slate_id"], "SUNDAY_MAIN")
        self.assertEqual(projection_payload[0]["mean"], 19.0)
        self.assertEqual(projection_payload[0]["p25"], 13.0)
        self.assertEqual(projection_payload[0]["p75"], 24.0)
        self.assertEqual(projection_payload[0]["calibration_role"], "LEAD")
        self.assertEqual(projection_payload[0]["calibration_sample_size"], 250)
        executed_sql = [str(call.args[0]) for call in connection.execute.call_args_list]
        self.assertTrue(any("INSERT INTO target.projection_run" in sql for sql in executed_sql))
        self.assertTrue(any("INSERT INTO target.active_projection_run" in sql for sql in executed_sql))
        self.assertFalse(any("DELETE FROM player_expected_points" in sql for sql in executed_sql))

    def test_active_run_resolution_uses_explicit_scope_pointer(self):
        connection = MagicMock()
        active_result = MagicMock()
        active_result.mappings.return_value.first.return_value = {
            "projection_run_id": "projection-active"
        }
        connection.execute.return_value = active_result
        inspector = MagicMock()
        inspector.has_table.return_value = True

        with patch("backend.app.product_services.predictions.inspect", return_value=inspector):
            resolved = PredictionsService._resolve_projection_run_id(
                connection,
                season=2025,
                week=11,
                slate="SUNDAY_MAIN",
                projection_run_id=None,
            )

        self.assertEqual(resolved, "projection-active")
        self.assertIn("target.active_projection_run", str(connection.execute.call_args.args[0]))

    def test_manual_active_run_selection_validates_scope_and_updates_pointer(self):
        service = PredictionsService.__new__(PredictionsService)
        service.engine = MagicMock()
        connection = service.engine.begin.return_value.__enter__.return_value
        run_result = MagicMock()
        run_result.mappings.return_value.first.return_value = {
            "projection_run_id": "projection-old",
            "model_run_id": "model-old",
            "season": 2025,
            "week": 11,
            "slate_id": "SUNDAY_MAIN",
            "row_count": 50,
            "data_cutoff_at": None,
            "status": "completed",
            "created_at": datetime(2025, 11, 16, 12, 0, tzinfo=timezone.utc),
        }
        connection.execute.side_effect = [run_result, MagicMock()]

        selected = service.select_active_prediction_run(
            season=2025,
            week=11,
            slate="SUNDAY_MAIN",
            projection_run_id="projection-old",
            selection_reason="rollback_after_review",
        )

        self.assertTrue(selected["active"])
        self.assertEqual(selected["projection_run_id"], "projection-old")
        pointer_call = connection.execute.call_args_list[1]
        self.assertIn("INSERT INTO target.active_projection_run", str(pointer_call.args[0]))
        self.assertEqual(pointer_call.args[1]["selection_reason"], "rollback_after_review")


if __name__ == "__main__":
    unittest.main()
