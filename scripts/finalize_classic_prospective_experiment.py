#!/usr/bin/env python3
"""Append post-slate actuals to a frozen Classic experiment after contest import."""

from __future__ import annotations

import argparse
import json

from sqlalchemy import text

from backend.app.db import engine
from backend.app.product_services.classic_prospective import (
    digest_payload, evaluate_postgame, validate_solver_snapshot,
)
from backend.app.product_services.optimizer_effectiveness import (
    actual_points_by_player, field_benchmarks,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("optimizer_run_id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        record = connection.execute(text("""
            SELECT e.solver_snapshot_json, e.solver_snapshot_sha256,
                   e.prelock_experiment_json, e.experiment_sha256,
                   r.season, r.week, r.slate_id
            FROM target.classic_prospective_experiment e
            JOIN target.optimizer_run r USING (optimizer_run_id)
            WHERE e.optimizer_run_id = :run_id
        """), {"run_id": args.optimizer_run_id}).mappings().one()
        snapshot = record["solver_snapshot_json"]
        experiment = record["prelock_experiment_json"]
        validate_solver_snapshot(snapshot)
        if snapshot["sha256"] != record["solver_snapshot_sha256"]:
            raise ValueError("Stored solver snapshot digest mismatch")
        if not experiment or experiment.get("status") != "prelock_frozen":
            raise ValueError("Run has no verified pre-lock prospective experiment")
        if (experiment.get("sha256") != record["experiment_sha256"] or
                digest_payload({key: value for key, value in experiment.items() if key != "sha256"}) !=
                record["experiment_sha256"]):
            raise ValueError("Stored prospective experiment digest mismatch")
        key = {"season": record["season"], "week": record["week"], "slate": record["slate_id"]}
        contests = [dict(row) for row in connection.execute(text("""
            SELECT contest_id, season, week, slate_id, contest_format, field_size
            FROM target.dfs_contest
            WHERE season=:season AND week=:week AND upper(slate_id)=upper(:slate)
              AND contest_format='classic'
        """), key).mappings()]
        observations = [dict(row) for row in connection.execute(text("""
            SELECT o.player_id, o.roster_position, o.actual_points, o.resolution_status
            FROM target.contest_ownership_observation o
            JOIN target.dfs_contest c USING (contest_id)
            WHERE c.season=:season AND c.week=:week AND upper(c.slate_id)=upper(:slate)
              AND c.contest_format='classic'
        """), key).mappings()]
        entry_rows = [dict(row) for row in connection.execute(text("""
            SELECT c.contest_id, e.entry_points
            FROM target.dfs_contest_entry_result e JOIN target.dfs_contest c USING (contest_id)
            WHERE c.season=:season AND c.week=:week AND upper(c.slate_id)=upper(:slate)
              AND c.contest_format='classic'
        """), key).mappings()]
        connection.rollback()
    by_contest: dict[str, list[dict]] = {}
    for row in entry_rows:
        by_contest.setdefault(str(row["contest_id"]), []).append(row)
    lines = {}
    for contest in contests:
        contest_id = str(contest["contest_id"])
        result = field_benchmarks(contest, by_contest.get(contest_id, []), [])
        if result.get("status") == "available":
            lines[contest_id] = {label: value for label, value in result["thresholds"].items()
                                 if label in {"top_20_percent", "top_10_percent",
                                              "top_5_percent", "top_1_percent"}}
    if not observations or not lines:
        raise ValueError("Resolved Classic player actuals and field thresholds are required")
    evaluation = evaluate_postgame(experiment, actual_points_by_player(observations, "classic"), lines)
    print(json.dumps(evaluation, indent=2, sort_keys=True))
    if args.dry_run:
        return
    if evaluation["status"] != "evaluated":
        raise ValueError("Candidate actual coverage is below 90%; postgame evaluation not appended")
    with engine.begin() as connection:
        connection.execute(text("""
            UPDATE target.classic_prospective_experiment
            SET postgame_json=CAST(:evaluation AS JSONB), postgame_updated_at=now()
            WHERE optimizer_run_id=:run_id AND solver_snapshot_sha256=:snapshot_sha256
              AND experiment_sha256=:experiment_sha256
        """), {"run_id": args.optimizer_run_id,
               "snapshot_sha256": snapshot["sha256"],
               "experiment_sha256": experiment["sha256"],
               "evaluation": json.dumps(evaluation, sort_keys=True, allow_nan=False)})


if __name__ == "__main__":
    main()
