from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.schemas import OptimalVsPredictedBacktestRequest
from backend.app.services.lineup_learning import LineupLearningService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="A/B backtest with matchup matrix model disabled vs enabled.",
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--slate", type=str, default=None)
    parser.add_argument("--slate-type", type=str, default="classic", choices=["classic", "showdown"])
    parser.add_argument("--lineups-per-slate", type=int, default=2000)
    parser.add_argument("--training-window-slates", type=int, default=24)
    parser.add_argument("--min-training-slates", type=int, default=4)
    parser.add_argument("--min-training-rows", type=int, default=2000)
    parser.add_argument("--learned-only", dest="learned_only", action="store_true")
    parser.add_argument("--allow-heuristics", dest="learned_only", action="store_false")
    parser.set_defaults(learned_only=True)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--limit-slates", type=int, default=0)
    parser.add_argument("--classic-value-driver-model-path", type=str, default=None)
    parser.add_argument("--classic-value-driver-prior-strength", type=float, default=0.0)
    parser.add_argument("--matchup-outcome-model-path", type=str, default=None)
    parser.add_argument("--matchup-outcome-prior-strength", type=float, default=0.0)
    parser.add_argument("--quiet-progress", action="store_true")
    parser.add_argument("--output-json", type=str, default="")
    return parser.parse_args()


def _mean_gap_points(rows: list[dict]) -> float | None:
    values = [
        float(row["gap_points"])
        for row in rows
        if row.get("status") == "ok" and row.get("gap_points") is not None
    ]
    if not values:
        return None
    return float(statistics.mean(values))


def _paired_improvement_counts(
    baseline_rows: list[dict],
    matrix_rows: list[dict],
) -> tuple[int, int]:
    base_map = {
        (int(row["season"]), int(row["week"]), str(row["slate"])): row
        for row in baseline_rows
        if row.get("status") == "ok" and row.get("gap_points") is not None
    }
    improved = 0
    paired = 0
    for row in matrix_rows:
        if row.get("status") != "ok" or row.get("gap_points") is None:
            continue
        key = (int(row["season"]), int(row["week"]), str(row["slate"]))
        base = base_map.get(key)
        if base is None:
            continue
        paired += 1
        if float(row["gap_points"]) < float(base["gap_points"]):
            improved += 1
    return improved, paired


def main() -> None:
    args = parse_args()
    request = OptimalVsPredictedBacktestRequest(
        source_system=args.source_system,
        season_start=args.season_start,
        season_end=args.season_end,
        slate=args.slate,
        slate_type=args.slate_type,
        lineups_per_slate=args.lineups_per_slate,
        training_window_slates=args.training_window_slates,
        min_training_slates=args.min_training_slates,
        min_training_rows=args.min_training_rows,
        learned_only=args.learned_only,
        random_seed=args.random_seed,
        limit_slates=args.limit_slates,
        classic_value_driver_model_path=args.classic_value_driver_model_path,
        classic_value_driver_prior_strength=args.classic_value_driver_prior_strength,
        matchup_outcome_model_path=args.matchup_outcome_model_path,
        matchup_outcome_prior_strength=args.matchup_outcome_prior_strength,
    )

    with SessionLocal() as session:
        service = LineupLearningService(session)
        baseline_hook = (
            None
            if args.quiet_progress
            else (lambda message: print(f"[baseline] {message}", flush=True))
        )
        service.set_matchup_matrix_projection_enabled(False)
        baseline = service.run_optimal_vs_predicted_backtest(request, progress_hook=baseline_hook)

        matrix_hook = (
            None
            if args.quiet_progress
            else (lambda message: print(f"[matrix] {message}", flush=True))
        )
        service.set_matchup_matrix_projection_enabled(True)
        matrix = service.run_optimal_vs_predicted_backtest(request, progress_hook=matrix_hook)

    baseline_summary = baseline.model_dump()
    matrix_summary = matrix.model_dump()
    baseline_rows = baseline_summary.get("rows", [])
    matrix_rows = matrix_summary.get("rows", [])
    baseline_mean_gap = _mean_gap_points(baseline_rows)
    matrix_mean_gap = _mean_gap_points(matrix_rows)
    improved_count, paired_count = _paired_improvement_counts(baseline_rows, matrix_rows)
    mean_gap_lift = None
    if baseline_mean_gap is not None and matrix_mean_gap is not None and baseline_mean_gap != 0.0:
        mean_gap_lift = ((baseline_mean_gap - matrix_mean_gap) / abs(baseline_mean_gap)) * 100.0

    payload = {
        "request": request.model_dump(),
        "baseline": {
            "slates_completed": baseline_summary.get("slates_completed"),
            "slates_failed_or_skipped": baseline_summary.get("slates_failed_or_skipped"),
            "mean_gap_points": baseline_mean_gap,
            "median_gap_points": baseline_summary.get("median_gap_points"),
        },
        "matrix": {
            "slates_completed": matrix_summary.get("slates_completed"),
            "slates_failed_or_skipped": matrix_summary.get("slates_failed_or_skipped"),
            "mean_gap_points": matrix_mean_gap,
            "median_gap_points": matrix_summary.get("median_gap_points"),
        },
        "comparison": {
            "mean_gap_lift_pct": mean_gap_lift,
            "paired_slates": paired_count,
            "paired_improved_count": improved_count,
            "paired_improved_rate": (improved_count / paired_count) if paired_count > 0 else None,
        },
        "baseline_rows": baseline_rows,
        "matrix_rows": matrix_rows,
    }

    print(json.dumps(payload, indent=2))
    if args.output_json:
        output_path = Path(args.output_json).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nWrote summary: {output_path}")


if __name__ == "__main__":
    main()
