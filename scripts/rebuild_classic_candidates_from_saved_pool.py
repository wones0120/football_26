#!/usr/bin/env python3
"""Rebuild Classic candidates from a saved optimizer eligibility snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from backend.app.db import engine
from backend.app.product_dependencies import get_optimizer_service
from backend.app.product_services.classic_small_field import analyze_small_field
from backend.app.product_services.gpp_optimizer import run_gpp_pipeline
from backend.app.product_services.optimizer import _json_safe
from backend.app.product_services.player_context_scoring import score_player_context
from backend.app.product_services.rule_library import resolve_strategy_profile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_run_id")
    parser.add_argument("output", type=Path)
    parser.add_argument("--comparison", type=Path)
    args = parser.parse_args()
    with engine.connect() as connection:
        source = connection.execute(text("""
            SELECT projection_run_id, season, week, slate_id, constraint_config_json
            FROM target.optimizer_run WHERE optimizer_run_id = :run_id
        """), {"run_id": args.source_run_id}).mappings().first()
    if source is None:
        raise SystemExit(f"Saved optimizer run {args.source_run_id} was not found")
    config = source["constraint_config_json"]
    if isinstance(config, str):
        config = json.loads(config)
    saved_rows = config["strategy_runtime"]["player_pool"]["rows"]
    included_ids = {str(row["player_id"]) for row in saved_rows if row.get("included")}
    service = get_optimizer_service()
    live = service._load_player_pool(  # noqa: SLF001 - diagnostic reconstruction
        int(source["season"]), int(source["week"]), str(source["slate_id"]),
        projection_run_id=str(source["projection_run_id"]),
    )
    pool = live[live["player_id"].astype(str).isin(included_ids)].copy()
    missing = included_ids - set(pool["player_id"].astype(str))
    if missing:
        raise RuntimeError(f"Projection pool is missing {len(missing)} saved eligible players")
    # Reapply the same context scorer to the frozen eligibility set. Safety,
    # availability, and user filters are not rerun because `included_ids` is the
    # persisted output of those stages from the source job.
    profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
    pool = score_player_context(pool, profile=profile).scored_pool
    ownership = pd.to_numeric(pool.get("ownership"), errors="coerce")
    ownership_available = bool(len(pool) and ownership.notna().sum() == len(pool))
    candidate_target = int(config.get("classic_candidate_pool_size", 120))
    result = run_gpp_pipeline(
        season=int(source["season"]), week=int(source["week"]),
        slate=str(source["slate_id"]), num_lineups=candidate_target,
        engine=engine, players=service._gpp_players_from_pool(pool),  # noqa: SLF001
        ownership_available=ownership_available, max_exposure=1.0,
        enforce_single_te=bool(config.get("enforce_single_te", False)),
        avoid_dst_opponents=bool(config.get("avoid_dst_opponents", False)),
        large_gpp=True, minimum_uniqueness=int(config.get("minimum_uniqueness", 2)),
        max_from_team=config.get("max_players_per_team"),
        max_from_game=config.get("max_players_per_game"),
        stack_templates=config.get("stack_templates"),
        maximum_exposure_by_player={player_id: 1.0 for player_id in config.get("locked_player_ids", [])},
        minimum_exposure_by_player={player_id: 1.0 for player_id in config.get("locked_player_ids", [])},
        include_control_comparisons=False,
    )
    source_rows = pool.to_dict("records")
    source_by_id = {str(row["player_id"]): row for row in source_rows}
    all_players = service._gpp_players_from_pool(pool)  # noqa: SLF001
    _, report = analyze_small_field(
        result,
        pool_rows=[{**source_by_id[player.player_id], "gpp_player": player} for player in all_players],
        count=int(config.get("num_lineups", 1)),
        max_exposure=float(config.get("max_exposure", 1.0)),
        ownership_available=ownership_available,
        locked_player_ids=set(config.get("locked_player_ids", [])),
        requested_candidate_count=candidate_target,
        enforce_single_te=bool(config.get("enforce_single_te", False)),
        avoid_dst_opponents=bool(config.get("avoid_dst_opponents", False)),
        ownership_evidence={
            "status": "available" if ownership_available else "unavailable",
            "source": "saved projection plus frozen source-job eligibility",
            "covered_players": int(ownership.notna().sum()),
            "eligible_players": len(pool),
        },
    )
    comparison = None
    if args.comparison:
        prior_payload = json.loads(args.comparison.read_text())
        prior = prior_payload["results"][0][0]["classic_small_field_report"]
        prior_signatures = [sorted(row["player_ids"]) for row in prior["top_50"]]
        rebuilt_signatures = [sorted(row["player_ids"]) for row in report["top_50"]]
        rank_mismatches = []
        for rank, (prior_row, rebuilt_row) in enumerate(
            zip(prior["top_50"], report["top_50"]), 1
        ):
            if sorted(prior_row["player_ids"]) == sorted(rebuilt_row["player_ids"]):
                continue
            prior_names = {
                str(row["player_id"]): row.get("name") for row in prior_row["roster"]
            }
            rebuilt_names = {
                str(row["player_id"]): row.get("name") for row in rebuilt_row["roster"]
            }
            rank_mismatches.append({
                "rank": rank,
                "prior_only": [prior_names[player_id] for player_id in sorted(set(prior_names) - set(rebuilt_names))],
                "rebuilt_only": [rebuilt_names[player_id] for player_id in sorted(set(rebuilt_names) - set(prior_names))],
                "prior_objective": prior_row["objective_score"],
                "rebuilt_objective": rebuilt_row["objective_score"],
                "objective_tied": abs(
                    float(prior_row["objective_score"])
                    - float(rebuilt_row["objective_score"])
                ) < 1e-12,
            })
        comparison = {
            "prior_top_50_count": len(prior_signatures),
            "rebuilt_top_50_count": len(rebuilt_signatures),
            "same_ranked_top_50": prior_signatures == rebuilt_signatures,
            "top_50_set_overlap": len(
                {tuple(row) for row in prior_signatures}
                & {tuple(row) for row in rebuilt_signatures}
            ),
            "rank_mismatches": rank_mismatches,
        }
    payload = _json_safe({
        "source_optimizer_run_id": args.source_run_id,
        "projection_run_id": source["projection_run_id"],
        "frozen_eligible_player_count": len(included_ids),
        "generated_candidate_count": len(result.lineups),
        "serialized_candidate_count": report["serialized_candidate_count"],
        "comparison_to_saved_top_50": comparison,
        "report": report,
    })
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps({key: payload[key] for key in (
        "source_optimizer_run_id", "projection_run_id", "frozen_eligible_player_count",
        "generated_candidate_count", "serialized_candidate_count",
        "comparison_to_saved_top_50",
    )}, indent=2))


if __name__ == "__main__":
    main()
