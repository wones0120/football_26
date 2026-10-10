"""Refresh, gate, freeze and generate a NEW Showdown run with a packet.

Example: PYTHONPATH=. .venv/bin/python scripts/run_live_showdown.py \
  --from-run 9cb62307-8915-49ab-97e6-5510d9f8d1a5 --ai-requested-entries 2
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

from backend.app.config import get_settings
from backend.app.product_services.optimizer import OptimizerService, _json_safe
from backend.app.product_services.ai_showdown_packet import build_packet, render_markdown, _game
from backend.app.product_services.showdown_data_readiness import (
    evaluate_readiness, freshness_rules, requires_ownership, ShowdownDataNotReady,
)
from backend.app.product_services.slate_preparation import digest


def saved_source(job):
    return _json_safe({k: getattr(job, k) for k in (
        "job_id", "season", "week", "slate", "strategy", "contest_format", "status", "created_at",
        "data_cutoff_at", "projection_run_id", "params", "results")})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-run", required=True, help="Saved run supplies scope and user controls; it is never updated")
    parser.add_argument("--ai-requested-entries", type=int, choices=range(2, 6), required=True)
    parser.add_argument("--allow-incomplete-evidence", action="store_true", help="Internal development/forensic override only")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    service = OptimizerService()
    old = service.get_job(args.from_run)
    if old is None:
        parser.error("Saved optimizer run was not found in the configured database")
    if old.contest_format != "showdown":
        parser.error("Reference run must be Showdown")
    directory = args.output_dir or Path("artifacts/showdown_data_readiness") / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    directory.mkdir(parents=True, exist_ok=False)
    def save(name, value):
        (directory / name).write_text(json.dumps(_json_safe(value), sort_keys=True, indent=2) + "\n")
    before = saved_source(old); save("old_run_unchanged.json", before)
    flat = [r for lineup in old.results or [] for r in lineup]
    baseline = _game(flat, old.data_cutoff_at)
    rows = deepcopy((old.params.get("strategy_runtime") or {}).get("player_pool", {}).get("rows") or [])
    old_readiness = evaluate_readiness(rows, season=old.season, week=old.week, slate=old.slate,
        projection_run_id=old.projection_run_id, evidence_cutoff=old.data_cutoff_at, evaluated_at=old.created_at,
        rules=freshness_rules(get_settings()), ownership_required=requires_ownership(old.params))
    save("old_readiness_audit.json", {"readiness": old_readiness, "saved_baseline": baseline,
        "interpretation": "Read-only reconstruction; missing archived fields remain unverified. No current data replaces archived inputs."})
    params = deepcopy(old.params)
    for key in ("prepared_input_job_id", "prepared_input_evidence", "strategy_runtime", "entry_readiness",
                "decision_snapshot", "data_readiness", "showdown_evidence_snapshot", "ownership_run_id", "player_pool_readiness"):
        params.pop(key, None)
    params.update(ai_requested_entries=args.ai_requested_entries, refresh_ownership=True)
    run_id = str(uuid4())
    report = {"reference_run_id": old.job_id, "attempt_run_id": run_id, "old_baseline": baseline,
              "old_readiness": old_readiness, "ai_requested_entries": args.ai_requested_entries}
    def progress(stage, current, total, message, **kwargs):
        print(f"{stage}: {message}", flush=True)
    try:
        job = service.run_job(season=old.season, week=old.week, slate=old.slate, strategy=old.strategy,
            params=params, contest_format="showdown", objective=old.objective, optimizer_run_id=run_id,
            allow_incomplete_evidence=args.allow_incomplete_evidence, progress=progress)
        report.update(status=job.status, message=job.message, data_readiness=job.params.get("data_readiness"))
        save("new_run.json", saved_source(job))
        if job.status == "completed":
            report["new_optimizer_run_id"] = job.job_id
            packet = build_packet(saved_source(job), ai_requested_entries=args.ai_requested_entries,
                                  allow_incomplete_evidence=args.allow_incomplete_evidence)
            save("AI_SHOWDOWN_SELECTION_PACKET.json", packet)
            (directory / "AI_SHOWDOWN_SELECTION_PACKET.md").write_text(render_markdown(packet))
            report["packet_evidence_hash"] = packet["evidence_hash"]
    except ShowdownDataNotReady as exc:
        report.update(status="blocked", message=str(exc), data_readiness=exc.readiness,
                      new_optimizer_run_id=None, solver_called=False)
    except Exception as exc:
        report.update(status="ERROR", message=f"{type(exc).__name__}: {exc}", new_optimizer_run_id=None)
    diagnostic = (report.get("data_readiness") or {}).get("player_pool_readiness")
    if diagnostic:
        save("SHOWDOWN_PLAYER_POOL_READINESS.json", diagnostic)
    after = service._load_persisted_job(old.job_id)
    report["old_run_unchanged"] = after is not None and digest(before) == digest(saved_source(after))
    save("pipeline_attempt.json", report)
    print(json.dumps({"status": report["status"], "new_optimizer_run_id": report.get("new_optimizer_run_id"),
                      "old_run_unchanged": report["old_run_unchanged"], "output_dir": str(directory)}, indent=2))


if __name__ == "__main__":
    main()
