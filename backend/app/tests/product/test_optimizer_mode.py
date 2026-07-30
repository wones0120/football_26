import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd

from backend.app.product_services.gpp_optimizer import (
    GPPOptimizerResult,
    Player,
    PortfolioStats,
    SlateAnalysis,
    build_slate_config,
)
from backend.app.product_services.optimizer import (
    CLASSIC_CASH_STACK_QB_PAIR_BRINGBACK_ID,
    CLASSIC_CASH_STACK_QB_PAIR_ID,
    CLASSIC_CASH_STACK_UNCONSTRAINED_ID,
    CLASSIC_GPP_ADVANCED_STRATEGY_ID,
    CLASSIC_GPP_BASELINE_STRATEGY_ID,
    CLASSIC_GPP_STACK_LEGACY_ID,
    SHOWDOWN_CASH_BASELINE_STRATEGY_ID,
    SHOWDOWN_GPP_BASELINE_STRATEGY_ID,
    OptimizerJob,
    OptimizerService,
    _merge_simulation_evidence,
    _safe_float,
    resolve_optimizer_mode,
    resolve_optimizer_strategy,
    resolve_stacking_policy,
)


class OptimizerModeTests(unittest.TestCase):
    def test_target_pool_query_excludes_injuries_after_projection_cutoff(self):
        service = OptimizerService.__new__(OptimizerService)
        service.engine = MagicMock()
        inspector = MagicMock()
        inspector.has_table.return_value = True
        inspector.get_columns.return_value = []

        with (
            patch("backend.app.product_services.optimizer.inspect", return_value=inspector),
            patch(
                "backend.app.product_services.optimizer.pd.read_sql",
                return_value=pd.DataFrame(),
            ) as read_sql,
        ):
            pool = service._load_target_player_pool(
                season=2025,
                week=11,
                slate="SUNDAY_MAIN",
                projection_run_id="projection-1",
            )

        self.assertTrue(pool.empty)
        sql = str(read_sql.call_args.args[0])
        self.assertIn("injury.as_of <= p.data_cutoff_at", sql)
        self.assertIn("p.data_cutoff_at IS NOT NULL", sql)

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

    def test_classic_gpp_strategy_resolves_explicit_versioned_engines(self):
        baseline = resolve_optimizer_strategy(
            contest_format="classic",
            objective="gpp",
            strategy=CLASSIC_GPP_BASELINE_STRATEGY_ID,
        )
        advanced = resolve_optimizer_strategy(
            contest_format="classic",
            objective="gpp",
            strategy=CLASSIC_GPP_ADVANCED_STRATEGY_ID,
        )

        self.assertEqual(baseline["engine"], "legacy_ilp")
        self.assertEqual(advanced["engine"], "slate_aware_gpp")
        self.assertEqual(advanced["source"], "explicit")

    def test_legacy_gpp_alias_preserves_the_baseline_and_invalid_modes_fail(self):
        legacy = resolve_optimizer_strategy(
            contest_format="classic",
            objective="gpp",
            strategy="gpp",
        )

        self.assertEqual(
            legacy["strategy_id"], CLASSIC_GPP_BASELINE_STRATEGY_ID
        )
        self.assertEqual(legacy["source"], "legacy_alias")
        with self.assertRaisesRegex(ValueError, "not valid for classic cash"):
            resolve_optimizer_strategy(
                contest_format="classic",
                objective="cash",
                strategy=CLASSIC_GPP_ADVANCED_STRATEGY_ID,
            )

    def test_showdown_cash_and_gpp_resolve_distinct_versioned_contracts(self):
        cash = resolve_optimizer_strategy(
            contest_format="showdown",
            objective="cash",
            strategy="gpp",
        )
        gpp = resolve_optimizer_strategy(
            contest_format="showdown",
            objective="gpp",
            strategy="gpp",
        )

        self.assertEqual(
            cash["strategy_id"], SHOWDOWN_CASH_BASELINE_STRATEGY_ID
        )
        self.assertEqual(gpp["strategy_id"], SHOWDOWN_GPP_BASELINE_STRATEGY_ID)
        self.assertEqual(cash["engine"], "captain_ilp")
        self.assertEqual(gpp["engine"], "captain_ilp")
        self.assertEqual(cash["source"], "legacy_alias")
        with self.assertRaisesRegex(ValueError, "showdown cash"):
            resolve_optimizer_strategy(
                contest_format="showdown",
                objective="cash",
                strategy=SHOWDOWN_GPP_BASELINE_STRATEGY_ID,
            )

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

    def test_advanced_strategy_executes_against_the_live_pool_without_fallback(self):
        service = OptimizerService.__new__(OptimizerService)
        service._jobs = {}
        service.engine = MagicMock()
        service._resolve_run_lineage = MagicMock(
            return_value=("projection-run-1", "rule-run-1", None)
        )
        positions = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "WR", "DST"]
        teams = ["AAA", "AAA", "BBB", "AAA", "BBB", "BBB", "CCC", "CCC", "CCC"]
        opponents = {"AAA": "BBB", "BBB": "AAA", "CCC": "DDD"}
        pool = pd.DataFrame(
            [
                {
                    "player_id": f"player-{index}",
                    "name": f"Player {index}",
                    "position": position,
                    "player_team": team,
                    "opponent_team": opponents[team],
                    "salary": 5000,
                    "projection": 10.0 + index,
                    "p90": 20.0 + index,
                    "ownership": 5.0,
                    "optimal_lineup_probability": 8.0,
                }
                for index, (position, team) in enumerate(zip(positions, teams))
            ]
        )
        service._load_player_pool = MagicMock(return_value=pool)
        service._apply_pool_filters = MagicMock(side_effect=lambda rows, contest_type: rows)
        service._solve_lineup = MagicMock()
        service._lineups_satisfy_stack = MagicMock(return_value=(True, ""))
        service._attach_symbolic_explanations = MagicMock()
        service._persist_optimizer_run = MagicMock(return_value=True)
        gpp_players = service._gpp_players_from_pool(pool)
        analysis = SlateAnalysis(
            game_count=1,
            chalk_concentration=0.0,
            feature_games=[],
        )
        config = build_slate_config(analysis)
        gpp_result = GPPOptimizerResult(
            job_id="advanced-service-run",
            status="completed",
            message="Generated 1 lineup(s) after 1 iteration(s)",
            created_at=datetime(2026, 7, 27, 12, 0, 0),
            updated_at=datetime(2026, 7, 27, 12, 0, 0),
            lineups=[gpp_players],
            config=config,
            analysis=analysis,
            portfolio=PortfolioStats(
                exposures={player.player_id: 1.0 for player in gpp_players},
                tag_counts={},
                avg_total_ownership=45.0,
                stack_summary={"2-with-qb_1-bringback": 1},
            ),
            iterations=1,
        )

        with (
            patch(
                "backend.app.product_services.optimizer.run_gpp_pipeline",
                return_value=gpp_result,
            ) as run_gpp,
            patch(
                "backend.app.product_services.optimizer.SimulationService.fetch_latest",
                return_value=None,
            ),
        ):
            job = service.run_job(
                season=2025,
                week=11,
                slate="SUNDAY_MAIN",
                strategy=CLASSIC_GPP_ADVANCED_STRATEGY_ID,
                params={"num_lineups": 1, "max_exposure": 0.75},
                contest_format="classic",
                objective="gpp",
            )

        self.assertEqual(job.status, "completed")
        self.assertEqual(job.strategy, CLASSIC_GPP_ADVANCED_STRATEGY_ID)
        self.assertEqual(job.params["strategy_config"]["engine"], "slate_aware_gpp")
        self.assertEqual(
            job.results[0][0]["lineup_optimizer_strategy"]["strategy_id"],
            CLASSIC_GPP_ADVANCED_STRATEGY_ID,
        )
        self.assertEqual(
            job.params["stack_policy"]["stack_min"],
            config.stack_rules.min_pass_catchers,
        )
        self.assertIn("strategy_runtime", job.params)
        self.assertEqual(
            job.params["strategy_runtime"]["validation"]["status"], "passed"
        )
        self.assertIn("lineup validation=passed", job.message)
        self.assertEqual(
            {player.player_id for player in run_gpp.call_args.kwargs["players"]},
            set(pool["player_id"]),
        )
        self.assertEqual(run_gpp.call_args.kwargs["max_exposure"], 0.75)
        service._solve_lineup.assert_not_called()

    def test_classic_lineup_validation_rejects_illegal_advanced_output(self):
        lineup = [
            {
                "player_id": f"player-{index}",
                "position": position,
                "player_team": "AAA" if index < 5 else "BBB",
                "opponent_team": "BBB" if index < 5 else "AAA",
                "salary": 5000,
            }
            for index, position in enumerate(
                ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "WR", "DST"]
            )
        ]

        valid, reason = OptimizerService._validate_classic_lineups(
            [lineup],
            requested_lineups=1,
            max_exposure=1.0,
            enforce_single_te=True,
            avoid_dst_opponents=False,
            uniqueness_overlap=7,
        )

        self.assertFalse(valid)
        self.assertIn("4-player classic team limit", reason)

    def test_showdown_lineup_validation_enforces_captain_flex_contract(self):
        lineup = [
            {
                "player_id": f"player-{index}",
                "roster_position": "CPT" if index == 0 else "FLEX",
                "player_team": "AAA" if index < 3 else "BBB",
                "salary": 7500,
            }
            for index in range(6)
        ]

        valid, reason = OptimizerService._validate_showdown_lineups(
            [lineup],
            requested_lineups=1,
            max_exposure=1.0,
        )
        self.assertTrue(valid, reason)

        lineup[1]["roster_position"] = "CPT"
        valid, reason = OptimizerService._validate_showdown_lineups(
            [lineup],
            requested_lineups=1,
            max_exposure=1.0,
        )
        self.assertFalse(valid)
        self.assertIn("exactly one CPT", reason)

    def test_showdown_solver_preserves_mean_and_p90_slot_values(self):
        service = OptimizerService.__new__(OptimizerService)
        pool = pd.DataFrame(
            [
                {
                    "player_id": f"player-{index}",
                    "name": f"Player {index}",
                    "position": "WR",
                    "player_team": "AAA" if index < 3 else "BBB",
                    "opponent_team": "BBB" if index < 3 else "AAA",
                    "salary": 5000,
                    "projection": 10.0 + index,
                    "p90": 20.0 + index,
                }
                for index in range(7)
            ]
        )

        lineup = service._solve_lineup(
            pool,
            score_col="p90",
            contest_type="captain",
        )

        self.assertIsNotNone(lineup)
        self.assertEqual(len(lineup), 6)
        self.assertEqual(
            [row["roster_position"] for row in lineup].count("CPT"),
            1,
        )
        for row in lineup:
            multiplier = 1.5 if row["roster_position"] == "CPT" else 1.0
            self.assertEqual(
                row["projection"], row["base_projection"] * multiplier
            )
            self.assertEqual(row["p90"], row["base_p90"] * multiplier)
            self.assertEqual(
                row["objective_score"], row["base_p90"] * multiplier
            )

    def test_showdown_run_persists_canonical_strategy_and_slot_validation(self):
        service = OptimizerService.__new__(OptimizerService)
        service._jobs = {}
        service.engine = MagicMock()
        service._resolve_run_lineage = MagicMock(
            return_value=("projection-run-showdown", "rule-run-showdown", None)
        )
        pool = pd.DataFrame(
            [
                {
                    "player_id": f"player-{index}",
                    "name": f"Player {index}",
                    "position": "WR",
                    "player_team": "AAA" if index < 3 else "BBB",
                    "opponent_team": "BBB" if index < 3 else "AAA",
                    "salary": 5000,
                    "projection": 10.0 + index,
                    "p90": 20.0 + index,
                }
                for index in range(6)
            ]
        )
        lineup = [
            {
                **row,
                "roster_position": "CPT" if index == 2 else "FLEX",
                "salary": row["salary"] * (1.5 if index == 2 else 1.0),
                "projection": row["p90"] * (1.5 if index == 2 else 1.0),
                "p90": row["p90"] * (1.5 if index == 2 else 1.0),
            }
            for index, row in enumerate(pool.to_dict(orient="records"))
        ]
        service._load_player_pool = MagicMock(return_value=pool)
        service._solve_lineup = MagicMock(return_value=lineup)
        service._lineups_satisfy_stack = MagicMock(return_value=(True, ""))
        service._attach_symbolic_explanations = MagicMock()
        service._persist_optimizer_run = MagicMock(return_value=True)

        job = service.run_job(
            season=2025,
            week=11,
            slate="THURSDAY_NIGHT",
            strategy="gpp",
            params={"num_lineups": 1},
            contest_format="showdown",
            objective="cash",
        )

        self.assertEqual(job.status, "completed")
        self.assertEqual(job.strategy, SHOWDOWN_CASH_BASELINE_STRATEGY_ID)
        self.assertEqual(job.params["objective_config"]["captain_slots"], 1)
        self.assertEqual(
            job.params["strategy_runtime"]["validation"]["flex_slots"], 5
        )
        self.assertEqual(job.results[0][0]["roster_position"], "CPT")
        self.assertEqual(
            [row["lineup_slot_index"] for row in job.results[0]],
            list(range(6)),
        )
        self.assertIn("showdown lineup validation=passed", job.message)
        self.assertTrue(job.lineage_persisted)

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
            params={
                "num_lineups": 20,
                "strategy_config": {
                    "strategy_id": CLASSIC_GPP_BASELINE_STRATEGY_ID,
                    "version": "v1",
                    "engine": "legacy_ilp",
                },
            },
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
        self.assertTrue(
            any(
                "optimizer_strategy" in str(call.args[0])
                for call in connection.execute.call_args_list
            )
        )

    def test_failed_showdown_run_persists_status_message_and_lineage(self):
        service = OptimizerService.__new__(OptimizerService)
        service.engine = MagicMock()
        connection = service.engine.begin.return_value.__enter__.return_value
        now = datetime(2026, 7, 12, 12, 0, 0)
        job = OptimizerJob(
            job_id="showdown-failed-run",
            status="failed",
            created_at=now,
            updated_at=now,
            season=2025,
            week=11,
            slate="THURSDAY_NIGHT",
            strategy=SHOWDOWN_CASH_BASELINE_STRATEGY_ID,
            contest_format="showdown",
            objective="cash",
            params={
                "strategy_config": {
                    "strategy_id": SHOWDOWN_CASH_BASELINE_STRATEGY_ID,
                    "engine": "captain_ilp",
                }
            },
            projection_run_id="projection-run-failed",
            rule_run_id="rule-run-failed",
            data_cutoff_at=now,
            results=None,
            message="Optimizer failed to find lineup.",
        )

        self.assertTrue(service._persist_optimizer_run(job))

        payload = next(
            call.args[1]
            for call in connection.execute.call_args_list
            if len(call.args) > 1
            and isinstance(call.args[1], dict)
            and call.args[1].get("optimizer_run_id") == "showdown-failed-run"
            and "contest_format" in call.args[1]
        )
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["message"], "Optimizer failed to find lineup.")
        self.assertEqual(payload["contest_format"], "showdown")
        self.assertEqual(payload["objective"], "cash")
        self.assertEqual(
            payload["strategy"], SHOWDOWN_CASH_BASELINE_STRATEGY_ID
        )
        self.assertEqual(payload["projection_run_id"], "projection-run-failed")
        self.assertEqual(payload["rule_run_id"], "rule-run-failed")

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
            "strategy": SHOWDOWN_GPP_BASELINE_STRATEGY_ID,
            "contest_format": "showdown",
            "objective": "gpp",
            "constraint_config_json": {
                "num_lineups": 1,
                "strategy_config": {
                    "strategy_id": SHOWDOWN_GPP_BASELINE_STRATEGY_ID
                },
            },
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
            {
                "slot_index": index,
                "roster_position": "CPT" if index == 0 else "FLEX",
                "player_json": {"player_id": f"player-{index + 2}"},
            }
            for index in range(6)
        ]
        connection.execute.side_effect = [run_result, lineup_result, player_result]

        job = service.get_job("optimizer-run-2")

        self.assertIsNotNone(job)
        self.assertEqual(job.contest_format, "showdown")
        self.assertEqual(job.objective, "gpp")
        self.assertEqual(job.strategy, SHOWDOWN_GPP_BASELINE_STRATEGY_ID)
        self.assertTrue(job.lineage_persisted)
        self.assertEqual(job.results[0][0]["roster_position"], "CPT")
        self.assertEqual(
            [row["roster_position"] for row in job.results[0]],
            ["CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"],
        )
        self.assertEqual(
            [row["lineup_slot_index"] for row in job.results[0]],
            list(range(6)),
        )

    def test_get_job_reloads_persisted_showdown_failure_after_restart(self):
        service = OptimizerService.__new__(OptimizerService)
        service._jobs = {}
        service.engine = MagicMock()
        connection = service.engine.begin.return_value.__enter__.return_value
        now = datetime(2026, 7, 12, 12, 0, 0)

        run_result = MagicMock()
        run_result.mappings.return_value.first.return_value = {
            "optimizer_run_id": "optimizer-run-failed",
            "status": "failed",
            "created_at": now,
            "updated_at": now,
            "season": 2025,
            "week": 11,
            "slate_id": "THURSDAY_NIGHT",
            "strategy": SHOWDOWN_CASH_BASELINE_STRATEGY_ID,
            "contest_format": "showdown",
            "objective": "cash",
            "constraint_config_json": {
                "strategy_config": {
                    "strategy_id": SHOWDOWN_CASH_BASELINE_STRATEGY_ID
                }
            },
            "projection_run_id": "projection-run-failed",
            "rule_run_id": "rule-run-failed",
            "data_cutoff_at": now,
            "message": "Optimizer failed to find lineup.",
        }
        lineup_result = MagicMock()
        lineup_result.mappings.return_value.all.return_value = []
        connection.execute.side_effect = [run_result, lineup_result]

        job = service.get_job("optimizer-run-failed")

        self.assertIsNotNone(job)
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.contest_format, "showdown")
        self.assertEqual(job.objective, "cash")
        self.assertEqual(job.strategy, SHOWDOWN_CASH_BASELINE_STRATEGY_ID)
        self.assertEqual(job.projection_run_id, "projection-run-failed")
        self.assertEqual(job.rule_run_id, "rule-run-failed")
        self.assertTrue(job.lineage_persisted)
        self.assertIsNone(job.results)
        self.assertEqual(job.message, "Optimizer failed to find lineup.")

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
