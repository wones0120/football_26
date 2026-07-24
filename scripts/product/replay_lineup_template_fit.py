#!/usr/bin/env python3
"""Replay whether classic GPP ownership-template fit is enriched in top finishes."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.product_services.ownership import OwnershipService
from scripts.product.report_lineup_ownership_templates import BUCKET_ORDER, load_ownership_lookup, load_slates, ownership_bucket


@dataclass(frozen=True)
class TemplateFitPolicy:
    min_total_ownership: float = 120.0
    max_total_ownership: float = 180.0
    loose_min_total_ownership: float = 100.0
    loose_max_total_ownership: float = 200.0
    min_mega_chalk: int = 1
    max_mega_chalk: int = 3
    min_chalk_plus_mega: int = 2
    max_chalk_plus_mega: int = 4
    min_low_plus_dart: int = 2
    max_low_plus_dart: int = 4
    min_dart: int = 1
    max_dart: int = 3
    strong_fit_score: int = 8
    weak_fit_score: int = 4


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


def count_between(value: int, min_value: int, max_value: int) -> bool:
    return min_value <= value <= max_value


def score_classic_template(players: list[dict[str, Any]], policy: TemplateFitPolicy = TemplateFitPolicy()) -> dict[str, Any]:
    buckets = Counter(player["bucket"] for player in players)
    slots = Counter(player["roster_position"] for player in players)
    total_ownership = sum(float(player.get("ownership") or 0.0) for player in players)
    score = 0
    checks = []

    def add_check(name: str, passed: bool, points: int) -> None:
        nonlocal score
        if passed:
            score += points
        checks.append({"name": name, "passed": passed, "points": points if passed else 0, "max_points": points})

    add_check("classic_roster_shape", len(players) == 9 and not slots.get("CPT"), 1)
    add_check("total_ownership_target", policy.min_total_ownership <= total_ownership <= policy.max_total_ownership, 2)
    if not checks[-1]["passed"]:
        add_check(
            "total_ownership_loose",
            policy.loose_min_total_ownership <= total_ownership <= policy.loose_max_total_ownership,
            1,
        )
    add_check("mega_chalk_count", count_between(buckets["mega_chalk"], policy.min_mega_chalk, policy.max_mega_chalk), 2)
    add_check(
        "chalk_plus_mega_count",
        count_between(buckets["mega_chalk"] + buckets["chalk"], policy.min_chalk_plus_mega, policy.max_chalk_plus_mega),
        1,
    )
    add_check(
        "low_plus_dart_count",
        count_between(buckets["low"] + buckets["dart"], policy.min_low_plus_dart, policy.max_low_plus_dart),
        2,
    )
    add_check("dart_count", count_between(buckets["dart"], policy.min_dart, policy.max_dart), 1)
    add_check("rb_has_chalk_or_mega", any(p["roster_position"] == "RB" and p["bucket"] in {"chalk", "mega_chalk"} for p in players), 1)
    add_check("dst_not_chalk", any(p["roster_position"] == "DST" and float(p.get("ownership") or 0.0) < 20 for p in players), 1)
    add_check("wr_has_low_or_dart", any(p["roster_position"] == "WR" and p["bucket"] in {"low", "dart"} for p in players), 1)

    return {
        "score": score,
        "total_ownership": round(total_ownership, 2),
        "bucket_counts": {bucket: int(buckets[bucket]) for bucket in BUCKET_ORDER if buckets[bucket]},
        "checks": checks,
    }


def load_entries(engine, season: int, week: int, slate: str, limit: int | None = None) -> list[dict[str, Any]]:
    limit_sql = "LIMIT :limit" if limit else ""
    params: dict[str, Any] = {"season": season, "week": week, "slate": slate}
    if limit:
        params["limit"] = limit
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT entry_id, rank, entry_points, lineup_text
                FROM dk_contest_entries
                WHERE season = :season AND week = :week AND slate = :slate
                  AND lineup_text IS NOT NULL
                ORDER BY rank ASC NULLS LAST, entry_points DESC NULLS LAST, entry_id
                {limit_sql}
                """
            ),
            params,
        ).mappings().all()
    return [dict(row) for row in rows]


def count_entries(engine, season: int, week: int, slate: str) -> int:
    with engine.begin() as conn:
        return int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM dk_contest_entries "
                    "WHERE season = :season AND week = :week AND slate = :slate"
                ),
                {"season": season, "week": week, "slate": slate},
            ).scalar_one()
            or 0
        )


def classify_finish(rank: int, total_entries: int) -> dict[str, bool]:
    denom = max(total_entries, 1)
    percentile = rank / denom
    return {
        "top_0_1_pct": percentile <= 0.001,
        "top_1_pct": percentile <= 0.01,
        "top_5_pct": percentile <= 0.05,
        "top_20_pct": percentile <= 0.20,
    }


