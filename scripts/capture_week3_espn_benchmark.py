#!/usr/bin/env python3
"""Capture ESPN's published Week 3 DK table against frozen canonical salary IDs."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

from Database.config import get_connection_string
from Database.dst import normalize_team
from backend.app.product_services.projection_audit import capture_benchmark
from scripts.validate_espn_projection_sanity import normalize_name, parse_espn_tables


SOURCE_URL = "https://www.espn.com/fantasy/football/story/_/id/50023263/draftkings-nfl-dfs-values-week-3"
FROZEN_RUN = "d150bb2a-91a8-46b6-9aa6-eaa9f0229bde"


def build_capture(connection, html: bytes, *, captured_at: str) -> dict:
    parsed = parse_espn_tables(html.decode("utf-8"))
    if not parsed or len(parsed) < 100:
        raise ValueError("ESPN source did not contain the expected full DK tables")
    lineage = connection.execute(text("""
        SELECT pr.season, pr.week, pr.slate_id, fr.source_versions_json
        FROM target.projection_run pr
        JOIN target.model_run mr ON mr.model_run_id = pr.model_run_id
        JOIN target.feature_generation_run fr ON fr.feature_run_id = mr.feature_run_id
        WHERE pr.projection_run_id = :run_id
    """), {"run_id": FROZEN_RUN}).mappings().one()
    salary_ids = lineage["source_versions_json"].get("salary_row_ids") or []
    if not salary_ids:
        raise ValueError("Frozen projection run lacks salary row IDs; identity match is unsafe")
    salary_rows = connection.execute(text("""
        SELECT curated_salary_id, player_master_id, player_name, team, position, salary
        FROM public.curated_salary WHERE curated_salary_id = ANY(:ids)
    """), {"ids": salary_ids}).mappings().all()
    projection_rows = connection.execute(text("""
        SELECT player_id, mean FROM target.player_projection
        WHERE projection_run_id = :run_id
    """), {"run_id": FROZEN_RUN}).mappings().all()
    means = {str(row["player_id"]): float(row["mean"]) for row in projection_rows}
    keys: dict[tuple, set[str]] = {}
    for row in salary_rows:
        key = (normalize_name(str(row["player_name"])), normalize_team(row["team"]),
               str(row["position"]).upper(), int(row["salary"]))
        if key[2] == "DST":
            key = ("", key[1], key[2], key[3])
        keys.setdefault(key, set()).add(str(row["player_master_id"]))
    alias_ids = [row["espn_player_id"] for row in parsed if row["espn_player_id"]]
    aliases = {str(row["source_key"]): str(row["player_master_id"])
               for row in connection.execute(text("""
                   SELECT source_key, player_master_id FROM public.player_alias
                   WHERE LOWER(source_system) = 'espn' AND source_key = ANY(:ids)
               """), {"ids": alias_ids}).mappings()}
    seen: set[str] = set()
    comparison = []
    for espn in parsed:
        key = (normalize_name(espn["player"]), normalize_team(espn["team"]),
               espn["position"], espn["salary"])
        if espn["position"] == "DST":
            key = ("", normalize_team(espn["team"]), "DST", espn["salary"])
        alias = aliases.get(str(espn["espn_player_id"]))
        candidates = ({alias} if alias and alias in means else keys.get(key, set()))
        candidates = {candidate for candidate in candidates if candidate in means}
        player_id = next(iter(candidates)) if len(candidates) == 1 else None
        if player_id in seen:
            player_id = None
        if player_id:
            seen.add(player_id)
        ours = means.get(player_id) if player_id else None
        comparison.append({
            "player_id": player_id, "player": espn["player"],
            "position": espn["position"], "team": espn["team"],
            "salary": espn["salary"], "source_player_id": espn["espn_player_id"],
            "external_mean": espn["projection"], "value_tier": espn["value_tier"],
            "our_mean": ours, "delta": ours - espn["projection"] if ours is not None else None,
            "match_method": ("espn_source_id" if alias == player_id else
                             "name_team_position_salary" if player_id else "unmatched"),
            "match_candidates": sorted(candidates) if player_id is None else [],
        })
    return {
        "projection_run_id": FROZEN_RUN,
        "source": SOURCE_URL,
        "source_published_at": "2026-09-24T21:45:20Z",
        "captured_at": captured_at,
        "raw_source_sha256": hashlib.sha256(html).hexdigest(),
        "season": lineage["season"], "week": lineage["week"],
        "slate_id": lineage["slate_id"],
        "espn_rows": len(parsed), "matched_rows": sum(r["player_id"] is not None for r in comparison),
        "rb_rows": [row for row in comparison if row["position"] == "RB"],
        "all_rows": comparison,
    }


def markdown(capture: dict) -> str:
    rb = capture["rb_rows"]
    matched = [row for row in rb if row["player_id"]]
    mean_delta = sum(row["delta"] for row in matched) / len(matched) if matched else None
    lines = ["# Week 3 ESPN RB projection benchmark", "",
             f"Official source: {capture['source']}",
             f"Published: {capture['source_published_at']}; captured: {capture['captured_at']}",
             f"Source SHA-256: `{capture['raw_source_sha256']}`",
             f"Frozen projection run: `{capture['projection_run_id']}`",
             f"Matched {len(matched)}/{len(rb)} ESPN RB rows; all-position match {capture['matched_rows']}/{capture['espn_rows']}.",
             f"Mean ours minus ESPN on matched RBs: {mean_delta:+.2f} DK points." if mean_delta is not None else "No matched RBs.",
             "", "Diagnostic comparison only; no projection or optimizer weights changed.", "",
             "| RB | Team | Salary | Our mean | ESPN mean | Our−ESPN | ESPN value tier | Match |",
             "|---|---|---:|---:|---:|---:|---|---|"]
    for row in sorted(rb, key=lambda item: abs(item["delta"] or 0), reverse=True):
        lines.append(f"| {row['player']} | {row['team']} | ${row['salary']:,} | "
                     f"{row['our_mean']:.2f} | {row['external_mean']:.2f} | {row['delta']:+.2f} | "
                     f"{row['value_tier']} | {row['match_method']} |" if row["our_mean"] is not None else
                     f"| {row['player']} | {row['team']} | ${row['salary']:,} | — | "
                     f"{row['external_mean']:.2f} | — | {row['value_tier']} | unmatched |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("html", type=Path, help="HTML fetched directly from the official ESPN URL")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("artifacts/week3-espn-benchmark-2026.json"))
    args = parser.parse_args()
    html = args.html.read_bytes()
    captured_at = datetime.now(timezone.utc).isoformat()
    engine = create_engine(get_connection_string())
    with engine.begin() as connection:
        capture = build_capture(connection, html, captured_at=captured_at)
        if args.persist:
            capture["benchmark_id"] = capture_benchmark(connection, {
                "source_name": "ESPN Mike Clay DK Week 3 2026",
                "source_url": SOURCE_URL,
                "season": capture["season"], "week": capture["week"],
                "slate_id": capture["slate_id"], "captured_at": captured_at,
                "raw_snapshot_uri": SOURCE_URL,
                "raw_snapshot_sha256": capture["raw_source_sha256"],
                "players": [
                    {"player_id": row["player_id"], "source_player_id": row["source_player_id"],
                     "projection": row["external_mean"],
                     "value": row["external_mean"] / (row["salary"] / 1000),
                     "classification": row["value_tier"]}
                    for row in capture["all_rows"] if row["player_id"]
                ],
            })
    args.output.write_text(json.dumps(capture, indent=2, sort_keys=True))
    args.output.with_suffix(".md").write_text(markdown(capture))
    print(f"ESPN {capture['matched_rows']}/{capture['espn_rows']} rows matched; "
          f"RB {sum(r['player_id'] is not None for r in capture['rb_rows'])}/{len(capture['rb_rows'])}; "
          f"benchmark_id={capture.get('benchmark_id', 'not persisted')}")


if __name__ == "__main__":
    main()
