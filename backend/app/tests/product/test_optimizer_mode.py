import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd

from backend.app.product_services.gpp_optimizer import (
    GPPOptimizerResult,
    Player,
    PortfolioStats,
    SlateAnalysis,
    build_large_gpp_config,
    build_slate_config,
)
from backend.app.product_services.optimizer import (
    CLASSIC_CASH_STACK_QB_PAIR_BRINGBACK_ID,
    CLASSIC_CASH_STACK_QB_PAIR_ID,
    CLASSIC_CASH_STACK_UNCONSTRAINED_ID,
    CLASSIC_GPP_ADVANCED_STRATEGY_ID,
    CLASSIC_GPP_BASELINE_STRATEGY_ID,
    CLASSIC_GPP_STACK_LEGACY_ID,
    CLASSIC_HEAD_TO_HEAD_STRATEGY_ID,
    CLASSIC_LARGE_GPP_STRATEGY_ID,
    SHOWDOWN_CASH_BASELINE_STRATEGY_ID,
    SHOWDOWN_CASH_QB_CAPTAIN_STACK_STRATEGY_ID,
    SHOWDOWN_GPP_CAPTAIN_INFORMED_V1_STRATEGY_ID,
    SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID,
    SHOWDOWN_GPP_BASELINE_STRATEGY_ID,
    SHOWDOWN_QB_CAPTAIN_RECEIVER_RULE_ID,
    OptimizerJob,
    OptimizerService,
    _merge_simulation_evidence,
    _safe_float,
    build_showdown_captain_prior,
    build_head_to_head_objective,
    restrict_pool_to_pregame_available,
    restrict_showdown_pool_to_starting_qbs,
    resolve_optimizer_mode,
    resolve_optimizer_strategy,
    resolve_stacking_policy,
    showdown_optimizer_rules,
    summarize_head_to_head_lineup,
    summarize_individual_ceiling_sum,
)


