from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.schemas import ActualTopLineupLearningRequest
from backend.app.services.lineup_learning import LineupLearningService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train/evaluate lineup ranker from stored top-actual lineups.")
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--slate", type=str, default=None)
    parser.add_argument("--top-k-label", type=int, default=100)
    parser.add_argument("--candidate-lineups-per-slate", type=int, default=3000)
    parser.add_argument("--training-window-slates", type=int, default=24)
    parser.add_argument("--min-training-slates", type=int, default=4)
    parser.add_argument("--min-training-rows", type=int, default=2000)
    parser.add_argument("--selection-size", type=int, default=100)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--show-rows", type=int, default=25)
    parser.add_argument("--quiet-progress", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    request = ActualTopLineupLearningRequest(
        source_system=args.source_system,
        season_start=args.season_start,
        season_end=args.season_end,
        slate=args.slate,
        top_k_label=args.top_k_label,
        candidate_lineups_per_slate=args.candidate_lineups_per_slate,
        training_window_slates=args.training_window_slates,
        min_training_slates=args.min_training_slates,
        min_training_rows=args.min_training_rows,
        selection_size=args.selection_size,
        random_seed=args.random_seed,
    )

    with SessionLocal() as session:
        service = LineupLearningService(session)
        progress_hook = None if args.quiet_progress else (lambda message: print(message, flush=True))
        result = service.run_actual_top_lineup_learning(request, progress_hook=progress_hook)

    summary = {
        "source_system": result.source_system,
        "season_start": result.season_start,
        "season_end": result.season_end,
        "slate": result.slate,
        "top_k_label": result.top_k_label,
        "candidate_lineups_per_slate": result.candidate_lineups_per_slate,
        "slates_total": result.slates_total,
        "slates_evaluated": result.slates_evaluated,
        "slates_warmup_or_failed": result.slates_warmup_or_failed,
        "mean_selected_points": result.mean_selected_points,
        "mean_random_points": result.mean_random_points,
        "points_uplift": result.points_uplift,
    }
    print(json.dumps(summary, indent=2))

    print(f"\nTop feature insights ({min(8, len(result.feature_insights))}):")
    for row in result.feature_insights[:8]:
        print(f"  {row.feature_name:<32} {row.direction:<8} {row.weight:>8.4f}")

    show = min(args.show_rows, len(result.rows))
    if show > 0:
        print(f"\nFirst {show} slate rows:")
        for row in result.rows[:show]:
            line = (
                f"{row.season} W{row.week:02d} {row.slate:<20} "
                f"gen={row.generated_lineups:<5} pos={row.positives_in_pool:<4} "
                f"uplift={row.uplift_points if row.uplift_points is not None else 'NA'}"
            )
            if row.error_message:
                line += f" error={row.error_message}"
            print(line)


if __name__ == "__main__":
    main()
