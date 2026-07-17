from __future__ import annotations

from collections.abc import Generator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.routes import router
from backend.app.db import get_db_session
from backend.app.models import Base


def _session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return factory()


def test_data_freshness_api_contract() -> None:
    session = _session()
    app = FastAPI()
    app.include_router(router)

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db_session] = override_session
    client = TestClient(app)

    response = client.get(
        "/api/coverage/freshness",
        params={
            "source_system": "draftkings",
            "season": 2025,
            "week": 1,
            "slate": "sunday_main",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_system"] == "draftkings"
    assert payload["season"] == 2025
    assert payload["week"] == 1
    assert payload["slate"] == "sunday_main"
    assert [row["dataset"] for row in payload["rows"]] == [
        "salaries",
        "injuries",
        "schedules",
        "weekly_stats",
    ]
    assert all(row["status"] == "missing" for row in payload["rows"])
    assert all(row["rows"] == 0 for row in payload["rows"])
    assert payload["rows"][0]["stale_after_hours"] == 24
    assert payload["rows"][1]["stale_after_hours"] == 12
    assert payload["rows"][2]["source_system"] == "nflreadpy"

    invalid = client.get(
        "/api/coverage/freshness",
        params={
            "source_system": "draftkings",
            "season": 2025,
            "week": 26,
            "slate": "sunday_main",
        },
    )
    assert invalid.status_code == 422
