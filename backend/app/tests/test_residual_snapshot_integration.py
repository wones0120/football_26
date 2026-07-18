from __future__ import annotations

from collections.abc import Generator
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.routes import router
from backend.app.db import get_db_session
from backend.app.models import Base, ProjectionResidualSnapshot
from backend.app.schemas import (
    ResidualSnapshotBuildRequest,
    SimulateWeekRequest,
)
from backend.app.services.residual_learning import (
    FEATURE_SET_HASH,
    ResidualObservation,
)
from backend.app.services.simulation import (
    SimulationService,
    _snapshot_parameters_hash,
)


def _session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )
    return factory()


def _observation(week: int, residual: float) -> ResidualObservation:
    return ResidualObservation(
        season=2025,
        week=week,
        player_master_id="player-a",
        source_player_key="dk-player-a",
        team="DAL",
        opponent="NYG",
        position="RB",
        salary=6000,
        game_total_line=47.0,
        team_spread_line=-2.5,
        baseline_points=10.0,
        actual_points=10.0 + residual,
    )


def _snapshot(
    week: int,
    *,
    request: ResidualSnapshotBuildRequest | None = None,
    residual: float = 2.0,
) -> ProjectionResidualSnapshot:
    request = request or ResidualSnapshotBuildRequest(
        season=2025,
        week=week,
    )
    parameters = request.model_dump(mode="json")
    return ProjectionResidualSnapshot(
        projection_residual_snapshot_id=f"snapshot-{week}",
        source_system="draftkings",
        season=2025,
        week=week,
        slate="sunday_main",
        parameters_hash=_snapshot_parameters_hash(parameters),
        parameters_json=parameters,
        feature_set_hash=FEATURE_SET_HASH,
        code_version="test",
        observations_json=[_observation(week, residual).to_dict()],
        observations_count=1,
        status="completed",
        created_at=datetime(2025, 1, week),
    )


def test_residual_gate_defaults_off() -> None:
    request = SimulateWeekRequest(season=2025, week=5)

    assert request.use_residual_learning is False


def test_simulation_run_persists_residual_gate() -> None:
    class FakeSession:
        def add(self, _row: object) -> None:
            return None

        def commit(self) -> None:
            return None

    request = SimulateWeekRequest(
        season=2025,
        week=5,
        use_residual_learning=True,
    )

    run = SimulationService(FakeSession())._new_run(request)  # type: ignore[arg-type]

    assert run.parameters_json is not None
    assert run.parameters_json["use_residual_learning"] is True


def test_residual_model_loads_only_strictly_prior_snapshots() -> None:
    session = _session()
    session.add_all([_snapshot(week) for week in range(1, 7)])
    session.commit()

    model, snapshot_count, warnings = SimulationService(
        session
    )._load_residual_model(
        source_system="draftkings",
        season=2025,
        week=5,
        slate="sunday_main",
    )

    assert warnings == []
    assert snapshot_count == 4
    assert model is not None
    assert model.training_slices == 4
    assert model.trained_through == (2025, 4)
    adjustment, scopes_used = model.adjustment_for(
        _observation(5, residual=0.0)
    )
    assert adjustment > 0.0
    assert scopes_used >= 1


def test_residual_model_falls_back_with_insufficient_history() -> None:
    session = _session()
    session.add_all([_snapshot(week) for week in range(1, 4)])
    session.commit()

    model, snapshot_count, warnings = SimulationService(
        session
    )._load_residual_model(
        source_system="draftkings",
        season=2025,
        week=5,
        slate="sunday_main",
    )

    assert model is None
    assert snapshot_count == 3
    assert "baseline projections were used" in warnings[0]


def test_snapshot_build_is_idempotent_and_immutable() -> None:
    session = _session()
    request = ResidualSnapshotBuildRequest(season=2025, week=5)
    session.add(_snapshot(5, request=request))
    session.commit()
    service = SimulationService(session)

    reused = service.build_residual_snapshot(request)

    assert reused.created is False
    assert reused.observations_count == 1
    with pytest.raises(ValueError, match="different parameters"):
        service.build_residual_snapshot(
            ResidualSnapshotBuildRequest(
                season=2025,
                week=5,
                iterations=2000,
            )
        )


def test_snapshot_api_reuses_existing_snapshot() -> None:
    session = _session()
    request = ResidualSnapshotBuildRequest(season=2025, week=5)
    session.add(_snapshot(5, request=request))
    session.commit()
    app = FastAPI()
    app.include_router(router)

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    client = TestClient(app)

    response = client.post(
        "/api/simulate/residual-snapshot",
        json=request.model_dump(mode="json"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["created"] is False
    assert payload["observations_count"] == 1
    assert payload["feature_set_hash"] == FEATURE_SET_HASH
