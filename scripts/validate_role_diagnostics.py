"""Read-only role sensitivity and calibration audit for a saved optimizer result.

Example: PYTHONPATH=. .venv/bin/python scripts/validate_role_diagnostics.py \
  artifacts/sunday-main-role-validation-2026w2.json \
  artifacts/sunday-role-diagnostic-2026w2.json

This script never writes production projections or optimizer jobs. The fitted
model is reconstructed from the saved projection's point-in-time input cutoff.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sklearn.ensemble import GradientBoostingRegressor

from Database.config import get_connection_string
from backend.app.product_services.canonical_projection_inputs import FEATURE_COLUMNS, load_inputs
from backend.app.product_services.classic_small_field import _role_projection_anomalies
from backend.app.product_services.gpp_optimizer import Player
from backend.app.product_services.predictions import (
    TARGET_COL, generate_walk_forward_residuals, historical_role_calibration,
    role_counterfactual_grid,
)


def enrich_saved_result(payload: dict, train: pd.DataFrame, target: pd.DataFrame) -> dict:
    """Add diagnostics to an in-memory copy; keep saved production data intact."""
    model = GradientBoostingRegressor(random_state=42)
    model.fit(train[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce").fillna(0.0), train[TARGET_COL])
    grids = role_counterfactual_grid(model, train, target, FEATURE_COLUMNS)
    frame = target.copy().reset_index(drop=True)
    frame["role_counterfactual_grid"] = grids
    source = {str(row["player_id"]): row for row in frame.to_dict("records")}
    report = payload["results"][0][0]["classic_small_field_report"]
    for row in report["role_exposure"]:
        evidence = source.get(str(row["player_id"]), {})
        row["role_counterfactual"] = evidence.get("role_counterfactual_grid")
        recent_targets = _number(evidence.get("targets_mean_3"))
        recent_carries = _number(evidence.get("carries_mean_3"))
        projected_targets = _number(evidence.get("projected_targets"))
        projected_carries = _number(evidence.get("projected_carries"))
        row["opportunity_validation"] = {
            "recent_targets_mean_3": recent_targets, "recent_carries_mean_3": recent_carries,
            "projected_targets_proxy": projected_targets, "projected_carries_proxy": projected_carries,
            "targets_proxy_minus_recent": projected_targets - recent_targets if projected_targets is not None and recent_targets is not None else None,
            "carries_proxy_minus_recent": projected_carries - recent_carries if projected_carries is not None and recent_carries is not None else None,
            "source": evidence.get("projected_opportunity_source") or "unavailable",
            "context_adjusted": evidence.get("pregame_opportunity_context_applied") is True,
            "point_model_context": {
                "game_total": _number(evidence.get("game_total_line")),
                "team_spread": _number(evidence.get("team_spread_line")),
                "team_implied_total": _number(evidence.get("team_implied_total")),
                "effect": "inputs enter nonlinear mean model; separate point effect unavailable",
            },
            "note": "Lagged allocation proxy, not independent forward opportunity forecast",
        }
        row["role_trend"] = {key: _number(evidence.get(key)) for key in (
            "snap_share_last", "snap_share_prior3", "snap_share_trend",
            "target_share_last", "target_share_prior3", "target_share_trend",
            "rush_share_last", "rush_share_prior3", "rush_share_trend")}
    residuals = generate_walk_forward_residuals(train, FEATURE_COLUMNS)
    report["historical_role_calibration"] = historical_role_calibration(residuals)
    player_rows = []
    candidate_counts = Counter()
    for row in report["role_exposure"]:
        evidence = source.get(str(row["player_id"]), {})
        candidate_counts[str(row["player_id"])] = row["candidate_count"]
        player_rows.append(Player(
            player_id=str(row["player_id"]), name=str(row["name"]), team=str(row["team"]),
            opponent=str(evidence.get("opponent_team") or ""), position=str(row["position"]),
            salary=int(row["salary"]), projection=float(row["mean"]), ceiling=float(row["p90"]),
            ownership=float(row["ownership"] or 0), game_id=str(evidence.get("game_id") or ""),
            game_total=float(evidence.get("game_total_line") or 0),
            spread=float(evidence.get("team_spread_line") or 0),
            team_total=float(evidence.get("team_implied_total") or 0),
        ))
    report["role_projection_anomalies"] = _role_projection_anomalies(
        player_rows, source, candidate_counts, report["candidate_count"])
    exposure_by_id = {str(row["player_id"]): row for row in report["role_exposure"]}
    top_saved = report["top_50"]
    for candidate in [*report["top_20"]]:
        sanity = candidate.get("football_sanity") or {}
        for omitted in sanity.get("omitted_central_players", []):
            matching = [row for row in top_saved if omitted["player_id"] in row["player_ids"]]
            best = max(matching, key=lambda row: row["objective_score"], default=None)
            if best is None:
                omitted["explanation"] = "Best containing candidate is outside saved top 50; exact gap unavailable"
                continue
            gap = candidate["objective_score"] - best["objective_score"]
            player = exposure_by_id[str(omitted["player_id"])]
            same_position = [row for row in report["role_exposure"] if row["position"] == player["position"]]
            value_rank = 1 + sum(row["mean_per_1000_salary"] > player["mean_per_1000_salary"]
                                 for row in same_position)
            omitted.update({
                "best_candidate_with_player_rank": best["rank"],
                "whole_lineup_objective_gap": gap,
                "explanation": f"Best generated containing candidate #{best['rank']} scored {gap:.3f} below this lineup; whole-lineup comparison, not causal swap",
                "projection_reason": f"Mean {player['mean']:.2f}; P90 {player['p90']:.2f}",
                "salary_value_reason": f"Salary ${player['salary']:,}; mean/$1,000 rank {value_rank}/{len(same_position)} at {player['position']}",
                "stack_correlation_reason": f"Containing candidate {best['stack']['type']} vs selected {candidate['stack']['type']}; correlation contributions {best['components'].get('correlation', 0):.3f} vs {candidate['components'].get('correlation', 0):.3f}",
                "ownership_reason": "Ownership unavailable; no cause assigned" if player['ownership'] is None else f"Ownership {player['ownership']:.1f}%; causal effect not isolated",
            })
    selected_by_rank = {row["rank"]: row["football_sanity"] for row in report["top_20"]}
    report["selected_football_sanity"] = [selected_by_rank.get(rank, row)
        for rank, row in zip(report["selected_ranks"], report["selected_football_sanity"])]
    report["role_diagnostic_provenance"] = {
        "method": "read-only reconstruction at saved projection cutoff",
        "production_projection_unchanged": True,
        "production_optimizer_job_unchanged": True,
        "omission_comparison_limitation": "The saved job retains top 50 of 120 candidates; exact all-candidate omission comparisons require a new optimizer run",
    }
    return payload


def _number(value):
    try:
        result = float(value)
        return result if pd.notna(result) else None
    except (TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("optimizer_json", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.optimizer_json.read_text())
    projection_run_id = payload["projection_run_id"]
    engine = create_engine(get_connection_string())
    with engine.connect() as connection:
        run = connection.execute(text("""
            SELECT season, week, slate_id, data_cutoff_at FROM target.projection_run
            WHERE projection_run_id = :projection_run_id AND status = 'completed'
        """), {"projection_run_id": projection_run_id}).mappings().one()
    train, target, _ = load_inputs(engine, season=run["season"], week=run["week"],
                                   slate=run["slate_id"], cutoff=run["data_cutoff_at"])
    enriched = enrich_saved_result(payload, train, target)
    args.output_json.write_text(json.dumps(enriched, indent=2, default=str, allow_nan=False) + "\n")
    report = enriched["results"][0][0]["classic_small_field_report"]
    print(json.dumps({"projection_run_id": projection_run_id,
                      "counterfactual_players": sum(row.get("role_counterfactual") is not None for row in report["role_exposure"]),
                      "anomaly_count": len(report["role_projection_anomalies"]),
                      "calibration_status": report["historical_role_calibration"]["status"],
                      "output": str(args.output_json)}))


if __name__ == "__main__":
    main()
