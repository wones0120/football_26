#!/usr/bin/env python3
"""Read-only Week 2 Sunday Main projection robustness and model-risk shadow."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable, Mapping

import pandas as pd
from sqlalchemy import text

from backend.app.db import engine
from backend.app.product_dependencies import get_optimizer_service
from backend.app.product_services.player_context_scoring import score_player_context
from backend.app.product_services.player_pool_safety import evaluate_player_pool_safety
from backend.app.product_services.rule_library import resolve_strategy_profile


AUDIT_NAMES = (
    "Derrick Henry", "Michael Wilson", "Jalen Coker", "Chase Brown", "Chris Olave", "Tyler Shough",
    "Lamar Jackson", "Justin Herbert", "Bo Nix", "Carson Wentz", "CeeDee Lamb", "Garrett Wilson",
    "Justin Jefferson", "Christian McCaffrey", "Ja'Marr Chase", "Bijan Robinson",
)
SUSPICIOUS_QBS = ("Michael Penix Jr.", "Lamar Jackson", "Justin Herbert", "Bo Nix", "Carson Wentz")
SENSITIVITY_NAMES = (*AUDIT_NAMES, "Michael Penix Jr.")
SERIOUS_RANKS = (1, 6, 12, 19)
MEAN_WEIGHT = 0.35
CEILING_WEIGHT = 0.48
MATERIAL_DIFFERENCE = 2.5


def numeric(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def core_players(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for rows in payload.get("sunday_core_by_team", {}).values():
        for row in rows:
            output[str(row["player"])] = row
    return output


def load_feature_rows(projection_run_id: str) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT p.player_id, d.full_name AS player, d.primary_position AS position,
                   p.mean, p.p90, p.calibration_role, f.feature_json
            FROM target.player_projection p
            JOIN target.model_run mr ON mr.model_run_id = p.model_run_id
            JOIN target.feature_player_game f
              ON f.feature_run_id = mr.feature_run_id
             AND f.season = p.season AND f.week = p.week AND f.player_id = p.player_id
            JOIN target.dim_player d ON d.player_id = p.player_id
            WHERE p.projection_run_id = :projection_run_id
        """), {"projection_run_id": projection_run_id}).mappings().all()
    return [{**dict(row), "feature_json": dict(row["feature_json"] or {})} for row in rows]


def load_week1_qb_rows(names: Iterable[str]) -> dict[str, dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT DISTINCT ON (player_name) player_name, team, opponent, raw_row_json
            FROM public.raw_nfl_weekly_stat
            WHERE season = 2026 AND week = 1 AND player_name = ANY(:names)
            ORDER BY player_name, created_at DESC
        """), {"names": list(names)}).mappings().all()
    return {str(row["player_name"]): {**dict(row), "raw_row_json": dict(row["raw_row_json"] or {})} for row in rows}


def load_starter_rows() -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT DISTINCT ON (player_name) player_name, team, status, source,
                   evidence_tier, evidence_json, updated_at
            FROM public.starting_qb_evidence
            WHERE season = 2026 AND week = 2 AND UPPER(slate) = 'SUNDAY_MAIN'
            ORDER BY player_name, updated_at DESC
        """)).mappings().all()
    by_name = {str(row["player_name"]): dict(row) for row in rows}
    by_team: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_team.setdefault(str(row["team"]), []).append(dict(row))
    return by_name, by_team


def prepare_pool(projection_run_id: str, cutoff: str | None) -> tuple[list[Any], dict[str, dict[str, Any]]]:
    service = get_optimizer_service()
    pool = service._load_player_pool(2026, 2, "SUNDAY_MAIN", projection_run_id=projection_run_id)  # noqa: SLF001
    profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
    safety = evaluate_player_pool_safety(
        pool, profile=profile, as_of=datetime.now(timezone.utc),
        projection_cutoff=datetime.fromisoformat(cutoff) if cutoff else None,
    )
    pool = score_player_context(safety.eligible_pool, profile=profile).scored_pool
    pool, _ = service._select_strategy_candidates(  # noqa: SLF001
        pool, strategy="classic_small_field_gpp", contest_type="tournament"
    )
    pool = pool.loc[~pool["opponent_team"].fillna("").str.upper().eq("DEN")].copy()
    pool["ownership"] = 0.0
    players = service._gpp_players_from_pool(pool)  # noqa: SLF001
    return players, {str(row["player_id"]): row for row in pool.to_dict("records")}


