from __future__ import annotations

import argparse
import json
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
        description=(
            "Walk-forward backtest: exact actual-optimal lineup vs learned-predicted top lineup per slate."
        )
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--slate", type=str, default=None)
    parser.add_argument("--slate-type", type=str, default="classic", choices=["all", "classic", "showdown"])
    parser.add_argument("--lineups-per-slate", type=int, default=4000)
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
    parser.add_argument("--matchup-prior-gate-model-path", type=str, default=None)
    parser.add_argument("--output-json", type=str, default="")
    parser.add_argument("--quiet-progress", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.slate_type == "all":
        raise ValueError("--slate-type all is not supported by this wrapper. Use classic or showdown.")
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
        matchup_prior_gate_model_path=args.matchup_prior_gate_model_path,
    )

    with SessionLocal() as session:
        service = LineupLearningService(session)
        progress_hook = None if args.quiet_progress else (lambda message: print(message, flush=True))
        result = service.run_optimal_vs_predicted_backtest(request, progress_hook=progress_hook)
    payload = {"summary": result.model_dump(exclude={"rows"}), "rows": result.model_dump()["rows"]}
    summary = payload["summary"]

    print(json.dumps(summary, indent=2))
    if args.output_json:
        output_path = Path(args.output_json).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nWrote detailed results: {output_path}")

    print("\nTop 10 slate gaps (largest missed opportunity):")
    ranked = sorted(
        [row for row in payload["rows"] if row.get("status") == "ok"],
        key=lambda row: float(row["gap_points"]),
        reverse=True,
    )[:10]
    for row in ranked:
        print(
            f"  {row['season']} W{row['week']:02d} {row['slate']}: "
            f"optimal={row['optimal_actual_points']:.2f} "
            f"predicted={row['predicted_actual_points']:.2f} "
            f"gap={row['gap_points']:.2f}"
        )


if __name__ == "__main__":
    main()
