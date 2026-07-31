from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.schemas import NflReadPySeasonRequest
from backend.app.services.ingest import IngestService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Load immutable nflverse weekly-roster and snap-count snapshots, then rebuild "
            "player participation and lagged team/opponent availability features."
        )
    )
    parser.add_argument("--season-start", type=int, default=2002)
    parser.add_argument("--season-end", type=int, default=datetime.now(UTC).year - 1)
    parser.add_argument(
        "--snap-season-start",
        type=int,
        default=2013,
        help="First nflverse snap-count season (default: 2013; the 2012 endpoint is empty).",
    )
    parser.add_argument("--skip-rosters", action="store_true")
    parser.add_argument("--skip-snaps", action="store_true")
    parser.add_argument("--output-json", type=str, default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    season_start = min(args.season_start, args.season_end)
    season_end = max(args.season_start, args.season_end)
    results: list[dict[str, object]] = []
    failed = False

    with SessionLocal() as session:
        service = IngestService(session)
        for season in range(season_start, season_end + 1):
            season_result: dict[str, object] = {"season": season}
            if not args.skip_rosters:
                print(f"[participation] {season} weekly rosters", flush=True)
                roster_result = service.ingest_nflreadpy_weekly_rosters(
                    NflReadPySeasonRequest(season=season)
                )
                season_result["weekly_rosters"] = roster_result.model_dump(mode="json")
                failed = failed or roster_result.status != "completed"
            if not args.skip_snaps and season >= args.snap_season_start:
                print(f"[participation] {season} snap counts", flush=True)
                snap_result = service.ingest_nflreadpy_snap_counts(
                    NflReadPySeasonRequest(season=season)
                )
                season_result["snap_counts"] = snap_result.model_dump(mode="json")
                failed = failed or snap_result.status != "completed"
            results.append(season_result)

    summary = {
        "season_start": season_start,
        "season_end": season_end,
        "snap_season_start": args.snap_season_start,
        "status": "failed" if failed else "completed",
        "seasons": results,
    }
    print(json.dumps(summary, indent=2))
    if args.output_json:
        output_path = Path(args.output_json).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"Wrote summary: {output_path}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