def rescore_candidates(
    candidates: list[dict[str, Any]], players: list[Any], stressed_means: Mapping[str, float]
) -> list[dict[str, Any]]:
    player_by_id = {str(player.player_id): player for player in players}
    max_mean = max(
        (float(stressed_means.get(str(player.player_id), player.projection))
         + float(player.optimizer_context_adjustment))
        for player in players
    )
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        ids = [str(row["player_id"]) for row in candidate["roster"]]
        stressed_mean = sum(float(stressed_means.get(pid, player_by_id[pid].projection)) for pid in ids)
        context_raw = sum(float(player_by_id[pid].optimizer_context_adjustment) for pid in ids)
        mean_component = MEAN_WEIGHT * stressed_mean / max_mean
        original_context = float(candidate["components"].get("context") or 0.0)
        p90_component = float(candidate["components"].get("p90") or 0.0)
        if p90_component and candidate["p90"]:
            max_p90 = CEILING_WEIGHT * float(candidate["p90"]) / p90_component
        else:
            max_p90 = 1.0
        context_component = context_raw * (MEAN_WEIGHT / max_mean + CEILING_WEIGHT / max_p90)
        score = (
            float(candidate["objective_score"])
            - float(candidate["components"]["mean"])
            - original_context
            + mean_component
            + context_component
        )
        rows.append({
            **candidate,
            "stressed_mean": stressed_mean,
            "stressed_objective": score,
            "stressed_mean_component": mean_component,
            "stressed_context_component": context_component,
        })
    rows.sort(key=lambda row: (-row["stressed_objective"], -row["stressed_mean"], row["shadow_rank"]))
    for rank, row in enumerate(rows, 1):
        row["stressed_rank"] = rank
    return rows


def top_player_counts(candidates: list[dict[str, Any]], limit: int = 20) -> Counter[str]:
    counts: Counter[str] = Counter()
    for candidate in candidates[:limit]:
        counts.update(str(row.get("player") or row.get("name")) for row in candidate["roster"])
    return counts


def qb_counts(candidates: list[dict[str, Any]], limit: int = 20) -> dict[str, int]:
    return dict(Counter(str(candidate["qb"]["name"]) for candidate in candidates[:limit]))


def lineup_key(candidate: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(str(row["player_id"]) for row in candidate["roster"]))


def scenario_summary(
    label: str,
    rescored: list[dict[str, Any]],
    baseline: list[dict[str, Any]],
) -> dict[str, Any]:
    winner = rescored[0]
    base_winner = baseline[0]
    original_names = {str(row.get("player") or row.get("name")) for row in base_winner["roster"]}
    new_names = {str(row.get("player") or row.get("name")) for row in winner["roster"]}
    return {
        "scenario": label,
        "selected_original_shadow_rank": winner["shadow_rank"],
        "number_one_changed": lineup_key(winner) != lineup_key(base_winner),
        "selected_lineup": [str(row.get("player") or row.get("name")) for row in winner["roster"]],
        "mean_under_original_model": winner["mean"],
        "mean_under_stressed_projections": winner["stressed_mean"],
        "p90_under_original_model": winner["p90"],
        "qb": winner["qb"]["name"],
        "stack": winner["stack"]["type"],
        "players_added": sorted(new_names - original_names),
        "players_removed": sorted(original_names - new_names),
        "original_objective": winner["objective_score"],
        "stressed_objective": winner["stressed_objective"],
        "relative_chalk": winner["relative_chalk"],
        "football_sanity": winner["sanity"],
        "top_20_qb_families": qb_counts(rescored),
    }


