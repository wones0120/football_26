#!/usr/bin/env python3
"""Replay a saved prelock Classic slate, then score it from historical actuals."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from sqlalchemy import text

from backend.app.db import engine
from backend.app.product_dependencies import get_optimizer_service
from backend.app.product_services.classic_small_field import describe_candidate
from backend.app.product_services.gpp_optimizer import (
    ObjectiveWeights, _build_lineup, build_format_specific_terms,
    build_lineup_correlation_terms, tag_players,
)
from backend.app.product_services.rule_library import resolve_strategy_profile
from scripts.audit_sunday_main_portfolio_frontier import configuration


OUTPUT = Path("artifacts/historical-classic-quality-guard-eligibility-2026w1-w2.json")
RUN_ID = "38d3309a-637d-4d05-a79c-28907aa884c4"


def main() -> None:
    with engine.connect() as connection:
        run = dict(connection.execute(text(
            "SELECT * FROM target.optimizer_run WHERE optimizer_run_id=:id"
        ), {"id": RUN_ID}).mappings().one())
        actual_rows = [dict(row) for row in connection.execute(text(
            "SELECT player_master_id::text player_id, dk_points, game_id, position, created_at "
            "FROM public.player_game_feature_matrix WHERE season=2026 AND week=2 "
            "AND slate='SUNDAY_MAIN' AND player_master_id IS NOT NULL"
        )).mappings()]
        week_1_observed = connection.execute(text(
            "SELECT count(DISTINCT player_id) FROM target.contest_ownership_observation "
            "WHERE season=2026 AND week=1 AND slate='SUNDAY_MAIN' "
            "AND player_id IS NOT NULL AND actual_points IS NOT NULL"
        )).scalar_one()
        target_actual_rows = connection.execute(text(
            "SELECT count(*) FROM target.fact_player_game_actual WHERE season=2026 AND week=2"
        )).scalar_one()
        late_runs = [dict(row) for row in connection.execute(text(
            "SELECT optimizer_run_id, created_at, data_cutoff_at FROM target.optimizer_run "
            "WHERE season=2026 AND week=2 AND slate_id='SUNDAY_LATE' "
            "AND strategy='classic_small_field_gpp' AND status='completed' "
            "ORDER BY created_at"
        )).mappings()]
        disruptions = [dict(row) for row in connection.execute(text(
            "SELECT week,slate,tag,count(*) event_count FROM target.player_outcome_event "
            "WHERE season=2026 AND week IN (1,2) GROUP BY week,slate,tag"
        )).mappings()]
    params = run["constraint_config_json"]
    runtime = params["strategy_runtime"]
    saved = {row["player_id"]: row for row in runtime["player_pool"]["rows"]}
    frame = get_optimizer_service()._load_player_pool(
        2026, 2, "SUNDAY_MAIN", projection_run_id=str(run["projection_run_id"]))
    eligible_ids = {player_id for player_id, row in saved.items() if row["included"]}
    frame = frame[frame.player_id.astype(str).isin(eligible_ids)].copy()
    if set(frame.player_id.astype(str)) != eligible_ids:
        raise ValueError("Prelock eligible player IDs cannot be replayed exactly")
    for field in ("salary", "projection", "p90"):
        if any(abs(float(row[field])-float(saved[str(row["player_id"])][field])) > 1e-8
               for row in frame.to_dict("records")):
            raise ValueError(f"Prelock {field} does not match saved snapshot")
    frame["optimizer_context_adjustment"] = frame.player_id.astype(str).map(
        lambda player_id: saved[player_id]["optimizer_context_adjustment"])
    players = get_optimizer_service()._gpp_players_from_pool(frame)
    config = configuration(runtime["config"])
    tag_players(players, config.tag_thresholds)
    by_id = {player.player_id: player for player in players}
    source = {str(row["player_id"]): row for row in frame.to_dict("records")}
    game_totals = sorted({float(player.game_total) for player in players
                          if player.game_total is not None})
    old = runtime["classic_small_field"]["all_candidates"]
    replay_errors = [abs(describe_candidate(
        [by_id[player_id] for player_id in row["player_ids"]], all_players=players,
        config=config, pool_by_id=source, ownership_available=False,
        game_totals=game_totals)["objective_score"] - row["objective_score"])
        for row in old]
    if max(replay_errors) > 1e-9:
        raise ValueError("Saved prelock selector scores did not replay exactly")
    if not all(player.market_context_point_in_time_safe is True for player in players):
        raise ValueError("Historical market context is not fully time safe")

    scores = {}
    for row in actual_rows:
        player_id = row["player_id"]
        score = float(row["dk_points"])
        if player_id in scores and abs(scores[player_id]-score) > 1e-9:
            raise ValueError(f"Conflicting actual scores for canonical player {player_id}")
        scores[player_id] = score
    if set(by_id) - set(scores):
        raise ValueError("Historical actual scores do not cover the full prelock pool")

    profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
    terms = build_lineup_correlation_terms(players, profile=profile)
    formats = build_format_specific_terms(players, profile=profile)
    restrictions = {"enforce_single_te": bool(params["enforce_single_te"]),
                    "avoid_dst_opponents": bool(params["avoid_dst_opponents"]),
                    "precomputed_correlation_terms": terms,
                    "precomputed_format_terms": formats}
    raw_config = replace(config,
        objective_weights=ObjectiveWeights(projection=1.0, ceiling=0.0,
                                           leverage=0.0, correlation=0.0),
        correlation_bonus=0.0)
    raw_players = [replace(player, optimizer_context_adjustment=0.0)
                   for player in players]
    raw_indexes = _build_lineup(raw_players, raw_config, None, [], **restrictions)
    if raw_indexes is None:
        raise ValueError("No globally legal highest-mean historical lineup")
    raw_ids = [players[index].player_id for index in raw_indexes]
    highest_mean = sum(by_id[player_id].projection for player_id in raw_ids)

    def evaluate(ids):
        lineup = [by_id[player_id] for player_id in ids]
        row = describe_candidate(lineup, all_players=players, config=config,
                                 pool_by_id=source, ownership_available=False,
                                 game_totals=game_totals)
        return {"player_ids": ids, "roster": [player.name for player in lineup],
                "mean": row["mean"], "p90": row["p90"],
                "selector": row["objective_score"],
                "mean_loss_vs_global": highest_mean-row["mean"],
                "actual_score": sum(scores[player_id] for player_id in ids)}

    selected_rank = runtime["classic_small_field"]["selected_ranks"][0]
    selected = evaluate(old[selected_rank-1]["player_ids"])
    raw = evaluate(raw_ids)
    guards = {}
    for gap in (3, 4, 5, 6, 7):
        indexes = _build_lineup(players, config, None, [],
                                minimum_mean=highest_mean-gap, **restrictions)
        if indexes is None:
            guards[str(gap)] = None
            continue
        row = evaluate([players[index].player_id for index in indexes])
        delta = row["actual_score"]-selected["actual_score"]
        row["actual_delta_vs_production"] = delta
        row["guard_effect"] = "helped" if delta > .25 else "hurt" if delta < -.25 else "no measurable effect"
        guards[str(gap)] = row
    payload = {
        "purpose": "historical hypothesis test; no permanent quality threshold selected",
        "no_current_week_3_outcomes_used": True,
        "eligible_completed_sunday_main_slates": 1,
        "week_1": {
            "resolved_actual_player_count": week_1_observed,
            "saved_small_field_candidate_snapshot_count": 0,
            "measurable_quality_guard_effect": None,
            "reason": "No Week 1 Sunday Main small-field run saved a candidate pool.",
        },
        "week_2": {
            "prelock_run_id": RUN_ID,
            "created_at": str(run["created_at"]),
            "data_cutoff_at": str(run["data_cutoff_at"]),
            "projection_run_id": str(run["projection_run_id"]),
            "saved_candidate_count": len(old),
            "saved_candidate_scores_replayed_exactly": len(old),
            "prelock_player_count": len(players),
            "actual_source": "public.player_game_feature_matrix (historical postgame dk_points)",
            "actual_canonical_id_coverage": len(set(by_id) & set(scores)),
            "target_fact_player_game_actual_rows": target_actual_rows,
            "production_selected": selected,
            "global_highest_mean_legal": raw,
            "mean_guard_frontier": guards,
        },
        "week_2_sunday_late_exclusion": {
            "saved_candidate_runs": len(late_runs),
            "first_run_created_at": str(late_runs[0]["created_at"]) if late_runs else None,
            "first_kickoff_local": "2026-09-20 16:05 America/New_York",
            "reason": "All saved candidate runs were created after first late-game kickoff; prelock inputs cannot be established for this replay.",
        },
        "injury_ejection_adjudication": {
            "source": "target.player_outcome_event",
            "events": disruptions,
            "rule": "Recorded in-game events remain separate; no postgame score is used in lineup construction.",
        },
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, default=str, allow_nan=False)+"\n")
    print(json.dumps({"output": str(OUTPUT),
                      "eligible": payload["eligible_completed_sunday_main_slates"],
                      "production_actual": selected["actual_score"],
                      "guards": {key: (value["actual_score"] if value else None)
                                 for key, value in guards.items()}}, indent=2))


if __name__ == "__main__":
    main()
