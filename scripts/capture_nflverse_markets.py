#!/usr/bin/env python3
"""Capture current nflverse schedule lines as immutable pre-lock market observations."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import nflreadpy
import polars as pl
from sqlalchemy import select, text

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.models import IngestRun, RawNflSchedule
from backend.app.product_services.market_snapshots import parse_nflverse_schedules
from backend.app.product_services.market_snapshots import canonical_team
from backend.app.services.historical_weather import schedule_kickoff_at
from backend.app.services.source_capture import SourceCaptureService


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--slate", default="all-games")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Fetch exactly once; the captured bytes, not a later upstream refresh, are parsed.
    frame = nflreadpy.load_schedules(args.season).filter(
        (pl.col("season") == args.season) & (pl.col("week") == args.week)
    )
    events = frame.to_dicts()
    if not events:
        raise SystemExit("No nflverse schedule games found for requested season/week")

    with SessionLocal() as session:
        schedule_rows = list(session.scalars(select(RawNflSchedule).where(
            RawNflSchedule.season == args.season, RawNflSchedule.week == args.week,
            RawNflSchedule.source_system == "nflreadpy",
        ).order_by(RawNflSchedule.created_at, RawNflSchedule.raw_nfl_schedule_id)))
        games = {}
        for row in schedule_rows:
            kickoff = schedule_kickoff_at(row)
            if row.game_id and kickoff:
                games[row.game_id] = {"season": row.season, "week": row.week,
                                      "game_id": row.game_id, "home_team": row.home_team,
                                      "away_team": row.away_team, "kickoff_at": kickoff}
        if not games:
            raise SystemExit("Capture the canonical nflverse schedule in the local database first")
        if args.slate.lower() != "all-games":
            salary_pairs = {
                frozenset((canonical_team(team), canonical_team(opponent)))
                for team, opponent in session.execute(text("""
                    SELECT DISTINCT team, opponent FROM public.curated_salary
                    WHERE season = :season AND week = :week AND UPPER(slate) = UPPER(:slate)
                      AND team IS NOT NULL AND opponent IS NOT NULL
                """), {"season": args.season, "week": args.week, "slate": args.slate})
            }
            if not salary_pairs:
                raise SystemExit(f"No canonical salary games found for slate {args.slate}")
            games = {
                game_id: game for game_id, game in games.items()
                if frozenset((canonical_team(game["home_team"]),
                              canonical_team(game["away_team"]))) in salary_pairs
            }
            if len(games) != len(salary_pairs):
                raise SystemExit("Salary slate games do not exactly match the canonical schedule")
            frame = frame.filter(pl.col("game_id").is_in(list(games)))
            events = frame.to_dicts()
        check_at = datetime.now(UTC)
        valid, rejected = parse_nflverse_schedules(events, schedule=games.values(),
                                                    season=args.season, week=args.week,
                                                    captured_at=check_at)
        if rejected or len(valid) != len(games):
            print(json.dumps({"accepted": len(valid), "scheduled": len(games),
                              "rejected": rejected}, indent=2))
            raise SystemExit("Market capture incomplete; no rows were ingested")
        if any(row.observed_at >= row.kickoff_at for row in valid):
            raise SystemExit("Market capture is at or after kickoff; no rows were ingested")
        if args.dry_run:
            print(json.dumps({"accepted": len(valid), "scheduled": len(games),
                              "observed_at": check_at.isoformat(), "dry_run": True}))
            return 0

        # Include fetch time in the immutable artifact so unchanged lines can be
        # observed again and receive a genuinely new freshness timestamp.
        raw = frame.to_pandas()
        raw["capture_observed_at"] = check_at.isoformat()
        capture = SourceCaptureService(session).capture_dataframe(
            raw, artifact_name=f"nflverse_market_{args.season}_w{args.week}.csv",
            source_system="nflverse", dataset="schedule_market_snapshot",
            season=args.season, week=args.week, slate=args.slate,
            source_license="nflverse/nfldata schedule data; upstream terms apply",
            source_uri="https://github.com/nflverse/nfldata/blob/master/data/games.csv",
            slate_lock_at=min(row.kickoff_at for row in valid),
            observation_basis="capture_clock",
            metadata={"spread_semantics": "positive_home_margin", "source_loader": "nflreadpy.load_schedules"},
        )
        observed_at = capture.snapshot.observed_at
        ingested_at = datetime.now(UTC)
        if observed_at >= min(row.kickoff_at for row in valid):
            raise SystemExit("Capture is at or after first kickoff; no market rows were ingested")
        ingest_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"football_26/market/{capture.snapshot.snapshot_id}"))
        if session.get(IngestRun, ingest_id):
            print(json.dumps({"ingest_run_id": ingest_id, "snapshot_id": capture.snapshot.snapshot_id,
                              "status": "already_ingested"}))
            return 0
        session.add(IngestRun(
            ingest_run_id=ingest_id, source_system="nflverse", source_table="market_snapshot",
            source_path=capture.snapshot.artifact_path,
            source_checksum=capture.snapshot.content_sha256,
            season=args.season, week=args.week, slate=args.slate.lower(), status="completed",
            rows_raw=len(events), rows_curated=len(valid), rows_unresolved=0,
            started_at=check_at.replace(tzinfo=None), completed_at=ingested_at.replace(tzinfo=None),
        ))
        session.flush()
        for row in valid:
            session.execute(text("""
                INSERT INTO target.market_snapshot
                    (market_snapshot_id, source_snapshot_id, ingest_run_id, season, week, game_id,
                     home_team, away_team, kickoff_at, game_total, home_spread, source,
                     source_game_id, observed_at, ingested_at)
                VALUES (:id, :snapshot, :ingest, :season, :week, :game, :home, :away,
                        :kickoff, :total, :spread, :source, :source_game,
                        :observed, :ingested)
            """), {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{capture.snapshot.snapshot_id}/{row.game_id}")),
                   "snapshot": capture.snapshot.snapshot_id, "ingest": ingest_id,
                   "season": row.season, "week": row.week, "game": row.game_id,
                   "home": row.home_team, "away": row.away_team, "kickoff": row.kickoff_at,
                   "total": row.game_total, "spread": row.home_spread, "source": row.source,
                   "source_game": row.source_game_id, "observed": observed_at,
                   "ingested": ingested_at})
        session.commit()
        SourceCaptureService(session).link_ingest_run(capture.snapshot.snapshot_id, ingest_id)
        print(json.dumps({"ingest_run_id": ingest_id, "snapshot_id": capture.snapshot.snapshot_id,
                          "observed_at": observed_at.isoformat(), "games": len(valid)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
