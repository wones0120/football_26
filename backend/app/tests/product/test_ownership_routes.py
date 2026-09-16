from unittest.mock import MagicMock, patch

from backend.app.api.product_routes import load_ownership
from backend.app.product_schemas import OwnershipLoadRequest
from backend.app.product_services.ownership import OwnershipLoadResult


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