def rate(num: int, denom: int) -> float:
    return round(num / denom, 6) if denom else 0.0


def summarize_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    if not rows:
        return {
            "lineups": 0,
            "avg_rank_percentile": 0.0,
            "avg_points": 0.0,
            "avg_template_score": 0.0,
            "top_0_1_pct_rate": 0.0,
            "top_1_pct_rate": 0.0,
            "top_5_pct_rate": 0.0,
            "top_20_pct_rate": 0.0,
        }
    return {
        "lineups": count,
        "avg_rank_percentile": round(sum(row["rank_percentile"] for row in rows) / count, 6),
        "avg_points": round(sum(row["points"] for row in rows) / count, 3),
        "avg_template_score": round(sum(row["template_score"] for row in rows) / count, 3),
        "top_0_1_pct_rate": rate(sum(1 for row in rows if row["finish"]["top_0_1_pct"]), count),
        "top_1_pct_rate": rate(sum(1 for row in rows if row["finish"]["top_1_pct"]), count),
        "top_5_pct_rate": rate(sum(1 for row in rows if row["finish"]["top_5_pct"]), count),
        "top_20_pct_rate": rate(sum(1 for row in rows if row["finish"]["top_20_pct"]), count),
    }


def lift(group: dict[str, Any], baseline: dict[str, Any], key: str) -> float:
    base = float(baseline.get(key) or 0.0)
    if base == 0:
        return 0.0
    return round(float(group.get(key) or 0.0) / base, 3)


def replay_slate(
    engine,
    season: int,
    week: int,
    slate: str,
    policy: TemplateFitPolicy,
    max_entries_per_slate: int | None = None,
) -> dict[str, Any]:
    entries = load_entries(engine, season, week, slate, limit=max_entries_per_slate)
    ownership_lookup = load_ownership_lookup(engine, season, week, slate)
    total_entries = count_entries(engine, season, week, slate)
    scored = []
    skipped_showdown = 0
    unmatched_players = Counter()

    for entry in entries:
        parsed = OwnershipService._parse_lineup(entry.get("lineup_text"))
        if any(player["roster_position"] == "CPT" for player in parsed):
            skipped_showdown += 1
            continue
        players = []
        for player in parsed:
            ownership = ownership_lookup.get(OwnershipService._norm_player_name(player["player_display_name"]))
            if ownership is None:
                unmatched_players[player["player_display_name"]] += 1
            players.append(
                {
                    "roster_position": player["roster_position"],
                    "player_display_name": player["player_display_name"],
                    "ownership": ownership,
                    "bucket": ownership_bucket(ownership),
                }
            )
        if len(players) != 9:
            continue
        fit = score_classic_template(players, policy)
        rank = int(entry["rank"] or total_entries)
        scored.append(
            {
                "entry_id": str(entry["entry_id"]),
                "rank": rank,
                "rank_percentile": rank / max(total_entries, 1),
                "points": float(entry["entry_points"] or 0.0),
                "template_score": int(fit["score"]),
                "total_ownership": fit["total_ownership"],
                "bucket_counts": fit["bucket_counts"],
                "finish": classify_finish(rank, total_entries),
            }
        )

    baseline = summarize_group(scored)
    strong = [row for row in scored if row["template_score"] >= policy.strong_fit_score]
    weak = [row for row in scored if row["template_score"] <= policy.weak_fit_score]
    by_score = {str(score): summarize_group([row for row in scored if row["template_score"] == score]) for score in range(0, 13)}
    strong_summary = summarize_group(strong)
    weak_summary = summarize_group(weak)

    return {
        "season": season,
        "week": week,
        "slate": slate,
        "entries_loaded": len(entries),
        "contest_entries": total_entries,
        "classic_lineups_scored": len(scored),
        "showdown_lineups_skipped": skipped_showdown,
        "baseline": baseline,
        "strong_fit": {
            **strong_summary,
            "top_1_pct_lift": lift(strong_summary, baseline, "top_1_pct_rate"),
            "top_5_pct_lift": lift(strong_summary, baseline, "top_5_pct_rate"),
            "top_20_pct_lift": lift(strong_summary, baseline, "top_20_pct_rate"),
        },
        "weak_fit": {
            **weak_summary,
            "top_1_pct_lift": lift(weak_summary, baseline, "top_1_pct_rate"),
            "top_5_pct_lift": lift(weak_summary, baseline, "top_5_pct_rate"),
            "top_20_pct_lift": lift(weak_summary, baseline, "top_20_pct_rate"),
        },
        "by_template_score": by_score,
        "top_strong_fit_lineups": sorted(strong, key=lambda row: row["rank"])[:10],
        "unmatched_players": [
            {"player_display_name": name, "count": int(count)} for name, count in unmatched_players.most_common(20)
        ],
    }


