from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.schemas import ActualTopLineupBuildRequest
from backend.app.services.lineup_learning import LineupLearningService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and persist top-K actual lineups per slate.")
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--slate", type=str, default=None)
    parser.add_argument("--top-k", type=int, default=100)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--limit-slates", type=int, default=0)
    parser.add_argument("--show-rows", type=int, default=30)
    parser.add_argument("--quiet-progress", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    request = ActualTopLineupBuildRequest(
        source_system=args.source_system,
        season_start=args.season_start,
        season_end=args.season_end,
        slate=args.slate,
        top_k=args.top_k,
        overwrite_existing=args.overwrite,
        limit_slates=args.limit_slates,
    )
    with SessionLocal() as session:
        service = LineupLearningService(session)
        progress_hook = None if args.quiet_progress else (lambda message: print(message, flush=True))
        result = service.build_actual_top_lineups(request, progress_hook=progress_hook)

    summary = {
        "source_system": result.source_system,
        "season_start": result.season_start,
        "season_end": result.season_end,
        "slate": result.slate,
        "top_k": result.top_k,
        "slates_total": result.slates_total,
        "slates_completed": result.slates_completed,
        "slates_failed": result.slates_failed,
        "rows_written": result.rows_written,
    }
    print(json.dumps(summary, indent=2))

    show = min(args.show_rows, len(result.rows))
    if show > 0:
        print(f"\nFirst {show} slice results:")
        for row in result.rows[:show]:
            line = (
                f"{row.season} W{row.week:02d} {row.slate:<20} "
                f"status={row.status:<16} rows={row.rows_written}"
            )
            if row.error_message:
                line += f" error={row.error_message}"
            print(line)


if __name__ == "__main__":
    main()