def group_stats(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[float]] = {}
    for row in rows:
        groups.setdefault(str(row.get(key) or "Unavailable"), []).append(float(row["signed_difference"]))
    return [{
        key: group,
        "count": len(values),
        "mean_signed_difference": mean(values),
        "median_signed_difference": median(values),
        "mean_absolute_difference": mean(abs(value) for value in values),
    } for group, values in sorted(groups.items())]


def classify_reason(
    row: Mapping[str, Any], feature: Mapping[str, Any], core: Mapping[str, Any] | None,
    week1: Mapping[str, Any] | None, starter: Mapping[str, Any] | None,
    team_starters: list[Mapping[str, Any]],
) -> tuple[list[str], str]:
    categories: list[str] = []
    direction = float(row["signed_difference"])
    start_probability = numeric(feature.get("pregame_start_probability"))
    if row["position"] == "QB" and start_probability == 0:
        categories.append("E. player-status / starter-role issue")
        named = ", ".join(str(item["player_name"]) for item in team_starters) or "another quarterback"
        return categories, (
            f"The conditional model mean before participation was {numeric(feature.get('pregame_point_mean_before_opportunity')):.2f}, "
            f"but an explicit 0.00 start probability reduced the published mean to zero. Current slate starter evidence names {named}."
        )
    missing = [name for name in ("player_roll3_mean", "player_roll8_mean", "game_total_line", "team_implied_total")
               if numeric(feature.get(name)) is None]
    if missing:
        categories.append("D. stale/missing input")
    roll3 = numeric(feature.get("player_roll3_mean")) or 0.0
    role_class = str((core or {}).get("football_classification") or feature.get("offensive_role_class") or "")
    current_usage = (core or {}).get("current_usage") or {}
    high_usage = (
        (numeric(current_usage.get("week_1_targets")) or 0) >= 7
        or (numeric(current_usage.get("week_1_carries")) or 0) >= 15
        or (week1 and ((numeric(week1.get("attempts")) or 0) >= 25 or (numeric(week1.get("carries")) or 0) >= 5))
    )
    if high_usage:
        categories.append("B. recent opportunity")
    team_total = numeric(feature.get("team_implied_total")) or 0.0
    spread = numeric(feature.get("team_spread_line")) or 0.0
    if team_total >= 25 or team_total <= 20 or abs(spread) >= 7:
        categories.append("C. matchup/context")
    role_supported = any(label in role_class for label in ("core", "centerpiece"))
    if not missing and ((direction > 0 and (roll3 >= row["our_mean"] or role_supported))
                        or (direction < 0 and roll3 <= row["espn_mean"])):
        categories.append("A. legitimate model opinion")
    if direction < -MATERIAL_DIFFERENCE and role_supported and high_usage:
        categories = [category for category in categories if category != "A. legitimate model opinion"]
        categories.append("F. unexplained model behavior")
    if (row["position"] == "QB" and direction < -MATERIAL_DIFFERENCE and week1
            and (numeric(week1.get("fantasy_points")) or 0) >= 18
            and team_total >= 19):
        categories = [category for category in categories if category != "A. legitimate model opinion"]
        categories.append("F. unexplained model behavior")
    if not categories:
        categories.append("F. unexplained model behavior")
    if direction > 0:
        reason = (
            f"High local estimate is supported by roll-3 DK form {roll3:.2f}, role {role_class or 'Unavailable'}, "
            f"and team implied total {team_total:.2f}."
        )
    else:
        reason = (
            f"Low local estimate reflects roll-3 DK form {roll3:.2f} and team implied total {team_total:.2f}; "
            f"role is {role_class or 'Unavailable'}."
        )
    if "F. unexplained model behavior" in categories:
        reason += " Strong current role/opportunity remains insufficiently reflected, so residual model compression is unresolved."
    if starter:
        reason += f" Starter evidence is {starter.get('evidence_tier')} from {starter.get('source')}."
    if row["position"] == "QB":
        reason += " Passing attempts are audit evidence but are not a stored production model feature; QB volume enters indirectly through fantasy-point history and game context."
    return list(dict.fromkeys(categories)), reason


def markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Week 2 Sunday Main projection robustness",
        "",
        "Diagnostic only. Production projections, P90, weights, and stack rules are unchanged.",
        "",
        "## Decision answers",
        "",
    ]
    for index, answer in enumerate(payload["decision_answers"], 1):
        lines.append(f"{index}. {answer}")
    lines += ["", "## Highest-impact audit", "",
              "| Player | Pos | Ours | ESPN | Diff | Salary | Role | W1 opportunity | Opp | Total / spread | Status | Cause |",
              "|---|---:|---:|---:|---:|---:|---|---|---|---|---|---|"]
    for row in payload["player_audit"]:
        w1 = row["week_1_opportunity"]
        if row["position"] == "QB":
            opportunity = f"{w1.get('attempts', '—')} att, {w1.get('carries', '—')} rush, {w1.get('dk_points', '—')} DK"
        else:
            opportunity = f"{w1.get('targets', '—')} tgt, {w1.get('carries', '—')} car, {w1.get('snap_share', '—')} snap"
        lines.append(
            f"| {row['player']} | {row['position']} | {row['our_mean']:.2f} | {row['espn_mean']:.2f} | "
            f"{row['signed_difference']:+.2f} | ${row['salary']:,} | {row['role_classification']} | {opportunity} | "
            f"{row['opponent']} | {row['game_total']} / {row['team_spread']:+.1f} | {row['active_injury_status']} | "
            f"{'; '.join(row['cause_categories'])} |"
        )
        lines.append(f"\n  - **Trace:** {row['reason']} Relevant stored inputs: `{json.dumps(row['relevant_model_inputs'], sort_keys=True)}`")

    lines += ["", "## One-player sensitivity", "",
              "| Player | Blend | Universe candidates | Best containing rank | New #1 | #1 changed | Player top-20 frequency | QB families | Serious ranks |",
              "|---|---:|---:|---:|---:|---|---:|---|---|"]
    for row in payload["one_at_a_time"]:
        lines.append(
            f"| {row['player']} | {row['espn_weight']:.0%} ESPN | {row['player_candidate_count']} | "
            f"{row['best_containing_rank_before'] or '—'}→{row['best_containing_rank_after'] or '—'} | #{row['winner_original_rank']} | "
            f"{row['number_one_changed']} | {row['player_top20_before']}→{row['player_top20_after']} | "
            f"{row['qb_family_change']} | {row['serious_rank_change']} |"
        )

    lines += ["", "## Cluster stress", "",
              "| Scenario | Selected original rank | QB / stack | Original mean | Stressed mean | P90 | Original obj | Stressed obj | Chalk | Sanity deficit | Added | Removed |",
              "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---|"]
    for row in payload["cluster_scenarios"]:
        lines.append(
            f"| {row['scenario']} | #{row['selected_original_shadow_rank']} | {row['qb']} / {row['stack']} | "
            f"{row['mean_under_original_model']:.2f} | {row['mean_under_stressed_projections']:.2f} | "
            f"{row['p90_under_original_model']:.2f} | {row['original_objective']:.4f} | {row['stressed_objective']:.4f} | "
            f"{row['relative_chalk']:.1f} | {row['football_sanity']['total_football_sanity_deficit']:.3f} | "
            f"{', '.join(row['players_added']) or '—'} | {', '.join(row['players_removed']) or '—'} |"
        )

    lines += ["", "## Control-lineup model risk", "",
              "| Lineup | Our total | ESPN total | Our−ESPN | Our high count | ESPN high count | ESPN coverage |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for row in payload["control_lineups"]:
        lines.append(
            f"| #{row['shadow_rank']} | {row['our_total']:.2f} | {row['espn_total']:.2f} | "
            f"{row['difference']:+.2f} | {row['our_higher_count']} | {row['espn_higher_count']} | "
            f"{row['espn_coverage']}/9 |"
        )

    lines += ["", "## Calibration summary", "",
              payload["calibration"]["selection_warning"], "",
              f"Matched mean signed difference: **{payload['calibration']['overall']['mean_signed_difference']:+.2f}**; "
              f"median: **{payload['calibration']['overall']['median_signed_difference']:+.2f}**.", ""]
    for label in ("by_position", "by_salary_tier", "by_our_projection_decile", "by_role_class"):
        lines += [f"### {label.replace('_', ' ').title()}", "", "| Group | N | Mean signed | Median signed | Mean absolute |",
                  "|---|---:|---:|---:|---:|"]
        key = next(key for key in payload["calibration"][label][0] if key not in {
            "count", "mean_signed_difference", "median_signed_difference", "mean_absolute_difference"
        }) if payload["calibration"][label] else "group"
        for row in payload["calibration"][label]:
            lines.append(f"| {row[key]} | {row['count']} | {row['mean_signed_difference']:+.2f} | "
                         f"{row['median_signed_difference']:+.2f} | {row['mean_absolute_difference']:.2f} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--exploration", type=Path, required=True)
    parser.add_argument("--optimizer", type=Path, required=True)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    comparison = json.loads(args.comparison.read_text())
    exploration = json.loads(args.exploration.read_text())
    optimizer = json.loads(args.optimizer.read_text())
    core = core_players(json.loads(args.core.read_text()))
    candidates = exploration["all_candidates"]
    projection_run_id = str(comparison["our_inputs"]["projection_run_id"])
    feature_rows = load_feature_rows(projection_run_id)
    features_by_id = {str(row["player_id"]): row for row in feature_rows}
    compare_by_name = {str(row["player"]): row for row in comparison["overlapping_players"]}
    compare_by_id = {str(row["player_id"]): row for row in comparison["overlapping_players"]}
    week1_qbs = load_week1_qb_rows(set(AUDIT_NAMES) | set(SUSPICIOUS_QBS))
    starters, starters_by_team = load_starter_rows()
    players, pool_by_id = prepare_pool(projection_run_id, optimizer.get("data_cutoff_at"))

    audits: list[dict[str, Any]] = []
    for name in (*AUDIT_NAMES, "Michael Penix Jr."):
        compared = compare_by_name.get(name)
        if not compared:
            continue
        feature_row = features_by_id[str(compared["player_id"])]
        feature = feature_row["feature_json"]
        core_row = core.get(name)
        qb_raw = (week1_qbs.get(name) or {}).get("raw_row_json") or {}
        starter = starters.get(name)
        categories, reason = classify_reason(
            compared, feature, core_row, qb_raw, starter,
            starters_by_team.get(str(compared["team"]), []),
        )
        if compared["position"] == "QB":
            week1 = {
                "attempts": numeric(qb_raw.get("attempts")), "completions": numeric(qb_raw.get("completions")),
                "passing_yards": numeric(qb_raw.get("passing_yards")), "passing_tds": numeric(qb_raw.get("passing_tds")),
                "carries": numeric(qb_raw.get("carries")), "rushing_yards": numeric(qb_raw.get("rushing_yards")),
                "dk_points": numeric(qb_raw.get("fantasy_points")),
            }
        else:
            usage = (core_row or {}).get("current_usage") or {}
            week1 = {
                "targets": numeric(usage.get("week_1_targets")), "target_share": numeric(usage.get("week_1_target_share")),
                "carries": numeric(usage.get("week_1_carries")), "carry_share": numeric(usage.get("week_1_carry_share")),
                "snap_share": numeric(usage.get("week_1_snap_share")),
            }
        audits.append({
            **{key: compared[key] for key in ("player_id", "player", "position", "team", "opponent", "salary", "our_mean", "espn_mean", "signed_difference")},
            "role_classification": (core_row or {}).get("football_classification") or feature.get("offensive_role_class") or "Unavailable",
            "role_confidence": (core_row or {}).get("current_evidence_confidence") or feature.get("offensive_role_confidence") or "Unavailable",
            "week_1_opportunity": week1,
            "game_total": numeric(feature.get("game_total_line")),
            "team_spread": numeric(feature.get("team_spread_line")),
            "active_injury_status": (
                f"{starter.get('status')} / {feature.get('pregame_injury_status') or 'no designation'}"
                if starter else f"roster {((core_row or {}).get('current_usage') or {}).get('week_2_roster_status', 'unknown')} / "
                f"{feature.get('pregame_injury_status') or 'no designation'}"
            ),
            "starter_evidence": starter,
            "relevant_model_inputs": {key: feature.get(key) for key in (
                "pregame_availability_probability", "pregame_start_probability", "player_games_history",
                "player_roll3_mean", "player_roll8_mean", "game_total_line", "team_spread_line",
                "team_implied_total", "defense_pos_allowed_roll3", "carries_mean_3", "targets_mean_3",
                "carry_share_mean_3", "target_share_mean_3", "snap_share_mean_3",
                "offensive_role_importance", "offensive_role_class",
            )} | ({"passing_attempts_feature_in_model": False} if compared["position"] == "QB" else {}),
            "cause_categories": categories,
            "reason": reason,
        })

    baseline = rescore_candidates(candidates, players, {})
    baseline_max_error = max(abs(row["stressed_objective"] - row["objective_score"]) for row in baseline)
    if baseline[0]["shadow_rank"] != 1 or baseline_max_error > 1e-9:
        raise RuntimeError(
            f"Zero-stress selector reproduction failed: winner={baseline[0]['shadow_rank']}, "
            f"max_error={baseline_max_error}"
        )
    baseline_top20 = top_player_counts(baseline)
    universe_counts = top_player_counts(baseline, limit=len(baseline))
    baseline_qbs = qb_counts(baseline)
    serious_keys = {rank: lineup_key(next(row for row in baseline if row["shadow_rank"] == rank)) for rank in SERIOUS_RANKS}
    one_at_a_time: list[dict[str, Any]] = []
    for name in SENSITIVITY_NAMES:
        compared = compare_by_name[name]
        player_id = str(compared["player_id"])
        for espn_weight in (0.25, 0.50):
            stressed = compared["our_mean"] * (1.0 - espn_weight) + compared["espn_mean"] * espn_weight
            rescored = rescore_candidates(candidates, players, {player_id: stressed})
            after_counts = top_player_counts(rescored)
            after_qbs = qb_counts(rescored)
            new_ranks = {lineup_key(row): row["stressed_rank"] for row in rescored}
            baseline_containing = [row for row in baseline if any(str(roster["player_id"]) == player_id for roster in row["roster"])]
            rescored_containing = [row for row in rescored if any(str(roster["player_id"]) == player_id for roster in row["roster"])]
            one_at_a_time.append({
                "player": name, "espn_weight": espn_weight, "stressed_player_mean": stressed,
                "winner_original_rank": rescored[0]["shadow_rank"],
                "number_one_changed": lineup_key(rescored[0]) != lineup_key(baseline[0]),
                "winner_added": sorted({str(r.get("player") or r.get("name")) for r in rescored[0]["roster"]} - {str(r.get("player") or r.get("name")) for r in baseline[0]["roster"]}),
                "winner_removed": sorted({str(r.get("player") or r.get("name")) for r in baseline[0]["roster"]} - {str(r.get("player") or r.get("name")) for r in rescored[0]["roster"]}),
                "player_top20_before": baseline_top20[name], "player_top20_after": after_counts[name],
                "best_containing_rank_before": baseline_containing[0]["stressed_rank"] if baseline_containing else None,
                "best_containing_rank_after": rescored_containing[0]["stressed_rank"] if rescored_containing else None,
                "player_candidate_count": universe_counts[name],
                "sensitivity_status": (
                    "not_identifiable_player_absent_from_frozen_candidate_universe"
                    if universe_counts[name] == 0 else "identified_within_frozen_candidate_universe"
                ),
                "qb_families_before": baseline_qbs, "qb_families_after": after_qbs,
                "qb_family_change": f"{baseline_qbs} → {after_qbs}" if baseline_qbs != after_qbs else "unchanged",
                "serious_ranks_before": {rank: rank for rank in SERIOUS_RANKS},
                "serious_ranks_after": {rank: new_ranks[key] for rank, key in serious_keys.items()},
                "serious_rank_change": ", ".join(f"#{rank}→#{new_ranks[key]}" for rank, key in serious_keys.items()),
                "top_four_original_ranks": [row["shadow_rank"] for row in rescored[:4]],
            })

    # Shough is explicitly part of the requested high-impact cluster and misses the
    # general 2.5 threshold by only 0.06, so include him alongside every material row.
    material = [row for row in comparison["overlapping_players"]
                if abs(row["signed_difference"]) >= MATERIAL_DIFFERENCE or row["player"] == "Tyler Shough"]
    cluster_scenarios: list[dict[str, Any]] = []
    for label, espn_weight in (("A: 25% ESPN", 0.25), ("B: 50% ESPN", 0.50), ("C: 100% ESPN diagnostic extreme", 1.0)):
        stresses = {str(row["player_id"]): row["our_mean"] * (1 - espn_weight) + row["espn_mean"] * espn_weight for row in material}
        cluster_scenarios.append(scenario_summary(label, rescore_candidates(candidates, players, stresses), baseline))

    controls: list[dict[str, Any]] = []
    for rank in SERIOUS_RANKS:
        candidate = next(row for row in candidates if row["shadow_rank"] == rank)
        comparisons = [compare_by_id.get(str(roster["player_id"])) for roster in candidate["roster"]]
        available = [row for row in comparisons if row]
        our_total = sum(float(row["our_mean"]) for row in available)
        espn_total = sum(float(row["espn_mean"]) for row in available)
        controls.append({
            "shadow_rank": rank, "players": [str(row.get("player") or row.get("name")) for row in candidate["roster"]],
            "our_total": our_total, "espn_total": espn_total, "difference": our_total - espn_total,
            "our_higher_count": sum(row["signed_difference"] >= MATERIAL_DIFFERENCE for row in available),
            "espn_higher_count": sum(row["signed_difference"] <= -MATERIAL_DIFFERENCE for row in available),
            "espn_coverage": len(available),
        })

    calibration_rows: list[dict[str, Any]] = []
    for compared in comparison["overlapping_players"]:
        feature = features_by_id.get(str(compared["player_id"]), {}).get("feature_json", {})
        core_row = core.get(str(compared["player"])) or {}
        salary = int(compared["salary"])
        calibration_rows.append({
            **compared,
            "salary_tier": "$4k or less" if salary <= 4000 else "$4.1k–$5.5k" if salary <= 5500 else "$5.6k–$7k" if salary <= 7000 else "Above $7k",
            "role_class": core_row.get("football_classification") or feature.get("offensive_role_class") or "Unavailable",
        })
    frame = pd.DataFrame(calibration_rows)
    frame["our_projection_decile"] = pd.qcut(frame["our_mean"].rank(method="first"), 10, labels=[f"D{i}" for i in range(1, 11)])
    calibration_rows = frame.to_dict("records")
    overall_values = [float(row["signed_difference"]) for row in calibration_rows]
    calibration = {
        "selection_warning": "Selection-truncated: ESPN publishes only players it projects for at least 4.0 DK points; these are not unbiased whole-slate calibration estimates.",
        "overall": {"count": len(overall_values), "mean_signed_difference": mean(overall_values), "median_signed_difference": median(overall_values)},
        "espn_10_plus": group_stats([{**row, "threshold": "ESPN 10+"} for row in calibration_rows if row["espn_mean"] >= 10], "threshold")[0],
        "espn_15_plus": group_stats([{**row, "threshold": "ESPN 15+"} for row in calibration_rows if row["espn_mean"] >= 15], "threshold")[0],
        "by_position": group_stats(calibration_rows, "position"),
        "by_salary_tier": group_stats(calibration_rows, "salary_tier"),
        "by_our_projection_decile": group_stats(calibration_rows, "our_projection_decile"),
        "by_role_class": group_stats(calibration_rows, "role_class"),
    }

    cluster_by_label = {row["scenario"]: row for row in cluster_scenarios}
    best_control = min(controls, key=lambda row: abs(row["difference"]))
    changed_individuals = sorted({row["player"] for row in one_at_a_time if row["number_one_changed"]})
    universe_by_name = {row["player"]: row["player_candidate_count"] for row in one_at_a_time}
    absent_sensitivity = sorted(name for name, count in universe_by_name.items() if count == 0)
    thin_sensitivity = sorted(name for name, count in universe_by_name.items() if 0 < count < 10)
    decision_answers = [
        "Henry, Coker, Brown, Olave, and Michael Wilson are directionally defensible from current high-confidence core roles and Week 1 volume, though their joint use creates concentrated model risk.",
        "Shough is defensible as a contrarian opinion: active inferred starter, 25.63 roll-3 DK mean, 27.0 implied team total, 46.5 game total, and modest rushing volume. Starter evidence remains inferred rather than official.",
        "Penix is not a broken zero: the stored 11.73 conditional mean is multiplied by a 0.00 start probability, and Atlanta has now officially named Cooper Rush while ruling Penix out. Wentz is also officially confirmed. The other audited QB lows have populated features and 1.00 start probability; Wentz and Lamar retain projection-compression risk rather than starter-status risk.",
        f"Individual disagreements that changed #1: {', '.join(changed_individuals) if changed_individuals else 'none'}. Top-20 representation and serious-lineup ordering still moved for additional players shown in the table. Zero candidate coverage makes sensitivity unidentifiable for {', '.join(absent_sensitivity)}; thin coverage below 10 candidates limits inference for {', '.join(thin_sensitivity)}. Both are direct candidate-generation evidence.",
        f"At 25% simultaneous shrinkage, selected original rank is #{cluster_by_label['A: 25% ESPN']['selected_original_shadow_rank']}; #1 survives: {not cluster_by_label['A: 25% ESPN']['number_one_changed']}.",
        f"At 50% simultaneous shrinkage, selected original rank is #{cluster_by_label['B: 50% ESPN']['selected_original_shadow_rank']}; #1 survives: {not cluster_by_label['B: 50% ESPN']['number_one_changed']}.",
        f"Of #1/#6/#12/#19, #{best_control['shadow_rank']} has the smallest absolute aggregate our-versus-ESPN difference ({abs(best_control['difference']):.2f} points) and is the least consensus-dependent by this narrow measure.",
        "The evidence is mixed: concentrated skill players are mostly legitimate contrarian opportunity opinions; the broader high-end comparison shows compression/calibration risk; Penix is a starter-status treatment requiring refresh, while no other audited QB has a confirmed missing-feature failure.",
    ]

    payload = {
        "artifact": "sunday_projection_robustness_v1", "generated_at": datetime.now(timezone.utc).isoformat(),
        "diagnostic_only": True, "production_changes": "none", "projection_run_id": projection_run_id,
        "candidate_universe": {"count": len(candidates), "source": str(args.exploration), "p90_changed": False},
        "method": {"mean_weight": MEAN_WEIGHT, "ceiling_weight": CEILING_WEIGHT, "material_difference": MATERIAL_DIFFERENCE,
                   "cluster_scope": "all deterministically matched players with absolute difference >= 2.5, plus explicitly requested Tyler Shough at 2.44",
                   "exposure_measure": "frequency in top 20 rescored frozen candidates; universe membership is unchanged",
                   "zero_stress_winner": baseline[0]["shadow_rank"],
                   "zero_stress_max_objective_error": baseline_max_error},
        "player_audit": audits, "one_at_a_time": one_at_a_time, "cluster_scenarios": cluster_scenarios,
        "control_lineups": controls, "calibration": calibration, "decision_answers": decision_answers,
    }
    args.output.write_text(json.dumps(payload, indent=2, default=str, allow_nan=False) + "\n")
    args.output.with_suffix(".md").write_text(markdown(payload))
    print(json.dumps({
        "output": str(args.output), "candidates": len(candidates), "audited_players": len(audits),
        "individual_changes": changed_individuals,
        "cluster_winners": {row["scenario"]: row["selected_original_shadow_rank"] for row in cluster_scenarios},
        "best_control": best_control["shadow_rank"],
    }, indent=2))


if __name__ == "__main__":
    main()
