from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.engine.interfaces import ReflectedIndex
from sqlalchemy.schema import Table, UniqueConstraint

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import get_settings
from backend.app.models import Base
from scripts.apply_migrations import (
    MIGRATION_DIR,
    apply_migrations_to_engine,
    get_applied_migrations,
    get_migration_files,
)


MIGRATION_NAME_PATTERN = re.compile(r"^(?P<number>\d{4})_[a-z0-9_]+\.sql$")
IGNORED_DATABASE_TABLES = {"schema_migrations"}


def _canonical_type(sql_type: Any, engine: Engine) -> str:
    compiled = str(sql_type.compile(dialect=engine.dialect)).upper()
    normalized = " ".join(compiled.split())
    aliases = {
        "FLOAT": "DOUBLE PRECISION",
        "TIMESTAMP": "TIMESTAMP WITHOUT TIME ZONE",
    }
    return aliases.get(normalized, normalized)


def _normalize_columns(columns: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    return tuple(str(column) for column in (columns or []))


def _metadata_table_signature(table: Table, engine: Engine) -> dict[str, Any]:
    unique_constraints = sorted(
        {
            _normalize_columns([column.name for column in constraint.columns])
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
    )
    foreign_keys = sorted(
        {
            (
                _normalize_columns(
                    [element.parent.name for element in constraint.elements]
                ),
                str(constraint.elements[0].column.table.name),
                _normalize_columns(
                    [element.column.name for element in constraint.elements]
                ),
                str(constraint.ondelete or "").upper(),
            )
            for constraint in table.foreign_key_constraints
        }
    )
    indexes = sorted(
        (
            _normalize_columns([column.name for column in index.columns]),
            bool(index.unique),
        )
        for index in table.indexes
    )
    return {
        "columns": {
            column.name: {
                "type": _canonical_type(column.type, engine),
                "nullable": bool(column.nullable),
            }
            for column in table.columns
        },
        "primary_key": _normalize_columns(
            [column.name for column in table.primary_key.columns]
        ),
        "unique_constraints": unique_constraints,
        "foreign_keys": foreign_keys,
        "indexes": indexes,
    }


def _reflected_index_signature(
    index: ReflectedIndex,
) -> tuple[tuple[str, ...], bool] | None:
    if index.get("duplicates_constraint"):
        return None
    column_names = index.get("column_names")
    if not column_names or any(column is None for column in column_names):
        raise ValueError(
            "Expression or partial indexes require explicit drift-check support: "
            f"{index.get('name')}"
        )
    return _normalize_columns(column_names), bool(index.get("unique", False))


def _database_table_signature(
    engine: Engine,
    *,
    table_name: str,
    schema: str,
) -> dict[str, Any]:
    inspector = inspect(engine)
    reflected_indexes = [
        signature
        for raw_index in inspector.get_indexes(table_name, schema=schema)
        if (signature := _reflected_index_signature(raw_index)) is not None
    ]
    foreign_keys = sorted(
        {
            (
                _normalize_columns(foreign_key.get("constrained_columns")),
                str(foreign_key.get("referred_table") or ""),
                _normalize_columns(foreign_key.get("referred_columns")),
                str(
                    (foreign_key.get("options") or {}).get("ondelete") or ""
                ).upper(),
            )
            for foreign_key in inspector.get_foreign_keys(
                table_name,
                schema=schema,
            )
        }
    )
    return {
        "columns": {
            str(column["name"]): {
                "type": _canonical_type(column["type"], engine),
                "nullable": bool(column["nullable"]),
            }
            for column in inspector.get_columns(table_name, schema=schema)
        },
        "primary_key": _normalize_columns(
            inspector.get_pk_constraint(
                table_name,
                schema=schema,
            ).get("constrained_columns")
        ),
        "unique_constraints": sorted(
            {
                _normalize_columns(constraint.get("column_names"))
                for constraint in inspector.get_unique_constraints(
                    table_name,
                    schema=schema,
                )
            }
        ),
        "foreign_keys": foreign_keys,
        "indexes": sorted(reflected_indexes),
    }


def metadata_schema_signature(
    metadata: MetaData,
    engine: Engine,
) -> dict[str, dict[str, Any]]:
    return {
        table.name: _metadata_table_signature(table, engine)
        for table in metadata.sorted_tables
    }


def database_schema_signature(
    engine: Engine,
    *,
    schema: str = "public",
) -> dict[str, dict[str, Any]]:
    inspector = inspect(engine)
    table_names = sorted(
        set(inspector.get_table_names(schema=schema)) - IGNORED_DATABASE_TABLES
    )
    return {
        table_name: _database_table_signature(
            engine,
            table_name=table_name,
            schema=schema,
        )
        for table_name in table_names
    }


def compare_schema_signatures(
    expected: dict[str, dict[str, Any]],
    actual: dict[str, dict[str, Any]],
) -> list[str]:
    issues: list[str] = []
    expected_tables = set(expected)
    actual_tables = set(actual)
    for table_name in sorted(expected_tables - actual_tables):
        issues.append(f"missing table: {table_name}")
    for table_name in sorted(actual_tables - expected_tables):
        issues.append(f"unexpected table: {table_name}")

    for table_name in sorted(expected_tables & actual_tables):
        expected_table = expected[table_name]
        actual_table = actual[table_name]
        expected_columns = expected_table["columns"]
        actual_columns = actual_table["columns"]
        for column_name in sorted(set(expected_columns) - set(actual_columns)):
            issues.append(f"{table_name}: missing column {column_name}")
        for column_name in sorted(set(actual_columns) - set(expected_columns)):
            issues.append(f"{table_name}: unexpected column {column_name}")
        for column_name in sorted(set(expected_columns) & set(actual_columns)):
            if expected_columns[column_name] != actual_columns[column_name]:
                issues.append(
                    f"{table_name}.{column_name}: expected "
                    f"{expected_columns[column_name]}, got "
                    f"{actual_columns[column_name]}"
                )
        for property_name in (
            "primary_key",
            "unique_constraints",
            "foreign_keys",
            "indexes",
        ):
            if expected_table[property_name] != actual_table[property_name]:
                issues.append(
                    f"{table_name}: {property_name} expected "
                    f"{expected_table[property_name]}, got "
                    f"{actual_table[property_name]}"
                )
    return issues


def validate_migration_names(migration_dir: Path = MIGRATION_DIR) -> list[str]:
    issues: list[str] = []
    files = get_migration_files(migration_dir)
    numbers: list[int] = []
    for file_path in files:
        match = MIGRATION_NAME_PATTERN.fullmatch(file_path.name)
        if match is None:
            issues.append(f"invalid migration filename: {file_path.name}")
            continue
        numbers.append(int(match.group("number")))
    expected_numbers = list(range(1, len(numbers) + 1))
    if numbers != expected_numbers:
        issues.append(
            f"migration sequence must be contiguous from 0001: "
            f"found {numbers}, expected {expected_numbers}"
        )
    return issues


def validate_migration_ledger(
    engine: Engine,
    *,
    migration_dir: Path = MIGRATION_DIR,
) -> list[str]:
    expected = [path.name for path in get_migration_files(migration_dir)]
    applied = get_applied_migrations(engine)
    if applied == expected:
        return []
    return [f"migration ledger expected {expected}, got {applied}"]


def run_schema_validation(
    engine: Engine,
    *,
    apply_migrations: bool,
    require_empty: bool,
    verify_idempotency: bool,
    migration_dir: Path = MIGRATION_DIR,
    schema: str = "public",
) -> dict[str, Any]:
    if engine.dialect.name != "postgresql":
        raise ValueError("Schema drift validation currently requires PostgreSQL.")
    if require_empty and not apply_migrations:
        raise ValueError("--require-empty requires --apply-migrations.")
    initial_tables = set(inspect(engine).get_table_names(schema=schema))
    if require_empty and initial_tables:
        raise ValueError(
            "Fresh-database smoke check requires an empty schema; found "
            f"{sorted(initial_tables)}."
        )

    migration_name_issues = validate_migration_names(migration_dir)
    newly_applied = (
        apply_migrations_to_engine(engine, migration_dir=migration_dir)
        if apply_migrations
        else []
    )
    ledger_issues = validate_migration_ledger(
        engine,
        migration_dir=migration_dir,
    )
    expected_signature = metadata_schema_signature(Base.metadata, engine)
    actual_signature = database_schema_signature(engine, schema=schema)
    drift_issues = compare_schema_signatures(
        expected_signature,
        actual_signature,
    )

    idempotency_issues: list[str] = []
    second_pass_applied: list[str] = []
    if verify_idempotency:
        before_second_pass = actual_signature
        second_pass_applied = apply_migrations_to_engine(
            engine,
            migration_dir=migration_dir,
        )
        after_second_pass = database_schema_signature(engine, schema=schema)
        if second_pass_applied:
            idempotency_issues.append(
                "second migration pass unexpectedly applied "
                f"{second_pass_applied}"
            )
        if before_second_pass != after_second_pass:
            idempotency_issues.append(
                "database schema changed during the second migration pass"
            )

    issues = (
        migration_name_issues
        + ledger_issues
        + drift_issues
        + idempotency_issues
    )
    return {
        "status": "ok" if not issues else "failed",
        "database_dialect": engine.dialect.name,
        "schema": schema,
        "migration_files": [
            path.name for path in get_migration_files(migration_dir)
        ],
        "newly_applied": newly_applied,
        "second_pass_applied": second_pass_applied,
        "orm_tables": len(expected_signature),
        "database_tables": len(actual_signature),
        "issues": issues,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Apply PostgreSQL migrations and verify migration history, "
            "idempotency, and ORM schema drift."
        )
    )
    parser.add_argument("--apply-migrations", action="store_true")
    parser.add_argument("--require-empty", action="store_true")
    parser.add_argument("--verify-idempotency", action="store_true")
    parser.add_argument("--schema", default="public")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()
    engine = create_engine(
        settings.sqlalchemy_database_uri,
        future=True,
    )
    try:
        result = run_schema_validation(
            engine,
            apply_migrations=args.apply_migrations,
            require_empty=args.require_empty,
            verify_idempotency=args.verify_idempotency,
            schema=args.schema,
        )
    finally:
        engine.dispose()

    print(json.dumps(result, indent=2))
    if result["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
