from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TARGET_TABLE_PATTERN = re.compile(
    r"CREATE TABLE IF NOT EXISTS (?:target|\{s\})\.([a-z_]+)"
)
MIGRATED_TARGET_TABLE_PATTERN = re.compile(
    r'CREATE TABLE IF NOT EXISTS (?:target|"target")\.([a-z_]+)'
)
TARGET_MIGRATION_PATTERN = re.compile(
    r"(?:CREATE|ALTER|DROP)\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?:target|\"target\")\.|public\.target_schema_contract",
    re.IGNORECASE,
)
RUNTIME_TARGET_DDL_PATTERN = re.compile(
    r"(?:"
    r"CREATE\s+SCHEMA\s+IF\s+NOT\s+EXISTS\s+[\"']?target|"
    r"(?:CREATE|ALTER|DROP)\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?:target|\"target\")\.|"
    r"CREATE\s+(?:UNIQUE\s+)?INDEX[\s\S]*?\sON\s+(?:target|\"target\")\."
    r")",
    re.IGNORECASE,
)


def _target_tables_in_product_code() -> set[str]:
    tables: set[str] = set()
    for source_root in (
        ROOT / "Database",
        ROOT / "backend" / "app" / "product_services",
        ROOT / "scripts" / "product",
    ):
        for path in source_root.rglob("*.py"):
            tables.update(TARGET_TABLE_PATTERN.findall(path.read_text()))
    return tables


def _target_tables_in_migrations() -> set[str]:
    tables: set[str] = set()
    for path in (ROOT / "migrations").glob("*.sql"):
        tables.update(MIGRATED_TARGET_TABLE_PATTERN.findall(path.read_text()))
    return tables


def _runtime_validated_target_tables() -> set[str]:
    tables: set[str] = set()
    service_root = ROOT / "backend" / "app" / "product_services"
    for path in service_root.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "validate_target_schema":
                continue
            required = next(
                (keyword.value for keyword in node.keywords if keyword.arg == "required_tables"),
                None,
            )
            if isinstance(required, (ast.Tuple, ast.List)):
                tables.update(
                    str(element.value)
                    for element in required.elts
                    if isinstance(element, ast.Constant)
                    and isinstance(element.value, str)
                )
    return tables


def test_every_product_target_table_has_a_numbered_migration() -> None:
    product_tables = _target_tables_in_product_code()
    migrated_tables = _target_tables_in_migrations()

    assert len(migrated_tables) == 55
    assert product_tables <= migrated_tables, sorted(product_tables - migrated_tables)


def test_product_services_do_not_mutate_target_schema_at_runtime() -> None:
    violations: list[str] = []
    service_root = ROOT / "backend" / "app" / "product_services"
    for path in service_root.glob("*.py"):
        if RUNTIME_TARGET_DDL_PATTERN.search(path.read_text()):
            violations.append(path.name)

    assert violations == []


def test_runtime_compatibility_checks_name_only_migrated_tables() -> None:
    assert _runtime_validated_target_tables() <= _target_tables_in_migrations()


def test_target_schema_migrations_are_in_the_canonical_ledger() -> None:
    migration_names = {path.name for path in (ROOT / "migrations").glob("*.sql")}

    assert "0011_target_product_schema.sql" in migration_names
    assert "0012_target_ownership_and_digital_twin.sql" in migration_names
    assert "0013_target_schema_governance.sql" in migration_names
    assert "0014_refresh_target_schema_contract.sql" in migration_names


def test_latest_target_schema_migration_records_the_contract() -> None:
    target_migrations = [
        (path, sql)
        for path in sorted((ROOT / "migrations").glob("*.sql"))
        if TARGET_MIGRATION_PATTERN.search(sql := path.read_text())
    ]
    _, sql = target_migrations[-1]

    assert "TRUNCATE TABLE public.target_schema_contract" in sql
    assert "INSERT INTO public.target_schema_contract" in sql
