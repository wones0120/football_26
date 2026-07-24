import unittest

from fastapi.testclient import TestClient

from backend.app.main import app


class AppSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_openapi_is_available(self) -> None:
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("paths", payload)
        self.assertIn("/api/optimizer/run", payload["paths"])
        self.assertIn("/api/replay/classic-cash/stack-policies", payload["paths"])
        self.assertIn("/api/data/quality/history", payload["paths"])
        self.assertIn("/api/digital-twin/beliefs", payload["paths"])
        self.assertIn("/api/digital-twin/beliefs/{belief_id}/revisions", payload["paths"])
        self.assertIn("/api/digital-twin/beliefs/{belief_id}/status", payload["paths"])
        self.assertIn("/api/digital-twin/thought-captures", payload["paths"])
        self.assertIn("/api/digital-twin/thought-candidates/{candidate_id}/decision", payload["paths"])
        self.assertIn("/api/digital-twin/impact-previews", payload["paths"])
        self.assertIn("/api/digital-twin/beliefs/{belief_id}/impact-previews", payload["paths"])
        self.assertIn("/api/digital-twin/impact-previews/{preview_id}/decision", payload["paths"])
        self.assertIn("/api/digital-twin/variant-sets", payload["paths"])
        self.assertIn("/api/digital-twin/variant-sets/{variant_set_id}/replay", payload["paths"])
        self.assertIn("/api/agent/rules", payload["paths"])
        self.assertIn("/api/agent/backtest", payload["paths"])
        self.assertIn("/api/agent/learning/evaluate", payload["paths"])

    def test_root_serves_ui_or_placeholder(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
