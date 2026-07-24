#!/usr/bin/env python3
"""Register legacy DraftKings fields and backfill normalized target entry results."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.product_services.contest_evidence import classify_contest_type
from backend.app.product_services.ownership import OwnershipService
from scripts.product.apply_target_schema_adapters import adapter_sql, build_connection_url


@dataclass(frozen=True)
class BackfillResult:
    season: int
    week: int
    slate: str
    source_file: str
    contest_id: str | None
    contest_format: str
    contest_type: str
    field_size: int
    status: str
    message: str = ""


def discover_legacy_fields(
    engine,
    *,
    season: int | None = None,
    week: int | None = None,
    slate: str | None = None,
) -> list[dict]:
    inspector = inspect(engine)
    if not inspector.has_table("dk_contest_entries", schema="public"):
        return []
    clauses = ["entry.source_file IS NOT NULL"]
    params: dict[str, object] = {}
    if season is not None:
        clauses.append("entry.season = :season")
        params["season"] = season
    if week is not None:
        clauses.append("entry.week = :week")
        params["week"] = week
    if slate:
        clauses.append("UPPER(entry.slate) = UPPER(:slate)")
        params["slate"] = slate
    position_join = ""
    position_select = "FALSE AS has_captain"
    position_group = ""
    if inspector.has_table("dk_contest_standings_rows", schema="public"):
        position_join = """
            LEFT JOIN (
                SELECT source_file,
                       BOOL_OR(UPPER(COALESCE(roster_position, '')) = 'CPT') AS has_captain
                FROM public.dk_contest_standings_rows
                GROUP BY source_file
            ) positions ON positions.source_file = entry.source_file
        """
        position_select = "COALESCE(positions.has_captain, FALSE) AS has_captain"
        position_group = ", positions.has_captain"
    with engine.begin() as connection:
        rows = connection.execute(
            text(
                f"""
                SELECT entry.season::int AS season, entry.week::int AS week,
                       entry.slate, entry.source_file,
                       COUNT(DISTINCT entry.entry_id)::int AS field_size,
                       {position_select}
                FROM public.dk_contest_entries entry
                {position_join}
                WHERE {' AND '.join(clauses)}
                GROUP BY entry.season, entry.week, entry.slate, entry.source_file
                         {position_group}
                ORDER BY entry.season, entry.week, entry.slate, entry.source_file
                """
            ),
            params,
        ).mappings().all()
    return [dict(row) for row in rows]


def backfill_normalized_fields(
    engine,
    *,
    season: int | None = None,
    week: int | None = None,
    slate: str | None = None,
    dry_run: bool = False,
) -> tuple[list[BackfillResult], int]:
    service = OwnershipService(engine=engine)
    fields = discover_legacy_fields(engine, season=season, week=week, slate=slate)
    results: list[BackfillResult] = []
    registered = 0
    for field in fields:
        source_path = Path(str(field["source_file"])).expanduser()
        contest_format = (
            "showdown"
            if field.get("has_captain") or "CAPTAIN" in str(field["slate"]).upper()
            else "classic"
        )
        classification = classify_contest_type(source_path.stem)
        common = {
            "season": int(field["season"]),
            "week": int(field["week"]),
            "slate": str(field["slate"]),
            "source_file": str(source_path),
            "contest_format": contest_format,
            "contest_type": str(classification["contest_type"]),
            "field_size": int(field["field_size"]),
        }
        if not source_path.is_file():
            results.append(
                BackfillResult(
                    **common,
                    contest_id=None,
                    status="missing_source_file",
                    message="Original standings file is required for content-addressed identity.",
                )
            )
            continue
        source_info = service._source_file_info(source_path)
        contest_id = service._resolve_contest_id(
            None,
            season=common["season"],
            week=common["week"],
            slate=common["slate"],
            content_sha256=source_info["content_sha256"],
        )
        if dry_run:
            results.append(
                BackfillResult(
                    **common,
                    contest_id=contest_id,
                    status="would_register",
                )
            )
            continue
        persisted = service._persist_target_contest(
            contest_id=contest_id,
            source_info=source_info,
            season=common["season"],
            week=common["week"],
            slate=common["slate"],
            contest_name=source_path.stem,
            contest_format=contest_format,
            contest_type=common["contest_type"],
            contest_type_source=str(classification["contest_type_source"]),
            cash_game_type=classification["cash_game_type"],
            entry_fee=None,
            field_size=common["field_size"],
            max_entries_per_user=None,
            prize_pool=None,
            payout_tiers=[],
            entries=None,
        )
        results.append(
            BackfillResult(
                **common,
                contest_id=contest_id,
                status="registered" if persisted else "failed",
                message="" if persisted else "Target contest persistence failed.",
            )
        )
        registered += int(persisted)

    entry_rows = 0
    if registered and not dry_run:
        with engine.begin() as connection:
            applied = connection.execute(
                text(adapter_sql("public", "target")["dfs_contest_entry_result"])
            )
            entry_rows = int(applied.rowcount or 0)
    return results, entry_rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill content-addressed target contest fields from linked legacy standings."
    )
    parser.add_argument("--database", help="Postgres database name. Defaults to PGDATABASE.")
    parser.add_argument("--host", help="Postgres host. Defaults to PGHOST or localhost.")
    parser.add_argument("--port", help="Postgres port. Defaults to PGPORT or 5432.")
    parser.add_argument("--user", help="Postgres user. Defaults to PGUSER.")
    parser.add_argument("--password", help="Postgres password. Defaults to PGPASSWORD.")
    parser.add_argument("--season", type=int)
    parser.add_argument("--week", type=int)
    parser.add_argument("--slate")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    engine = create_engine(build_connection_url(args))
    results, entry_rows = backfill_normalized_fields(
        engine,
        season=args.season,
        week=args.week,
        slate=args.slate,
        dry_run=args.dry_run,
    )
    payload = {
        "database": args.database,
        "dry_run": args.dry_run,
        "fields_seen": len(results),
        "registered": sum(row.status == "registered" for row in results),
        "would_register": sum(row.status == "would_register" for row in results),
        "missing_source_files": sum(row.status == "missing_source_file" for row in results),
        "failed": sum(row.status == "failed" for row in results),
        "entry_rows": entry_rows,
        "results": [asdict(row) for row in results],
    }
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
    return 1 if payload["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
