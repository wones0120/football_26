from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.schemas import OptimalVsPredictedBacktestRequest
from backend.app.services.lineup_learning import FEATURE_NAMES, LineupLearningService


def _parse_int_grid(raw: str, *, minimum: int) -> list[int]:
    values = sorted({int(value.strip()) for value in raw.split(",") if value.strip()})
    if not values or any(value < minimum for value in values):
        raise ValueError(f"Expected comma-separated integers >= {minimum}.")
    return values


def _parse_float_grid(
    raw: str,
    *,
    minimum: float,
    maximum: float,
) -> list[float]:
    values = sorted({float(value.strip()) for value in raw.split(",") if value.strip()})
    if not values or any(value < minimum or value > maximum for value in values):
        raise ValueError(
            f"Expected comma-separated numbers between {minimum} and {maximum}."
        )
    return values


def _select_best_run(
    runs: list[dict[str, Any]],
    *,
    min_completed_rate: float,
) -> dict[str, Any] | None:
    eligible = [
        row
        for row in runs
        if row.get("status") == "ok"
        and row.get("mean_gap_points") is not None
        and float(row.get("completed_rate") or 0.0) >= min_completed_rate
    ]
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda row: (
            float(row["mean_gap_points"]),
            float(row["median_gap_points"]),
            -int(row["slates_completed"]),
            int(row["config"]["lineups_per_slate"]),
            int(row["config"]["training_window_slates"]),
            float(row["config"]["classic_top_target_percentile"]),
        ),
    )