def aggregate_replay(slates: list[dict[str, Any]], policy: TemplateFitPolicy) -> dict[str, Any]:
    baseline_rows = []
    strong_weighted = Counter()
    weak_weighted = Counter()
    totals = Counter()

    for slate in slates:
        totals["classic_lineups_scored"] += int(slate["classic_lineups_scored"])
        totals["entries_loaded"] += int(slate["entries_loaded"])
        totals["slates"] += 1
        for key in ("top_1_pct_rate", "top_5_pct_rate", "top_20_pct_rate", "avg_template_score", "avg_rank_percentile"):
            baseline_rows.append((key, float(slate["baseline"].get(key) or 0.0), int(slate["baseline"]["lineups"])))
        for key in ("top_1_pct_rate", "top_5_pct_rate", "top_20_pct_rate"):
            strong_weighted[key] += float(slate["strong_fit"].get(key) or 0.0) * int(slate["strong_fit"]["lineups"])
            weak_weighted[key] += float(slate["weak_fit"].get(key) or 0.0) * int(slate["weak_fit"]["lineups"])
        totals["strong_lineups"] += int(slate["strong_fit"]["lineups"])
        totals["weak_lineups"] += int(slate["weak_fit"]["lineups"])

    def weighted_baseline(key: str) -> float:
        values = [(value, weight) for row_key, value, weight in baseline_rows if row_key == key]
        denom = sum(weight for _, weight in values)
        return round(sum(value * weight for value, weight in values) / denom, 6) if denom else 0.0

    baseline = {
        "lineups": int(totals["classic_lineups_scored"]),
        "avg_template_score": weighted_baseline("avg_template_score"),
        "avg_rank_percentile": weighted_baseline("avg_rank_percentile"),
        "top_1_pct_rate": weighted_baseline("top_1_pct_rate"),
        "top_5_pct_rate": weighted_baseline("top_5_pct_rate"),
        "top_20_pct_rate": weighted_baseline("top_20_pct_rate"),
    }

    def weighted_group(weighted: Counter, lineups: int) -> dict[str, Any]:
        payload = {key: round(float(weighted[key]) / max(lineups, 1), 6) if lineups else 0.0 for key in weighted}
        payload["lineups"] = int(lineups)
        payload["top_1_pct_lift"] = lift(payload, baseline, "top_1_pct_rate")
        payload["top_5_pct_lift"] = lift(payload, baseline, "top_5_pct_rate")
        payload["top_20_pct_lift"] = lift(payload, baseline, "top_20_pct_rate")
        return payload

    return {
        "policy": asdict(policy),
        "slates": int(totals["slates"]),
        "entries_loaded": int(totals["entries_loaded"]),
        "classic_lineups_scored": int(totals["classic_lineups_scored"]),
        "baseline": baseline,
        "strong_fit": weighted_group(strong_weighted, int(totals["strong_lineups"])),
        "weak_fit": weighted_group(weak_weighted, int(totals["weak_lineups"])),
    }


def replay_template_fit(
    engine,
    season: int | None = None,
    week: int | None = None,
    slate: str | None = None,
    max_entries_per_slate: int | None = None,
    policy: TemplateFitPolicy = TemplateFitPolicy(),
) -> dict[str, Any]:
    slate_rows = load_slates(engine, season=season, week=week, slate=slate)
    slate_reports = []
    for row in slate_rows:
        report = replay_slate(
            engine,
            season=int(row["season"]),
            week=int(row["week"]),
            slate=str(row["slate"]),
            policy=policy,
            max_entries_per_slate=max_entries_per_slate,
        )
        if report["classic_lineups_scored"]:
            slate_reports.append(report)
    return {
        "filters": {"season": season, "week": week, "slate": slate, "max_entries_per_slate": max_entries_per_slate},
        "aggregate": aggregate_replay(slate_reports, policy),
        "slates": slate_reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay classic GPP ownership-template fit against contest standings.")
    parser.add_argument("--database", help="Postgres database name. Defaults to PGDATABASE.")
    parser.add_argument("--host", help="Postgres host. Defaults to PGHOST or localhost.")
    parser.add_argument("--port", help="Postgres port. Defaults to PGPORT or 5432.")
    parser.add_argument("--user", help="Postgres user. Defaults to PGUSER.")
    parser.add_argument("--password", help="Postgres password. Defaults to PGPASSWORD.")
    parser.add_argument("--season", type=int)
    parser.add_argument("--week", type=int)
    parser.add_argument("--slate")
    parser.add_argument("--max-entries-per-slate", type=int)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    engine = create_engine(build_connection_url(args))
    report = replay_template_fit(
        engine=engine,
        season=args.season,
        week=args.week,
        slate=args.slate,
        max_entries_per_slate=args.max_entries_per_slate,
    )
    report["database"] = args.database or os.getenv("PGDATABASE")
    print(json.dumps(report, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
