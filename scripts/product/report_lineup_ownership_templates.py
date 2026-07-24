#!/usr/bin/env python3
"""Report ownership templates used by winning and high-finishing DK lineups."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.product_services.ownership import OwnershipService


BUCKET_ORDER = ["mega_chalk", "chalk", "popular", "mid", "low", "dart", "unknown"]


@dataclass(frozen=True)
class OwnershipBucket:
    bucket: str
    min_pct: float | None
    max_pct: float | None


BUCKETS = [
    OwnershipBucket("mega_chalk", 30.0, None),
    OwnershipBucket("chalk", 20.0, 30.0),
    OwnershipBucket("popular", 15.0, 20.0),
    OwnershipBucket("mid", 10.0, 15.0),
    OwnershipBucket("low", 5.0, 10.0),
    OwnershipBucket("dart", 0.0, 5.0),
]


def build_connection_url(args: argparse.Namespace) -> URL:
    database = args.database or os.getenv("PGDATABASE")
    if not database:
        raise RuntimeError("Database is required. Pass --database or set PGDATABASE.")
    return URL.create(
        drivername="postgresql",
        username=args.user or os.getenv("PGUSER"),
        password=args.password or os.getenv("PGPASSWORD"),
        host=args.host or os.getenv("PGHOST", "localhost"),
        port=int(args.port or os.getenv("PGPORT", "5432")),
        database=database,
    )


def ownership_bucket(value: float | None) -> str:
    if value is None:
        return "unknown"
    try:
        pct = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if not math.isfinite(pct):
        return "unknown"
    for bucket in BUCKETS:
        if bucket.min_pct is not None and pct < bucket.min_pct:
            continue
        if bucket.max_pct is not None and pct >= bucket.max_pct:
            continue
        return bucket.bucket
    return "unknown"


def bucket_sort_key(bucket: str) -> int:
    try:
        return BUCKET_ORDER.index(bucket)
    except ValueError:
        return len(BUCKET_ORDER)


def load_slates(engine, season: int | None, week: int | None, slate: str | None) -> list[dict[str, Any]]:
    where = []
    params: dict[str, Any] = {}
    if season is not None:
        where.append("season = :season")
        params["season"] = season
    if week is not None:
        where.append("week = :week")
        params["week"] = week
    if slate is not None:
        where.append("slate = :slate")
        params["slate"] = slate
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT season, week, slate, COUNT(*) AS entries
                FROM dk_contest_entries
                {where_sql}
                GROUP BY season, week, slate
                ORDER BY season, week, slate
                """
            ),
            params,
        ).mappings().all()
    return [dict(row) for row in rows]


def load_top_entries(engine, season: int, week: int, slate: str, top_n: int, top_pct: float) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        total = conn.execute(
            text(
                "SELECT COUNT(*) FROM dk_contest_entries "
                "WHERE season = :season AND week = :week AND slate = :slate"
            ),
            {"season": season, "week": week, "slate": slate},
        ).scalar_one()
        limit = min(int(total), max(1, min(top_n, math.ceil(int(total) * top_pct))))
        rows = conn.execute(
            text(
                """
                SELECT entry_id, rank, entry_points, lineup_text
                FROM dk_contest_entries
                WHERE season = :season AND week = :week AND slate = :slate
                ORDER BY rank ASC NULLS LAST, entry_points DESC NULLS LAST, entry_id
                LIMIT :limit
                """
            ),
            {"season": season, "week": week, "slate": slate, "limit": limit},
        ).mappings().all()
    return [dict(row) for row in rows]


