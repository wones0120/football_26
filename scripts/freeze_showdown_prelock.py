"""Freeze the current Thursday input lineage; no optimizer or entry writes."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path

from sqlalchemy import text

from backend.app.db import engine
from backend.app.product_services.classic_prospective import digest_payload
from backend.app.product_services.optimizer import OptimizerService, _json_safe
from backend.app.product_services.ownership import OwnershipService
from backend.app.product_services.readiness import SlateReadinessService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--slate", required=True)
    parser.add_argument("--projection-run-id", required=True)
    parser.add_argument("--refresh-ownership", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Input freezes are immutable; choose a new output path")
    ownership = None
    if args.refresh_ownership:
        ownership = OwnershipService(engine=engine).run_projection_model(
            args.season, args.week, args.slate, data_cutoff_at=datetime.now(UTC),
            projection_run_id=args.projection_run_id,
        ).__dict__
    readonly = engine.execution_options(postgresql_readonly=True, isolation_level="REPEATABLE READ")
    params = {"season": args.season, "week": args.week, "slate": args.slate,
              "projection": args.projection_run_id}
    queries = {
        "projection_header": "SELECT * FROM target.projection_run WHERE projection_run_id=:projection",
        "projections": "SELECT * FROM target.player_projection WHERE projection_run_id=:projection ORDER BY player_id",
        "salaries": "SELECT * FROM public.curated_salary WHERE season=:season AND week=:week AND upper(slate)=upper(:slate) ORDER BY curated_salary_id",
        "ownership_headers": "SELECT * FROM target.ownership_model_run WHERE season=:season AND week=:week AND upper(slate_id)=upper(:slate) ORDER BY created_at",
    }
    with readonly.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        frozen = {key: [dict(row) for row in connection.execute(text(query), params).mappings()]
                  for key, query in queries.items()}
    service = OptimizerService()
    service.engine = readonly
    pool = service._load_player_pool(args.season, args.week, args.slate,
                                    projection_run_id=args.projection_run_id)
    readiness = SlateReadinessService()
    readiness.engine = readonly
    frozen.update({"frozen_at": datetime.now(UTC).isoformat(), "season": args.season,
                   "week": args.week, "slate": args.slate,
                   "projection_run_id": args.projection_run_id,
                   "player_pool": _json_safe(pool.to_dict("records")),
                   "pool_attrs": _json_safe(pool.attrs),
                   "ownership_refresh": ownership,
                   "readiness": readiness.report(season=args.season, week=args.week, slate=args.slate)})
    body = json.loads(json.dumps(frozen, default=str))
    args.output.write_text(json.dumps({"payload": body, "sha256": digest_payload(body)}, indent=2, sort_keys=True)+"\n")
    print({"pool_rows": len(pool), "ownership": ownership, "output": str(args.output)}, flush=True)


if __name__ == "__main__":
    main()
