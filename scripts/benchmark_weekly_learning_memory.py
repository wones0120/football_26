"""Measure learning memory in a fresh process; compare immutable saved conclusions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import resource
import subprocess
import sys
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from backend.app.product_services.slate_learning import SlateLearningService, _canonical_hash


def system_memory() -> dict:
    if sys.platform != "darwin":
        return {"swap_used_bytes": None, "pageouts": None}
    vm = subprocess.run(["vm_stat"], capture_output=True, text=True, check=True).stdout
    swap = subprocess.run(["sysctl", "vm.swapusage"], capture_output=True, text=True, check=True).stdout
    pageouts = re.search(r"Pageouts:\s+(\d+)", vm)
    used = re.search(r"used = ([\d.]+)M", swap)
    return {"swap_used_bytes": int(float(used.group(1)) * 1024 ** 2) if used else None,
            "pageouts": int(pageouts.group(1)) if pageouts else None}


def conclusions(report: dict) -> dict:
    new_keys = {"candidates", "candidate_preview", "candidate_detail", "configuration_hash", "inclusion_reason"}
    def normalize(value, key=""):
        if isinstance(value, dict):
            return {k: normalize(v, k) for k, v in value.items()}
        if isinstance(value, list):
            items = [normalize(item) for item in value]
            if key.endswith(("_frequency", "_exposure")) and all(isinstance(item, (list, tuple)) and len(item) == 2 for item in items):
                items = sorted(items, key=lambda item: (-item[1], str(item[0])))
                limit = 25 if key == "player_exposure" else 15
                if len(items) == limit:
                    boundary_count = items[-1][1]
                    # v1 used insertion order for a truncated tie group; v2 uses canonical IDs.
                    items = [["boundary_tie", count] if count == boundary_count else [identity, count]
                             for identity, count in items]
                return items
            return items
        return value
    return normalize({"summary": report["summary"], "entries": report["entries"],
            "missing_evidence": report["missing_evidence"], "run_ids": report["run_ids"],
            "runs": [{key: value for key, value in run.items() if key not in new_keys}
                     for run in report["optimizer_effectiveness"]["runs"]
                     if run.get("run_scope", "entry_linked") == "entry_linked"]})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--slate", default="SUNDAY_MAIN")
    parser.add_argument("--weekly", action="store_true", help="Build the full weekly report, including stats refresh and calibration history")
    parser.add_argument("--entry-user", required=True)
    parser.add_argument("--compare-report-id", help="Existing immutable slate report used for conclusion parity")
    parser.add_argument("--diagnostic-run-id", action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.weekly and (args.compare_report_id or args.diagnostic_run_id):
        parser.error("--compare-report-id and --diagnostic-run-id apply to individual slate benchmarks")
    service = SlateLearningService()
    baseline = None
    if args.compare_report_id:
        with service.engine.connect() as connection:
            baseline = connection.execute(text("""
                SELECT (report_json - 'optimizer_effectiveness') || jsonb_build_object(
                    'optimizer_effectiveness', jsonb_build_object('runs', (
                        SELECT jsonb_agg(run.value - 'candidates')
                        FROM jsonb_array_elements(report_json->'optimizer_effectiveness'->'runs') run(value)
                        WHERE coalesce(run.value->>'run_scope', 'entry_linked')='entry_linked'
                    ))) AS report
                FROM target.slate_learning_report WHERE report_id=:report_id
                  AND season=:season AND week=:week AND upper(slate)=:slate AND lower(entry_user)=:entry_user
            """), {"report_id": args.compare_report_id, "season": args.season, "week": args.week,
                    "slate": args.slate.upper(), "entry_user": args.entry_user.casefold()}).scalar_one()
    before = system_memory()
    started = monotonic()
    report = (service.generate_week(season=args.season, week=args.week, entry_user=args.entry_user) if args.weekly
              else service.generate(season=args.season, week=args.week, slate=args.slate, entry_user=args.entry_user,
                                    diagnostic_run_ids=args.diagnostic_run_id))
    elapsed = monotonic() - started
    response_bytes = len(json.dumps(report, default=str).encode())
    after = system_memory()
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_bytes = peak if sys.platform == "darwin" else peak * 1024
    slates = report["slate_reports"] if args.weekly else [report]
    telemetry = {key: sum(slate["telemetry"][key] for slate in slates) for key in (
        "loaded_configuration_count", "completed_configuration_bytes", "loaded_configuration_bytes", "candidate_count")}
    result = {"contract_id": "learning_memory_benchmark_v1", "report_id": report["report_id"],
              "report_contract": report["contract_id"], "evidence_hash": report["evidence_hash"],
              "season": args.season, "week": args.week, "slate": "ALL_ENTERED" if args.weekly else args.slate.upper(),
              "peak_rss_bytes": peak_bytes, "elapsed_seconds": elapsed,
              "serialized_response_bytes": response_bytes,
              "selected_optimizer_run_count": telemetry["loaded_configuration_count"],
              "total_configuration_bytes": telemetry["completed_configuration_bytes"],
              "loaded_configuration_bytes": telemetry["loaded_configuration_bytes"],
              "candidate_count": telemetry["candidate_count"],
              "included_run_ids": [run["optimizer_run_id"] for slate in slates for run in slate["optimizer_effectiveness"]["runs"]],
              "system_memory_before": before, "system_memory_after": after,
              "system_memory_deltas": {key: after[key] - before[key] if before[key] is not None and after[key] is not None else None
                                       for key in before},
              "within_memory_budget": peak_bytes <= 1_000_000_000,
              "within_response_budget": response_bytes <= 2_000_000}
    # Rehydrate only the small number of entered lineups from frozen evidence for parity.
    if args.weekly:
        result["conclusions_hash"] = _canonical_hash({key: report[key] for key in (
            "summary", "optimizer_effectiveness_history", "optimizer_correlation_aggregate")})
        encoded = json.dumps(result, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded + "\n")
        print(encoded)
        return
    for entry in report["entries"]:
        if entry.pop("entry_evidence", None):
            frozen = service.entry_detail(report["report_id"], entry["entry_id"], entry["contest_id"])
            entry.update(frozen["evidence"])
    result["conclusions_hash"] = _canonical_hash(conclusions(report))
    if baseline is not None:
        result["baseline_report_id"] = args.compare_report_id
        result["baseline_conclusions_match"] = conclusions(baseline) == conclusions(report)
        result["comparison_differences"] = [key for key in conclusions(report)
                                             if conclusions(baseline)[key] != conclusions(report)[key]]
        result["comparison_policy"] = "exact_outcome_metrics; truncated_frequency_boundary_ties_compare_counts"
    encoded = json.dumps(result, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n")
    print(encoded)


if __name__ == "__main__":
    main()
