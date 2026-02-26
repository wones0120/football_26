from __future__ import annotations

import re
import sys
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import get_settings


VALID_DB_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def recreate_database() -> None:
    settings = get_settings()
    target_db = settings.pgdatabase
    maintenance_db = "postgres"

    if not VALID_DB_NAME_RE.match(target_db):
        raise ValueError(
            f"Unsafe database name: {target_db!r}. Only letters, numbers, and underscore are allowed."
        )

    conn = psycopg.connect(
        host=settings.pghost,
        port=settings.pgport,
        user=settings.pguser,
        password=settings.pgpassword,
        dbname=maintenance_db,
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (target_db,),
            )
            cur.execute(f"DROP DATABASE IF EXISTS {target_db}")
            cur.execute(f"CREATE DATABASE {target_db}")
        print(f"Recreated database: {target_db}")
    finally:
        conn.close()


if __name__ == "__main__":
    recreate_database()

