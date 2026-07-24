from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.routes import router
from backend.app.db import get_db_session
from backend.app.models import Base, SimulationRun


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


def _simulation_run(
    simulation_run_id: str,
    *,
    shocked: bool,
    random_seed: int = 42,
    week: int = 18,
    status: str = "completed",
    completed_offset: int = 0,
) -> SimulationRun:
    started_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
        minutes=completed_offset
    )
    return SimulationRun(
        simulation_run_id=simulation_run_id,
        source_system="draftkings",
        season=2025,
        week=week,
        slate="sunday_main",
        iterations=1000,
        random_seed=random_seed,
        parameters_json={
            "min_history_games": 4,
            "prior_weight": 12.0,
            "noise_scale": 0.12,
            "use_residual_learning": False,
            "role_shocks": (
                [{"source_player_key": "scenario-player"}]
                if shocked
                else []
            ),
            "point_in_time_shocks": [],
        },
        players_considered=25,
        players_simulated=25,
        status=status,
        started_at=started_at,
        completed_at=started_at if status == "completed" else None,
    )


def test_simulation_run_options_return_only_compatible_baselines() -> None:
    session = _session()
    session.add_all(
        [
            _simulation_run(
                "baseline-compatible",
                shocked=False,
                completed_offset=1,
            ),
            _simulation_run(
                "scenario-role-shock",
                shocked=True,
                completed_offset=4,
            ),
            _simulation_run(
                "baseline-wrong-seed",
                shocked=False,
                random_seed=7,
                completed_offset=3,
            ),
            _simulation_run(
                "other-shock",
                shocked=True,
                completed_offset=2,
            ),
            _simulation_run(
                "still-running",
                shocked=False,
                status="running",
            ),
            _simulation_run(
                "wrong-slice",
                shocked=False,
                week=17,
            ),
        ]
    )
    session.commit()

    app = FastAPI()
    app.include_router(router)

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    client = TestClient(app)
    response = client.get(
        "/api/simulate/runs",
        params={
            "source_system": "draftkings",
            "season": 2025,
            "week": 18,
            "slate": "sunday_main",
            "scenario_run_id": "scenario-role-shock",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [row["simulation_run_id"] for row in payload["rows"]] == [
        "scenario-role-shock",
        "baseline-wrong-seed",
        "other-shock",
        "baseline-compatible",
    ]
    assert payload["compatible_baseline_run_ids"] == [
        "baseline-compatible"
    ]
    scenario = payload["rows"][0]
    assert scenario["has_role_shocks"] is True
    assert scenario["has_point_in_time_shocks"] is False
    assert scenario["players_simulated"] == 25


def test_simulation_run_options_reject_cross_slice_scenario() -> None:
    session = _session()
    session.add(
        _simulation_run(
            "wrong-slice",
            shocked=True,
            week=17,
        )
    )
    session.commit()

    app = FastAPI()
    app.include_router(router)

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    client = TestClient(app)
    response = client.get(
        "/api/simulate/runs",
        params={
            "source_system": "draftkings",
            "season": 2025,
            "week": 18,
            "slate": "sunday_main",
            "scenario_run_id": "wrong-slice",
        },
    )

    assert response.status_code == 422
    assert "targets draftkings 2025-W17" in response.json()["detail"]
