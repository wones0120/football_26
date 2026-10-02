#!/usr/bin/env python3
"""Regenerate Week 2 Sunday Main candidates under projection stress scenarios.

This is a read-only diagnostic. It does not persist projections, candidates, or
optimizer settings.
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from math import log
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping

from backend.app.db import engine
from backend.app.product_services.classic_small_field import describe_candidate
from backend.app.product_services.football_sanity_deficit import lineup_sanity_deficit
from backend.app.product_services.gpp_optimizer import StackRules, _build_lineup, run_gpp_pipeline
from scripts.validate_sunday_candidate_exploration import (
    FAMILIES,
    latest_ownership,
    lineup_key,
    relative_percentiles,
)
from scripts.validate_sunday_projection_robustness import (
    load_starter_rows,
    load_week1_qb_rows,
    prepare_pool,
)


MATERIAL_DIFFERENCE = 2.5
QB_TOP_N = 20
QB_TOP_MEAN_N = 12
QB_VALUE_GAP = 0.80
TRACKED_RANKS = (1, 6, 12, 19, 7)
SCENARIOS = (
    ("control", 0.0, "control"),
    ("stress_25_mean_only", 0.25, "mean_only"),
    ("stress_25_spread_preserving", 0.25, "spread_preserving"),
    ("stress_50_mean_only", 0.50, "mean_only"),
    ("stress_50_spread_preserving", 0.50, "spread_preserving"),
)


def scenario_players(
    control_players: list[Any],
    espn_by_id: Mapping[str, Mapping[str, Any]],
    *,
    blend: float,
    ceiling_treatment: str,
) -> tuple[list[Any], dict[str, dict[str, Any]]]:
    """Create an in-memory shadow pool while preserving every non-projection input."""
    output = []
    changes: dict[str, dict[str, Any]] = {}
    for player in control_players:
        row = espn_by_id.get(str(player.player_id))
        material = bool(row and abs(float(row["espn_mean"]) - float(player.projection)) >= MATERIAL_DIFFERENCE)
        stressed_mean = (
            (1.0 - blend) * float(player.projection) + blend * float(row["espn_mean"])
            if blend and material else float(player.projection)
        )
        if ceiling_treatment == "spread_preserving":
            stressed_p90 = stressed_mean + (float(player.ceiling) - float(player.projection))
        else:
            stressed_p90 = float(player.ceiling)
        stressed_p90 = max(stressed_mean, stressed_p90)
        salary_k = max(0.001, float(player.salary) / 1000.0)
        output.append(replace(
            player,
            projection=stressed_mean,
            ceiling=stressed_p90,
            value_per_k=stressed_mean / salary_k,
            ceiling_per_k=stressed_p90 / salary_k,
        ))
        if material and blend:
            changes[str(player.player_id)] = {
                "player": player.name,
                "our_mean": float(player.projection),
                "espn_mean": float(row["espn_mean"]),
                "stressed_mean": stressed_mean,
                "our_p90": float(player.ceiling),
                "stressed_p90": stressed_p90,
            }
    return output, changes


def eligible_qb_ids(
    control_players: list[Any], scenario: list[Any], *, top_n: int = QB_TOP_N,
    top_mean_n: int = QB_TOP_MEAN_N, value_gap: float = QB_VALUE_GAP,
    external_means: Mapping[str, float] | None = None,
) -> tuple[set[str], list[dict[str, Any]]]:
    """Union top value/mean QBs under either view plus QBs close to a value leader."""
    control = {str(player.player_id): player for player in control_players if player.position == "QB"}
    stressed = {str(player.player_id): player for player in scenario if player.position == "QB"}
    common = set(control) & set(stressed)
    own_value = {pid: control[pid].projection / max(0.001, control[pid].salary / 1000) for pid in common}
    stressed_value = {pid: stressed[pid].projection / max(0.001, stressed[pid].salary / 1000) for pid in common}
    own_order = sorted(common, key=lambda pid: (-own_value[pid], control[pid].name))
    stressed_order = sorted(common, key=lambda pid: (-stressed_value[pid], stressed[pid].name))
    own_mean_order = sorted(common, key=lambda pid: (-control[pid].projection, control[pid].name))
    stressed_mean_order = sorted(common, key=lambda pid: (-stressed[pid].projection, stressed[pid].name))
    external = {pid: float(value) for pid, value in (external_means or {}).items() if pid in common}
    external_value = {
        pid: value / max(0.001, control[pid].salary / 1000) for pid, value in external.items()
    }
    external_value_order = sorted(external, key=lambda pid: (-external_value[pid], control[pid].name))
    external_mean_order = sorted(external, key=lambda pid: (-external[pid], control[pid].name))
    selected = set(own_order[:top_n]) | set(stressed_order[:top_n])
    selected |= set(own_mean_order[:top_mean_n]) | set(stressed_mean_order[:top_mean_n])
    selected |= set(external_value_order[:top_n]) | set(external_mean_order[:top_mean_n])
    own_leader = max(own_value.values(), default=0.0)
    stressed_leader = max(stressed_value.values(), default=0.0)
    selected |= {pid for pid in common if own_leader - own_value[pid] <= value_gap}
    selected |= {pid for pid in common if stressed_leader - stressed_value[pid] <= value_gap}
    audit = [{
        "player_id": pid,
        "qb": control[pid].name,
        "our_value_per_1k": own_value[pid],
        "stressed_value_per_1k": stressed_value[pid],
        "our_value_rank": own_order.index(pid) + 1,
        "stressed_value_rank": stressed_order.index(pid) + 1,
        "our_mean_rank": own_mean_order.index(pid) + 1,
        "stressed_mean_rank": stressed_mean_order.index(pid) + 1,
        "external_value_rank": external_value_order.index(pid) + 1 if pid in external else None,
        "external_mean_rank": external_mean_order.index(pid) + 1 if pid in external else None,
        "selected": pid in selected,
    } for pid in stressed_order]
    return selected, audit


def _solve_variants(
    players: list[Any], config: Any, *, variants: int,
    required_qb_id: str | None = None,
) -> list[tuple[list[Any], str]]:
    solved: list[tuple[list[Any], str]] = []
    for partners, bring_backs in FAMILIES:
        excluded: list[set[int]] = []
        rules = StackRules(**{
            **config.stack_rules.__dict__,
            "min_pass_catchers": partners,
            "min_bring_backs": bring_backs,
        })
        label = f"QB+{partners}" + ("+bring-back" if bring_backs else "")
        for _ in range(variants):
            indexes = _build_lineup(
                players, config, None, excluded,
                enforce_single_te=True,
                avoid_dst_opponents=True,
                stack_rules=rules,
                required_player_ids={required_qb_id} if required_qb_id else None,
                exact_pass_catchers=partners,
                exact_bring_backs=bring_backs,
            )
            if indexes is None:
                break
            excluded.append(set(indexes))
            solved.append(([players[index] for index in indexes], label))
    return solved


def generate_candidates(
    players: list[Any], *, control_players: list[Any], config: Any,
    pool_by_id: dict[str, dict[str, Any]], core_by_id: dict[str, dict[str, Any]],
    ownership_by_id: Mapping[str, float], external_qb_means: Mapping[str, float],
    global_variants: int, qb_variants: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    eligible_ids, qb_eligibility = eligible_qb_ids(
        control_players, players, external_means=external_qb_means
    )
    qbs = [player for player in players if str(player.player_id) in eligible_ids]
    generated: dict[tuple[str, ...], dict[str, Any]] = {}

    work: list[tuple[str, Any]] = [("global", None)] + [("qb", qb) for qb in qbs]
    with ThreadPoolExecutor(max_workers=min(12, len(work))) as executor:
        futures = []
        for kind, qb in work:
            variants = global_variants if kind == "global" else qb_variants
            futures.append((kind, qb, executor.submit(
                _solve_variants, players, config, variants=variants,
                required_qb_id=str(qb.player_id) if qb else None,
            )))
        for kind, qb, future in futures:
            for lineup, family in future.result():
                key = lineup_key(lineup)
                saved = generated.setdefault(key, {"lineup": lineup, "sources": set()})
                source = f"global:{family}" if kind == "global" else f"qb_family:{qb.name}:{family}"
                saved["sources"].add(source)

    game_totals = sorted({float(player.game_total) for player in players if player.game_total is not None})
    sanity_pool = [{
        "player_id": player.player_id, "name": player.name, "team": player.team,
        "position": player.position, "salary": player.salary, "projection": player.projection,
    } for player in players]
    candidates = []
    for saved in generated.values():
        candidate = describe_candidate(
            saved["lineup"], all_players=players, config=config,
            pool_by_id=pool_by_id, ownership_available=False, game_totals=game_totals,
        )
        ids = [str(player.player_id) for player in saved["lineup"]]
        missing = [player.name for player in saved["lineup"] if str(player.player_id) not in ownership_by_id]
        candidate["ownership_complete"] = not missing
        candidate["ownership_missing_players"] = missing
        candidate["ownership_sum"] = (
            sum(float(ownership_by_id[pid]) for pid in ids) if not missing else None
        )
        candidate["log_ownership"] = (
            sum(log(max(0.01, float(ownership_by_id[pid])) / 100.0) for pid in ids)
            if not missing else None
        )
        candidate["generation_sources"] = sorted(saved["sources"])
        candidate["sanity"] = lineup_sanity_deficit(
            candidate["roster"], core_by_id=core_by_id, player_pool=sanity_pool,
        )
        candidates.append(candidate)
    candidates.sort(key=lambda row: (-float(row["objective_score"]), -float(row["mean"])))
    for rank, candidate in enumerate(candidates, 1):
        candidate["rank"] = rank
    complete = [row for row in candidates if row["ownership_complete"]]
    percentiles = relative_percentiles([float(row["log_ownership"]) for row in complete])
    for row in candidates:
        row["relative_chalk"] = None
    for row, percentile in zip(complete, percentiles, strict=True):
        row["relative_chalk"] = percentile
    return candidates, qb_eligibility


def score_lineup(
    ids: Iterable[str], *, players: list[Any], config: Any,
    pool_by_id: dict[str, dict[str, Any]], core_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    player_by_id = {str(player.player_id): player for player in players}
    lineup = [player_by_id[str(pid)] for pid in ids]
    game_totals = sorted({float(player.game_total) for player in players if player.game_total is not None})
    row = describe_candidate(
        lineup, all_players=players, config=config, pool_by_id=pool_by_id,
        ownership_available=False, game_totals=game_totals,
    )
    row["sanity"] = lineup_sanity_deficit(
        row["roster"], core_by_id=core_by_id,
        player_pool=[{
            "player_id": player.player_id, "name": player.name, "team": player.team,
            "position": player.position, "salary": player.salary, "projection": player.projection,
        } for player in players],
    )
    return row


def compact(
    row: Mapping[str, Any], *, control_score: float | None = None,
    original_model_mean: float | None = None,
) -> dict[str, Any]:
    return {
        "rank": row.get("rank"),
        "lineup_key": sorted(str(pid) for pid in row["player_ids"]),
        "lineup": [player["name"] for player in row["roster"]],
        "qb": row["qb"]["name"],
        "stack_form": row["stack"]["type"],
        "salary": row["salary"],
        "original_model_projection": (
            original_model_mean if original_model_mean is not None else row["mean"]
        ),
        "stressed_projection": row["mean"],
        "mean": row["mean"],
        "p90": row["p90"],
        "original_selector_objective": control_score if control_score is not None else row["objective_score"],
        "scenario_selector_objective": row["objective_score"],
        "relative_chalk": row.get("relative_chalk"),
        "football_sanity_deficit": row["sanity"]["total_football_sanity_deficit"],
        "generation_sources": row.get("generation_sources", []),
    }


def candidate_player_ids(row: Mapping[str, Any]) -> list[str]:
    """Read player IDs from either full solver rows or prior concise artifacts."""
    if row.get("player_ids"):
        return [str(player_id) for player_id in row["player_ids"]]
    return [str(player["player_id"]) for player in row.get("roster", [])]


def qb_family_rows(candidates: list[dict[str, Any]], control_by_id: Mapping[str, Any]) -> list[dict[str, Any]]:
    winner = float(candidates[0]["objective_score"])
    rows = []
    for qb, family in sorted({row["qb"]["name"]: row["qb"]["player_id"] for row in candidates}.items()):
        members = [row for row in candidates if row["qb"]["player_id"] == family]
        best = members[0]
        ids = [str(pid) for pid in best["player_ids"]]
        rows.append({
            "qb": qb,
            "candidate_count": len(members),
            "best_lineup_rank": best["rank"],
            "best_original_mean": sum(float(control_by_id[pid].projection) for pid in ids),
            "best_p90": best["p90"],
            "best_stressed_mean": best["mean"],
            "relative_chalk": best.get("relative_chalk"),
            "objective_gap_to_winner": winner - float(best["objective_score"]),
            "best_stack": best["stack"]["type"],
        })
    return sorted(rows, key=lambda row: (row["objective_gap_to_winner"], row["qb"]))


def markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Week 2 Sunday Main full robustness re-solve",
        "",
        "> Diagnostic only. Production projections and selector weights were not changed.",
        "",
        "## Decision output",
        "",
    ]
    for index, answer in enumerate(payload["decision_output"], 1):
        lines.append(f"{index}. {answer}")
    lines += ["", "## Scenario winners", "",
              "| Scenario | QB | Stack | Mean | P90 | Objective | Chalk | Sanity deficit |",
              "|---|---|---|---:|---:|---:|---:|---:|"]
    for scenario in payload["scenarios"]:
        row = scenario["winner"]
        lines.append(
            f"| {scenario['label']} | {row['qb']} | {row['stack_form']} | {row['mean']:.2f} | "
            f"{row['p90']:.2f} | {row['scenario_selector_objective']:.4f} | "
            f"{row['relative_chalk'] if row['relative_chalk'] is not None else 'Unavailable'} | "
            f"{row['football_sanity_deficit']:.3f} |"
        )
    lines += ["", "## Robust frontier", "",
              "| Lineup | Control rank | 25% rank | 50% rank | Worst rank | Mean regret | Max regret |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for row in payload["robust_frontier"][:20]:
        ranks = row["ranks"]
        lines.append(
            f"| {', '.join(row['lineup'])} | {ranks['control']} | "
            f"{ranks['stress_25_spread_preserving']} | {ranks['stress_50_spread_preserving']} | "
            f"{row['worst_rank']} | {row['mean_objective_regret']:.4f} | {row['maximum_objective_regret']:.4f} |"
        )
    lines += ["", "## Tracked shortlist", ""]
    for row in payload["tracked_shortlist"]:
        lines.append(f"### Previous #{row['previous_rank']}")
        lines.append("")
        lines.append(", ".join(row["lineup"]))
        lines.append("")
        for label, result in row["scenarios"].items():
            lines.append(
                f"- {label}: rank {result['rank']}; recreated={result['generator_recreated']}; "
                f"regret {result['objective_regret']:.4f}."
            )
        lines.append("")
    lines += ["## QB family results", ""]
    for scenario in payload["scenarios"]:
        lines += [f"### {scenario['label']}", "",
                  "| QB | Candidates | Best rank | Original mean | Scenario mean | P90 | Gap |",
                  "|---|---:|---:|---:|---:|---:|---:|"]
        for row in scenario["qb_families"]:
            lines.append(
                f"| {row['qb']} | {row['candidate_count']} | {row['best_lineup_rank']} | "
                f"{row['best_original_mean']:.2f} | {row['best_stressed_mean']:.2f} | "
                f"{row['best_p90']:.2f} | {row['objective_gap_to_winner']:.4f} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--projection-run-id", required=True)
    parser.add_argument("--espn", type=Path, required=True)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--prior-candidates", type=Path, required=True)
    parser.add_argument("--global-variants-per-family", type=int, default=12)
    parser.add_argument("--qb-variants-per-family", type=int, default=2)
    parser.add_argument("--output", type=Path, default=Path("artifacts/sunday-main-full-robustness-resolve-2026w2.json"))
    args = parser.parse_args()

    control_players, pool_by_id = prepare_pool(args.projection_run_id, None)
    control_by_id = {str(player.player_id): player for player in control_players}
    espn_payload = json.loads(args.espn.read_text())
    espn_by_id = {str(row["player_id"]): row for row in espn_payload["overlapping_players"]}
    external_qb_means = {
        player_id: float(row["espn_mean"])
        for player_id, row in espn_by_id.items() if str(row.get("position")) == "QB"
    }
    core_payload = json.loads(args.core.read_text())
    core_by_id = {str(row["player_id"]): row for row in core_payload["players"]}
    prior = json.loads(args.prior_candidates.read_text())
    prior_by_rank = {int(row["shadow_rank"]): row for row in prior["all_candidates"]}
    ownership_by_id, ownership_run = latest_ownership()

    seed = run_gpp_pipeline(
        2026, 2, "SUNDAY_MAIN", num_lineups=1, engine=engine, players=control_players,
        ownership_available=False, max_exposure=1.0, enforce_single_te=True,
        avoid_dst_opponents=True, large_gpp=True, minimum_uniqueness=2,
        max_from_team=4, max_from_game=5, include_control_comparisons=False,
    )
    config = seed.config
    scenario_state: dict[str, dict[str, Any]] = {}
    for label, blend, treatment in SCENARIOS:
        players, changes = scenario_players(
            control_players, espn_by_id, blend=blend, ceiling_treatment=treatment,
        )
        candidates, eligibility = generate_candidates(
            players, control_players=control_players, config=config,
            pool_by_id=pool_by_id, core_by_id=core_by_id, ownership_by_id=ownership_by_id,
            external_qb_means=external_qb_means,
            global_variants=args.global_variants_per_family,
            qb_variants=args.qb_variants_per_family,
        )
        if not candidates:
            raise RuntimeError(f"No candidates generated for {label}")
        scenario_state[label] = {
            "players": players, "candidates": candidates, "changes": changes,
            "eligibility": eligibility,
        }

    # Add original objective and report views after every independent solve finishes.
    scenarios = []
    for label, _, _ in SCENARIOS:
        state = scenario_state[label]
        top = []
        for row in state["candidates"][:10]:
            control_row = score_lineup(
                row["player_ids"], players=control_players, config=config,
                pool_by_id=pool_by_id, core_by_id=core_by_id,
            )
            top.append(compact(
                row,
                control_score=float(control_row["objective_score"]),
                original_model_mean=float(control_row["mean"]),
            ))
        scenarios.append({
            "label": label,
            "candidate_count": len(state["candidates"]),
            "material_players_shifted": len(state["changes"]),
            "winner": top[0],
            "top_10": top,
            "qb_eligibility": state["eligibility"],
            "qb_families": qb_family_rows(state["candidates"], control_by_id),
        })

    # Serious lineups are every top-10 scenario result plus the requested old shortlist.
    serious: dict[tuple[str, ...], dict[str, Any]] = {}
    for state in scenario_state.values():
        for row in state["candidates"][:10]:
            serious.setdefault(tuple(sorted(str(pid) for pid in row["player_ids"])), row)
    for rank in TRACKED_RANKS:
        row = prior_by_rank[rank]
        serious.setdefault(tuple(sorted(candidate_player_ids(row))), row)

    frontier = []
    generated_keys = {
        label: {tuple(sorted(str(pid) for pid in row["player_ids"])) for row in state["candidates"]}
        for label, state in scenario_state.items()
    }
    scored_serious: dict[str, dict[tuple[str, ...], dict[str, Any]]] = {}
    reference_scores: dict[str, float] = {}
    for label, _, _ in SCENARIOS:
        state = scenario_state[label]
        scored_serious[label] = {
            key: score_lineup(
                key, players=state["players"], config=config,
                pool_by_id=pool_by_id, core_by_id=core_by_id,
            ) for key in serious
        }
        reference_scores[label] = max(
            float(state["candidates"][0]["objective_score"]),
            *(float(row["objective_score"]) for row in scored_serious[label].values()),
        )

    for key, seed_row in serious.items():
        results = {}
        regrets = []
        ranks = {}
        for label, _, _ in SCENARIOS:
            state = scenario_state[label]
            scored = scored_serious[label][key]
            comparison_scores = {
                tuple(sorted(str(pid) for pid in row["player_ids"])): float(row["objective_score"])
                for row in state["candidates"]
            }
            comparison_scores.update({
                serious_key: float(serious_row["objective_score"])
                for serious_key, serious_row in scored_serious[label].items()
            })
            rank = 1 + sum(value > float(scored["objective_score"]) + 1e-12
                           for comparison_key, value in comparison_scores.items() if comparison_key != key)
            regret = reference_scores[label] - float(scored["objective_score"])
            ranks[label] = rank
            regrets.append(regret)
            results[label] = {
                "rank": rank,
                "objective": scored["objective_score"],
                "objective_regret": regret,
                "generator_recreated": key in generated_keys[label],
            }
        control_scored = score_lineup(
            key, players=control_players, config=config,
            pool_by_id=pool_by_id, core_by_id=core_by_id,
        )
        ownership_missing = [pid for pid in key if pid not in ownership_by_id]
        frontier.append({
            "lineup_key": list(key),
            "lineup": [control_by_id[pid].name for pid in key],
            "qb": control_scored["qb"]["name"],
            "ranks": ranks,
            "worst_rank": max(ranks.values()),
            "mean_objective_regret": mean(regrets),
            "maximum_objective_regret": max(regrets),
            "relative_chalk_raw_ownership_sum": None if ownership_missing else sum(ownership_by_id[pid] for pid in key),
            "football_sanity_deficit": control_scored["sanity"]["total_football_sanity_deficit"],
            "scenario_results": results,
        })
    frontier.sort(key=lambda row: (row["maximum_objective_regret"], row["mean_objective_regret"], row["worst_rank"]))

    tracked = []
    for rank in TRACKED_RANKS:
        old = prior_by_rank[rank]
        key = tuple(sorted(candidate_player_ids(old)))
        frontier_row = next(row for row in frontier if tuple(row["lineup_key"]) == key)
        tracked.append({
            "previous_rank": rank,
            "lineup": [row["name"] for row in old["roster"]],
            "legal_and_scorable": all(pid in control_by_id for pid in key),
            "scenarios": frontier_row["scenario_results"],
        })

    # QB evidence is audit-only and never enters candidate scoring.
    qb_names = sorted({player.name for player in control_players if player.position == "QB"})
    week1 = load_week1_qb_rows(qb_names)
    starters, team_starters = load_starter_rows()
    qb_diagnostics = []
    for player in sorted((p for p in control_players if p.position == "QB"), key=lambda p: -p.projection):
        espn = espn_by_id.get(str(player.player_id))
        raw = dict((week1.get(player.name) or {}).get("raw_row_json") or {})
        scenario_means = {
            label: next(p.projection for p in scenario_state[label]["players"] if p.player_id == player.player_id)
            for label in ("stress_25_spread_preserving", "stress_50_spread_preserving")
        }
        family_best = {}
        for scenario in scenarios:
            family = next((row for row in scenario["qb_families"] if row["qb"] == player.name), None)
            family_best[scenario["label"]] = family
        starter = starters.get(player.name)
        starter_confirmed = bool(starter) and (
            str(starter.get("evidence_tier") or "").lower() == "confirmed"
            or str(starter.get("status") or "").lower() in {"confirmed", "starter", "expected"}
        )
        attempts = raw.get("attempts") or raw.get("passing_attempts")
        carries = raw.get("carries") or raw.get("rushing_attempts")
        competitive = any(row and row["objective_gap_to_winner"] <= 0.20 for row in family_best.values())
        materially_low = bool(espn and float(espn["espn_mean"]) - player.projection >= MATERIAL_DIFFERENCE)
        qb_diagnostics.append({
            "qb": player.name, "team": player.team,
            "recent_pass_attempts": attempts, "recent_rushing_attempts": carries,
            "expected_start_status": (starter or {}).get("status", "unavailable"),
            "starter_evidence_tier": (starter or {}).get("evidence_tier", "unavailable"),
            "team_starter_evidence": [row["player_name"] for row in team_starters.get(player.team, [])],
            "team_implied_total": player.team_total,
            "current_model_mean": player.projection,
            "stress_25_mean": scenario_means["stress_25_spread_preserving"],
            "stress_50_mean": scenario_means["stress_50_spread_preserving"],
            "current_p90": player.ceiling,
            "family_best": family_best,
            "flag_low_projection_competitive_construction": bool(
                starter_confirmed and materially_low and competitive
            ),
        })

    tracked_by_rank = {row["previous_rank"]: row for row in tracked}
    major = {"Lamar Jackson", "Justin Herbert", "Bo Nix", "Carson Wentz"}
    competitive_major = []
    for scenario in scenarios:
        for row in scenario["qb_families"]:
            if row["qb"] in major and row["objective_gap_to_winner"] <= 0.20:
                competitive_major.append(f"{row['qb']} ({scenario['label']}, gap {row['objective_gap_to_winner']:.3f})")
    robust = frontier[0]
    evaluated_winners = {}
    for label, _, _ in SCENARIOS:
        evaluated_winners[label] = max(
            frontier,
            key=lambda row: float(row["scenario_results"][label]["objective"]),
        )
    previous_one = tracked_by_rank[1]
    prior_one_25_mean = previous_one["scenarios"]["stress_25_mean_only"]
    prior_one_25_spread = previous_one["scenarios"]["stress_25_spread_preserving"]
    winner_50 = evaluated_winners["stress_50_spread_preserving"]
    answer = [
        ("Yes." if prior_one_25_mean["rank"] == 1 else "No.")
        + f" Previous #1 ranks {prior_one_25_mean['rank']} under 25% mean-only stress; "
        + ("the generator did not recreate the exact lineup, so this result comes from explicit shortlist rescoring."
           if not prior_one_25_mean["generator_recreated"] else "the generator recreated it."),
        ("Yes." if prior_one_25_spread["rank"] == 1 else "No.")
        + f" Previous #1 ranks {prior_one_25_spread['rank']} when P90 is shifted consistently; "
        + ("the generator did not recreate the exact lineup."
           if not prior_one_25_spread["generator_recreated"] else "the generator recreated it."),
        f"At 50% spread-preserving stress, the best evaluated serious lineup is {', '.join(winner_50['lineup'])}.",
        ("Competitive major alternatives: " + "; ".join(sorted(set(competitive_major)))
         if competitive_major else "Lamar/Herbert/Nix/Wentz all generated families, but none finished within 0.20 objective points of a scenario winner."),
        f"The minimum-regret diagnostic lineup is {', '.join(robust['lineup'])} (max regret {robust['maximum_objective_regret']:.4f}).",
        f"Previous #6 has worst rank {max(x['rank'] for x in tracked_by_rank[6]['scenarios'].values())} and max regret "
        f"{max(x['objective_regret'] for x in tracked_by_rank[6]['scenarios'].values()):.4f}; compare directly with the frontier rather than assuming it remains the best lower-chalk alternative.",
        ("Yes: scenario winners differ, so projection uncertainty supports retaining multiple contest-entry candidates."
         if len({tuple(s['winner']['lineup_key']) for s in scenarios}) > 1
         else "No from this diagnostic alone: every scenario selected the same lineup."),
        "Refresh official inactives/starter evidence, injuries, weather and game markets, ownership, and the latest role/opportunity snapshot Sunday morning; then rerun production projections before final selection.",
    ]
    payload = {
        "artifact": "Week 2 Sunday Main full robustness re-solve",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "diagnostic_only": True,
        "projection_run_id": args.projection_run_id,
        "production_projection_changes": "None",
        "production_selector_weight_changes": "None",
        "hard_rules": {"opponents_vs_denver_excluded": True, "single_te": True},
        "method": {
            "material_difference": MATERIAL_DIFFERENCE,
            "stress_only_materially_disagreed_matched_players": True,
            "qb_top_n_each_view": QB_TOP_N,
            "qb_top_mean_n_each_view": QB_TOP_MEAN_N,
            "qb_value_gap_from_leader": QB_VALUE_GAP,
            "global_variants_per_family": args.global_variants_per_family,
            "qb_variants_per_family": args.qb_variants_per_family,
            "ownership_run_id": str(ownership_run.get("ownership_run_id") or ""),
        },
        "scenarios": scenarios,
        "robust_frontier": frontier,
        "tracked_shortlist": tracked,
        "qb_model_diagnostic": qb_diagnostics,
        "decision_output": answer,
    }
    args.output.write_text(json.dumps(payload, indent=2, default=str))
    args.output.with_suffix(".md").write_text(markdown(payload))
    print(json.dumps({
        "output": str(args.output),
        "scenario_candidate_counts": {row["label"]: row["candidate_count"] for row in scenarios},
        "winners": {row["label"]: row["winner"]["lineup"] for row in scenarios},
    }, indent=2))


if __name__ == "__main__":
    main()
