import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from backend.app.product_services.model_governance import (
    ModelGovernanceService,
    evaluate_metric_gates,
    normalize_data_window,
)


def _result(*, first=None, one=None, scalar=None, rowcount=0):
    result = MagicMock()
    result.mappings.return_value.first.return_value = first
    result.mappings.return_value.one.return_value = one
    result.scalar.return_value = scalar
    result.rowcount = rowcount
    return result


def _window():
    return {
        "training": {
            "start": {"season": 2024, "week": 1},
            "end": {"season": 2024, "week": 18},
        },
        "validation": {
            "start": {"season": 2025, "week": 1},
            "end": {"season": 2025, "week": 7},
        },
        "test": {
            "start": {"season": 2025, "week": 8},
            "end": {"season": 2025, "week": 11},
        },
    }


def _code_hash(run_id: str) -> str:
    return ("a" if run_id == "champion" else "b") * 64


def _run(run_id: str, model_run_id: str, feature_hash: str):
    return {
        "projection_run_id": run_id,
        "model_run_id": model_run_id,
        "season": 2025,
        "week": 12,
        "slate_id": "SUNDAY_MAIN",
        "row_count": 50,
        "data_cutoff_at": datetime(2025, 11, 23, 12, tzinfo=timezone.utc),
        "status": "completed",
        "created_at": datetime(2025, 11, 23, 13, tzinfo=timezone.utc),
        "model_id": f"model-{run_id}",
        "feature_run_id": f"feature-{run_id}",
        "feature_set_hash": feature_hash,
        "params_json": {"code_hash": _code_hash(run_id)},
    }


def _evaluation_row(status: str = "passed"):
    return {
        "evaluation_id": "evaluation-1",
        "season": 2025,
        "week": 12,
        "slate_id": "SUNDAY_MAIN",
        "champion_projection_run_id": "champion",
        "challenger_projection_run_id": "challenger",
        "data_window_json": _window(),
        "champion_feature_set_hash": "feature-champion",
        "challenger_feature_set_hash": "feature-challenger",
        "champion_code_hash": _code_hash("champion"),
        "challenger_code_hash": _code_hash("challenger"),
        "gate_policy_json": [],
        "gate_results_json": [],
        "status": status,
        "evaluation_hash": "evaluation-hash",
        "evaluated_by": "Model Review",
        "evidence_uri": "docs/model-evidence.json",
        "notes": None,
        "created_at": datetime(2026, 7, 30, tzinfo=timezone.utc),
    }


def _decision_row(action: str):
    promotion = action == "promotion"
    return {
        "decision_id": f"decision-{action}",
        "evaluation_id": "evaluation-1",
        "action": action,
        "approved_by": "Reviewer",
        "approval_reason": f"Approved {action}",
        "previous_projection_run_id": "champion" if promotion else "challenger",
        "selected_projection_run_id": "challenger" if promotion else "champion",
        "rollback_of_decision_id": None if promotion else "decision-promotion",
        "decision_hash": f"hash-{action}",
        "created_at": datetime(2026, 7, 30, tzinfo=timezone.utc),
    }


