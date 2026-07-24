import json
import unittest

from backend.app.api.product_routes import get_slate_readiness
from backend.app.product_services.data_quality import DataQualityService, build_load_quality_report
from backend.app.product_services.readiness import SlateReadinessMetrics, evaluate_slate_readiness


class _RecordingConnection:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))


class _BeginContext:
    def __init__(self, connection: _RecordingConnection) -> None:
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, traceback):
        return False


class _RecordingEngine:
    url = "postgresql://test"

    def __init__(self) -> None:
        self.connection = _RecordingConnection()

    def begin(self):
        return _BeginContext(self.connection)


class _RecordingDataQualityService(DataQualityService):
    def _ensure_schema(self) -> None:
        return None


class DataQualityTests(unittest.TestCase):
    def test_load_report_preserves_values_thresholds_and_scope(self) -> None:
        report = build_load_quality_report(
            trigger="raw_salary_load",
            season=2025,
            week=11,
            slate="sunday_main",
            summaries=[
                {"dataset": "raw_salaries", "rows_written": 56},
                {"dataset": "unmatched_salaries", "rows_written": 0},
            ],
        )

        self.assertEqual(report["contract_id"], "load_quality_v1")
        self.assertEqual(report["status"], "warn")
        self.assertEqual(report["summary"], {"pass": 1, "warn": 1, "fail": 0})
        self.assertEqual(report["checks"][0]["value"], 56)
        self.assertEqual(report["checks"][0]["threshold"], "> 0 rows")
        self.assertEqual(report["checks"][0]["affected_scope"]["slate"], "SUNDAY_MAIN")
        self.assertEqual(report["checks"][1]["status"], "warn")

    def test_explicit_batch_failure_is_retained_and_report_id_is_stable(self) -> None:
        payload = {
            "trigger": "draftkings_batch_import",
            "season": 2025,
            "week": 11,
            "slate": "SUNDAY_MAIN",
            "summaries": [
                {
                    "dataset": "draftkings_salary",
                    "rows_written": 0,
                    "status": "fail",
                    "path": "/tmp/bad.csv",
                    "message": "Malformed salary export",
                }
            ],
        }

        first = build_load_quality_report(**payload)
        second = build_load_quality_report(**payload)

        self.assertEqual(first["report_id"], second["report_id"])
        self.assertEqual(first["status"], "fail")
        self.assertEqual(first["score"], 0)
        self.assertEqual(first["checks"][0]["details"]["path"], "/tmp/bad.csv")

    def test_record_report_inserts_run_and_check_rows(self) -> None:
        engine = _RecordingEngine()
        service = _RecordingDataQualityService(engine=engine)
        report = build_load_quality_report(
            trigger="feature_build",
            season=2025,
            week=11,
            slate=None,
            summaries=[{"dataset": "predictive_features", "rows_written": 100}],
        )

        quality_run_id = service.record_report(report, trigger="feature_build")

        self.assertTrue(quality_run_id.startswith("quality-"))
        self.assertEqual(len(engine.connection.calls), 2)
        run_params = engine.connection.calls[0][1]
        check_params = engine.connection.calls[1][1]
        self.assertEqual(run_params["quality_run_id"], quality_run_id)
        self.assertEqual(run_params["trigger"], "feature_build")
        self.assertEqual(json.loads(run_params["summary_json"]), {"fail": 0, "pass": 1, "warn": 0})
        self.assertEqual(len(check_params), 1)
        self.assertEqual(check_params[0]["value_json"], "100")
        self.assertEqual(
            json.loads(check_params[0]["affected_scope_json"])["dataset"],
            "predictive_features",
        )

    def test_readiness_reads_are_not_recorded_unless_explicitly_requested(self) -> None:
        report = evaluate_slate_readiness(
            SlateReadinessMetrics(season=2025, week=11, slate="SUNDAY_MAIN")
        )

        class _ReadinessService:
            def report(self, **_kwargs):
                return report

        class _QualityService:
            def __init__(self) -> None:
                self.triggers = []

            def record_readiness(self, _report, *, trigger):
                self.triggers.append(trigger)

        quality = _QualityService()
        get_slate_readiness(
            season=2025,
            week=11,
            slate="SUNDAY_MAIN",
            record=False,
            service=_ReadinessService(),
            quality_service=quality,
        )
        self.assertEqual(quality.triggers, [])

        get_slate_readiness(
            season=2025,
            week=11,
            slate="SUNDAY_MAIN",
            record=True,
            service=_ReadinessService(),
            quality_service=quality,
        )
        self.assertEqual(quality.triggers, ["readiness_preflight"])


if __name__ == "__main__":
    unittest.main()
