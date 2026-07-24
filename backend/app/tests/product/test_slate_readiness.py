from datetime import datetime, timezone
import unittest

from backend.app.product_schemas import SlateReadinessResponse
from backend.app.product_services.readiness import SlateReadinessMetrics, evaluate_slate_readiness


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

    def test_multiple_projection_versions_require_active_selection(self) -> None:
        metrics = _complete_metrics()
        metrics.projection_run_count = 2

        report = evaluate_slate_readiness(metrics)

        self.assertEqual(report["gates"]["replay"]["status"], "fail")
        self.assertIn("projection_run_lineage", report["gates"]["replay"]["blocking_checks"])

    def test_showdown_salary_markers_block_classic_only(self) -> None:
        metrics = _complete_metrics()
        metrics.roster_position_counts = {"CPT": 50, "FLEX": 50}

        report = evaluate_slate_readiness(metrics)

        self.assertEqual(report["gates"]["classic_gpp"]["status"], "fail")
        self.assertIn("classic_roster_coverage", report["gates"]["classic_gpp"]["blocking_checks"])
        self.assertEqual(report["gates"]["showdown_gpp"]["status"], "pass")


if __name__ == "__main__":
    unittest.main()
