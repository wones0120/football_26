import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.product_dependencies import get_model_governance_service


def _evaluation_payload() -> dict:
    gate = {
        "metric": "mae",
        "direction": "minimize",
        "champion_value": 4.8,
        "challenger_value": 4.6,
        "required_improvement": 0.1,
    }
    return {
        "evaluation_id": "evaluation-1",
        "contract_id": "model_challenger_evaluation_v1",
        "season": 2025,
        "week": 12,
        "slate_id": "SUNDAY_MAIN",
        "champion_projection_run_id": "champion",
        "challenger_projection_run_id": "challenger",
        "data_window": {
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
        },
        "champion_feature_set_hash": "feature-champion",
        "challenger_feature_set_hash": "feature-challenger",
        "champion_code_hash": "a" * 64,
        "challenger_code_hash": "b" * 64,
        "gates": [gate],
        "gate_results": [{**gate, "observed_improvement": 0.2, "passed": True}],
        "status": "passed",
        "evaluation_hash": "evaluation-hash",
        "evaluated_by": "Model Review",
        "evidence_uri": "docs/model-evidence.json",
        "notes": None,
        "created_at": datetime(2026, 7, 30, tzinfo=timezone.utc),
    }


def _decision_payload(action: str) -> dict:
    promotion = action == "promotion"
    return {
        "decision_id": f"decision-{action}",
        "contract_id": "model_promotion_decision_v1",
        "evaluation_id": "evaluation-1",
        "action": action,
        "approved_by": "Reviewer",
        "approval_reason": f"Approved {action}",
        "previous_projection_run_id": "champion" if promotion else "challenger",
        "selected_projection_run_id": "challenger" if promotion else "champion",
        "rollback_of_decision_id": None if promotion else "decision-promotion",
        "decision_hash": f"hash-{action}",
        "selection_reason": f"model_{action}:decision-{action}",
        "active": True,
        "created_at": datetime(2026, 7, 30, tzinfo=timezone.utc),
    }


class _GovernanceStub:
    def __init__(self) -> None:
        self.evaluation_kwargs: dict | None = None

    def create_evaluation(self, **kwargs):
        self.evaluation_kwargs = kwargs
        return _evaluation_payload()

    def get_evaluation(self, evaluation_id: str):
        return _evaluation_payload() if evaluation_id == "evaluation-1" else None

    def promote(self, evaluation_id: str, **kwargs):
        assert evaluation_id == "evaluation-1"
        return _decision_payload("promotion")

    def rollback(self, promotion_decision_id: str, **kwargs):
        assert promotion_decision_id == "decision-promotion"
        return _decision_payload("rollback")


class ModelGovernanceRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stub = _GovernanceStub()
        app.dependency_overrides[get_model_governance_service] = lambda: self.stub
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.pop(get_model_governance_service, None)

    def test_evaluation_contract_serializes_declared_lineage_and_gates(self) -> None:
        payload = _evaluation_payload()
        request = {
            key: payload[key]
            for key in (
                "champion_projection_run_id",
                "challenger_projection_run_id",
                "data_window",
                "champion_code_hash",
                "challenger_code_hash",
                "gates",
                "evaluated_by",
                "evidence_uri",
                "notes",
            )
        }

        response = self.client.post("/api/model-governance/evaluations", json=request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["evaluation_id"], "evaluation-1")
        self.assertEqual(self.stub.evaluation_kwargs["gates"][0]["metric"], "mae")
        self.assertEqual(
            self.stub.evaluation_kwargs["data_window"]["test"]["end"],
            {"season": 2025, "week": 11},
        )

    def test_promotion_and_rollback_contracts_return_pointer_lineage(self) -> None:
        promotion = self.client.post(
            "/api/model-governance/evaluations/evaluation-1/promote",
            json={"approved_by": "Reviewer", "approval_reason": "Approved promotion"},
        )
        rollback = self.client.post(
            "/api/model-governance/decisions/decision-promotion/rollback",
            json={"approved_by": "Reviewer", "approval_reason": "Approved rollback"},
        )

        self.assertEqual(promotion.status_code, 200)
        self.assertEqual(promotion.json()["selected_projection_run_id"], "challenger")
        self.assertEqual(rollback.status_code, 200)
        self.assertEqual(rollback.json()["selected_projection_run_id"], "champion")

    def test_missing_evaluation_returns_not_found(self) -> None:
        response = self.client.get("/api/model-governance/evaluations/missing")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
