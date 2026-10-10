from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock, patch

from backend.app.product_schemas import SlateReadinessResponse
from backend.app.product_services.readiness import (
    SlateReadinessMetrics,
    SlateReadinessService,
    _eligible_salary_rows,
    evaluate_slate_readiness,
)


def _complete_metrics() -> SlateReadinessMetrics:
    return SlateReadinessMetrics(
        season=2025,
        week=11,
        slate="SUNDAY_MAIN",
        salary_table_available=True,
        eligible_salary_rows=50,
        position_counts={"QB": 5, "RB": 15, "WR": 20, "TE": 5, "DST": 5},
        roster_position_counts={
            "QB": 5,
            "RB": 15,
            "WR": 20,
            "TE": 5,
            "DST": 5,
            "CPT": 50,
            "FLEX": 50,
        },
        team_count=10,
        resolved_identity_rows=50,
        complete_game_rows=50,
        valid_salary_rows=50,
        salary_timestamp_rows=50,
        salary_latest_created_at=datetime(2025, 11, 16, 15, 0, tzinfo=timezone.utc),
        slate_lock_at=datetime(2025, 11, 16, 18, 0, tzinfo=timezone.utc),
        injury_rows=12,
        injury_identity_rows=12,
        projection_run_count=1,
        projection_run_id="projection-1",
        projected_salary_rows=50,
        positive_projection_rows=50,
        positive_projection_positions={"QB": 5, "RB": 15, "WR": 20, "TE": 5, "DST": 5},
        projection_cutoff_rows=50,
        projection_data_cutoff_at=datetime(2025, 11, 16, 17, 0, tzinfo=timezone.utc),
        ownership_rows=50,
        actual_salary_rows=50,
        actual_position_counts={"QB": 5, "RB": 15, "WR": 20, "TE": 5, "DST": 5},
        normalized_contest_rows=1,
        legacy_contest_entry_rows=1000,
    )


