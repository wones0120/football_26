#!/usr/bin/env python3
"""Reproduce a saved optimizer request after candidate-pool persistence changes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import text

from backend.app.db import engine
from backend.app.product_dependencies import get_optimizer_service
from backend.app.product_services.optimizer import _json_safe


DERIVED_PARAM_KEYS = {
    "objective_config", "optimizer_rules", "stack_policy",
    "stack_policy_id", "strategy_config", "strategy_runtime",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_run_id")
    parser.add_argument("output", type=Path)
    parser.add_argument("--projection-run-id", default="")
    parser.add_argument(
        "--skip-qb-family-diagnostics", action="store_true",
        help="Skip extra diagnostic QB-family solves; candidate generation is unchanged.",
    )
    args = parser.parse_args()
    with engine.connect() as connection:
        source = connection.execute(text("""
            SELECT optimizer_run_id, projection_run_id, rule_run_id, slate_id,
                   season, week, contest_format, objective, strategy,
                   data_cutoff_at, constraint_config_json
            FROM target.optimizer_run
            WHERE optimizer_run_id = :run_id
        """), {"run_id": args.source_run_id}).mappings().first()
    if source is None:
        raise SystemExit(f"Saved optimizer run {args.source_run_id} was not found")
    raw_params = source["constraint_config_json"]
    if isinstance(raw_params, str):
        raw_params = json.loads(raw_params)
    params = {
        key: value for key, value in dict(raw_params).items()
        if key not in DERIVED_PARAM_KEYS
    }
    params["diagnostic_source_optimizer_run_id"] = args.source_run_id
    if args.skip_qb_family_diagnostics:
        params["classic_qb_family_diagnostics"] = False
    projection_run_id = args.projection_run_id or str(source["projection_run_id"])
    data_cutoff_at = None if args.projection_run_id else source["data_cutoff_at"]
    job = get_optimizer_service().run_job(
        season=int(source["season"]), week=int(source["week"]),
        slate=str(source["slate_id"]), strategy=str(source["strategy"]),
        params=params, contest_format=str(source["contest_format"]),
        objective=str(source["objective"]),
        projection_run_id=projection_run_id,
        rule_run_id=str(source["rule_run_id"]) if source["rule_run_id"] else None,
        data_cutoff_at=data_cutoff_at,
    )
    payload = _json_safe({
        "source_optimizer_run_id": args.source_run_id,
        "job_id": job.job_id,
        "status": job.status,
        "message": job.message,
        "season": job.season,
        "week": job.week,
        "slate": job.slate,
        "strategy": job.strategy,
        "contest_format": job.contest_format,
        "objective": job.objective,
        "projection_run_id": job.projection_run_id,
        "rule_run_id": job.rule_run_id,
        "data_cutoff_at": job.data_cutoff_at,
        "params": params,
        "results": job.results,
    })
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps({
        "source_run_id": args.source_run_id,
        "new_run_id": job.job_id,
        "status": job.status,
        "message": job.message,
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
