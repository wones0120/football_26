from unittest.mock import MagicMock, patch

from backend.app.api.product_routes import load_ownership, run_ownership_model
from backend.app.product_schemas import OwnershipLoadRequest, OwnershipRunRequest
from backend.app.product_services.ownership import OWNERSHIP_MODEL_ID, OwnershipLoadResult


def test_load_ownership_normalizes_missing_model_metrics_in_response():
    service = MagicMock()
    service.load_contest_standings.return_value = OwnershipLoadResult(
        season=2026,
        week=1,
        slate="SUNDAY_NIGHT",
        rows_written=55,
        message="Loaded contest standings",
        contest_id="195526180",
        source_file_id="dk_file_example",
        target_persisted=True,
        model_metrics=None,
    )

    request = OwnershipLoadRequest(
        season=2026,
        week=1,
        slate="SUNDAY_NIGHT",
        path="contest-standings-195526180.zip",
        contest_id="195526180",
        contest_format="showdown",
    )
    with patch("backend.app.api.product_routes._record_load_quality"):
        response = load_ownership(request, service, MagicMock())

    assert response.rows_written == 55
    assert response.model_metrics == {}
    assert response.target_persisted is True


def test_ownership_run_response_exposes_model_version():
    service = MagicMock()
    service.run_projection_model.return_value = OwnershipLoadResult(
        season=2026, week=3, slate="SUNDAY_MAIN", rows_written=100,
        message="Wrote ownership projections", ownership_run_id="run-123",
        target_persisted=True, model_metrics={"mae": 3.17},
        model_id=OWNERSHIP_MODEL_ID,
    )
    response = run_ownership_model(
        OwnershipRunRequest(season=2026, week=3, slate="SUNDAY_MAIN"), service,
    )
    assert response.model_id == "slate_aware_ownership_v2_prelock"
    assert response.ownership_run_id == "run-123"
