from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import (
    Base,
    CuratedSalary,
    IngestRun,
    PlayerAlias,
    PlayerMaster,
    RawNflWeeklyStat,
    RawSalaryRow,
)
from backend.app.schemas import (
    BacktestWeekRequest,
    NflReadPyBootstrapRequest,
    NflReadPySeasonRequest,
    SalaryIngestRequest,
)
from backend.app.services.ingest import IngestService
from backend.app.services.simulation import SimulationService


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )
    return factory()


def _weekly_stats() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for week in (1, 2):
        rows.extend(
            [
                {
                    "season": 2025,
                    "week": week,
                    "player_id": "nfl-qb-1",
                    "player_display_name": "Integration Quarterback",
                    "recent_team": "BUF",
                    "opponent_team": "MIA",
                    "position": "QB",
                    "passing_yards": 250,
                    "passing_tds": 2,
                },
                {
                    "season": 2025,
                    "week": week,
                    "player_id": "nfl-wr-1",
                    "player_display_name": "Integration Receiver",
                    "recent_team": "MIA",
                    "opponent_team": "BUF",
                    "position": "WR",
                    "receptions": 8,
                },
            ]
        )
    rows.extend(
        [
            {
                "season": 2025,
                "week": 3,
                "player_id": "nfl-qb-1",
                "player_display_name": "Integration Quarterback",
                "recent_team": "BUF",
                "opponent_team": "MIA",
                "position": "QB",
                "passing_yards": 300,
                "passing_tds": 3,
            },
            {
                "season": 2025,
                "week": 3,
                "player_id": "nfl-wr-1",
                "player_display_name": "Integration Receiver",
                "recent_team": "MIA",
                "opponent_team": "BUF",
                "position": "WR",
                "receptions": 4,
                "receiving_yards": 60,
            },
        ]
    )
    return pd.DataFrame(rows).fillna(0)


def _write_salary_csv(path: Path) -> None:
    pd.DataFrame(
        [
            {
                "ID": "dk-qb-1",
                "Name": "Integration Quarterback",
                "TeamAbbrev": "BUF",
                "Position": "QB",
                "Salary": 7000,
            },
            {
                "ID": "dk-wr-1",
                "Name": "Integration Receiver",
                "TeamAbbrev": "MIA",
                "Position": "WR",
                "Salary": 4000,
            },
        ]
    ).to_csv(path, index=False)


def test_ingestion_curation_to_backtest_critical_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    weekly_stats = _weekly_stats()
    fake_nflreadpy = SimpleNamespace(
        import_weekly_data=lambda _seasons: weekly_stats.copy()
    )
    monkeypatch.setitem(sys.modules, "nflreadpy", fake_nflreadpy)

    session = _session()
    ingest_service = IngestService(session)

    bootstrap = ingest_service.bootstrap_nflreadpy(
        NflReadPyBootstrapRequest(season=2025, weeks=[1, 2, 3])
    )
    stats_ingest = ingest_service.ingest_nflreadpy_weekly_stats(
        NflReadPySeasonRequest(season=2025, weeks=[1, 2, 3])
    )

    salary_path = tmp_path / "draftkings_week_3.csv"
    _write_salary_csv(salary_path)
    salary_ingest = ingest_service.ingest_salaries(
        SalaryIngestRequest(
            source_system="draftkings",
            season=2025,
            week=3,
            slate="main",
            path=str(salary_path),
        )
    )

    assert bootstrap.status == "completed"
    assert bootstrap.rows_curated == 2
    assert stats_ingest.status == "completed"
    assert stats_ingest.rows_curated == 6
    assert salary_ingest.status == "completed"
    assert salary_ingest.rows_raw == 2
    assert salary_ingest.rows_curated == 2
    assert salary_ingest.rows_unresolved == 0

    curated_rows = session.query(CuratedSalary).order_by(
        CuratedSalary.source_player_key
    ).all()
    assert len(curated_rows) == 2
    assert all(row.player_master_id for row in curated_rows)
    assert session.query(PlayerMaster).count() == 2
    assert session.query(PlayerAlias).count() == 4
    assert session.query(RawSalaryRow).count() == 2
    assert session.query(RawNflWeeklyStat).count() == 6
    assert session.query(IngestRun).count() == 3

    result = SimulationService(session).backtest_week(
        BacktestWeekRequest(
            source_system="draftkings",
            season=2025,
            week=3,
            slate="main",
            iterations=500,
            min_history_games=1,
            prior_weight=0.0,
            noise_scale=0.0,
            random_seed=42,
            evaluation_top_n=5,
        )
    )

    assert result.players_considered == 2
    assert result.players_simulated == 2
    assert result.players_with_actuals == 2
    assert {row.player_name for row in result.rows} == {
        "Integration Quarterback",
        "Integration Receiver",
    }
    predicted_by_name = {
        row.player_name: row.predicted_mean_points for row in result.rows
    }
    actual_by_name = {row.player_name: row.actual_points for row in result.rows}
    assert predicted_by_name == pytest.approx(
        {
            "Integration Quarterback": 18.0,
            "Integration Receiver": 8.0,
        }
    )
    assert actual_by_name == pytest.approx(
        {
            "Integration Quarterback": 27.0,
            "Integration Receiver": 10.0,
        }
    )
    assert result.mae == pytest.approx(5.5)
