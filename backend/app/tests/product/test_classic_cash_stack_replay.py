import unittest
from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO
from zoneinfo import ZoneInfo

import pandas as pd

from backend.app.api.product_routes import replay_classic_cash_stack_policies
from backend.app.product_schemas import ClassicCashStackReplayRequest
from backend.app.product_services.optimizer import (
    CLASSIC_CASH_STACK_QB_PAIR_BRINGBACK_ID,
    CLASSIC_CASH_STACK_QB_PAIR_ID,
    CLASSIC_CASH_STACK_UNCONSTRAINED_ID,
    OptimizerService,
)
from backend.app.product_services.contest_evidence import (
    build_contest_field_evidence,
    classify_contest_type,
    public_field_evidence,
    score_lineup_against_contest,
)
from backend.app.product_services.replay import (
    CLASSIC_CASH_STACK_REPLAY_ID,
    DEFAULT_CASH_STACK_POLICY_IDS,
    ClassicCashStackReplayService,
    assess_cutoff_safety,
    assess_salary_snapshot,
    canonical_hash,
    evidence_cutoff,
    parse_slate_lock,
    score_lineup_outcomes,
    summarize_policy_replays,
)


def replay_pool() -> pd.DataFrame:
    rows = [
        ("qb", "Quarterback", "QB", "AAA", "BBB", 22.0),
        ("rb1", "Runner One", "RB", "CCC", "DDD", 19.0),
        ("rb2", "Runner Two", "RB", "DDD", "CCC", 18.0),
        ("rb3", "Runner Three", "RB", "EEE", "FFF", 17.0),
        ("a_wr1", "Alpha One", "WR", "AAA", "BBB", 16.0),
        ("a_wr2", "Alpha Two", "WR", "AAA", "BBB", 15.0),
        ("b_wr", "Bring Back", "WR", "BBB", "AAA", 14.0),
        ("c_wr", "Charlie Wideout", "WR", "CCC", "DDD", 13.0),
        ("d_wr", "Delta Wideout", "WR", "DDD", "CCC", 12.0),
        ("te1", "Tight End One", "TE", "EEE", "FFF", 11.0),
        ("te2", "Tight End Two", "TE", "FFF", "EEE", 10.0),
        ("dst", "Defense", "DST", "GGG", "HHH", 9.0),
    ]
    pool = pd.DataFrame(
        rows,
        columns=[
            "player_id",
            "name",
            "position",
            "player_team",
            "opponent_team",
            "projection",
        ],
    )
    pool["player_name"] = pool["name"]
    pool["dk_player_id"] = pool["player_id"]
    pool["salary"] = 5000
    pool["predicted_p50"] = pool["projection"]
    pool["predicted_p10"] = pool["projection"] * 0.65
    pool["predicted_p90"] = pool["projection"] * 1.35
    pool["p90"] = pool["predicted_p90"]
    pool["game_id"] = "AAA@BBB 11/16/2025 01:00PM ET"
    pool["projection_run_id"] = "projection-1"
    pool["calibration_role"] = "test"
    pool["calibration_sample_size"] = 100
    pool["calibration_method"] = "test"
    pool["calibration_position"] = pool["position"]
    pool["name_norm"] = pool["name"].str.lower()
    pool["team_norm"] = pool["player_team"]
    return pool


def replay_service() -> ClassicCashStackReplayService:
    service = ClassicCashStackReplayService.__new__(ClassicCashStackReplayService)
    service.optimizer = OptimizerService.__new__(OptimizerService)
    return service