class SlateReadinessTests(unittest.TestCase):
    def test_live_showdown_preflight_blocks_on_generation_evidence_despite_coverage(self):
        from backend.app.tests.product.test_showdown_upstream_data import canonical_rows, assess
        rows = canonical_rows()
        rows[1].update(canonical_role=None, role_source=None)
        metrics = _complete_metrics()
        metrics.injury_rows = metrics.injury_identity_rows = 0
        metrics.showdown_data_readiness = assess(rows)
        report = evaluate_slate_readiness(metrics)
        self.assertEqual(report['gates']['showdown_gpp']['status'], 'fail')
        self.assertEqual(report['gates']['showdown_cash']['status'], 'fail')
        self.assertEqual(report['gates']['classic_gpp']['status'], 'warn')
        self.assertIn('showdown_player_status', report['gates']['showdown_gpp']['blocking_checks'])
        check = next(c for c in report['checks'] if c['check_id'] == 'showdown_player_status')
        self.assertIn('Player 1', check['message'])
        self.assertIn('player_role_missing', check['message'])
        self.assertEqual(SlateReadinessResponse(**report).showdown_data_readiness['status'], 'NOT_READY')

    def test_generation_ready_sources_do_not_turn_optional_injury_warning_into_blocker(self):
        from backend.app.tests.product.test_showdown_upstream_data import canonical_rows, assess
        metrics = _complete_metrics()
        metrics.injury_rows = metrics.injury_identity_rows = 0
        metrics.showdown_data_readiness = assess(canonical_rows())
        report = evaluate_slate_readiness(metrics)
        self.assertEqual(report['gates']['showdown_gpp']['status'], 'warn')
        self.assertEqual(report['gates']['showdown_gpp']['blocking_checks'], [])
        self.assertEqual(report['showdown_data_readiness']['status'], 'READY')

    def test_live_showdown_read_error_fails_closed(self):
        service = SlateReadinessService.__new__(SlateReadinessService)
        service.engine = MagicMock()
        service.connection_string = 'sqlite://'
        service.collect_metrics = MagicMock(return_value=_complete_metrics())
        with patch('backend.app.product_services.showdown_data_readiness.is_live_slate', return_value=True), \
             patch('backend.app.product_services.showdown_data_readiness.assess_current_inputs', side_effect=RuntimeError('source unavailable')):
            report = service.report(season=2026, week=5, slate='THURSDAY_NIGHT')
        self.assertEqual(report['showdown_data_readiness']['status'], 'ERROR')
        self.assertIn('showdown_generation_assessment', report['gates']['showdown_gpp']['blocking_checks'])

    def test_live_preflight_reads_generation_pool_without_refresh_or_solver(self):
        from backend.app.product_services.showdown_data_readiness import assess_current_inputs
        from backend.app.tests.product.test_showdown_upstream_data import canonical_rows
        from backend.app.tests.product.test_showdown_data_readiness import NOW, PROJECTION, service_fixture
        service = service_fixture(canonical_rows())
        with patch('backend.app.product_services.showdown_data_readiness.datetime') as clock, \
             patch('backend.app.product_services.showdown_data_readiness.refresh_live_sources') as refresh:
            clock.now.return_value = NOW
            readiness = assess_current_inputs(service, season=NOW.year, week=5,
                slate='THURSDAY_NIGHT', projection_run_id=PROJECTION)
        self.assertEqual(readiness['status'], 'READY', readiness['reason_codes'])
        self.assertEqual(readiness['evaluated_at'], NOW.isoformat())
        self.assertEqual(service._load_player_pool.call_args.kwargs['evidence_cutoff_at'], NOW)
        refresh.assert_not_called()
        service._solve_lineup.assert_not_called()
        service._persist_optimizer_run.assert_not_called()

    def test_historical_preflight_preserves_the_original_contract(self):
        service = SlateReadinessService.__new__(SlateReadinessService)
        service.engine = MagicMock()
        service.connection_string = 'sqlite://'
        service.collect_metrics = MagicMock(return_value=_complete_metrics())
        with patch('backend.app.product_services.showdown_data_readiness.is_live_slate', return_value=False), \
             patch('backend.app.product_services.showdown_data_readiness.assess_current_inputs') as assess:
            report = service.report(season=2025, week=11, slate='SUNDAY_MAIN')
        assess.assert_not_called()
        self.assertIsNone(report['showdown_data_readiness'])
        self.assertEqual(report['gates']['showdown_gpp']['status'], 'pass')

    def test_showdown_uses_flex_rows_kickers_and_active_roster_status(self) -> None:
        salary_rows = [
            {
                "player_id": f"{name}-{role}",
                "position": position,
                "roster_position": role,
                "roster_status": status,
            }
            for name, position, status in (
                ("receiver", "WR", "ACT"),
                ("kicker", "K", "ACT"),
                ("practice-squad", "WR", "DEV"),
                ("missing", "TE", None),
                ("defense", "DST", None),
                ("salary-out", "RB", "ACT"),
            )
            for role in ("CPT", "FLEX")
        ]
        for row in salary_rows:
            row["player_status"] = "OUT" if row["player_id"].startswith("salary-out") else ""
            row["roster_evidence_available"] = True

        eligible, excluded = _eligible_salary_rows(
            salary_rows,
            {"CPT": 6, "FLEX": 6},
        )

        self.assertEqual(
            {row["player_id"] for row in eligible},
            {"receiver-FLEX", "kicker-FLEX", "defense-FLEX"},
        )
        self.assertEqual(excluded, {"DEV": 1, "MISSING": 1, "SALARY_OUT": 1})

        metrics = _complete_metrics()
        metrics.excluded_roster_status_counts = excluded
        report = evaluate_slate_readiness(metrics)
        salary_pool = next(
            check for check in report["checks"] if check["check_id"] == "salary_pool"
        )
        self.assertEqual(salary_pool["details"]["excluded_salary_statuses"], {"OUT": 1})
        self.assertEqual(
            salary_pool["details"]["excluded_roster_statuses"],
            {"DEV": 1, "MISSING": 1},
        )

    def test_partial_roster_evidence_does_not_exclude_uncovered_team(self) -> None:
        eligible, excluded = _eligible_salary_rows(
            [
                {
                    "player_id": "lar-qb",
                    "position": "QB",
                    "roster_position": "FLEX",
                    "player_status": "",
                    "roster_status": None,
                    "roster_evidence_available": False,
                },
                {
                    "player_id": "nyg-qb",
                    "position": "QB",
                    "roster_position": "FLEX",
                    "player_status": "",
                    "roster_status": "ACT",
                    "roster_evidence_available": True,
                },
            ],
            {"CPT": 2, "FLEX": 2},
        )

        self.assertEqual({row["player_id"] for row in eligible}, {"lar-qb", "nyg-qb"})
        self.assertEqual(excluded, {})

    def test_complete_slate_passes_every_gate(self) -> None:
        report = evaluate_slate_readiness(_complete_metrics())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["score"], 100)
        self.assertTrue(all(gate["status"] == "pass" for gate in report["gates"].values()))
        self.assertEqual(SlateReadinessResponse(**report).contract_id, "slate_readiness_v1")

    def test_missing_salary_pool_blocks_prediction_and_optimizers(self) -> None:
        report = evaluate_slate_readiness(
            SlateReadinessMetrics(season=2025, week=11, slate="SUNDAY_MAIN")
        )

        self.assertEqual(report["gates"]["prediction"]["status"], "fail")
        self.assertIn("salary_pool", report["gates"]["prediction"]["blocking_checks"])
        self.assertEqual(report["gates"]["classic_gpp"]["status"], "fail")
        self.assertEqual(report["gates"]["showdown_cash"]["status"], "fail")

    def test_dst_gap_blocks_classic_without_blocking_showdown(self) -> None:
        metrics = _complete_metrics()
        metrics.resolved_identity_rows = 40
        metrics.quarantined_identity_rows = 10
        metrics.quarantine_reason_counts = {"no_match": 8, "ambiguous": 2}
        metrics.injury_rows = 0
        metrics.injury_identity_rows = 0
        metrics.projected_salary_rows = 35
        metrics.positive_projection_rows = 30
        metrics.positive_projection_positions = {"QB": 5, "RB": 9, "WR": 12, "TE": 4}
        metrics.projection_data_cutoff_at = None
        metrics.salary_latest_created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        metrics.actual_salary_rows = 45
        metrics.actual_position_counts = {"QB": 5, "RB": 14, "WR": 20, "TE": 6}
        metrics.normalized_contest_rows = 0
        metrics.legacy_contest_entry_rows = 1000

        report = evaluate_slate_readiness(metrics)

        self.assertEqual(report["gates"]["prediction"]["status"], "warn")
        self.assertEqual(report["gates"]["classic_cash"]["status"], "fail")
        self.assertEqual(report["gates"]["classic_gpp"]["blocking_checks"], ["dst_projection"])
        self.assertEqual(report["gates"]["classic_gpp"]["summary"]["fail"], 1)
        self.assertEqual(report["gates"]["showdown_cash"]["status"], "warn")
        self.assertEqual(report["gates"]["replay"]["status"], "fail")
        self.assertIn("contest_result_linkage", report["gates"]["replay"]["blocking_checks"])

    def test_untracked_unresolved_identity_blocks_every_input_gate(self) -> None:
        metrics = _complete_metrics()
        metrics.resolved_identity_rows = 49

        report = evaluate_slate_readiness(metrics)
        identity = next(
            check for check in report["checks"] if check["check_id"] == "player_identity_coverage"
        )

        self.assertEqual(identity["status"], "fail")
        self.assertEqual(identity["details"]["untracked"], 1)
        self.assertIn("not quarantined", identity["message"])
        self.assertTrue(all(gate["status"] == "fail" for gate in report["gates"].values()))

    def test_identity_report_distinguishes_accepted_quarantine_reasons(self) -> None:
        metrics = _complete_metrics()
        metrics.resolved_identity_rows = 47
        metrics.quarantined_identity_rows = 3
        metrics.quarantine_reason_counts = {"no_match": 2, "ambiguous": 1}

        report = evaluate_slate_readiness(metrics)
        identity = next(
            check for check in report["checks"] if check["check_id"] == "player_identity_coverage"
        )

        self.assertEqual(identity["status"], "warn")
        self.assertEqual(identity["details"]["resolved"], 47)
        self.assertEqual(identity["details"]["ambiguous"], 1)
        self.assertEqual(identity["details"]["no_match"], 2)
        self.assertEqual(identity["details"]["accepted_quarantine"], 3)
        self.assertEqual(identity["details"]["unaccepted_quarantine"], 0)

    def test_unaccepted_quarantine_reason_blocks_every_input_gate(self) -> None:
        metrics = _complete_metrics()
        metrics.resolved_identity_rows = 49
        metrics.quarantined_identity_rows = 1
        metrics.quarantine_reason_counts = {"missing_name": 1}

        report = evaluate_slate_readiness(metrics)
        identity = next(
            check for check in report["checks"] if check["check_id"] == "player_identity_coverage"
        )

        self.assertEqual(identity["status"], "fail")
        self.assertEqual(identity["details"]["unaccepted_quarantine"], 1)
        self.assertIn("do not have an accepted reason", identity["message"])
        self.assertTrue(all(gate["status"] == "fail" for gate in report["gates"].values()))

    def test_report_id_is_stable_for_identical_metrics(self) -> None:
        metrics = _complete_metrics()

        first = evaluate_slate_readiness(metrics)
        second = evaluate_slate_readiness(metrics)

        self.assertEqual(first["report_id"], second["report_id"])
        self.assertLessEqual(first["generated_at"], second["generated_at"])

    def test_partial_timestamps_cannot_pass_replay_cutoffs(self) -> None:
        metrics = _complete_metrics()
        metrics.salary_timestamp_rows = 49
        metrics.projection_cutoff_rows = 49

        report = evaluate_slate_readiness(metrics)

        self.assertEqual(report["gates"]["replay"]["status"], "fail")
        self.assertIn("salary_snapshot_cutoff", report["gates"]["replay"]["blocking_checks"])
        self.assertIn("projection_cutoff", report["gates"]["replay"]["blocking_checks"])

    def test_multiple_projection_versions_pass_with_explicit_active_run(self) -> None:
        metrics = _complete_metrics()
        metrics.projection_run_count = 3
        metrics.projection_run_is_explicit = True

        report = evaluate_slate_readiness(metrics)
        lineage = next(
            check for check in report["checks"] if check["check_id"] == "projection_run_lineage"
        )

        self.assertEqual(lineage["status"], "pass")
        self.assertTrue(lineage["details"]["selection_is_explicit"])
        self.assertEqual(report["gates"]["replay"]["status"], "pass")

    def test_multiple_projection_versions_use_latest_for_optimizer_but_require_exact_replay(self) -> None:
        metrics = _complete_metrics()
        metrics.projection_run_count = 2

        report = evaluate_slate_readiness(metrics)

        self.assertEqual(report["gates"]["classic_gpp"]["status"], "pass")
        self.assertEqual(report["gates"]["replay"]["status"], "fail")
        self.assertIn("replay_projection_run_lineage", report["gates"]["replay"]["blocking_checks"])

    def test_showdown_salary_markers_block_classic_only(self) -> None:
        metrics = _complete_metrics()
        metrics.roster_position_counts = {"CPT": 50, "FLEX": 50}

        report = evaluate_slate_readiness(metrics)

        self.assertEqual(report["gates"]["classic_gpp"]["status"], "fail")
        self.assertIn("classic_roster_coverage", report["gates"]["classic_gpp"]["blocking_checks"])
        self.assertEqual(report["gates"]["showdown_gpp"]["status"], "pass")


if __name__ == "__main__":
    unittest.main()
