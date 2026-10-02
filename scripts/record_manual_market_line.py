#!/usr/bin/env python3
"""Record a traceable pre-lock market-line override without mutating source rows."""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import and_, select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.models import (
    IngestRun,
    RawNflSchedule,
    SourceSnapshotIngestRun,
)
from backend.app.services.source_capture import SourceCaptureService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--slate", required=True)
    parser.add_argument("--home-team", required=True)
    parser.add_argument("--away-team", required=True)
    parser.add_argument("--total", type=float, required=True)
    parser.add_argument(
        "--home-margin",
        type=float,
        required=True,
        help="Expected home-team margin; positive means the home team is favored.",
    )
    parser.add_argument("--note", required=True)
    parser.add_argument("--source-uri")
    parser.add_argument(
        "--source-kind", choices=("user_supplied", "public_page"),
        default="user_supplied",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    home_team = args.home_team.strip().upper()
    away_team = args.away_team.strip().upper()
    observed_at = datetime.now(UTC)
    if args.source_kind == "public_page" and not args.source_uri:
        raise SystemExit("A public-page market observation requires --source-uri")
    source_system = "public_market" if args.source_kind == "public_page" else "manual_market"

    with SessionLocal() as session:
        source_row = session.scalar(
            select(RawNflSchedule)
            .where(
                and_(
                    RawNflSchedule.season == args.season,
                    RawNflSchedule.week == args.week,
                    RawNflSchedule.home_team == home_team,
                    RawNflSchedule.away_team == away_team,
                )
            )
            .order_by(
                RawNflSchedule.created_at.desc(),
                RawNflSchedule.raw_nfl_schedule_id.desc(),
            )
            .limit(1)
        )
        if source_row is None:
            raise SystemExit(
                f"No schedule row found for {away_team} at {home_team}, "
                f"{args.season} Week {args.week}."
            )

        evidence = {
            "season": args.season,
            "week": args.week,
            "slate": args.slate.strip().upper(),
            "game_id": source_row.game_id,
            "home_team": home_team,
            "away_team": away_team,
            "total_line": args.total,
            "spread_line": args.home_margin,
            "spread_semantics": "positive_home_margin",
            "note": args.note,
            "observed_at": observed_at.isoformat(),
        }
        capture = SourceCaptureService(session).capture_dataframe(
            pd.DataFrame([evidence]),
            artifact_name=(
                f"{source_system}_{args.season}_{args.week:02d}_"
                f"{away_team}_{home_team}.csv"
            ),
            source_system=source_system,
            dataset="schedule_market_line",
            season=args.season,
            week=args.week,
            slate=args.slate,
            source_license=("Publicly displayed market observation"
                            if args.source_kind == "public_page"
                            else "User-supplied market observation"),
            source_uri=args.source_uri,
            effective_at=observed_at,
            observation_basis=args.source_kind,
            metadata={
                "note": args.note,
                "spread_semantics": "positive_home_margin",
                "approximate": args.source_kind == "user_supplied",
            },
        )
        ingest_run_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"football_26/{source_system}/{capture.snapshot.snapshot_id}",
            )
        )
        if session.get(IngestRun, ingest_run_id) is not None:
            print(
                f"Manual market snapshot already recorded: {capture.snapshot.snapshot_id}"
            )
            return 0

        payload = dict(source_row.raw_row_json or {})
        payload.update(evidence)
        session.add(
            IngestRun(
                ingest_run_id=ingest_run_id,
                source_system=source_system,
                source_table="nfl_schedule_market_line",
                source_path=capture.snapshot.artifact_path,
                source_checksum=capture.snapshot.content_sha256,
                season=args.season,
                week=args.week,
                slate=args.slate.strip().lower(),
                status="completed",
                rows_raw=1,
                rows_curated=1,
                rows_unresolved=0,
                started_at=observed_at.replace(tzinfo=None),
                completed_at=observed_at.replace(tzinfo=None),
            )
        )
        session.add(
            SourceSnapshotIngestRun(
                snapshot_id=capture.snapshot.snapshot_id,
                ingest_run_id=ingest_run_id,
            )
        )
        session.add(
            RawNflSchedule(
                ingest_run_id=ingest_run_id,
                source_system=source_system,
                season=args.season,
                week=args.week,
                game_id=source_row.game_id,
                home_team=home_team,
                away_team=away_team,
                game_type=source_row.game_type,
                kickoff=source_row.kickoff,
                status=source_row.status,
                stadium=source_row.stadium,
                raw_row_json=payload,
            )
        )
        session.commit()

        print(f"Recorded snapshot: {capture.snapshot.snapshot_id}")
        print(
            f"{away_team} at {home_team}: total {args.total:.1f}, "
            f"home margin {args.home_margin:+.1f}"
        )
        print(f"Ingest run: {ingest_run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