def load_ownership_lookup(engine, season: int, week: int, slate: str) -> dict[str, float]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT player_display_name, MAX(projected_ownership) AS ownership
                FROM dk_ownership
                WHERE season = :season AND week = :week AND slate = :slate
                GROUP BY player_display_name
                """
            ),
            {"season": season, "week": week, "slate": slate},
        ).mappings().all()
    return {OwnershipService._norm_player_name(row["player_display_name"]): float(row["ownership"] or 0.0) for row in rows}


def slot_template(players: list[dict[str, Any]]) -> str:
    slot_counts: dict[str, int] = defaultdict(int)
    pieces = []
    for player in players:
        slot = str(player["roster_position"] or "UNK")
        slot_counts[slot] += 1
        suffix = str(slot_counts[slot]) if slot_counts[slot] > 1 else ""
        pieces.append(f"{slot}{suffix}:{player['bucket']}")
    return "|".join(pieces)


def bucket_count_signature(players: list[dict[str, Any]]) -> str:
    counts = Counter(player["bucket"] for player in players)
    return ",".join(f"{bucket}={counts[bucket]}" for bucket in BUCKET_ORDER if counts[bucket])


def summarize_slate(engine, season: int, week: int, slate: str, top_n: int, top_pct: float) -> dict[str, Any]:
    entries = load_top_entries(engine, season, week, slate, top_n=top_n, top_pct=top_pct)
    ownership_lookup = load_ownership_lookup(engine, season, week, slate)

    lineups = []
    slot_bucket_counts: dict[str, Counter] = defaultdict(Counter)
    bucket_counts = Counter()
    template_counts = Counter()
    bucket_signature_counts = Counter()
    unmatched_players = Counter()

    for entry in entries:
        parsed = OwnershipService._parse_lineup(entry.get("lineup_text"))
        players = []
        for player in parsed:
            name = player["player_display_name"]
            ownership = ownership_lookup.get(OwnershipService._norm_player_name(name))
            bucket = ownership_bucket(ownership)
            if ownership is None:
                unmatched_players[name] += 1
            enriched = {
                "roster_position": player["roster_position"],
                "player_display_name": name,
                "ownership": ownership,
                "bucket": bucket,
            }
            players.append(enriched)
            slot_bucket_counts[player["roster_position"]][bucket] += 1
            bucket_counts[bucket] += 1
        template = slot_template(players)
        bucket_signature = bucket_count_signature(players)
        template_counts[template] += 1
        bucket_signature_counts[bucket_signature] += 1
        lineups.append(
            {
                "entry_id": entry["entry_id"],
                "rank": int(entry["rank"] or 0),
                "points": float(entry["entry_points"] or 0.0),
                "template": template,
                "bucket_signature": bucket_signature,
                "total_ownership": round(sum(float(p["ownership"] or 0.0) for p in players), 2),
                "players": players,
            }
        )

    contest_type = "showdown" if any(
        any(player["roster_position"] == "CPT" for player in row["players"]) for row in lineups
    ) else "classic"
    lineup_count = max(len(lineups), 1)
    avg_total_ownership = sum(row["total_ownership"] for row in lineups) / lineup_count if lineups else 0.0
    avg_bucket_counts = {
        bucket: round(
            sum(Counter(p["bucket"] for p in row["players"])[bucket] for row in lineups) / lineup_count,
            2,
        )
        for bucket in BUCKET_ORDER
    }

    return {
        "season": season,
        "week": week,
        "slate": slate,
        "contest_type": contest_type,
        "entries_analyzed": len(lineups),
        "avg_total_ownership": round(avg_total_ownership, 2),
        "avg_bucket_counts_per_lineup": avg_bucket_counts,
        "slot_bucket_distribution": {
            slot: {
                bucket: {
                    "count": int(count),
                    "pct": round((count / sum(counter.values())) * 100, 2) if sum(counter.values()) else 0.0,
                }
                for bucket, count in sorted(counter.items(), key=lambda item: bucket_sort_key(item[0]))
            }
            for slot, counter in sorted(slot_bucket_counts.items())
        },
        "top_slot_templates": [
            {"template": template, "lineups": int(count), "pct": round(count / lineup_count * 100, 2)}
            for template, count in template_counts.most_common(10)
        ],
        "top_bucket_signatures": [
            {"signature": signature, "lineups": int(count), "pct": round(count / lineup_count * 100, 2)}
            for signature, count in bucket_signature_counts.most_common(10)
        ],
        "top_lineups": lineups[:10],
        "unmatched_players": [
            {"player_display_name": name, "count": int(count)} for name, count in unmatched_players.most_common(20)
        ],
    }


def aggregate_report(slates: list[dict[str, Any]]) -> dict[str, Any]:
    bucket_weighted = Counter()
    slot_bucket_weighted: dict[str, Counter] = defaultdict(Counter)
    signature_counts = Counter()
    lineup_total = 0
    ownership_total = 0.0

    for slate in slates:
        lineups = int(slate["entries_analyzed"])
        lineup_total += lineups
        ownership_total += float(slate["avg_total_ownership"] or 0.0) * lineups
        for bucket, avg in slate["avg_bucket_counts_per_lineup"].items():
            bucket_weighted[bucket] += float(avg or 0.0) * lineups
        for slot, distribution in slate["slot_bucket_distribution"].items():
            for bucket, payload in distribution.items():
                slot_bucket_weighted[slot][bucket] += int(payload["count"] or 0)
        for payload in slate["top_bucket_signatures"]:
            signature_counts[payload["signature"]] += int(payload["lineups"] or 0)

    denom = max(lineup_total, 1)
    return {
        "slates": len(slates),
        "lineups_analyzed": lineup_total,
        "avg_total_ownership": round(ownership_total / denom, 2) if lineup_total else 0.0,
        "avg_bucket_counts_per_lineup": {
            bucket: round(bucket_weighted[bucket] / denom, 2) for bucket in BUCKET_ORDER
        },
        "slot_bucket_distribution": {
            slot: {
                bucket: {
                    "count": int(count),
                    "pct": round(count / sum(counter.values()) * 100, 2) if sum(counter.values()) else 0.0,
                }
                for bucket, count in sorted(counter.items(), key=lambda item: bucket_sort_key(item[0]))
            }
            for slot, counter in sorted(slot_bucket_weighted.items())
        },
        "top_bucket_signatures": [
            {"signature": signature, "lineups": int(count), "pct": round(count / denom * 100, 2)}
            for signature, count in signature_counts.most_common(10)
        ],
    }


def aggregate_by_contest_type(slates: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for slate in slates:
        grouped[str(slate.get("contest_type") or "unknown")].append(slate)
    return {contest_type: aggregate_report(rows) for contest_type, rows in sorted(grouped.items())}


def report_lineup_templates(
    engine,
    season: int | None = None,
    week: int | None = None,
    slate: str | None = None,
    top_n: int = 100,
    top_pct: float = 0.01,
    include_lineups: bool = False,
) -> dict[str, Any]:
    slate_rows = load_slates(engine, season=season, week=week, slate=slate)
    slate_reports = [
        summarize_slate(
            engine,
            season=int(row["season"]),
            week=int(row["week"]),
            slate=str(row["slate"]),
            top_n=top_n,
            top_pct=top_pct,
        )
        for row in slate_rows
    ]
    if not include_lineups:
        for slate_report in slate_reports:
            slate_report.pop("top_lineups", None)
    return {
        "filters": {"season": season, "week": week, "slate": slate, "top_n": top_n, "top_pct": top_pct},
        "ownership_buckets": [asdict(bucket) for bucket in BUCKETS] + [asdict(OwnershipBucket("unknown", None, None))],
        "aggregate": aggregate_report(slate_reports),
        "aggregate_by_contest_type": aggregate_by_contest_type(slate_reports),
        "slates": slate_reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Report ownership templates for high-finishing DK lineups.")
    parser.add_argument("--database", help="Postgres database name. Defaults to PGDATABASE.")
    parser.add_argument("--host", help="Postgres host. Defaults to PGHOST or localhost.")
    parser.add_argument("--port", help="Postgres port. Defaults to PGPORT or 5432.")
    parser.add_argument("--user", help="Postgres user. Defaults to PGUSER.")
    parser.add_argument("--password", help="Postgres password. Defaults to PGPASSWORD.")
    parser.add_argument("--season", type=int)
    parser.add_argument("--week", type=int)
    parser.add_argument("--slate")
    parser.add_argument("--top-n", type=int, default=100)
    parser.add_argument("--top-pct", type=float, default=0.01)
    parser.add_argument("--include-lineups", action="store_true", help="Include the first 10 analyzed lineups per slate.")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    engine = create_engine(build_connection_url(args))
    report = report_lineup_templates(
        engine=engine,
        season=args.season,
        week=args.week,
        slate=args.slate,
        top_n=args.top_n,
        top_pct=args.top_pct,
        include_lineups=args.include_lineups,
    )
    report["database"] = args.database or os.getenv("PGDATABASE")
    print(json.dumps(report, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