class OptimizerModeTests(unittest.TestCase):
    def test_target_pool_query_loads_cutoff_safe_eligibility_evidence_for_audit(self):
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
        self.assertIn("captain_site_player_id", sql)
        self.assertIn("UPPER(salary.roster_position) = 'FLEX'", sql)
        self.assertIn("participation.roster_status", sql)
        self.assertIn("IN ('FLEX', 'CPT')", sql)
        self.assertIn("projection_feature.feature_json ->> 'game_total_line'", sql)
        self.assertIn("projection_model_run.feature_run_id", sql)
        self.assertIn("TRUE AS market_context_point_in_time_safe", sql)
        self.assertNotIn("player_game_feature_matrix", sql)
        self.assertIn("starting_qb_evidence", sql)
        self.assertIn("feature_player_game", sql)
        self.assertIn("pregame_availability_probability", sql)
        self.assertIn("pregame_context_observed_at", sql)
        self.assertIn("pregame_expected_snaps", sql)
        self.assertIn("pregame_goal_line_share", sql)
        self.assertIn("identity_resolved", sql)
        self.assertIn("roster_evidence_available", sql)
        self.assertIn("salary.player_status", sql)
        self.assertIn("'OUT'", sql)

    def test_pregame_zero_availability_is_excluded_from_optimizer_pool(self):
        eligible_pool = pd.DataFrame(
            [
                {
                    "player_id": "out-player",
                    "pregame_availability_probability": 0.0,
                },
                {
                    "player_id": "questionable-player",
                    "pregame_availability_probability": 0.75,
                },
                {
                    "player_id": "no-context-player",
                    "pregame_availability_probability": None,
                },
            ]
        )

        filtered, excluded_ids = restrict_pool_to_pregame_available(eligible_pool)

        self.assertEqual(
            set(filtered["player_id"]),
            {"questionable-player", "no-context-player"},
        )
        self.assertEqual(excluded_ids, {"out-player"})

    def test_target_salary_fallback_pairs_captain_id_and_recovers_position(self):
        service = OptimizerService.__new__(OptimizerService)
        service.engine = MagicMock()
        inspector = MagicMock()
        inspector.has_table.side_effect = (
            lambda table_name, schema=None: table_name != "curated_salary"
        )
        inspector.get_columns.return_value = []

        with (
            patch("backend.app.product_services.optimizer.inspect", return_value=inspector),
            patch(
                "backend.app.product_services.optimizer.pd.read_sql",
                return_value=pd.DataFrame(),
            ) as read_sql,
        ):
            pool = service._load_target_player_pool(
                season=2026,
                week=1,
                slate="WEDNESDAY_NIGHT",
            )

        self.assertTrue(pool.empty)
        sql = str(read_sql.call_args.args[0])
        self.assertIn("FROM target.snapshot_salary salary", sql)
        self.assertIn("captain.site_player_id AS captain_site_player_id", sql)
        self.assertIn("IN ('FLEX', 'CPT')", sql)
        self.assertIn("d.primary_position", sql)
        self.assertIn("salary.player_status", sql)
        self.assertIn("'OUT'", sql)

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

    def test_explicit_head_to_head_and_large_gpp_contracts_are_distinct(self):
        head_to_head = resolve_optimizer_strategy(
            contest_format="classic",
            objective="cash",
            strategy=CLASSIC_HEAD_TO_HEAD_STRATEGY_ID,
        )
        large_gpp = resolve_optimizer_strategy(
            contest_format="classic",
            objective="gpp",
            strategy=CLASSIC_LARGE_GPP_STRATEGY_ID,
        )

        self.assertEqual(head_to_head["engine"], "head_to_head_ilp")
        self.assertEqual(large_gpp["engine"], "large_gpp_portfolio")
        self.assertNotEqual(head_to_head["objective"], large_gpp["objective"])

    def test_head_to_head_pool_is_broad_and_excludes_backup_qbs_with_real_reason(self):
        service = OptimizerService.__new__(OptimizerService)
        pool = pd.DataFrame(
            [
                {"player_id": "qb1", "position": "QB", "salary": 7000, "projection": 20.0, "p90": 30.0, "is_starting_qb": True},
                {"player_id": "qb2", "position": "QB", "salary": 5000, "projection": 8.0, "p90": 16.0, "is_starting_qb": False},
                {"player_id": "starter-wr", "position": "WR", "salary": 5500, "projection": 10.0, "p90": 12.0, "is_starting_qb": False},
                {"player_id": "zero-role", "position": "WR", "salary": 3000, "projection": 0.0, "p90": 0.0, "is_starting_qb": False},
            ]
        )

        filtered, reasons = service._select_strategy_candidates(
            pool,
            strategy=CLASSIC_HEAD_TO_HEAD_STRATEGY_ID,
            contest_type="cash",
        )

        self.assertEqual(set(filtered["player_id"]), {"qb1", "starter-wr"})
        self.assertEqual(reasons["qb2"], ["backup QB / zero expected snaps"])
        self.assertEqual(reasons["zero-role"], ["no positive projection"])

    def test_head_to_head_pool_keeps_qb_with_explicit_package_snaps(self):
        service = OptimizerService.__new__(OptimizerService)
        pool = pd.DataFrame(
            [
                {
                    "player_id": "qb-starter",
                    "position": "QB",
                    "salary": 7000,
                    "projection": 20.0,
                    "p90": 28.0,
                    "is_starting_qb": True,
                },
                {
                    "player_id": "qb-package",
                    "position": "QB",
                    "salary": 3000,
                    "projection": 2.0,
                    "p90": 8.0,
                    "is_starting_qb": False,
                    "pregame_expected_snaps": 4.0,
                },
            ]
        )

        filtered, reasons = service._select_strategy_candidates(
            pool,
            strategy=CLASSIC_HEAD_TO_HEAD_STRATEGY_ID,
            contest_type="cash",
        )

        self.assertIn("qb-package", set(filtered["player_id"]))
        self.assertNotIn("qb-package", reasons)

    def test_head_to_head_objective_is_mean_dominant_and_reports_floor(self):
        scored = build_head_to_head_objective(
            pd.DataFrame(
                [
                    {"player_id": "steady", "salary": 6000, "projection": 15.0, "p90": 20.0, "predicted_p10": 10.0, "calibration_role": "PRIMARY"},
                    {"player_id": "fragile", "salary": 3000, "projection": 4.0, "p90": 15.0, "predicted_p10": 1.0, "calibration_role": "ROTATION"},
                ]
            )
        )

        self.assertGreater(scored.loc[0, "h2h_score"], scored.loc[1, "h2h_score"])
        self.assertEqual(scored.loc[1, "h2h_fragile_punt_penalty"], 0.5)
        summary = summarize_head_to_head_lineup(scored.to_dict(orient="records"))
        self.assertEqual(summary["projected_mean"], 19.0)
        self.assertEqual(summary["projected_floor_p10"], 11.0)
        self.assertEqual(summary["downside_risk"], 8.0)
        self.assertEqual(summary["individual_ceiling_sum"], 35.0)
        self.assertFalse(summary["projected_p90_is_joint_quantile"])

    def test_summed_player_p90_is_labeled_as_an_individual_ceiling_sum(self):
        summary = summarize_individual_ceiling_sum(
            [
                {"player_id": "one", "p90": 21.0},
                {"player_id": "two", "p90": 18.5},
            ]
        )

        self.assertEqual(summary["metric_id"], "individual_ceiling_sum_v1")
        self.assertEqual(summary["label"], "Individual Ceiling Sum")
        self.assertEqual(summary["value"], 39.5)
        self.assertFalse(summary["is_joint_quantile"])

    def test_large_gpp_config_redistributes_missing_ownership_weight(self):
        analysis = SlateAnalysis(game_count=12, chalk_concentration=0.0, feature_games=[])
        without_ownership = build_large_gpp_config(
            analysis, ownership_available=False
        )
        with_ownership = build_large_gpp_config(
            analysis, ownership_available=True
        )

        self.assertEqual(without_ownership.objective_weights.leverage, 0.0)
        self.assertGreater(
            without_ownership.objective_weights.ceiling,
            with_ownership.objective_weights.ceiling,
        )
        self.assertEqual(
            without_ownership.stack_templates,
            ((1, 0), (1, 1), (2, 0), (2, 1)),
        )

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
        with self.assertRaisesRegex(ValueError, "for classic cash"):
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
            cash["strategy_id"], SHOWDOWN_CASH_QB_CAPTAIN_STACK_STRATEGY_ID
        )
        self.assertEqual(
            gpp["strategy_id"], SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID
        )
        self.assertEqual(cash["engine"], "captain_ilp")
        self.assertEqual(gpp["engine"], "captain_informed_ilp")
        self.assertEqual(cash["source"], "legacy_alias")
        with self.assertRaisesRegex(ValueError, "showdown cash"):
            resolve_optimizer_strategy(
                contest_format="showdown",
                objective="cash",
                strategy=SHOWDOWN_GPP_BASELINE_STRATEGY_ID,
            )

        informed = resolve_optimizer_strategy(
            contest_format="showdown",
            objective="gpp",
            strategy=SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID,
        )
        self.assertEqual(informed["engine"], "captain_informed_ilp")
        self.assertEqual(
            informed["evidence_status"],
            "production_validated_plus_user_rule",
        )

        historical = resolve_optimizer_strategy(
            contest_format="showdown",
            objective="gpp",
            strategy=SHOWDOWN_GPP_CAPTAIN_INFORMED_V1_STRATEGY_ID,
        )
        baseline_alias = resolve_optimizer_strategy(
            contest_format="showdown",
            objective="gpp",
            strategy="baseline",
        )
        self.assertEqual(historical["evidence_status"], "production_validated")
        self.assertEqual(
            baseline_alias["strategy_id"], SHOWDOWN_GPP_BASELINE_STRATEGY_ID
        )
        self.assertEqual(showdown_optimizer_rules(historical["strategy_id"]), [])
        self.assertEqual(
            showdown_optimizer_rules(informed["strategy_id"])[0]["rule_id"],
            SHOWDOWN_QB_CAPTAIN_RECEIVER_RULE_ID,
        )

    def test_showdown_pool_keeps_one_unique_top_salary_qb_per_team(self):
        pool = pd.DataFrame(
            [
                {"player_id": "aaa-qb1", "name": "AAA One", "position": "QB", "player_team": "AAA", "salary": 10000},
                {"player_id": "aaa-qb2", "name": "AAA Two", "position": "QB", "player_team": "AAA", "salary": 7000},
                {"player_id": "aaa-qb3", "name": "AAA Three", "position": "QB", "player_team": "AAA", "salary": 5000},
                {"player_id": "bbb-qb1", "name": "BBB One", "position": "QB", "player_team": "BBB", "salary": 9600},
                {"player_id": "bbb-qb2", "name": "BBB Two", "position": "QB", "player_team": "BBB", "salary": 6800},
                {"player_id": "wr-1", "name": "Receiver", "position": "WR", "player_team": "AAA", "salary": 8000},
                {"player_id": "wr-2", "name": "Receiver Two", "position": "WR", "player_team": "BBB", "salary": 7800},
            ]
        )

        filtered, evidence = restrict_showdown_pool_to_starting_qbs(pool)

        qbs = filtered[filtered["position"] == "QB"]
        self.assertEqual(set(qbs["player_id"]), {"aaa-qb1", "bbb-qb1"})
        self.assertTrue(qbs["showdown_qb_eligible"].all())
        self.assertEqual(evidence["excluded_qb_count"], 3)
        self.assertEqual(evidence["evidence_status"], "salary_inferred")

    def test_showdown_pool_preserves_explicit_specialty_qb_package(self):
        pool = pd.DataFrame(
            [
                {"player_id": "aaa-qb1", "position": "QB", "player_team": "AAA", "salary": 10000},
                {"player_id": "aaa-package", "position": "QB", "player_team": "AAA", "salary": 3000, "pregame_expected_snaps": 4.0},
                {"player_id": "bbb-qb1", "position": "QB", "player_team": "BBB", "salary": 9800},
                {"player_id": "wr-1", "position": "WR", "player_team": "AAA", "salary": 8000},
                {"player_id": "wr-2", "position": "WR", "player_team": "BBB", "salary": 7800},
            ]
        )

        filtered, evidence = restrict_showdown_pool_to_starting_qbs(pool)

        self.assertEqual(
            set(filtered.loc[filtered["position"] == "QB", "player_id"]),
            {"aaa-qb1", "aaa-package", "bbb-qb1"},
        )
        self.assertEqual(evidence["specialty_qb_ids"], ["aaa-package"])
        specialty = filtered.loc[filtered["player_id"] == "aaa-package"].iloc[0]
        self.assertTrue(specialty["showdown_qb_eligible"])
        self.assertEqual(specialty["starter_qb_source"], "explicit_specialty_role")

    def test_showdown_pool_prefers_explicit_qb1_and_fails_on_salary_tie(self):
        explicit_pool = pd.DataFrame(
            [
                {"player_id": "aaa-explicit", "position": "QB", "player_team": "AAA", "salary": 6000, "depth_chart_position": "QB1"},
                {"player_id": "aaa-expensive", "position": "QB", "player_team": "AAA", "salary": 10000, "depth_chart_position": "QB"},
                {"player_id": "bbb-explicit", "position": "QB", "player_team": "BBB", "salary": 6200, "is_starting_qb": True},
                {"player_id": "bbb-expensive", "position": "QB", "player_team": "BBB", "salary": 9800},
                {"player_id": "wr-1", "position": "WR", "player_team": "AAA", "salary": 8000},
                {"player_id": "wr-2", "position": "WR", "player_team": "BBB", "salary": 7800},
            ]
        )

        filtered, evidence = restrict_showdown_pool_to_starting_qbs(explicit_pool)

        self.assertEqual(
            set(filtered.loc[filtered["position"] == "QB", "player_id"]),
            {"aaa-explicit", "bbb-explicit"},
        )
        self.assertEqual(evidence["evidence_status"], "confirmed")

        tied_pool = explicit_pool.drop(columns=["depth_chart_position", "is_starting_qb"])
        tied_pool.loc[tied_pool["player_team"] == "AAA", "salary"] = 10000
        with self.assertRaisesRegex(ValueError, "ambiguous for AAA"):
            restrict_showdown_pool_to_starting_qbs(tied_pool)

    def test_showdown_pool_rechecks_stored_salary_inference(self):
        pool = pd.DataFrame(
            [
                {"player_id": "aaa-old", "position": "QB", "player_team": "AAA", "salary": 6000, "is_starting_qb": True, "starting_qb_evidence_tier": "inferred"},
                {"player_id": "aaa-current", "position": "QB", "player_team": "AAA", "salary": 10000},
                {"player_id": "bbb-current", "position": "QB", "player_team": "BBB", "salary": 9800},
                {"player_id": "wr-1", "position": "WR", "player_team": "AAA", "salary": 8000},
                {"player_id": "wr-2", "position": "WR", "player_team": "BBB", "salary": 7800},
            ]
        )

        filtered, _ = restrict_showdown_pool_to_starting_qbs(pool)

        self.assertEqual(
            set(filtered.loc[filtered["position"] == "QB", "player_id"]),
            {"aaa-current", "bbb-current"},
        )

    def test_validated_captain_model_adds_position_probabilities_and_weights(self):
        positions = ["QB", "QB", "RB", "RB", "WR", "WR", "TE", "K", "DST"]
        pool = pd.DataFrame(
            [
                {
                    "player_id": f"player-{index}",
                    "position": position,
                    "player_team": "AAA" if index % 2 == 0 else "BBB",
                    "salary": 10000 - (index * 500),
                    "projection": 20.0 - index,
                    "game_total_line": 44.5,
                    "team_spread_line": -3.5 if index % 2 == 0 else 3.5,
                    "team_implied_total": 24.0 if index % 2 == 0 else 20.5,
                }
                for index, position in enumerate(positions)
            ]
        )

        weighted, evidence = build_showdown_captain_prior(
            pool,
            model_path="docs/showdown_captain_model_2024_2025.json",
            strength=0.35,
        )

        self.assertAlmostEqual(
            sum(evidence["position_probabilities"].values()), 1.0
        )
        self.assertEqual(evidence["prior_strength"], 0.35)
        self.assertEqual(
            evidence["probability_source"],
            "historical_position_mix_fallback",
        )
        self.assertAlmostEqual(
            evidence["position_probabilities"]["WR"],
            17 / 41,
        )
        self.assertTrue(evidence["out_of_distribution_features"])
        self.assertTrue(weighted["captain_position_probability"].between(0, 1).all())
        self.assertGreater(
            weighted["captain_objective_multiplier"].nunique(), 1
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
                    "game_total_line": 50.0,
                    "team_spread_line": -3.0 if team == "AAA" else 3.0,
                    "team_implied_total": 27.0 if team == "AAA" else 23.0,
                    "market_context_point_in_time_safe": True,
                    "pregame_context_run_id": "context-run-1",
                    "pregame_expected_snaps": 50.0,
                    "pregame_expected_routes": 25.0,
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
        ceiling_summary = job.results[0][0]["lineup_ceiling_summary"]
        self.assertEqual(ceiling_summary["label"], "Individual Ceiling Sum")
        self.assertFalse(ceiling_summary["is_joint_quantile"])
        self.assertEqual(
            ceiling_summary["value"],
            sum(row["p90"] for row in job.results[0]),
        )
        self.assertEqual(
            job.params["stack_policy"]["stack_min"],
            config.stack_rules.min_pass_catchers,
        )
        self.assertIn("strategy_runtime", job.params)
        self.assertEqual(
            job.params["strategy_runtime"]["validation"]["status"], "passed"
        )
        player_pool = job.params["strategy_runtime"]["player_pool"]
        self.assertEqual(player_pool["projection_run_id"], "projection-run-1")
        self.assertEqual(player_pool["initial_count"], len(pool))
        self.assertEqual(player_pool["included_count"], len(pool))
        self.assertEqual(player_pool["excluded_count"], 0)
        self.assertTrue(all(row["included"] for row in player_pool["rows"]))
        self.assertIn("lineup validation=passed", job.message)
        self.assertEqual(
            {player.player_id for player in run_gpp.call_args.kwargs["players"]},
            set(pool["player_id"]),
        )
        scored_players = run_gpp.call_args.kwargs["players"]
        self.assertTrue(
            any(player.optimizer_context_adjustment > 0 for player in scored_players)
        )
        self.assertEqual(scored_players[0].game_total, 50.0)
        self.assertEqual(scored_players[0].team_total, 27.0)
        self.assertEqual(
            job.params["strategy_runtime"]["context_scoring"]["library_id"],
            "optimizer_player_context",
        )
        self.assertEqual(
            job.params["strategy_runtime"]["lineup_correlation"]["library_id"],
            "optimizer_lineup_correlation",
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
                    "dk_player_id": f"flex-{index}",
                    "dk_captain_id": f"captain-{index}",
                    "name": f"Player {index}",
                    "position": "QB" if index in {0, 3} else "WR",
                    "player_team": "AAA" if index < 3 else "BBB",
                    "opponent_team": "BBB" if index < 3 else "AAA",
                    "salary": 5000,
                    "projection": 10.0 + index,
                    "p90": 20.0 + index,
                    "showdown_qb_eligible": index in {0, 3},
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
            expected_site_id = (
                row["dk_captain_id"]
                if row["roster_position"] == "CPT"
                else f"flex-{row['player_id'].split('-')[-1]}"
            )
            self.assertEqual(row["dk_player_id"], expected_site_id)
            self.assertEqual(
                row["projection"], row["base_projection"] * multiplier
            )
            self.assertEqual(row["p90"], row["base_p90"] * multiplier)
            self.assertEqual(
                row["objective_score"], row["base_p90"] * multiplier
            )

    def test_showdown_solver_uses_captain_prior_only_for_captain_slot(self):
        service = OptimizerService.__new__(OptimizerService)
        pool = pd.DataFrame(
            [
                {
                    "player_id": f"player-{index}",
                    "name": f"Player {index}",
                    "position": "QB" if index == 0 else "WR",
                    "player_team": "AAA" if index < 4 else "BBB",
                    "opponent_team": "BBB" if index < 4 else "AAA",
                    "salary": 5000,
                    "projection": 10.0,
                    "p90": 30.0 if index == 0 else 20.0,
                    "captain_objective_multiplier": 0.5 if index == 0 else 2.0,
                }
                for index in range(7)
            ]
        )

        lineup = service._solve_lineup(
            pool,
            score_col="p90",
            contest_type="captain",
        )

        captain = next(row for row in lineup or [] if row["roster_position"] == "CPT")
        self.assertEqual(captain["position"], "WR")
        self.assertEqual(captain["objective_score"], 60.0)

    def test_showdown_solver_pairs_qb_captain_with_same_team_receiver(self):
        service = OptimizerService.__new__(OptimizerService)
        pool = pd.DataFrame(
            [
                {
                    "player_id": "aaa-qb",
                    "name": "AAA QB",
                    "position": "QB",
                    "player_team": "AAA",
                    "salary": 5000,
                    "projection": 1000.0,
                    "p90": 1000.0,
                },
                {
                    "player_id": "aaa-wr",
                    "name": "AAA WR",
                    "position": "WR",
                    "player_team": "AAA",
                    "salary": 5000,
                    "projection": 1.0,
                    "p90": 1.0,
                },
                *[
                    {
                        "player_id": f"bbb-{index}",
                        "name": f"BBB Player {index}",
                        "position": "RB" if index < 5 else "WR",
                        "player_team": "BBB",
                        "salary": 5000,
                        "projection": 50.0 - index,
                        "p90": 50.0 - index,
                    }
                    for index in range(6)
                ],
            ]
        )

        lineup = service._solve_lineup(
            pool,
            score_col="p90",
            contest_type="captain",
            stack_params={"require_qb_captain_receiver": True},
        )

        captain = next(row for row in lineup or [] if row["roster_position"] == "CPT")
        flex_player_ids = {
            row["player_id"]
            for row in lineup or []
            if row["roster_position"] == "FLEX"
        }
        self.assertEqual(captain["player_id"], "aaa-qb")
        self.assertIn("aaa-wr", flex_player_ids)

    def test_showdown_validation_rejects_qb_without_starter_evidence(self):
        lineup = [
            {
                "player_id": f"player-{index}",
                "position": "QB" if index == 0 else "WR",
                "roster_position": "CPT" if index == 0 else "FLEX",
                "player_team": "AAA" if index < 3 else "BBB",
                "salary": 5000,
                "showdown_qb_eligible": False,
            }
            for index in range(6)
        ]

        valid, reason = OptimizerService._validate_showdown_lineups(
            [lineup],
            requested_lineups=1,
            max_exposure=1.0,
        )

        self.assertFalse(valid)
        self.assertIn("without starter evidence", reason)

    def test_showdown_validation_enforces_qb_captain_receiver_rule(self):
        lineup = [
            {
                "player_id": f"player-{index}",
                "position": "QB" if index == 0 else "RB",
                "roster_position": "CPT" if index == 0 else "FLEX",
                "player_team": "AAA" if index < 2 else "BBB",
                "salary": 5000,
                "showdown_qb_eligible": index == 0,
            }
            for index in range(6)
        ]

        valid, reason = OptimizerService._validate_showdown_lineups(
            [lineup],
            requested_lineups=1,
            max_exposure=1.0,
            require_qb_captain_receiver=True,
        )

        self.assertFalse(valid)
        self.assertIn("without a same-team WR or TE", reason)

        lineup[1]["position"] = "TE"
        valid, reason = OptimizerService._validate_showdown_lineups(
            [lineup],
            requested_lineups=1,
            max_exposure=1.0,
            require_qb_captain_receiver=True,
        )
        self.assertTrue(valid, reason)

    def test_showdown_run_persists_qb_captain_rule_rejection(self):
        service = OptimizerService.__new__(OptimizerService)
        service._jobs = {}
        service.engine = MagicMock()
        service._resolve_run_lineage = MagicMock(
            return_value=("projection-run-showdown", None, None)
        )
        pool = pd.DataFrame(
            [
                {
                    "player_id": f"player-{index}",
                    "name": f"Player {index}",
                    "position": "QB" if index in {0, 4} else "RB",
                    "player_team": "AAA" if index < 2 else "BBB",
                    "salary": 5000,
                    "projection": 10.0,
                    "p90": 20.0,
                }
                for index in range(6)
            ]
        )
        rejected_lineup = [
            {
                **row,
                "roster_position": "CPT" if index == 0 else "FLEX",
                "salary": row["salary"] * (1.5 if index == 0 else 1.0),
                "showdown_qb_eligible": index in {0, 4},
            }
            for index, row in enumerate(pool.to_dict(orient="records"))
        ]
        service._load_player_pool = MagicMock(return_value=pool)
        service._solve_lineup = MagicMock(return_value=rejected_lineup)
        service._persist_optimizer_run = MagicMock(return_value=True)

        job = service.run_job(
            season=2026,
            week=1,
            slate="WEDNESDAY_NIGHT",
            strategy="gpp",
            params={"num_lineups": 1},
            contest_format="showdown",
            objective="cash",
        )

        validation = job.params["strategy_runtime"]["validation"]
        self.assertEqual(job.status, "failed")
        self.assertIsNone(job.results)
        self.assertEqual(validation["status"], "failed")
        self.assertIn("without a same-team WR or TE", validation["rejection_reason"])
        self.assertEqual(
            validation["optimizer_rule_ids"],
            [SHOWDOWN_QB_CAPTAIN_RECEIVER_RULE_ID],
        )

    def test_showdown_run_persists_canonical_strategy_and_slot_validation(self):
        service = OptimizerService.__new__(OptimizerService)
        service._jobs = {}
        service.engine = MagicMock()
        service._resolve_run_lineage = MagicMock(
            return_value=("projection-run-showdown", "rule-run-showdown", None)
        )
        eligible_pool = pd.DataFrame(
            [
                {
                    "player_id": f"player-{index}",
                    "name": f"Player {index}",
                    "position": "QB" if index in {0, 3} else "WR",
                    "player_team": "AAA" if index < 3 else "BBB",
                    "opponent_team": "BBB" if index < 3 else "AAA",
                    "salary": 5000,
                    "projection": 10.0 + index,
                    "p90": 20.0 + index,
                    "showdown_qb_eligible": index in {0, 3},
                }
                for index in range(6)
            ]
        )
        eligible_pool.loc[0, "salary"] = 200
        lineup = [
            {
                **row,
                "roster_position": "CPT" if index == 2 else "FLEX",
                "salary": row["salary"] * (1.5 if index == 2 else 1.0),
                "projection": row["p90"] * (1.5 if index == 2 else 1.0),
                "p90": row["p90"] * (1.5 if index == 2 else 1.0),
            }
            for index, row in enumerate(eligible_pool.to_dict(orient="records"))
        ]
        pool = pd.concat(
            [
                eligible_pool,
                pd.DataFrame(
                    [
                        {
                            "player_id": "final-out-player",
                            "name": "Final Out Player",
                            "position": "WR",
                            "player_team": "AAA",
                            "opponent_team": "BBB",
                            "salary": 2400,
                            "projection": 0.0,
                            "p90": 0.0,
                            "pregame_availability_probability": 0.0,
                            "pregame_context_run_id": "context-final",
                            "pregame_context_source": "official_final_report",
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
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
            params={"num_lineups": 1, "lock_player_ids": ["player-2"]},
            contest_format="showdown",
            objective="cash",
        )

        self.assertEqual(job.status, "completed")
        solve_pool = service._solve_lineup.call_args.args[0]
        self.assertIn(200, solve_pool["salary"].tolist())
        self.assertNotIn("final-out-player", set(solve_pool["player_id"]))
        self.assertEqual(
            job.strategy, SHOWDOWN_CASH_QB_CAPTAIN_STACK_STRATEGY_ID
        )
        self.assertEqual(
            job.params["optimizer_rules"][0]["rule_id"],
            SHOWDOWN_QB_CAPTAIN_RECEIVER_RULE_ID,
        )
        self.assertTrue(
            service._solve_lineup.call_args.kwargs["stack_params"][
                "require_qb_captain_receiver"
            ]
        )
        self.assertEqual(
            service._solve_lineup.call_args.kwargs["locked_player_ids"],
            {"player-2"},
        )
        self.assertEqual(job.params["objective_config"]["captain_slots"], 1)
        self.assertEqual(
            job.params["strategy_runtime"]["validation"]["flex_slots"], 5
        )
        self.assertEqual(job.results[0][0]["roster_position"], "CPT")
        self.assertEqual(
            [row["lineup_slot_index"] for row in job.results[0]],
            list(range(6)),
        )
        self.assertEqual(
            job.results[0][0]["lineup_optimizer_rules"][0]["rule_id"],
            SHOWDOWN_QB_CAPTAIN_RECEIVER_RULE_ID,
        )
        self.assertEqual(
            job.params["strategy_runtime"]["validation"][
                "optimizer_rule_ids"
            ],
            [SHOWDOWN_QB_CAPTAIN_RECEIVER_RULE_ID],
        )
        self.assertIn("showdown lineup validation=passed", job.message)
        self.assertTrue(job.lineage_persisted)
        audit_by_id = {
            row["player_id"]: row
            for row in job.params["strategy_runtime"]["player_pool"]["rows"]
        }
        self.assertFalse(audit_by_id["final-out-player"]["included"])
        self.assertEqual(
            audit_by_id["final-out-player"]["exclusion_reasons"],
            ["pregame_availability_zero"],
        )
        self.assertEqual(
            audit_by_id["final-out-player"]["exclusion_details"][0]["category"],
            "eligibility",
        )
        self.assertEqual(
            audit_by_id["final-out-player"]["pregame_context_run_id"],
            "context-final",
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
            "strategy": SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID,
            "contest_format": "showdown",
            "objective": "gpp",
            "constraint_config_json": {
                "num_lineups": 1,
                "strategy_config": {
                    "strategy_id": SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID
                },
                "optimizer_rules": showdown_optimizer_rules(
                    SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID
                ),
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
                "player_json": {
                    "player_id": f"player-{index + 2}",
                    "lineup_optimizer_rules": showdown_optimizer_rules(
                        SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID
                    ),
                },
            }
            for index in range(6)
        ]
        connection.execute.side_effect = [run_result, lineup_result, player_result]

        job = service.get_job("optimizer-run-2")

        self.assertIsNotNone(job)
        self.assertEqual(job.contest_format, "showdown")
        self.assertEqual(job.objective, "gpp")
        self.assertEqual(
            job.strategy, SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID
        )
        self.assertEqual(
            job.params["optimizer_rules"][0]["rule_id"],
            SHOWDOWN_QB_CAPTAIN_RECEIVER_RULE_ID,
        )
        self.assertEqual(
            job.results[0][0]["lineup_optimizer_rules"][0]["rule_id"],
            SHOWDOWN_QB_CAPTAIN_RECEIVER_RULE_ID,
        )
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
