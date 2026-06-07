from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.services.lineup_learning import LineupLearningService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build player_game_feature_matrix from curated salary + nflreadpy historical context.",
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--slate", type=str, default=None)
    parser.add_argument("--quiet-progress", action="store_true")
    parser.add_argument("--output-json", type=str, default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with SessionLocal() as session:
        service = LineupLearningService(session)
        progress_hook = None if args.quiet_progress else (lambda message: print(message, flush=True))
        summary = service.rebuild_player_game_feature_matrix(
            source_system=args.source_system,
            season_start=args.season_start,
            season_end=args.season_end,
            slate=args.slate,
            progress_hook=progress_hook,
        )

    print(json.dumps(summary, indent=2))
    if args.output_json:
        output_path = Path(args.output_json).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nWrote summary: {output_path}")


if __name__ == "__main__":
    main()
