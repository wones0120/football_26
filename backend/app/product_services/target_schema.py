"""Read-only compatibility validation for the migration-owned target schema."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import TypeAlias

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


TARGET_SCHEMA_MIGRATION = "0014_refresh_target_schema_contract.sql"

ContractKey: TypeAlias = tuple[str, str, str]
SchemaContract: TypeAlias = dict[ContractKey, str]


class TargetSchemaCompatibilityError(RuntimeError):
    """Raised when a product service sees an unmigrated or drifted target schema."""


_ACTUAL_CONTRACT_SQL = """
    SELECT 'table' AS object_type,
           table_class.relname AS table_name,
           table_class.relname AS object_name,
           'table' AS definition
    FROM pg_class table_class
    JOIN pg_namespace namespace
      ON namespace.oid = table_class.relnamespace
    WHERE namespace.nspname = 'target'
      AND table_class.relkind IN ('r', 'p')

    UNION ALL

    SELECT 'column' AS object_type,
           table_class.relname AS table_name,
           attribute.attname AS object_name,
           format(
               '%s|not_null=%s|identity=%s|generated=%s',
               format_type(attribute.atttypid, attribute.atttypmod),
               attribute.attnotnull,
               attribute.attidentity,
               attribute.attgenerated
           ) AS definition
    FROM pg_attribute attribute
    JOIN pg_class table_class
      ON table_class.oid = attribute.attrelid
    JOIN pg_namespace namespace
      ON namespace.oid = table_class.relnamespace
    WHERE namespace.nspname = 'target'
      AND table_class.relkind IN ('r', 'p')
      AND attribute.attnum > 0
      AND NOT attribute.attisdropped

    UNION ALL

    SELECT 'constraint' AS object_type,
           table_class.relname AS table_name,
           constraint_row.conname AS object_name,
           format(
               '%s|%s',
               constraint_row.contype,
               pg_get_constraintdef(constraint_row.oid, true)
           ) AS definition
    FROM pg_constraint constraint_row
    JOIN pg_class table_class
      ON table_class.oid = constraint_row.conrelid
    JOIN pg_namespace namespace
      ON namespace.oid = table_class.relnamespace
    WHERE namespace.nspname = 'target'
      AND table_class.relkind IN ('r', 'p')
"""


def _contract_from_rows(rows: Iterable[Mapping[str, object]]) -> SchemaContract:
    return {
        (
            str(row["object_type"]),
            str(row["table_name"]),
            str(row["object_name"]),
        ): str(row["definition"])
        for row in rows
    }


def expected_target_schema_contract(engine: Engine) -> SchemaContract:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT object_type, table_name, object_name, definition
                FROM public.target_schema_contract
                """
            )
        ).mappings()
        return _contract_from_rows(rows)


def actual_target_schema_contract(engine: Engine) -> SchemaContract:
    with engine.connect() as connection:
        rows = connection.execute(text(_ACTUAL_CONTRACT_SQL)).mappings()
        return _contract_from_rows(rows)


def _describe_contract_key(key: ContractKey) -> str:
    object_type, table_name, object_name = key
    if object_type == "table":
        return f"target.{table_name} table"
    return f"target.{table_name}.{object_name} {object_type}"


def compare_target_schema_contracts(
    expected: Mapping[ContractKey, str],
    actual: Mapping[ContractKey, str],
) -> list[str]:
    """Return precise table/column/constraint differences between two contracts."""

    issues: list[str] = []
    expected_keys = set(expected)
    actual_keys = set(actual)
    for key in sorted(expected_keys - actual_keys):
        issues.append(f"missing {_describe_contract_key(key)}")
    for key in sorted(actual_keys - expected_keys):
        issues.append(f"unexpected {_describe_contract_key(key)}")
    for key in sorted(expected_keys & actual_keys):
        if expected[key] != actual[key]:
            issues.append(
                f"{_describe_contract_key(key)}: expected {expected[key]!r}, "
                f"got {actual[key]!r}"
            )
    return issues


def _only_tables(
    contract: Mapping[ContractKey, str],
    table_names: set[str],
) -> SchemaContract:
    return {
        key: value
        for key, value in contract.items()
        if key[1] in table_names
    }


def validate_target_schema(
    engine: Engine,
    *,
    consumer: str,
    required_tables: Sequence[str],
) -> None:
    """Fail closed when a service's migrated target tables are incompatible.

    Unit tests commonly inject lightweight engine doubles. Those doubles have no
    concrete dialect name and are intentionally left to their focused SQL mocks.
    Real database engines must be PostgreSQL and carry the migration-recorded
    target contract.
    """

    dialect_name = getattr(getattr(engine, "dialect", None), "name", None)
    if not isinstance(dialect_name, str):
        return
    if dialect_name != "postgresql":
        raise TargetSchemaCompatibilityError(
            f"{consumer} requires the migration-owned PostgreSQL target schema; "
            f"got {dialect_name}."
        )

    table_names = {str(table_name) for table_name in required_tables}
    try:
        expected = expected_target_schema_contract(engine)
        actual = actual_target_schema_contract(engine)
    except SQLAlchemyError as exc:
        raise TargetSchemaCompatibilityError(
            f"{consumer} cannot validate target schema compatibility. Apply "
            f"numbered migrations through {TARGET_SCHEMA_MIGRATION}."
        ) from exc

    recorded_tables = {
        table_name
        for object_type, table_name, _ in expected
        if object_type == "table"
    }
    unrecorded = sorted(table_names - recorded_tables)
    if unrecorded:
        raise TargetSchemaCompatibilityError(
            f"{consumer} requires tables absent from the migration contract: "
            + ", ".join(f"target.{table_name}" for table_name in unrecorded)
        )

    issues = compare_target_schema_contracts(
        _only_tables(expected, table_names),
        _only_tables(actual, table_names),
    )
    if issues:
        details = "; ".join(issues[:10])
        if len(issues) > 10:
            details += f"; plus {len(issues) - 10} more issue(s)"
        raise TargetSchemaCompatibilityError(
            f"{consumer} found target schema drift: {details}. Apply numbered "
            "migrations; runtime services will not repair schema."
        )
