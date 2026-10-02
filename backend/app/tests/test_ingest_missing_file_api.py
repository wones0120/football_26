from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes import router
from backend.app.db import get_db_session
from backend.app.schemas import AutoDiscoverIngestRequest


def test_auto_discovery_defaults_to_nfl_directory():
    assert AutoDiscoverIngestRequest().directory == "~/NFL"


def test_missing_local_ingest_file_returns_actionable_client_error(tmp_path):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db_session] = lambda: None
    client = TestClient(app)
    missing = tmp_path / "missing.csv"

    for source, endpoint in (("draftkings", "salaries"), ("fanduel", "injuries")):
        response = client.post(
            f"/api/ingest/{endpoint}",
            json={"source_system": source, "season": 2026, "week": 3,
                  "slate": "MONDAY_NIGHT", "path": str(missing)},
        )
        assert response.status_code == 422
        assert response.json() == {"detail": f"File not found: {missing}"}