class ModelGovernanceTests(unittest.TestCase):
    def test_requires_ordered_non_overlapping_windows(self) -> None:
        normalized = normalize_data_window(_window())
        self.assertEqual(normalized["test"]["end"], {"season": 2025, "week": 11})

        overlapping = _window()
        overlapping["validation"]["start"] = {"season": 2024, "week": 18}
        with self.assertRaisesRegex(ValueError, "Training must end"):
            normalize_data_window(overlapping)

    def test_metric_gates_require_and_measure_a_strict_win(self) -> None:
        results = evaluate_metric_gates(
            [
                {
                    "metric": "mae",
                    "direction": "minimize",
                    "champion_value": 4.8,
                    "challenger_value": 4.6,
                    "required_improvement": 0.1,
                },
                {
                    "metric": "p10_p90_coverage",
                    "direction": "maximize",
                    "champion_value": 0.78,
                    "challenger_value": 0.80,
                    "required_improvement": 0.0,
                },
            ]
        )

        self.assertTrue(all(row["passed"] for row in results))
        self.assertAlmostEqual(results[0]["observed_improvement"], 0.2)
        with self.assertRaisesRegex(ValueError, "strict positive improvement"):
            evaluate_metric_gates(
                [
                    {
                        "metric": "mae",
                        "direction": "minimize",
                        "champion_value": 4.8,
                        "challenger_value": 4.8,
                        "required_improvement": 0.0,
                    }
                ]
            )

    def test_create_evaluation_validates_lineage_and_persists_gate_result(self) -> None:
        service = ModelGovernanceService.__new__(ModelGovernanceService)
        service.engine = MagicMock()
        connection = service.engine.begin.return_value.__enter__.return_value
        created = _evaluation_row()
        created["gate_policy_json"] = [
            {
                "metric": "mae",
                "direction": "minimize",
                "champion_value": 4.8,
                "challenger_value": 4.6,
                "required_improvement": 0.1,
            }
        ]
        created["gate_results_json"] = [{**created["gate_policy_json"][0], "passed": True}]
        connection.execute.side_effect = [
            _result(first=_run("champion", "model-champion", "feature-champion")),
            _result(first=_run("challenger", "model-challenger", "feature-challenger")),
            _result(first=None),
            _result(scalar="champion"),
            _result(one=created),
        ]

        evaluation = service.create_evaluation(
            champion_projection_run_id="champion",
            challenger_projection_run_id="challenger",
            data_window=_window(),
            champion_code_hash=_code_hash("champion"),
            challenger_code_hash=_code_hash("challenger"),
            gates=created["gate_policy_json"],
            evaluated_by="Model Review",
            evidence_uri="docs/model-evidence.json",
        )

        self.assertEqual(evaluation["status"], "passed")
        self.assertEqual(evaluation["champion_feature_set_hash"], "feature-champion")
        insert_call = connection.execute.call_args_list[-1]
        self.assertIn("INSERT INTO target.model_challenger_evaluation", str(insert_call.args[0]))
        self.assertEqual(insert_call.args[1]["status"], "passed")

    def test_blocked_evaluation_cannot_be_promoted(self) -> None:
        service = ModelGovernanceService.__new__(ModelGovernanceService)
        service.engine = MagicMock()
        connection = service.engine.begin.return_value.__enter__.return_value
        connection.execute.return_value = _result(first=_evaluation_row(status="blocked"))

        with self.assertRaisesRegex(ValueError, "cannot be promoted"):
            service.promote(
                "evaluation-1",
                approved_by="Reviewer",
                approval_reason="Insufficient improvement",
            )

    def test_idempotent_promotion_reports_inactive_after_rollback(self) -> None:
        service = ModelGovernanceService.__new__(ModelGovernanceService)
        service.engine = MagicMock()
        connection = service.engine.begin.return_value.__enter__.return_value
        connection.execute.side_effect = [
            _result(first=_evaluation_row()),
            _result(first=_decision_row("promotion")),
            _result(scalar="champion"),
        ]

        promotion = service.promote(
            "evaluation-1",
            approved_by="Reviewer",
            approval_reason="Approved promotion",
        )

        self.assertFalse(promotion["active"])

    def test_promotion_and_rollback_atomically_reverse_the_pointer(self) -> None:
        service = ModelGovernanceService.__new__(ModelGovernanceService)
        service.engine = MagicMock()
        connection = service.engine.begin.return_value.__enter__.return_value
        promotion_row = _decision_row("promotion")
        connection.execute.side_effect = [
            _result(first=_evaluation_row()),
            _result(first=None),
            _result(scalar="champion"),
            _result(first=None),
            _result(first=None),
            _result(one=promotion_row),
            _result(rowcount=1),
        ]

        promotion = service.promote(
            "evaluation-1",
            approved_by="Reviewer",
            approval_reason="Approved promotion",
        )

        self.assertEqual(promotion["selected_projection_run_id"], "challenger")
        pointer_call = connection.execute.call_args_list[-1]
        self.assertEqual(pointer_call.args[1]["previous_projection_run_id"], "champion")
        self.assertEqual(pointer_call.args[1]["selected_projection_run_id"], "challenger")

        rollback_row = _decision_row("rollback")
        connection.execute.reset_mock()
        connection.execute.side_effect = [
            _result(first=promotion_row),
            _result(first=_evaluation_row()),
            _result(first=None),
            _result(scalar="challenger"),
            _result(first=None),
            _result(first=None),
            _result(one=rollback_row),
            _result(rowcount=1),
        ]

        rollback = service.rollback(
            "decision-promotion",
            approved_by="Reviewer",
            approval_reason="Approved rollback",
        )

        self.assertEqual(rollback["selected_projection_run_id"], "champion")
        pointer_call = connection.execute.call_args_list[-1]
        self.assertEqual(pointer_call.args[1]["previous_projection_run_id"], "challenger")
        self.assertEqual(pointer_call.args[1]["selected_projection_run_id"], "champion")


if __name__ == "__main__":
    unittest.main()
