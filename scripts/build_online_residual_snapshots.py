from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import and_, select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.models import CuratedSalary
from backend.app.schemas import ResidualSnapshotBuildRequest
from backend.app.services.simulation import SimulationService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build immutable, idempotent weekly residual-learning snapshots "
            "from completed DraftKings salary slices and nflreadpy actuals."
        )
    )
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--slate", default="sunday_main")
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--min-history-games", type=int, default=4)
    parser.add_argument("--prior-weight", type=float, default=12.0)
    parser.add_argument("--noise-scale", type=float, default=0.12)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--limit-slates", type=int, default=0)
    parser.add_argument(
        "--output-json",
        default="docs/online_residual_snapshot_backfill_2024_2025.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    season_start = min(args.season_start, args.season_end)
    season_end = max(args.season_start, args.season_end)
    if args.iterations < 500:
        raise ValueError("--iterations must be at least 500.")
    if args.limit_slates < 0:
        raise ValueError("--limit-slates cannot be negative.")

    with SessionLocal() as session:
        slices = session.execute(
            select(
                CuratedSalary.season,
                CuratedSalary.week,
                CuratedSalary.slate,
            )
            .where(
                and_(
                    CuratedSalary.source_system == "draftkings",
                    CuratedSalary.season >= season_start,
                    CuratedSalary.season <= season_end,
                    CuratedSalary.slate == args.slate,
                )
            )
            .group_by(
                CuratedSalary.season,
                CuratedSalary.week,
                CuratedSalary.slate,
            )
            .order_by(
                CuratedSalary.season,
                CuratedSalary.week,
                CuratedSalary.slate,
            )
        ).all()
        if args.limit_slates:
            slices = slices[-args.limit_slates :]
        if not slices:
            raise ValueError(
                "No matching DraftKings salary slices were found."
            )

        service = SimulationService(session)
        rows: list[dict[str, object]] = []
        failures: list[dict[str, object]] = []
        for index, (season, week, slate) in enumerate(slices, start=1):
            print(
                f"[{index}/{len(slices)}] "
                f"draftkings {season}-W{int(week):02d} {slate}",
                flush=True,
            )
            request = ResidualSnapshotBuildRequest(
                season=int(season),
                week=int(week),
                slate=str(slate),
                iterations=args.iterations,
                min_history_games=args.min_history_games,
                prior_weight=args.prior_weight,
                noise_scale=args.noise_scale,
                random_seed=args.random_seed,
            )
            try:
                result = service.build_residual_snapshot(request)
                rows.append(result.model_dump(mode="json"))
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                failures.append(
                    {
                        "season": int(season),
                        "week": int(week),
                        "slate": str(slate),
                        "error": str(exc),
                    }
                )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "config": {
            "source_system": "draftkings",
            "season_start": season_start,
            "season_end": season_end,
            "slate": args.slate,
            "iterations": args.iterations,
            "min_history_games": args.min_history_games,
            "prior_weight": args.prior_weight,
            "noise_scale": args.noise_scale,
            "random_seed": args.random_seed,
            "limit_slates": args.limit_slates,
        },
        "summary": {
            "slices_attempted": len(slices),
            "snapshots_completed": len(rows),
            "snapshots_created": sum(
                1 for row in rows if bool(row["created"])
            ),
            "snapshots_reused": sum(
                1 for row in rows if not bool(row["created"])
            ),
            "observations": sum(
                int(row["observations_count"]) for row in rows
            ),
            "failures": len(failures),
        },
        "snapshots": rows,
        "failures": failures,
    }
    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], indent=2))
    print(f"Wrote JSON: {output_path}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
