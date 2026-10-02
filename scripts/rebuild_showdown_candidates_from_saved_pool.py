#!/usr/bin/env python3
"""Rebuild Showdown candidates from a saved optimizer eligibility snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from backend.app.config import get_settings
from backend.app.db import engine
from backend.app.product_dependencies import get_optimizer_service
from backend.app.product_services.lineup_correlation_scoring import score_lineup_correlations
from backend.app.product_services.optimizer import (
    _json_safe,
    _saturated_showdown_correlation_summary,
    build_showdown_captain_prior,
)
from backend.app.product_services.player_context_scoring import score_player_context
from backend.app.product_services.rule_library import resolve_strategy_profile
from backend.app.product_services.showdown_single_entry import select_single_entry_lineups
from backend.app.product_services.showdown_three_max import select_small_max_lineups


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_run_id")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with engine.connect() as connection:
        source = connection.execute(text("""
            SELECT projection_run_id, season, week, slate_id, strategy, constraint_config_json
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
    profile = resolve_strategy_profile(contest_format="showdown", objective="gpp")
    pool = score_player_context(pool, profile=profile).scored_pool
    starter_ids = {
        str(row["player_id"])
        for row in config["strategy_runtime"]["starter_qb_filter"]["selected"]
    }
    pool["showdown_qb_eligible"] = pool.apply(
        lambda row: (
            str(row.get("position") or "").upper() != "QB"
            or str(row.get("player_id")) in starter_ids
        ),
        axis=1,
    )
    settings = get_settings()
    pool, captain_runtime = build_showdown_captain_prior(
        pool, model_path=settings.showdown_captain_model_path,
        strength=settings.showdown_captain_prior_strength,
    )
    pool = pool.reset_index(drop=True)
    stack_cfg = dict(config["stack_policy"])
    stack_cfg.update({
        "require_qb_captain_receiver": False,
        "require_starting_qb": True,
        "hard_qb_correlations": True,
        "opportunity_gate": True,
        "saturate_correlations": True,
        "use_role_ownership": bool(
            {"captain_ownership", "flex_ownership"} <= set(pool.columns)
            and pd.to_numeric(pool["captain_ownership"], errors="coerce").notna().any()
            and pd.to_numeric(pool["flex_ownership"], errors="coerce").notna().any()
        ),
        "ownership_weight": float(config.get("ownership_weight", 0.08)),
    })
    score_col = "optimizer_context_ceiling_score"
    candidate_limit = max(30, min(50, int(config.get("single_entry_candidate_pool_size", 40))))
    broad_count = max(10, int(candidate_limit * 0.6))
    forced_count = (candidate_limit - broad_count) // 2
    forced_captains = [
        str(player_id) for player_id in pool.sort_values(score_col, ascending=False)["player_id"]
        if str(player_id) not in set(config.get("flex_only_player_ids", []))
    ]
    teams = sorted(str(team) for team in pool["player_team"].dropna().unique())
    scripts = [
        {"script_id": f"single_entry_{kind}_{team}", "kind": kind, "team": team}
        for kind in ("run_control", "pass_led", "contrarian") for team in teams
    ]
    excluded = []
    candidates = []
    for index in range(candidate_limit):
        forced = (
            forced_captains[index - broad_count]
            if broad_count <= index < broad_count + forced_count
            and index - broad_count < len(forced_captains) else None
        )
        script_index = index - broad_count - forced_count
        script = scripts[script_index] if 0 <= script_index < len(scripts) else None
        lineup = service._solve_lineup(  # noqa: SLF001
            pool, score_col=score_col, exclude_signatures=excluded,
            # Older saved runs predate explicit propagation of this flag. Use
            # their recorded effective behavior only for frozen-pool replay.
            enforce_single_te=bool(config.get("enforce_single_te", False)), contest_type="captain",
            stack_params=stack_cfg, locked_player_ids=set(config.get("locked_player_ids", [])),
            flex_only_player_ids=set(config.get("flex_only_player_ids", [])),
            rule_profile=profile, include_control_comparison=False,
            locked_captain_player_id=forced, portfolio_script=script,
        )
        if not lineup:
            if forced or script:
                continue
            break
        excluded.append([(str(row["player_id"]), str(row["roster_position"])) for row in lineup])
        correlation = score_lineup_correlations(lineup, profile=profile)
        lineup[0]["lineup_correlation_summary"] = _saturated_showdown_correlation_summary(
            lineup, correlation
        )
        candidates.append(lineup)
    if source["strategy"] == "showdown_single_entry_portfolio":
        _, report = select_single_entry_lineups(
            candidates,
            num_contests=int(config.get("num_single_entry_contests", 1)),
            weights=config.get("single_entry_objective_weights"),
            report_candidate_limit=10,
        )
        saved_candidates = config["strategy_runtime"]["single_entry"].get("candidates", [])
        saved_signatures = {
            int(row["rank"]): tuple(tuple(item) for item in row["signature"])
            for row in saved_candidates
        }
        rebuilt_signatures = {
            int(row["rank"]): tuple(tuple(item) for item in row["signature"])
            for row in report["all_candidates"]
        }
        exact_ranks = [
            rank for rank, signature in saved_signatures.items()
            if rebuilt_signatures.get(rank) == signature
        ]
        comparison = {
            "saved_candidate_count": len(saved_candidates),
            "exact_signature_rank_count": len(exact_ranks),
            "exact_signature_ranks": exact_ranks,
        }
    else:
        contest = dict(config["strategy_runtime"]["small_max"]["contest"])
        _, report = select_small_max_lineups(
            candidates, contest=contest, entries_to_use=config.get("entries_to_use", "auto"),
            exposure_rates={
                "captain": config.get("captain_max_exposure", 1.0),
                "core": config.get("core_player_max_exposure", 1.0),
                "starting_qb": config.get("starting_qb_max_exposure", 1.0),
                "cheap_punt": config.get("cheap_punt_max_exposure", 1.0),
            },
            weights=config.get("single_entry_objective_weights"),
        )
        comparison = None
    payload = _json_safe({
        "source_optimizer_run_id": args.source_run_id,
        "projection_run_id": source["projection_run_id"],
        "source_strategy": source["strategy"],
        "saved_enforce_single_te": config.get("enforce_single_te"),
        "replay_enforce_single_te": bool(config.get("enforce_single_te", False)),
        "frozen_eligible_player_count": len(included_ids),
        "generated_candidate_count": len(candidates),
        "serialized_candidate_count": report["serialized_candidate_count"],
        "captain_prior": captain_runtime,
        "player_pool": pool.to_dict("records"),
        "report": report,
        "comparison_to_saved_candidates": comparison,
    })
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps({key: payload[key] for key in (
        "source_optimizer_run_id", "projection_run_id", "frozen_eligible_player_count",
        "generated_candidate_count", "serialized_candidate_count",
    )}, indent=2))


if __name__ == "__main__":
    main()