def _git_metadata() -> tuple[str | None, bool | None]:
    revision_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if revision_result.returncode != 0:
        return None, None
    status_result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    tracked_worktree_dirty = (
        bool(status_result.stdout.strip())
        if status_result.returncode == 0
        else None
    )
    return revision_result.stdout.strip() or None, tracked_worktree_dirty


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sweep classic walk-forward lineup parameters and persist the best configuration.",
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--slate", type=str, default=None)
    parser.add_argument("--candidate-lineups", default="300,600,1000")
    parser.add_argument("--training-windows", default="12,24,36")
    parser.add_argument("--top-target-percentiles", default="95,98")
    parser.add_argument("--min-training-slates", type=int, default=4)
    parser.add_argument("--min-training-rows", type=int, default=1200)
    parser.add_argument("--min-completed-rate", type=float, default=0.60)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--limit-slates", type=int, default=0)
    parser.add_argument("--quiet-progress", action="store_true")
    parser.add_argument("--output-json", type=str, required=True)
    parser.add_argument("--best-config-json", type=str, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    candidate_lineups = _parse_int_grid(args.candidate_lineups, minimum=100)
    training_windows = _parse_int_grid(args.training_windows, minimum=2)
    top_target_percentiles = _parse_float_grid(
        args.top_target_percentiles,
        minimum=80.0,
        maximum=99.5,
    )
    if not 0.0 <= args.min_completed_rate <= 1.0:
        raise ValueError("--min-completed-rate must be between 0 and 1.")

    parameter_grid = list(product(
        candidate_lineups,
        training_windows,
        top_target_percentiles,
    ))
    runs: list[dict[str, Any]] = []
    with SessionLocal() as session:
        service = LineupLearningService(session)
        for index, (lineups_per_slate, training_window, target_percentile) in enumerate(
            parameter_grid,
            start=1,
        ):
            config = {
                "lineups_per_slate": lineups_per_slate,
                "training_window_slates": training_window,
                "classic_top_target_percentile": target_percentile,
                "min_training_slates": args.min_training_slates,
                "min_training_rows": args.min_training_rows,
            }
            request = OptimalVsPredictedBacktestRequest(
                source_system=args.source_system,
                season_start=args.season_start,
                season_end=args.season_end,
                slate=args.slate,
                slate_type="classic",
                lineups_per_slate=lineups_per_slate,
                training_window_slates=training_window,
                min_training_slates=args.min_training_slates,
                min_training_rows=args.min_training_rows,
                classic_top_target_percentile=target_percentile,
                learned_only=True,
                random_seed=args.random_seed,
                limit_slates=args.limit_slates,
            )
            label = (
                f"{index}/{len(parameter_grid)} candidates={lineups_per_slate} "
                f"window={training_window} target_p={target_percentile:g}"
            )
            if not args.quiet_progress:
                print(f"[classic_sweep] start {label}", flush=True)
            try:
                hook = (
                    None
                    if args.quiet_progress
                    else (lambda message, run_label=label: print(
                        f"[classic_sweep {run_label}] {message}",
                        flush=True,
                    ))
                )
                response = service.run_optimal_vs_predicted_backtest(
                    request,
                    progress_hook=hook,
                )
                completed_rate = (
                    float(response.slates_completed / response.slates_total)
                    if response.slates_total > 0
                    else 0.0
                )
                runs.append({
                    "status": "ok",
                    "config": config,
                    "slates_total": response.slates_total,
                    "slates_completed": response.slates_completed,
                    "slates_failed_or_skipped": response.slates_failed_or_skipped,
                    "completed_rate": completed_rate,
                    "mean_gap_points": response.mean_gap_points,
                    "median_gap_points": response.median_gap_points,
                    "best_case_gap_points": response.best_case_gap_points,
                    "worst_case_gap_points": response.worst_case_gap_points,
                })
            except Exception as exc:  # noqa: BLE001
                runs.append({
                    "status": "failed",
                    "config": config,
                    "error_message": str(exc),
                })
            if not args.quiet_progress:
                print(f"[classic_sweep] done {label} status={runs[-1]['status']}", flush=True)

    best = _select_best_run(runs, min_completed_rate=args.min_completed_rate)
    if best is None:
        raise ValueError(
            "No sweep configuration met the completed-slate requirement with a non-null mean gap."
        )

    feature_set_hash = hashlib.sha256(
        json.dumps(FEATURE_NAMES, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    generated_at = datetime.now(UTC).isoformat()
    code_revision, tracked_worktree_dirty = _git_metadata()
    metadata = {
        "generated_at": generated_at,
        "code_revision": code_revision,
        "tracked_worktree_dirty": tracked_worktree_dirty,
        "feature_set_hash": feature_set_hash,
        "feature_names": FEATURE_NAMES,
        "source_system": args.source_system,
        "season_start": min(args.season_start, args.season_end),
        "season_end": max(args.season_start, args.season_end),
        "slate": args.slate,
        "random_seed": args.random_seed,
        "limit_slates": args.limit_slates,
        "learned_only": True,
        "external_priors_enabled": False,
        "selection_objective": (
            "Minimum mean actual-optimal gap among runs meeting min_completed_rate; "
            "then median gap, completed slates, and lower-cost parameters."
        ),
        "min_completed_rate": args.min_completed_rate,
        "evaluated_configurations": len(runs),
    }
    sweep_payload = {
        "metadata": metadata,
        "parameter_grid": {
            "candidate_lineups": candidate_lineups,
            "training_windows": training_windows,
            "top_target_percentiles": top_target_percentiles,
            "min_training_slates": args.min_training_slates,
            "min_training_rows": args.min_training_rows,
        },
        "best_run": best,
        "runs": runs,
    }
    best_config_payload = {
        "metadata": metadata,
        "best_config": best["config"],
        "acceptance_metrics": {
            key: best[key]
            for key in (
                "slates_total",
                "slates_completed",
                "completed_rate",
                "mean_gap_points",
                "median_gap_points",
                "best_case_gap_points",
                "worst_case_gap_points",
            )
        },
    }

    output_path = Path(args.output_json).expanduser().resolve()
    best_config_path = Path(args.best_config_json).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    best_config_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(sweep_payload, indent=2), encoding="utf-8")
    best_config_path.write_text(json.dumps(best_config_payload, indent=2), encoding="utf-8")
    print(json.dumps(best_config_payload, indent=2))
    print(f"\nWrote sweep: {output_path}")
    print(f"Wrote best config: {best_config_path}")


if __name__ == "__main__":
    main()
