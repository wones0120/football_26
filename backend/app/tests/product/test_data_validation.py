from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from backend.app.product_services.validation import fetch_weekly_row_counts


def _database_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'coverage.db'}"


def test_current_salary_alias_is_scoped_to_the_requested_slate(tmp_path: Path) -> None:
    connection_string = _database_url(tmp_path)
    engine = create_engine(connection_string)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE curated_salary (
                    season INTEGER NOT NULL,
                    week INTEGER NOT NULL,
                    slate TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO curated_salary (season, week, slate) VALUES
                    (2026, 1, 'WEDNESDAY_NIGHT'),
                    (2026, 1, 'WEDNESDAY_NIGHT'),
                    (2026, 1, 'SUNDAY_MAIN')
                """
            )
        )

    rows = fetch_weekly_row_counts(
        table_name="curated_salaries",
        seasons=[2026],
        week=1,
        slate="wednesday_night",
        connection_string=connection_string,
    )

    assert rows == [
        {
            "season": 2026,
            "week": 1,
            "rows": 2,
            "expected_rows": 2,
            "status": "ok",
        }
    ]


def test_missing_current_layer_returns_a_missing_result_instead_of_crashing(
    tmp_path: Path,
) -> None:
    assert fetch_weekly_row_counts(
        table_name="player_projection",
        seasons=[2026],
        week=1,
        slate="WEDNESDAY_NIGHT",
        connection_string=_database_url(tmp_path),
    ) == [
        {
            "season": 2026,
            "week": 1,
            "rows": 0,
            "expected_rows": None,
            "status": "missing",
        }
    ]


def test_validation_rejects_unapproved_table_names(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported validation table"):
        fetch_weekly_row_counts(
            table_name="player_master; DROP TABLE player_master",
            connection_string=_database_url(tmp_path),
        )
