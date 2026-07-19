from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import get_settings


MIGRATION_DIR = REPO_ROOT / "migrations"


def get_migration_files(migration_dir: Path = MIGRATION_DIR) -> list[Path]:
    return sorted(p for p in migration_dir.glob("*.sql") if p.is_file())


def get_applied_migrations(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return [
            str(row[0])
            for row in connection.execute(
                text("SELECT version FROM schema_migrations ORDER BY version")
            )
        ]


def apply_migrations_to_engine(
    engine: Engine,
    *,
    migration_dir: Path = MIGRATION_DIR,
) -> list[str]:
    migration_files = get_migration_files(migration_dir)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(128) PRIMARY KEY,
                    applied_at TIMESTAMP NOT NULL DEFAULT now()
                )
                """
            )
        )
        applied = {
            row[0]
            for row in connection.execute(
                text("SELECT version FROM schema_migrations")
            ).fetchall()
        }

    newly_applied: list[str] = []
    for file_path in migration_files:
        version = file_path.name
        if version in applied:
            continue
        sql = file_path.read_text()
        with engine.begin() as connection:
            connection.exec_driver_sql(sql)
            connection.execute(
                text("INSERT INTO schema_migrations (version) VALUES (:version)"),
                {"version": version},
            )
        print(f"Applied migration: {version}")
        newly_applied.append(version)
    return newly_applied


def apply_migrations() -> list[str]:
    settings = get_settings()
    engine = create_engine(settings.sqlalchemy_database_uri, future=True)
    try:
        return apply_migrations_to_engine(engine)
    finally:
        engine.dispose()


if __name__ == "__main__":
    apply_migrations()
