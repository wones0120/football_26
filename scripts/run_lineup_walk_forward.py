from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.schemas import LineupLearningRequest
from backend.app.services.lineup_learning import LineupLearningService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run walk-forward data-driven lineup learning over historical slates.",
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--slate", type=str, default=None)
    parser.add_argument("--lineups-per-slate", type=int, default=6000)
    parser.add_argument("--selection-size", type=int, default=150)
    parser.add_argument("--min-training-slates", type=int, default=6)
    parser.add_argument("--min-training-rows", type=int, default=15000)
    parser.add_argument("--training-window-slates", type=int, default=24)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--show-top", type=int, default=15, help="Show top N slates by points uplift.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    request = LineupLearningRequest(
        source_system=args.source_system,
        season_start=args.season_start,
        season_end=args.season_end,
        slate=args.slate,
        lineups_per_slate=args.lineups_per_slate,
        selection_size=args.selection_size,
        min_training_slates=args.min_training_slates,
        min_training_rows=args.min_training_rows,
        training_window_slates=args.training_window_slates,
        random_seed=args.random_seed,
    )
    with SessionLocal() as session:
        service = LineupLearningService(session)
        result = service.run_walk_forward_learning(request)

    summary = {
        "source_system": result.source_system,
        "season_start": result.season_start,
        "season_end": result.season_end,
        "slate": result.slate,
        "lineups_per_slate": result.lineups_per_slate,
        "slates_total": result.slates_total,
        "slates_evaluated": result.slates_evaluated,
        "slates_warmup_or_failed": result.slates_warmup_or_failed,
        "mean_selected_points": result.mean_selected_points,
        "mean_random_points": result.mean_random_points,
        "points_uplift": result.points_uplift,
        "mean_selected_top1pct_rate": result.mean_selected_top1pct_rate,
        "mean_random_top1pct_rate": result.mean_random_top1pct_rate,
        "top1pct_rate_uplift": result.top1pct_rate_uplift,
        "discovered_patterns": result.discovered_patterns,
        "feature_insights": [
            {
                "feature_name": row.feature_name,
                "weight": row.weight,
                "direction": row.direction,
            }
            for row in result.feature_insights
        ],
    }
    print(json.dumps(summary, indent=2))

    rows = [row for row in result.rows if row.uplift_points is not None]
    rows.sort(key=lambda row: row.uplift_points or -9999, reverse=True)
    print(f"\nTop {min(args.show_top, len(rows))} slates by points uplift:")
    for row in rows[: args.show_top]:
        print(
            f"  {row.season}-W{row.week:02d} {row.slate:<20} "
            f"{row.mean_selected_points:.2f} vs {row.mean_random_points:.2f} "
            f"(+{row.uplift_points:.2f})"
        )

    failed = [row for row in result.rows if row.error_message and "Warm-up" not in row.error_message]
    if failed:
        print(f"\nFailed slates ({len(failed)}):")
        for row in failed[:20]:
            print(f"  {row.season}-W{row.week:02d} {row.slate}: {row.error_message}")


if __name__ == "__main__":
    main()
