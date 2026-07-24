#!/usr/bin/env python3
"""Replay versioned classic-cash stacking policies on exact historical inputs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy.engine import URL

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.product_services.replay import (
    DEFAULT_CASH_STACK_POLICY_IDS,
    ClassicCashStackReplayService,
)


def build_connection_url(args: argparse.Namespace) -> URL:
    database = args.database or os.getenv("PGDATABASE")
    if not database:
        raise RuntimeError("Database is required. Pass --database or set PGDATABASE.")
    return URL.create(
        drivername="postgresql",
        username=args.user or os.getenv("PGUSER"),
        password=args.password or os.getenv("PGPASSWORD"),
        host=args.host or os.getenv("PGHOST", "localhost"),
        port=int(args.port or os.getenv("PGPORT", "5432")),
        database=database,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run deterministic, cutoff-safe classic cash stacking-policy replay. "
            "Omit --week to replay every available week for the requested slate."
        )
    )
    parser.add_argument("--database", help="Postgres database name. Defaults to PGDATABASE.")
    parser.add_argument("--host", help="Postgres host. Defaults to PGHOST or localhost.")
    parser.add_argument("--port", help="Postgres port. Defaults to PGPORT or 5432.")
    parser.add_argument("--user", help="Postgres user. Defaults to PGUSER.")
    parser.add_argument("--password", help="Postgres password. Defaults to PGPASSWORD.")
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--week", type=int)
    parser.add_argument("--slate", default="SUNDAY_MAIN")
    parser.add_argument(
        "--projection-run-id",
        help="Exact projection run. Required when more than one compatible run exists.",
    )
    parser.add_argument(
        "--policy",
        action="append",
        choices=DEFAULT_CASH_STACK_POLICY_IDS,
        help="Policy to replay. Repeat for multiple policies; defaults to all DT-402 policies.",
    )
    parser.add_argument("--output", help="Optional path for the deterministic JSON artifact.")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    if args.projection_run_id and args.week is None:
        parser.error("--projection-run-id requires --week")
    if args.week is not None and not 1 <= args.week <= 25:
        parser.error("--week must be between 1 and 25")

    service = ClassicCashStackReplayService(connection_string=str(build_connection_url(args)))
    report = service.run(
        season=args.season,
        week=args.week,
        slate=args.slate,
        projection_run_id=args.projection_run_id,
        policy_ids=tuple(args.policy or DEFAULT_CASH_STACK_POLICY_IDS),
    )
    payload = json.dumps(report, indent=2 if args.pretty else None, sort_keys=True)
    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
