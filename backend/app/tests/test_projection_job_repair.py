from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.app.product_services.canonical_projection_inputs import (
    StaleTrainingOutcomeError,
)
from backend.app.services import job_handlers
from backend.app.services.job_queue import PermanentJobError


class _Context:
    run_id = "projection-run-1"
    checkpoint = {
        "feature_run_id": "feature-run-1",
        "model_run_id": "model-run-1",
        "data_cutoff_at": "2026-09-22T10:00:00+00:00",
    }

    def __init__(self):
        self.progress_rows = []

    def progress(
        self, stage, current, total, message, *, run_id=None, checkpoint=None
    ):
        if checkpoint is not None:
            self.checkpoint = dict(checkpoint)
        self.progress_rows.append(
            {
                "stage": stage,
                "current": current,
                "total": total,
                "message": message,
                "checkpoint": checkpoint,
            }
        )


def test_projection_job_repairs_stale_prior_week_features_and_retries(monkeypatch):
    calls = []

    class _Predictions:
        def __init__(self, _connection_string):
            pass

        def fetch_completed_run_summary(self, _run_id):
            return None

        def train_and_predict(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise StaleTrainingOutcomeError([(2026, 2)])
            return SimpleNamespace(
                records=[object()],
                target_persisted=True,
                feature_run_id=kwargs["feature_run_id"],
                model_run_id=kwargs["model_run_id"],
                projection_run_id=kwargs["projection_run_id"],
                data_cutoff_at=kwargs["data_cutoff_at"],
                calibration_metrics={},
            )

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    rebuild_calls = []

    class _Learning:
        def __init__(self, _session):
            pass

        def rebuild_player_game_feature_matrix(self, **kwargs):
            rebuild_calls.append(kwargs)
            return {
                "slates_total": 5,
                "slates_completed": 5,
                "slates_failed": 0,
                "rows_written": 1000,
            }

    monkeypatch.setattr(job_handlers, "PredictionsService", _Predictions)
    monkeypatch.setattr(
        job_handlers,
        "StartingQBService",
        lambda _connection_string: SimpleNamespace(
            derive_starters=lambda **_kwargs: SimpleNamespace(
                rows_written=2, message="Stored 2 starting QBs."
            )
        ),
    )
    monkeypatch.setattr(job_handlers, "LineupLearningService", _Learning)
    monkeypatch.setattr(job_handlers, "SessionLocal", _Session)
    monkeypatch.setattr(job_handlers, "get_connection_string", lambda: "local")

    context = _Context()
    response = job_handlers._projection_handler(
        context,
        {"season": 2026, "week": 3, "slate": "THURSDAY_NIGHT"},
    )

    assert response["rows_written"] == 1
    assert len(calls) == 2
    assert calls[0]["data_cutoff_at"] > datetime(
        2026, 9, 22, 10, tzinfo=UTC
    )
    assert context.checkpoint["data_cutoff_at"] == calls[1]["data_cutoff_at"].isoformat()
    assert calls[1]["data_cutoff_at"] > calls[0]["data_cutoff_at"]
    assert rebuild_calls == [
        {
            "source_system": "draftkings",
            "season_start": 2026,
            "season_end": 2026,
            "weeks": [2],
        }
    ]
    refresh = context.checkpoint["automatic_training_feature_refresh"]
    assert refresh == {
        "periods": [{"season": 2026, "week": 2}],
        "slates_completed": 5,
        "rows_written": 1000,
    }
    assert any(
        row["stage"] == "training_feature_refresh"
        for row in context.progress_rows
    )


def test_projection_job_resolves_starters_before_training(monkeypatch):
    events = []

    class _Predictions:
        def __init__(self, _connection_string):
            pass

        def fetch_completed_run_summary(self, _run_id):
            return None

        def train_and_predict(self, **kwargs):
            events.append("train")
            return SimpleNamespace(
                records=[object()], target_persisted=True,
                feature_run_id=kwargs["feature_run_id"],
                model_run_id=kwargs["model_run_id"],
                projection_run_id=kwargs["projection_run_id"],
                data_cutoff_at=kwargs["data_cutoff_at"],
                calibration_metrics={},
            )

    class _Starters:
        def __init__(self, _connection_string):
            pass

        def derive_starters(self, **kwargs):
            events.append("starters")
            assert kwargs == {"season": 2026, "week": 3, "slate": "MONDAY_NIGHT"}
            return SimpleNamespace(rows_written=2, message="Stored 2 starting QBs.")

    monkeypatch.setattr(job_handlers, "PredictionsService", _Predictions)
    monkeypatch.setattr(job_handlers, "StartingQBService", _Starters)
    monkeypatch.setattr(job_handlers, "get_connection_string", lambda: "local")

    context = _Context()
    response = job_handlers._projection_handler(
        context,
        {"season": 2026, "week": 3, "slate": "MONDAY_NIGHT"},
    )

    assert response["rows_written"] == 1
    assert events == ["starters", "train"]
    assert datetime.fromisoformat(response["data_cutoff_at"]) == datetime.fromisoformat(
        context.checkpoint["data_cutoff_at"]
    )


def test_projection_job_stops_when_starters_remain_unresolved(monkeypatch):
    class _Predictions:
        def __init__(self, _connection_string):
            pass

        def fetch_completed_run_summary(self, _run_id):
            return None

        def train_and_predict(self, **_kwargs):
            pytest.fail("Projection training must not start without QB evidence")

    monkeypatch.setattr(job_handlers, "PredictionsService", _Predictions)
    monkeypatch.setattr(
        job_handlers,
        "StartingQBService",
        lambda _connection_string: SimpleNamespace(
            derive_starters=lambda **_kwargs: SimpleNamespace(
                rows_written=0, message="CHI QB evidence is ambiguous"
            )
        ),
    )
    monkeypatch.setattr(job_handlers, "get_connection_string", lambda: "local")

    with pytest.raises(PermanentJobError, match="CHI QB evidence is ambiguous"):
        job_handlers._projection_handler(
            _Context(),
            {"season": 2026, "week": 3, "slate": "MONDAY_NIGHT"},
        )
