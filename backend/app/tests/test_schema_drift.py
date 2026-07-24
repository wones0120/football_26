from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine

from backend.app.models import Base
from backend.app.product_services.target_schema import compare_target_schema_contracts
from scripts.check_schema_drift import (
    compare_schema_signatures,
    metadata_schema_signature,
    validate_migration_names,
)


def _table_signature(
    *,
    columns: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "columns": columns,
        "primary_key": ("id",),
        "unique_constraints": [],
        "foreign_keys": [],
        "indexes": [],
    }


def test_current_migration_names_are_contiguous() -> None:
    assert validate_migration_names() == []


def test_migration_name_validation_rejects_gaps_and_bad_names(
    tmp_path: Path,
) -> None:
    (tmp_path / "0001_init.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "0003_gap.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "bad-name.sql").write_text("SELECT 1;", encoding="utf-8")

    issues = validate_migration_names(tmp_path)

    assert "invalid migration filename: bad-name.sql" in issues
    assert any("migration sequence must be contiguous" in issue for issue in issues)


def test_compare_schema_signatures_reports_structural_drift() -> None:
    expected = {
        "example": _table_signature(
            columns={
                "id": {"type": "BIGINT", "nullable": False},
                "payload": {"type": "JSONB", "nullable": False},
            }
        )
    }
    actual = {
        "example": _table_signature(
            columns={
                "id": {"type": "INTEGER", "nullable": False},
                "unexpected": {"type": "TEXT", "nullable": True},
            }
        ),
        "extra_table": _table_signature(
            columns={"id": {"type": "BIGINT", "nullable": False}}
        ),
    }

    issues = compare_schema_signatures(expected, actual)

    assert "unexpected table: extra_table" in issues
    assert "example: missing column payload" in issues
    assert "example: unexpected column unexpected" in issues
    assert any("example.id: expected" in issue for issue in issues)


def test_compare_target_schema_contracts_reports_precise_drift() -> None:
    expected = {
        ("table", "lineup", "lineup"): "table",
        ("column", "lineup", "lineup_id"): "text|not_null=true|identity=|generated=",
        ("constraint", "lineup", "lineup_pkey"): "p|PRIMARY KEY (lineup_id)",
    }
    actual = {
        ("table", "lineup", "lineup"): "table",
        ("column", "lineup", "lineup_id"): "uuid|not_null=true|identity=|generated=",
        ("column", "lineup", "rogue_column"): "text|not_null=false|identity=|generated=",
    }

    issues = compare_target_schema_contracts(expected, actual)

    assert "missing target.lineup.lineup_pkey constraint" in issues
    assert "unexpected target.lineup.rogue_column column" in issues
    assert any("target.lineup.lineup_id column: expected" in issue for issue in issues)


def test_orm_metadata_matches_migrated_postgresql_type_contract() -> None:
    engine = create_engine("postgresql+psycopg://")
    try:
        signature = metadata_schema_signature(Base.metadata, engine)
    finally:
        engine.dispose()

    assert signature["player_alias"]["columns"]["alias_id"]["type"] == "BIGINT"
    assert (
        signature["projection_residual_snapshot"]["columns"]["parameters_json"][
            "type"
        ]
        == "JSONB"
    )
    assert (
        (
            (
                "source_system",
                "slate",
                "low_salary_threshold",
                "low_salary_hit_points",
            ),
            False,
        )
        in signature["simulation_calibration_factor"]["indexes"]
    )
    assert (
        signature["ultimate_lineup_run"]["columns"]["request_json"]["type"]
        == "JSONB"
    )
    assert (
        signature["ultimate_lineup_run"]["columns"]["result_json"]["type"]
        == "JSONB"
    )
