import json
import unittest
from datetime import datetime
from unittest.mock import MagicMock

import pandas as pd

from backend.app.product_services.optimizer import (
    CASH_OBJECTIVE_ID,
    CLASSIC_CASH_STACK_UNCONSTRAINED_ID,
    OptimizerJob,
    OptimizerService,
    build_classic_cash_objective,
    cash_objective_config,
    resolve_stacking_policy,
    summarize_classic_cash_lineup,
)


class ClassicCashObjectiveTests(unittest.TestCase):
    def test_projection_only_rows_preserve_existing_cash_score(self):
        pool = pd.DataFrame([{"player_id": "p1", "projection": 12.5}])

        scored = build_classic_cash_objective(pool)

        self.assertAlmostEqual(scored.loc[0, "cash_score"], 12.5)
        self.assertAlmostEqual(scored.loc[0, "cash_floor"], 12.5)
        self.assertEqual(scored.loc[0, "cash_objective_id"], CASH_OBJECTIVE_ID)
        self.assertEqual(scored.loc[0, "cash_evidence_status"], "projection_only")

    def test_calibrated_floor_penalizes_fragile_player(self):
        pool = pd.DataFrame(
            [
                {
                    "player_id": "stable",
                    "projection": 20.0,
                    "predicted_p50": 20.0,
                    "predicted_p10": 17.0,
                    "calibration_role": "primary_receiver",
                    "calibration_sample_size": 250,
                },
                {
                    "player_id": "fragile",
                    "projection": 20.0,
                    "predicted_p50": 20.0,
                    "predicted_p10": 8.0,
                    "calibration_role": "primary_receiver",
                    "calibration_sample_size": 250,
                },
            ]
        )

        scored = build_classic_cash_objective(pool).set_index("player_id")

        self.assertGreater(scored.loc["stable", "cash_score"], scored.loc["fragile", "cash_score"])
        self.assertLess(
            scored.loc["stable", "cash_fragility_penalty"],
            scored.loc["fragile", "cash_fragility_penalty"],
        )

    def test_role_sample_size_produces_bounded_certainty_bonus(self):
        pool = pd.DataFrame(
            [
                {
                    "player_id": "known-role",
                    "projection": 15.0,
                    "predicted_p50": 15.0,
                    "predicted_p10": 12.0,
                    "calibration_role": "lead_back",
                    "calibration_sample_size": 500,
                },
                {
                    "player_id": "fallback-role",
                    "projection": 15.0,
                    "predicted_p50": 15.0,
                    "predicted_p10": 12.0,
                    "calibration_role": "unknown",
                    "calibration_sample_size": 0,
                },
            ]
        )

        scored = build_classic_cash_objective(pool).set_index("player_id")

        self.assertEqual(scored.loc["known-role", "cash_role_certainty"], 1.0)
        self.assertEqual(scored.loc["fallback-role", "cash_role_certainty"], 0.0)
        self.assertGreater(scored.loc["known-role", "cash_role_bonus"], 0.0)

    def test_lineup_summary_aggregates_declared_terms(self):
        scored = build_classic_cash_objective(
            pd.DataFrame(
                [
                    {
                        "player_id": "p1",
                        "projection": 10.0,
                        "predicted_p50": 9.0,
                        "predicted_p10": 6.0,
                        "calibration_role": "rotation",
                        "calibration_sample_size": 100,
                    },
                    {
                        "player_id": "p2",
                        "projection": 20.0,
                        "predicted_p50": 19.0,
                        "predicted_p10": 15.0,
                        "calibration_role": "primary",
                        "calibration_sample_size": 250,
                    },
                ]
            )
        )

        summary = summarize_classic_cash_lineup(scored.to_dict(orient="records"))

        self.assertEqual(summary["objective_id"], CASH_OBJECTIVE_ID)
        self.assertEqual(summary["player_count"], 2)
        self.assertAlmostEqual(summary["projected_mean"], 30.0)
        self.assertAlmostEqual(summary["projected_median"], 28.0)
        self.assertAlmostEqual(summary["projected_floor_p10"], 21.0)
        self.assertTrue(summary["evidence_complete"])

    def test_cash_pool_filter_retains_dst_when_projection_is_missing(self):
        service = OptimizerService.__new__(OptimizerService)
        pool = pd.DataFrame(
            [
                {
                    "player_id": "dst-1",
                    "name": "Defense One",
                    "position": "DST",
                    "player_team": "AAA",
                    "opponent_team": "BBB",
                    "salary": 3000,
                    "projection": 0.0,
                    "p90": 0.0,
                }
            ]
        )

        filtered = service._apply_pool_filters(pool, contest_type="cash")

        self.assertEqual(filtered["player_id"].tolist(), ["dst-1"])

    def test_classic_cash_run_uses_versioned_score_and_returns_explanation(self):
        service = OptimizerService.__new__(OptimizerService)
        service._jobs = {}
        service.engine = MagicMock()
        service._resolve_run_lineage = MagicMock(return_value=(None, None, None))
        pool = pd.DataFrame(
            [
                {
                    "player_id": f"p{index}",
                    "name": f"Player {index}",
                    "position": "WR",
                    "player_team": "AAA",
                    "opponent_team": "BBB",
                    "salary": 5000,
                    "projection": 10.0 + index,
                    "predicted_p50": 9.0 + index,
                    "predicted_p10": 6.0 + index,
                    "p90": 18.0 + index,
                    "calibration_role": "primary",
                    "calibration_sample_size": 250,
                }
                for index in range(9)
            ]
        )
        service._load_player_pool = MagicMock(return_value=pool)
        service._apply_pool_filters = MagicMock(side_effect=lambda rows, contest_type: rows)

        def solve(rows, **kwargs):
            self.assertEqual(kwargs["score_col"], "cash_score")
            self.assertEqual(
                kwargs["stack_params"]["policy_id"],
                CLASSIC_CASH_STACK_UNCONSTRAINED_ID,
            )
            self.assertFalse(kwargs["stack_params"]["enabled"])
            return rows.to_dict(orient="records")

        service._solve_lineup = MagicMock(side_effect=solve)
        service._lineups_satisfy_stack = MagicMock(return_value=(True, ""))
        service._attach_symbolic_explanations = MagicMock()
        service._persist_optimizer_run = MagicMock(return_value=True)

        job = service.run_job(
            season=2025,
            week=11,
            slate="SUNDAY_MAIN",
            strategy="baseline",
            params={"num_lineups": 1},
            contest_format="classic",
            objective="cash",
        )

        self.assertEqual(job.status, "completed")
        self.assertEqual(job.params["objective_config"]["objective_id"], CASH_OBJECTIVE_ID)
        self.assertEqual(job.params["stack_policy_id"], CLASSIC_CASH_STACK_UNCONSTRAINED_ID)
        self.assertIn("lineup_cash_summary", job.results[0][0])
        self.assertEqual(
            job.results[0][0]["lineup_stack_policy"]["policy_id"],
            CLASSIC_CASH_STACK_UNCONSTRAINED_ID,
        )
        self.assertIn(CASH_OBJECTIVE_ID, job.message)
        self.assertIn(CLASSIC_CASH_STACK_UNCONSTRAINED_ID, job.message)

    def test_cash_persistence_records_version_and_lineup_terms(self):
        service = OptimizerService.__new__(OptimizerService)
        service.engine = MagicMock()
        connection = service.engine.begin.return_value.__enter__.return_value
        now = datetime(2026, 7, 12, 12, 0, 0)
        scored_row = build_classic_cash_objective(
            pd.DataFrame(
                [
                    {
                        "player_id": "player-1",
                        "position": "RB",
                        "salary": 7000,
                        "projection": 18.0,
                        "predicted_p50": 17.5,
                        "predicted_p10": 12.0,
                        "p90": 28.0,
                        "calibration_role": "lead_back",
                        "calibration_sample_size": 250,
                    }
                ]
            )
        ).iloc[0].to_dict()
        stack_policy = resolve_stacking_policy(
            contest_format="classic",
            objective="cash",
        )
        job = OptimizerJob(
            job_id="cash-run-1",
            status="completed",
            created_at=now,
            updated_at=now,
            season=2025,
            week=11,
            slate="SUNDAY_MAIN",
            strategy="baseline",
            contest_format="classic",
            objective="cash",
            params={
                "objective_config": cash_objective_config(),
                "stack_policy_id": stack_policy["policy_id"],
                "stack_policy": stack_policy,
            },
            results=[[scored_row]],
        )

        self.assertTrue(service._persist_optimizer_run(job))

        run_payload = next(
            call.args[1]
            for call in connection.execute.call_args_list
            if len(call.args) > 1
            and isinstance(call.args[1], dict)
            and call.args[1].get("optimizer_run_id") == "cash-run-1"
            and "objective_config_json" in call.args[1]
        )
        self.assertEqual(json.loads(run_payload["objective_config_json"])["objective_id"], CASH_OBJECTIVE_ID)
        lineup_payload = next(
            call.args[1]
            for call in connection.execute.call_args_list
            if len(call.args) > 1
            and isinstance(call.args[1], dict)
            and call.args[1].get("lineup_id") == "cash-run-1:1"
            and "objective_score" in call.args[1]
        )
        self.assertIsNotNone(lineup_payload["projected_floor"])
        self.assertIsNotNone(lineup_payload["objective_score"])
        self.assertTrue(
            any("cash_objective" in str(call.args[0]) for call in connection.execute.call_args_list)
        )
        self.assertTrue(
            any("stack_policy" in str(call.args[0]) for call in connection.execute.call_args_list)
        )


if __name__ == "__main__":
    unittest.main()
