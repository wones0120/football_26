from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.app.main import app
from backend.app.db import get_db_session
from backend.app.product_dependencies import get_data_quality_service
from backend.app.services.lineup_learning import LineupLearningService


def test_matrix_build_uses_selected_slice_and_reports_missing_or_failed_inputs():
    session = MagicMock()
    app.dependency_overrides[get_db_session] = lambda: session
    app.dependency_overrides[get_data_quality_service] = lambda: MagicMock()
    try:
        client = TestClient(app)
        with patch(
            "backend.app.api.product_routes.LineupLearningService"
        ) as service, patch("backend.app.api.product_routes._record_load_quality") as quality:
            builder = service.return_value.rebuild_player_game_feature_matrix
            builder.return_value = dict(slates_total=1, slates_completed=1, slates_failed=0, rows_written=68)
            payload = {"season": 2026, "weeks": [1], "slate": "WEDNESDAY_NIGHT"}
            response = client.post("/api/features/matrix/build", json=payload)
            assert response.status_code == 200
            assert response.json()["rows_written"] == 68
            builder.assert_called_once_with(
                source_system="draftkings", season_start=2026, season_end=2026,
                weeks=[1], slate="WEDNESDAY_NIGHT",
            )
            assert quality.call_args.kwargs["slate"] == "WEDNESDAY_NIGHT"
            builder.return_value = dict(slates_total=0)
            response = client.post("/api/features/matrix/build", json=payload)
            assert response.status_code == 422
            assert "Load salaries first" in response.json()["detail"]
            builder.return_value = dict(slates_total=1, slates_failed=1, slates_completed=0)
            response = client.post("/api/features/matrix/build", json=payload)
            assert response.status_code == 422
            assert "1 slate(s)" in response.json()["detail"]
            assert quality.call_count == 1
            builder.return_value = dict(slates_total=2, slates_completed=2, slates_failed=0, rows_written=100)
            response = client.post("/api/features/matrix/build", json={"season": 2026})
            assert response.status_code == 200
            builder.assert_called_with(
                source_system="draftkings", season_start=2026, season_end=2026,
                weeks=None, slate=None,
            )
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_data_quality_service, None)


def test_matrix_build_filters_weeks_before_computing_any_features():
    service = LineupLearningService(MagicMock())
    with patch.object(service, "_fetch_available_slate_slices", return_value=[
        (2026, 1, "WEDNESDAY_NIGHT"), (2026, 2, "WEDNESDAY_NIGHT"),
    ]), patch.object(service, "_compute_player_projection_lookup", side_effect=ValueError("fixture")) as compute:
        summary = service.rebuild_player_game_feature_matrix(
            source_system="draftkings", season_start=2026, season_end=2026,
            slate="WEDNESDAY_NIGHT", weeks=[1],
        )
    assert summary["slates_total"] == 1
    compute.assert_called_once_with(source_system="draftkings", season=2026, week=1, slate="WEDNESDAY_NIGHT")


def test_salary_slice_lookup_accepts_shell_case_and_preserves_stored_identifier():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE curated_salary (source_system TEXT, season INT, week INT, slate TEXT)"))
        connection.execute(text("INSERT INTO curated_salary VALUES ('draftkings', 2026, 1, 'sunday_main')"))
    with Session(engine) as session:
        slices = LineupLearningService(session)._fetch_available_slate_slices(
            source_system="draftkings", season_start=2026, season_end=2026, slate_filter="SUNDAY_MAIN",
        )
    assert slices == [(2026, 1, "sunday_main")]