class ClassicCashStackReplayTests(unittest.TestCase):
    def test_contest_type_requires_explicit_or_unambiguous_evidence(self):
        self.assertEqual(
            classify_contest_type("NFL $10 Double Up")["contest_type"],
            "cash",
        )
        self.assertEqual(
            classify_contest_type("NFL Millionaire Maker")["contest_type"],
            "gpp",
        )
        self.assertEqual(
            classify_contest_type("NFL Contest")["contest_type"],
            "unknown",
        )

    def test_verified_cash_line_and_roi_preserve_tie_uncertainty(self):
        contest = build_contest_field_evidence(
            {
                "contest_id": "double-up",
                "contest_name": "NFL $10 Double Up",
                "contest_format": "classic",
                "contest_type": "cash",
                "entry_fee": 10,
                "field_size": 4,
            },
            [
                {"entry_id": "one", "rank": 1, "entry_points": 150},
                {"entry_id": "two", "rank": 2, "entry_points": 120},
                {"entry_id": "three", "rank": 3, "entry_points": 100},
                {"entry_id": "four", "rank": 4, "entry_points": 80},
            ],
            [{"min_rank": 1, "max_rank": 2, "payout": 18}],
        )

        winner = score_lineup_against_contest(130.0, contest)
        boundary = score_lineup_against_contest(120.0, contest)

        self.assertTrue(contest["cash_line_verified"])
        self.assertEqual(contest["cash_line_points"], 120.0)
        self.assertEqual(winner["cash_status"], "cashed")
        self.assertEqual(winner["roi_exact"], 0.8)
        self.assertEqual(boundary["cash_status"], "tie_boundary")
        self.assertIsNone(boundary["cash_hit"])
        self.assertIsNone(boundary["roi_exact"])
        self.assertNotIn("_entry_scores", public_field_evidence({"contests": [contest]})["contests"][0])

    def test_partial_normalized_field_is_not_performance_evidence(self):
        contest = build_contest_field_evidence(
            {
                "contest_id": "partial",
                "contest_name": "NFL $10 Double Up",
                "contest_format": "classic",
                "contest_type": "cash",
                "field_size": 3,
            },
            [{"entry_id": "one", "rank": 1, "entry_points": 150}],
            [{"min_rank": 1, "max_rank": 1, "payout": 18}],
        )

        self.assertFalse(contest["field_proxy_eligible"])
        self.assertFalse(score_lineup_against_contest(160, contest)["eligible"])

    def test_canonical_hash_is_order_independent_for_mapping_keys(self):
        self.assertEqual(canonical_hash({"a": 1, "b": 2}), canonical_hash({"b": 2, "a": 1}))

    def test_evidence_cutoff_uses_only_prior_periods(self):
        self.assertEqual(evidence_cutoff(2025, 1), {"season": 2024, "week": None})
        self.assertEqual(evidence_cutoff(2025, 11), {"season": 2025, "week": 10})

    def test_cutoff_assessment_accepts_logical_prior_contract(self):
        lock = parse_slate_lock(["AAA@BBB 11/16/2025 01:00PM ET"])
        assessment = assess_cutoff_safety(
            {
                "data_cutoff_at": None,
                "source_versions_json": {"leakage_policy": "prior_games_only"},
            },
            season=2025,
            week=11,
            slate_lock_at=lock,
        )

        self.assertTrue(assessment["safe"])
        self.assertEqual(assessment["cutoff_basis"], "logical_prior_period_contract")
        self.assertEqual(assessment["logical_evidence_through"]["week"], 10)

    def test_cutoff_assessment_rejects_post_lock_projection(self):
        lock = datetime(2025, 11, 16, 13, 0, tzinfo=ZoneInfo("America/New_York"))
        assessment = assess_cutoff_safety(
            {
                "data_cutoff_at": datetime(
                    2025, 11, 16, 14, 0, tzinfo=ZoneInfo("America/New_York")
                ),
                "source_versions_json": {
                    "target_season": 2025,
                    "target_week": 11,
                    "leakage_policy": "labeled rows strictly before target season/week",
                },
            },
            season=2025,
            week=11,
            slate_lock_at=lock,
        )

        self.assertFalse(assessment["safe"])
        self.assertIn("after slate lock", assessment["reasons"][0])

    def test_timestamped_projection_requires_a_known_slate_lock(self):
        assessment = assess_cutoff_safety(
            {
                "data_cutoff_at": datetime(2025, 11, 16, 12, 0, tzinfo=ZoneInfo("UTC")),
                "source_versions_json": {"leakage_policy": "prior_games_only"},
            },
            season=2025,
            week=11,
            slate_lock_at=None,
        )

        self.assertFalse(assessment["safe"])
        self.assertEqual(assessment["cutoff_basis"], "unproven")
        self.assertIn("slate lock is unavailable", assessment["reasons"][0])

    def test_post_lock_salary_ingestion_is_not_treated_as_point_in_time_evidence(self):
        pool = pd.DataFrame(
            {
                "salary_created_at": [
                    datetime(2026, 2, 25, 12, 0, tzinfo=ZoneInfo("America/New_York"))
                ]
            }
        )
        lock = datetime(2025, 11, 16, 13, 0, tzinfo=ZoneInfo("America/New_York"))

        assessment = assess_salary_snapshot(pool, lock)

        self.assertFalse(assessment["proven_prelock"])
        self.assertEqual(assessment["status"], "post_lock_ingestion_or_unknown_lock")

    def test_outcome_scoring_never_fabricates_missing_dst_actual(self):
        lineup = [
            {"player_id": "qb", "name": "QB", "position": "QB", "salary": 5000},
            {"player_id": "dst", "name": "DST", "position": "DST", "salary": 3000},
        ]
        outcome = score_lineup_outcomes(lineup, {"qb": 20.0})

        self.assertFalse(outcome["complete"])
        self.assertIsNone(outcome["actual_points"])
        self.assertEqual(outcome["observed_actual_points"], 20.0)
        self.assertEqual(outcome["missing_actual_positions"], ["DST"])

    def test_same_inputs_and_configuration_produce_same_replay_artifact(self):
        pool = replay_pool()
        actuals = {row.player_id: float(index + 1) for index, row in enumerate(pool.itertuples())}
        actuals.pop("dst")
        manifest = {
            "projection_run_id": "projection-1",
            "model_run_id": "model-1",
            "projection_rows": len(pool),
            "data_cutoff_at": None,
            "source_versions_json": {"leakage_policy": "prior_games_only"},
        }
        cutoff = assess_cutoff_safety(
            manifest,
            season=2025,
            week=11,
            slate_lock_at=parse_slate_lock(pool["game_id"]),
        )
        service = replay_service()

        output = StringIO()
        with redirect_stdout(output):
            first = service.replay_from_frames(
                season=2025,
                week=11,
                slate="SUNDAY_MAIN",
                pool=pool,
                actual_points=actuals,
                projection_manifest=manifest,
                cutoff_assessment=cutoff,
                field_proxy={"available": True, "median_points": 120.0},
            )
            second = service.replay_from_frames(
                season=2025,
                week=11,
                slate="SUNDAY_MAIN",
                pool=pool,
                actual_points=actuals,
                projection_manifest=manifest,
                cutoff_assessment=cutoff,
                field_proxy={"available": True, "median_points": 120.0},
            )

        self.assertEqual(output.getvalue(), "")
        self.assertEqual(first["replay_id"], second["replay_id"])
        self.assertEqual(first["artifact_hash"], second["artifact_hash"])
        self.assertEqual(first["evidence_status"], "diagnostic_incomplete_inputs_or_outcomes")
        self.assertFalse(first["performance_claim_eligible"])
        by_policy = {row["policy_id"]: row for row in first["policies"]}
        self.assertEqual(set(by_policy), set(DEFAULT_CASH_STACK_POLICY_IDS))
        self.assertIn(
            "a_wr1",
            {row["player_id"] for row in by_policy[CLASSIC_CASH_STACK_QB_PAIR_ID]["lineup"]},
        )
        self.assertIn(
            "b_wr",
            {
                row["player_id"]
                for row in by_policy[CLASSIC_CASH_STACK_QB_PAIR_BRINGBACK_ID]["lineup"]
            },
        )
        self.assertEqual(
            by_policy[CLASSIC_CASH_STACK_UNCONSTRAINED_ID]["policy"]["stack_min"],
            0,
        )

    def test_complete_normalized_cash_field_enables_cash_metrics(self):
        pool = replay_pool()
        pool["salary_created_at"] = datetime(
            2025, 11, 16, 10, 0, tzinfo=ZoneInfo("America/New_York")
        )
        actuals = {player_id: 20.0 for player_id in pool["player_id"]}
        manifest = {
            "projection_run_id": "projection-1",
            "model_run_id": "model-1",
            "projection_rows": len(pool),
            "data_cutoff_at": None,
            "source_versions_json": {"leakage_policy": "prior_games_only"},
        }
        cutoff = assess_cutoff_safety(
            manifest,
            season=2025,
            week=11,
            slate_lock_at=parse_slate_lock(pool["game_id"]),
        )
        contest = build_contest_field_evidence(
            {
                "contest_id": "double-up",
                "contest_name": "NFL $10 Double Up",
                "contest_format": "classic",
                "contest_type": "cash",
                "entry_fee": 10,
                "field_size": 4,
            },
            [
                {"entry_id": "one", "rank": 1, "entry_points": 200},
                {"entry_id": "two", "rank": 2, "entry_points": 170},
                {"entry_id": "three", "rank": 3, "entry_points": 150},
                {"entry_id": "four", "rank": 4, "entry_points": 120},
            ],
            [{"min_rank": 1, "max_rank": 2, "payout": 18}],
        )
        field_evidence = {
            "available": True,
            "normalized_contests": 1,
            "eligible_field_contests": 1,
            "verified_cash_contests": 1,
            "evidence_status": "linked_normalized_contest_field",
            "contests": [contest],
        }
        service = replay_service()

        report = service.replay_from_frames(
            season=2025,
            week=11,
            slate="SUNDAY_MAIN",
            pool=pool,
            actual_points=actuals,
            projection_manifest=manifest,
            cutoff_assessment=cutoff,
            field_proxy=field_evidence,
            policy_ids=(CLASSIC_CASH_STACK_UNCONSTRAINED_ID,),
        )
        aggregate = summarize_policy_replays(
            [report],
            (CLASSIC_CASH_STACK_UNCONSTRAINED_ID,),
        )[CLASSIC_CASH_STACK_UNCONSTRAINED_ID]

        self.assertTrue(report["performance_claim_eligible"])
        self.assertTrue(report["cash_performance_claim_eligible"])
        self.assertEqual(report["evidence_status"], "promotion_evidence_complete_cash_line")
        self.assertEqual(aggregate["cash_rate"], 1.0)
        self.assertEqual(aggregate["double_up_rate"], 1.0)
        self.assertEqual(aggregate["roi"], 0.8)

    def test_gpp_payout_does_not_enter_cash_roi_aggregate(self):
        policy_id = CLASSIC_CASH_STACK_UNCONSTRAINED_ID
        summary = summarize_policy_replays(
            [
                {
                    "policies": [
                        {
                            "policy_id": policy_id,
                            "status": "completed",
                            "outcome": {
                                "observed_actual_points": 150.0,
                                "actual_points": 150.0,
                            },
                            "performance_claim_eligible": True,
                            "cash_performance_claim_eligible": False,
                            "contest_results": [
                                {
                                    "eligible": True,
                                    "contest_type": "gpp",
                                    "margin_vs_median": 10.0,
                                    "cash_hit": None,
                                    "double_up_hit": None,
                                    "entry_fee": 10.0,
                                    "payout_exact": 20.0,
                                    "roi_exact": 1.0,
                                }
                            ],
                        }
                    ]
                }
            ],
            (policy_id,),
        )[policy_id]

        self.assertEqual(summary["exact_roi_contests"], 0)
        self.assertIsNone(summary["roi"])

    def test_policy_summary_reports_field_downside_and_tie_aware_win_rate(self):
        policy_id = CLASSIC_CASH_STACK_UNCONSTRAINED_ID
        margins_and_cash = [
            (-40.0, False, "missed"),
            (-20.0, None, "tie_boundary"),
            (0.0, True, "cashed"),
            (10.0, None, "unavailable"),
        ]
        steps = []
        for margin, cash_hit, cash_status in margins_and_cash:
            steps.append(
                {
                    "policies": [
                        {
                            "policy_id": policy_id,
                            "status": "completed",
                            "outcome": {
                                "observed_actual_points": 120.0 + margin,
                                "actual_points": 120.0 + margin,
                            },
                            "performance_claim_eligible": False,
                            "cash_performance_claim_eligible": False,
                            "contest_results": [
                                {
                                    "eligible": True,
                                    "contest_type": "cash",
                                    "margin_vs_median": margin,
                                    "cash_hit": cash_hit,
                                    "cash_status": cash_status,
                                    "double_up_hit": cash_hit,
                                    "entry_fee": None,
                                    "payout_exact": None,
                                    "roi_exact": None,
                                }
                            ],
                        }
                    ]
                }
            )

        summary = summarize_policy_replays(steps, (policy_id,))[policy_id]
        downside = summary["field_margin_downside"]

        self.assertEqual(downside["sample_size"], 4)
        self.assertEqual(downside["worst_margin"], -40.0)
        self.assertEqual(downside["p10_margin"], -34.0)
        self.assertEqual(downside["p25_margin"], -25.0)
        self.assertEqual(downside["median_margin"], -10.0)
        self.assertEqual(downside["lower_quartile_mean"], -40.0)
        self.assertEqual(downside["below_field_median_rate"], 0.5)
        self.assertEqual(summary["cash_hits"], 1)
        self.assertEqual(summary["cash_misses"], 1)
        self.assertEqual(summary["cash_tie_boundaries"], 1)
        self.assertEqual(summary["win_rate"], 0.5)
        self.assertEqual(summary["double_up_rate"], 0.5)
        self.assertEqual(summary["p10_margin_delta_vs_unconstrained"], 0.0)

    def test_api_route_uses_default_policy_set(self):
        class FakeReplayService:
            def run(self, **kwargs):
                self.kwargs = kwargs
                return {
                    "contract_id": CLASSIC_CASH_STACK_REPLAY_ID,
                    "season": 2025,
                    "requested_week": 11,
                    "slate": "SUNDAY_MAIN",
                    "policy_ids": list(kwargs["policy_ids"]),
                    "status": "completed",
                    "weeks_requested": 1,
                    "weeks_completed": 1,
                    "steps": [],
                    "failures": [],
                    "aggregate": {},
                    "performance_claim_eligible": False,
                    "evidence_status": "diagnostic_only",
                    "artifact_hash": "hash",
                }

        service = FakeReplayService()
        response = replay_classic_cash_stack_policies(
            ClassicCashStackReplayRequest(season=2025, week=11),
            service=service,
        )

        self.assertEqual(tuple(response.policy_ids), DEFAULT_CASH_STACK_POLICY_IDS)
        self.assertIsNone(service.kwargs["projection_run_id"])

    def test_explicit_week_replay_propagates_a_contract_failure(self):
        service = ClassicCashStackReplayService.__new__(ClassicCashStackReplayService)

        def fail_slate(**_kwargs):
            raise ValueError("unsafe projection")

        service.run_slate = fail_slate

        with self.assertRaisesRegex(ValueError, "unsafe projection"):
            service.run(season=2025, week=11, slate="SUNDAY_MAIN")


if __name__ == "__main__":
    unittest.main()
