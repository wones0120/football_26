import unittest
from datetime import datetime
from unittest.mock import MagicMock

import pandas as pd

from backend.app.product_services.optimizer import (
    CLASSIC_CASH_STACK_QB_PAIR_BRINGBACK_ID,
    CLASSIC_CASH_STACK_QB_PAIR_ID,
    CLASSIC_CASH_STACK_UNCONSTRAINED_ID,
    CLASSIC_GPP_STACK_LEGACY_ID,
    OptimizerJob,
    OptimizerService,
    _merge_simulation_evidence,
    _safe_float,
    resolve_optimizer_mode,
    resolve_stacking_policy,
)


class OptimizerModeTests(unittest.TestCase):
    def test_simulation_merge_preserves_existing_ownership_when_evidence_is_null(self):
        pool = pd.DataFrame(
            [
                {"player_id": "player-1", "ownership": 18.0},
                {"player_id": "player-2", "ownership": 7.5},
            ]
        )

        merged = _merge_simulation_evidence(
            pool,
            [
                {
                    "player_id": "player-1",
                    "optimal_lineup_probability": 24.0,
                    "field_ownership": None,
                    "leverage_score": None,
                }
            ],
        )

        by_id = merged.set_index("player_id")
        self.assertEqual(by_id.loc["player-1", "ownership"], 18.0)
        self.assertEqual(by_id.loc["player-2", "ownership"], 7.5)
        self.assertTrue(pd.isna(by_id.loc["player-1", "leverage"]))

    def test_safe_float_normalizes_missing_lineup_values(self):
        self.assertEqual(_safe_float(pd.NA), 0.0)
        self.assertEqual(_safe_float(float("nan")), 0.0)
        self.assertEqual(_safe_float("12.5"), 12.5)

    def test_explicit_classic_cash_mode(self):
        self.assertEqual(
            resolve_optimizer_mode(contest_format="classic", objective="cash"),
            ("classic", "cash", "cash"),
        )

    def test_explicit_showdown_gpp_uses_captain_solver(self):
        self.assertEqual(
            resolve_optimizer_mode(contest_format="showdown", objective="gpp"),
            ("showdown", "gpp", "captain"),
        )

    def test_legacy_contest_types_remain_supported(self):
        self.assertEqual(
            resolve_optimizer_mode(contest_format=None, objective=None, params={"contest_type": "cash"}),
            ("classic", "cash", "cash"),
        )
        self.assertEqual(
            resolve_optimizer_mode(contest_format=None, objective=None, params={"contest_type": "captain"}),
            ("showdown", "gpp", "captain"),
        )

    def test_explicit_contract_overrides_legacy_param(self):
        self.assertEqual(
            resolve_optimizer_mode(
                contest_format="showdown",
                objective="cash",
                params={"contest_type": "tournament"},
            ),
            ("showdown", "cash", "captain"),
        )

    def test_rejects_unknown_values(self):
        with self.assertRaisesRegex(ValueError, "contest_format"):
            resolve_optimizer_mode(contest_format="best-ball", objective="gpp")
        with self.assertRaisesRegex(ValueError, "objective"):
            resolve_optimizer_mode(contest_format="classic", objective="double-up")

    def test_classic_cash_defaults_to_unconstrained_replay_baseline(self):
        policy = resolve_stacking_policy(
            contest_format="classic",
            objective="cash",
        )

        self.assertEqual(policy["policy_id"], CLASSIC_CASH_STACK_UNCONSTRAINED_ID)
        self.assertFalse(policy["enabled"])
        self.assertEqual(policy["evidence_status"], "replay_baseline")
        self.assertEqual(policy["source"], "default")

    def test_classic_cash_policy_can_select_pair_or_pair_with_bringback(self):
        pair = resolve_stacking_policy(
            contest_format="classic",
            objective="cash",
            params={"stack_policy_id": CLASSIC_CASH_STACK_QB_PAIR_ID},
        )
        bringback = resolve_stacking_policy(
            contest_format="classic",
            objective="cash",
            params={"stack_policy_id": CLASSIC_CASH_STACK_QB_PAIR_BRINGBACK_ID},
        )

        self.assertEqual(pair["stack_min"], 1)
        self.assertFalse(pair["bringback"])
        self.assertTrue(bringback["bringback"])
        self.assertEqual(bringback["bringback_positions"], ["WR", "TE"])

    def test_classic_gpp_preserves_the_legacy_stack_default(self):
        policy = resolve_stacking_policy(
            contest_format="classic",
            objective="gpp",
        )

        self.assertEqual(policy["policy_id"], CLASSIC_GPP_STACK_LEGACY_ID)
        self.assertTrue(policy["enabled"])
        self.assertEqual(policy["stack_min"], 2)
        self.assertTrue(policy["bringback"])
        self.assertEqual(policy["evidence_status"], "legacy_default")

    def test_legacy_stack_params_are_preserved_as_an_explicit_custom_policy(self):
        policy = resolve_stacking_policy(
            contest_format="classic",
            objective="cash",
            params={"bringback": False, "include_rb_in_stack": True},
        )

        self.assertEqual(policy["policy_id"], "classic_cash_custom_v1")
        self.assertEqual(policy["base_policy_id"], CLASSIC_CASH_STACK_QB_PAIR_BRINGBACK_ID)
        self.assertEqual(policy["stack_min"], 1)
        self.assertFalse(policy["bringback"])
        self.assertTrue(policy["include_rb_in_stack"])

    def test_versioned_policy_rejects_legacy_overrides_and_wrong_objective(self):
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            resolve_stacking_policy(
                contest_format="classic",
                objective="cash",
                params={
                    "stack_policy_id": CLASSIC_CASH_STACK_QB_PAIR_ID,
                    "bringback": True,
                },
            )
        with self.assertRaisesRegex(ValueError, "not valid for classic gpp"):
            resolve_stacking_policy(
                contest_format="classic",
                objective="gpp",
                params={"stack_policy_id": CLASSIC_CASH_STACK_QB_PAIR_ID},
            )

    def test_unconstrained_policy_skips_stack_validation(self):
        ok, reason = OptimizerService._lineups_satisfy_stack(
            [[{"player_id": "qb-1", "position": "QB"}]],
            {"enabled": False, "stack_min": 0, "bringback": False},
            "cash",
        )

        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_unconstrained_policy_allows_lineup_without_qb_pass_catcher(self):
        service = OptimizerService.__new__(OptimizerService)
        pool = pd.DataFrame(
            [
                {"player_id": "qb", "name": "QB", "position": "QB", "player_team": "AAA", "opponent_team": "BBB"},
                {"player_id": "rb1", "name": "RB1", "position": "RB", "player_team": "CCC", "opponent_team": "DDD"},
                {"player_id": "rb2", "name": "RB2", "position": "RB", "player_team": "DDD", "opponent_team": "CCC"},
                {"player_id": "rb3", "name": "RB3", "position": "RB", "player_team": "EEE", "opponent_team": "FFF"},
                {"player_id": "wr1", "name": "WR1", "position": "WR", "player_team": "CCC", "opponent_team": "DDD"},
                {"player_id": "wr2", "name": "WR2", "position": "WR", "player_team": "DDD", "opponent_team": "CCC"},
                {"player_id": "wr3", "name": "WR3", "position": "WR", "player_team": "EEE", "opponent_team": "FFF"},
                {"player_id": "te", "name": "TE", "position": "TE", "player_team": "FFF", "opponent_team": "EEE"},
                {"player_id": "dst", "name": "DST", "position": "DST", "player_team": "GGG", "opponent_team": "HHH"},
            ]
        )
        pool["salary"] = 5000
        pool["projection"] = 10.0

        unconstrained = resolve_stacking_policy(
            contest_format="classic",
            objective="cash",
        )
        constrained = resolve_stacking_policy(
            contest_format="classic",
            objective="cash",
            params={"stack_policy_id": CLASSIC_CASH_STACK_QB_PAIR_ID},
        )

        self.assertEqual(
            len(
                service._solve_lineup(
                    pool,
                    score_col="projection",
                    contest_type="cash",
                    stack_params=unconstrained,
                )
                or []
            ),
            9,
        )
        self.assertIsNone(
            service._solve_lineup(
                pool,
                score_col="projection",
                contest_type="cash",
                stack_params=constrained,
            )
        )

    def test_optimizer_run_persistence_carries_mode_and_lineage(self):
        service = OptimizerService.__new__(OptimizerService)
        service.engine = MagicMock()
        connection = service.engine.begin.return_value.__enter__.return_value
        now = datetime(2026, 7, 12, 12, 0, 0)
        job = OptimizerJob(
            job_id="optimizer-run-1",
            status="completed",
            created_at=now,
            updated_at=now,
            season=2025,
            week=11,
            slate="SUNDAY_MAIN",
            strategy="baseline",
            contest_format="classic",
            objective="gpp",
            params={"num_lineups": 20},
            projection_run_id="projection-run-1",
            rule_run_id="rule-run-1",
            data_cutoff_at=now,
            results=[
                [
                    {
                        "player_id": "player-1",
                        "name": "Player One",
                        "position": "QB",
                        "salary": 6500,
                        "projection": 20.0,
                        "p90": 30.0,
                        "ownership": 12.5,
                    }
                ]
            ],
        )

        self.assertTrue(service._persist_optimizer_run(job))

        payload = next(
            call.args[1]
            for call in connection.execute.call_args_list
            if len(call.args) > 1
            and isinstance(call.args[1], dict)
            and call.args[1].get("optimizer_run_id") == "optimizer-run-1"
            and "contest_format" in call.args[1]
        )
        self.assertEqual(payload["optimizer_run_id"], "optimizer-run-1")
        self.assertEqual(payload["contest_format"], "classic")
        self.assertEqual(payload["objective"], "gpp")
        self.assertEqual(payload["projection_run_id"], "projection-run-1")
        self.assertEqual(payload["rule_run_id"], "rule-run-1")
        player_payload = next(
            call.args[1]
            for call in connection.execute.call_args_list
            if len(call.args) > 1
            and isinstance(call.args[1], list)
            and call.args[1]
            and call.args[1][0].get("player_id") == "player-1"
        )
        self.assertEqual(player_payload[0]["lineup_id"], "optimizer-run-1:1")

    def test_get_job_reloads_persisted_lineups_after_restart(self):
        service = OptimizerService.__new__(OptimizerService)
        service._jobs = {}
        service.engine = MagicMock()
        connection = service.engine.begin.return_value.__enter__.return_value
        now = datetime(2026, 7, 12, 12, 0, 0)

        run_result = MagicMock()
        run_result.mappings.return_value.first.return_value = {
            "optimizer_run_id": "optimizer-run-2",
            "status": "completed",
            "created_at": now,
            "updated_at": now,
            "season": 2025,
            "week": 11,
            "slate_id": "SUNDAY_MAIN",
            "strategy": "baseline",
            "contest_format": "showdown",
            "objective": "gpp",
            "constraint_config_json": {"num_lineups": 1},
            "projection_run_id": "projection-run-2",
            "rule_run_id": None,
            "data_cutoff_at": now,
            "message": "completed",
        }
        lineup_result = MagicMock()
        lineup_result.mappings.return_value.all.return_value = [
            {"lineup_id": "optimizer-run-2:1", "lineup_number": 1}
        ]
        player_result = MagicMock()
        player_result.mappings.return_value.all.return_value = [
            {"player_json": {"player_id": "player-2", "roster_position": "CPT"}}
        ]
        connection.execute.side_effect = [run_result, lineup_result, player_result]

        job = service.get_job("optimizer-run-2")

        self.assertIsNotNone(job)
        self.assertEqual(job.contest_format, "showdown")
        self.assertEqual(job.objective, "gpp")
        self.assertTrue(job.lineage_persisted)
        self.assertEqual(job.results[0][0]["roster_position"], "CPT")

    def test_optimizer_resolves_latest_target_prediction_lineage(self):
        service = OptimizerService.__new__(OptimizerService)
        service.engine = MagicMock()
        connection = service.engine.begin.return_value.__enter__.return_value
        cutoff = datetime(2025, 11, 16, 13, 0, 0)
        projection_result = MagicMock()
        projection_result.mappings.return_value.first.return_value = {
            "projection_run_id": "projection-run-latest",
            "data_cutoff_at": cutoff,
        }
        rule_result = MagicMock()
        rule_result.mappings.return_value.first.return_value = {
            "rule_run_id": "rule-run-latest"
        }
        connection.execute.side_effect = [projection_result, rule_result]

        projection_run_id, rule_run_id, data_cutoff_at = service._resolve_run_lineage(
            season=2025,
            week=11,
            slate="SUNDAY_MAIN",
            projection_run_id=None,
            rule_run_id=None,
            data_cutoff_at=None,
        )

        self.assertEqual(projection_run_id, "projection-run-latest")
        self.assertEqual(rule_run_id, "rule-run-latest")
        self.assertEqual(data_cutoff_at, cutoff)

        rule_params = connection.execute.call_args_list[1].args[1]
        self.assertEqual(rule_params["projection_run_id"], "projection-run-latest")

    def test_optimizer_resolves_cutoff_and_rule_for_explicit_projection(self):
        service = OptimizerService.__new__(OptimizerService)
        service.engine = MagicMock()
        connection = service.engine.begin.return_value.__enter__.return_value
        cutoff = datetime(2025, 11, 16, 13, 0, 0)
        projection_result = MagicMock()
        projection_result.mappings.return_value.first.return_value = {
            "projection_run_id": "projection-run-explicit",
            "data_cutoff_at": cutoff,
        }
        rule_result = MagicMock()
        rule_result.mappings.return_value.first.return_value = {
            "rule_run_id": "rule-run-compatible"
        }
        connection.execute.side_effect = [projection_result, rule_result]

        projection_run_id, rule_run_id, data_cutoff_at = service._resolve_run_lineage(
            season=2025,
            week=11,
            slate="SUNDAY_MAIN",
            projection_run_id="projection-run-explicit",
            rule_run_id=None,
            data_cutoff_at=None,
        )

        self.assertEqual(projection_run_id, "projection-run-explicit")
        self.assertEqual(rule_run_id, "rule-run-compatible")
        self.assertEqual(data_cutoff_at, cutoff)
        projection_params = connection.execute.call_args_list[0].args[1]
        rule_params = connection.execute.call_args_list[1].args[1]
        self.assertEqual(projection_params["projection_run_id"], "projection-run-explicit")
        self.assertEqual(rule_params["projection_run_id"], "projection-run-explicit")


if __name__ == "__main__":
    unittest.main()
