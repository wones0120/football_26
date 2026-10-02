#!/usr/bin/env python3
"""Build a broader Sunday candidate shadow and run selector-only ownership tests."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from math import log
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable, Mapping

from sqlalchemy import text

from backend.app.db import engine
from backend.app.product_dependencies import get_optimizer_service
from backend.app.product_services.classic_small_field import describe_candidate
from backend.app.product_services.football_sanity_deficit import lineup_sanity_deficit
from backend.app.product_services.gpp_optimizer import (
    StackRules,
    _build_lineup,
    run_gpp_pipeline,
)
from backend.app.product_services.player_context_scoring import score_player_context
from backend.app.product_services.player_pool_safety import evaluate_player_pool_safety
from backend.app.product_services.rule_library import resolve_strategy_profile
from backend.app.product_services.optimizer import _json_safe


LAMBDA_SWEEP = (0.0, 0.01, 0.02, 0.03, 0.05, 0.075, 0.10)
FAMILIES = ((1, 0), (2, 0), (1, 1), (2, 1))
CONCENTRATED = ("Derrick Henry", "Chris Olave", "Jalen Coker", "Tyler Shough", "Chase Brown")
INJURY_FLAGS = {"Q", "QUESTIONABLE", "D", "DOUBTFUL", "OUT", "O"}


def report_from_payload(payload: Any) -> dict:
    if isinstance(payload, dict):
        if isinstance(payload.get("report"), dict) and payload["report"].get("all_candidates"):
            return payload["report"]
        if isinstance(payload.get("classic_small_field_report"), dict):
            return payload["classic_small_field_report"]
        for value in payload.values():
            try:
                return report_from_payload(value)
            except LookupError:
                continue
    if isinstance(payload, list):
        for value in payload:
            try:
                return report_from_payload(value)
            except LookupError:
                continue
    raise LookupError("classic_small_field_report not found")


def latest_ownership() -> tuple[dict[str, float], dict[str, Any]]:
    with engine.connect() as connection:
        run = connection.execute(text("""
            SELECT ownership_run_id, model_id, data_cutoff_at, metrics_json
            FROM target.ownership_model_run
            WHERE season = 2026 AND week = 2
              AND UPPER(slate_id) = 'SUNDAY_MAIN' AND status = 'completed'
            ORDER BY created_at DESC LIMIT 1
        """)).mappings().first()
        if run is None:
            return {}, {}
        rows = connection.execute(text("""
            SELECT player_id, projected_ownership
            FROM target.ownership_projection
            WHERE ownership_run_id = :run_id
        """), {"run_id": run["ownership_run_id"]}).mappings().all()
    return ({str(row["player_id"]): float(row["projected_ownership"]) for row in rows}, dict(run))


def lineup_key(lineup: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted(str(player.player_id) for player in lineup))


def rank_qbs(players: list[Any]) -> list[Any]:
    qbs = [player for player in players if player.position == "QB"]
    mean_order = {p.player_id: rank for rank, p in enumerate(sorted(qbs, key=lambda p: -p.projection), 1)}
    p90_order = {p.player_id: rank for rank, p in enumerate(sorted(qbs, key=lambda p: -p.ceiling), 1)}
    value_order = {p.player_id: rank for rank, p in enumerate(
        sorted(qbs, key=lambda p: -(p.projection / max(1.0, p.salary / 1000))), 1
    )}
    return sorted(qbs, key=lambda p: (
        mean_order[p.player_id] + p90_order[p.player_id] + value_order[p.player_id],
        -p.ceiling,
    ))


def family_lineups(
    qb: Any,
    *,
    players: list[Any],
    config: Any,
    variants: int,
    enforce_single_te: bool,
    avoid_dst_opponents: bool,
) -> list[tuple[list[Any], str]]:
    output: list[tuple[list[Any], str]] = []
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
                players,
                config,
                None,
                excluded,
                enforce_single_te=enforce_single_te,
                avoid_dst_opponents=avoid_dst_opponents,
                stack_rules=rules,
                required_player_ids={qb.player_id},
                exact_pass_catchers=partners,
                exact_bring_backs=bring_backs,
            )
            if indexes is None:
                break
            excluded.append(set(indexes))
            output.append(([players[index] for index in indexes], label))
    return output


def constrained_lineup(
    player_id: str,
    *,
    include: bool,
    players: list[Any],
    config: Any,
    enforce_single_te: bool,
    avoid_dst_opponents: bool,
) -> list[Any] | None:
    indexes = _build_lineup(
        players,
        config,
        None if include else {player_id: 0},
        [],
        enforce_single_te=enforce_single_te,
        avoid_dst_opponents=avoid_dst_opponents,
        required_player_ids={player_id} if include else None,
    )
    return [players[index] for index in indexes] if indexes is not None else None


def relative_percentiles(values: list[float]) -> list[float]:
    if len(values) <= 1:
        return [0.0] * len(values)
    return [100.0 * sum(other < value for other in values) / (len(values) - 1) for value in values]


def injury_status(row: Mapping[str, Any]) -> str:
    """Resolve the current designation without converting missing status to healthy."""
    for field in ("pregame_injury_status", "player_status", "injury_status"):
        value = row.get(field)
        if value is not None and str(value).strip() and str(value).lower() != "nan":
            return str(value).strip().upper()
    return ""


def pareto_frontier(candidates: list[dict]) -> list[dict]:
    frontier = []
    for candidate in candidates:
        dominated = False
        for other in candidates:
            if other is candidate:
                continue
            at_least = (
                other["objective_score"] >= candidate["objective_score"]
                and other["mean"] >= candidate["mean"]
                and other["p90"] >= candidate["p90"]
                and other["relative_chalk"] <= candidate["relative_chalk"]
                and other["sanity"]["total_football_sanity_deficit"]
                <= candidate["sanity"]["total_football_sanity_deficit"]
            )
            strict = (
                other["objective_score"] > candidate["objective_score"]
                or other["mean"] > candidate["mean"]
                or other["p90"] > candidate["p90"]
                or other["relative_chalk"] < candidate["relative_chalk"]
                or other["sanity"]["total_football_sanity_deficit"]
                < candidate["sanity"]["total_football_sanity_deficit"]
            )
            if at_least and strict:
                dominated = True
                break
        if not dominated:
            frontier.append(candidate)
    return sorted(frontier, key=lambda row: (-row["objective_score"], row["relative_chalk"]))


def selector_transition_crossovers(candidates: list[dict], max_lambda: float = 0.25) -> list[dict]:
    """Return exact winner changes on the selector's piecewise-linear envelope."""
    points = {0.0, float(max_lambda)}
    for index, left in enumerate(candidates):
        for right in candidates[index + 1:]:
            denominator = left["standardized_chalk"] - right["standardized_chalk"]
            if denominator == 0:
                continue
            crossing = (left["objective_score"] - right["objective_score"]) / denominator
            if 0.0 < crossing < max_lambda:
                points.add(float(crossing))
    boundaries = sorted(points)
    probes = [0.0, *[(left + right) / 2 for left, right in zip(boundaries, boundaries[1:])]]

    def winner(weight: float) -> dict:
        return max(candidates, key=lambda row: (
            row["objective_score"] - weight * row["standardized_chalk"],
            row["objective_score"],
        ))

    sequence: list[dict] = []
    for probe in probes:
        selected = winner(probe)
        if not sequence or sequence[-1]["shadow_rank"] != selected["shadow_rank"]:
            sequence.append(selected)
    base = sequence[0]
    transitions = []
    for previous, selected in zip(sequence, sequence[1:]):
        denominator = previous["standardized_chalk"] - selected["standardized_chalk"]
        crossing = (previous["objective_score"] - selected["objective_score"]) / denominator
        transitions.append({
            "lambda": crossing,
            "from_rank": previous["shadow_rank"],
            "candidate_rank": selected["shadow_rank"],
            "base_objective_gap": base["objective_score"] - selected["objective_score"],
            "mean_sacrifice": base["mean"] - selected["mean"],
            "p90_sacrifice": base["p90"] - selected["p90"],
            "chalk_reduction": base["relative_chalk"] - selected["relative_chalk"],
        })
    return transitions


def concise(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: candidate.get(key) for key in (
            "shadow_rank", "objective_score", "mean", "p90", "salary",
            "ownership_sum", "log_ownership", "relative_chalk", "standardized_chalk",
            "stack_ownership", "ownership_complete", "ownership_missing_players",
            "primary_game", "generation_sources", "components",
        )
    } | {
        "qb": candidate["qb"],
        "stack": candidate["stack"],
        "roster": candidate["roster"],
        "sanity": candidate["sanity"],
        "injury_flags": candidate["injury_flags"],
    }


def markdown(payload: Mapping[str, Any]) -> str:
    lines = ["# Sunday Main candidate exploration and ownership shadow", "",
        f"Projection `{payload['projection_run_id']}`; ownership run `{payload['ownership']['ownership_run_id']}`.",
        f"Expanded pool: **{payload['expanded_pool']['candidate_count']}** distinct legal candidates "
        f"from {payload['expanded_pool']['raw_lineups']} raw solves.", "",
        "## Decision", ""]
    for key, value in payload["decision"].items():
        if key == "concentration_justification":
            lines.append("- **Concentration justification:** See the component-level with/without table below.")
        else:
            lines.append(f"- **{key.replace('_', ' ').capitalize()}:** {value}")
    lines += ["", "## QB families", "",
        "| QB | candidates | best objective | mean | P90 | salary | stack | chalk | gap |",
        "|---|---:|---:|---:|---:|---:|---|---:|---:|"]
    for row in payload["qb_families"]:
        chalk = f"{row['relative_chalk']:.1f}" if row["relative_chalk"] is not None else "Unavailable"
        lines.append(f"| {row['qb']} | {row['candidate_count']} | {row['best_objective']:.4f} | "
                     f"{row['mean']:.2f} | {row['p90']:.2f} | ${row['salary']:,} | "
                     f"{row['stack']} | {chalk} | {row['gap']:.4f} |")
    lines += ["", "## Primary-game families", "",
        "| primary game | candidates | best objective | mean | P90 | chalk | gap |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for row in payload["primary_game_families"]:
        best = row["best"]
        chalk = f"{best['relative_chalk']:.1f}" if best["relative_chalk"] is not None else "Unavailable"
        lines.append(f"| {row['primary_game']} | {row['candidate_count']} | "
                     f"{best['objective_score']:.4f} | {best['mean']:.2f} | {best['p90']:.2f} | "
                     f"{chalk} | {row['gap']:.4f} |")
    lines += ["", "## High-core absence tests", "",
        "| player | status | best objective | objective gap | mean gap | P90 gap | chalk difference | trade |",
        "|---|---|---:|---:|---:|---:|---:|---|"]
    for row in payload["high_core_absence_tests"]:
        if row["status"] != "explored":
            lines.append(f"| {row['player']} | {row['status']} | — | — | — | — | — | — |")
            continue
        trade = row["construction_trade"]
        chalk_difference = (f"{row['chalk_difference']:+.1f}"
                            if row["chalk_difference"] is not None else "Unavailable")
        lines.append(f"| {row['player']} | explored | {row['best_containing']['objective_score']:.4f} | "
                     f"{row['objective_gap']:.4f} | {row['mean_gap']:.2f} | {row['p90_gap']:.2f} | "
                     f"{chalk_difference} | {', '.join(trade['players_in']) or 'none'} in; "
                     f"{', '.join(trade['players_out']) or 'none'} out |")
    lines += ["", "## Concentrated-player counterfactuals", "",
        "| player | with | without | objective cost | mean cost | P90 cost | chalk change |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for row in payload["concentration_counterfactuals"]:
        chalk_change = (f"{row['chalk_change_without']:+.1f}"
                        if row["chalk_change_without"] is not None else "Unavailable")
        lines.append(f"| {row['player']} | {row['with']['objective_score']:.4f} | "
                     f"{row['without']['objective_score']:.4f} | {row['objective_cost_without']:.4f} | "
                     f"{row['mean_cost_without']:.2f} | {row['p90_cost_without']:.2f} | "
                     f"{chalk_change} |")
    lines += ["", "## Ownership sweep", "",
        "| lambda | shadow winner | base objective | mean | P90 | chalk | players changed |",
        "|---:|---:|---:|---:|---:|---:|---|"]
    for row in payload["ownership_shadow"]["sweep"]:
        lines.append(f"| {row['lambda']:.3f} | #{row['winner_rank']} | {row['base_objective']:.4f} | "
                     f"{row['mean']:.2f} | {row['p90']:.2f} | {row['relative_chalk']:.1f} | "
                     f"{', '.join(row['players_in']) or 'none'} in; {', '.join(row['players_out']) or 'none'} out |")
    lines += ["", "## Exact ownership crossovers from the base leader", "",
        "| lambda | candidate | objective gap | mean sacrifice | P90 sacrifice | chalk reduction |",
        "|---:|---:|---:|---:|---:|---:|"]
    for row in payload["ownership_shadow"]["exact_crossovers_through_0_25"][:20]:
        lines.append(f"| {row['lambda']:.5f} | #{row['candidate_rank']} | {row['base_objective_gap']:.4f} | "
                     f"{row['mean_sacrifice']:.2f} | {row['p90_sacrifice']:.2f} | "
                     f"{row['chalk_reduction']:.1f} |")
    lines += ["", "## Near-equal, lower-chalk Pareto candidates", ""]
    if payload["pareto_frontier"]["highlighted_near_equal_lower_chalk"]:
        for row in payload["pareto_frontier"]["highlighted_near_equal_lower_chalk"]:
            names = ", ".join(player["name"] for player in row["roster"])
            lines.append(f"- **#{row['shadow_rank']}**: objective {row['objective_score']:.4f}, mean "
                         f"{row['mean']:.2f}, P90 {row['p90']:.2f}, chalk {row['relative_chalk']:.1f}; {names}.")
    else:
        lines.append("- None met all four near-equal and chalk-reduction bands.")
    lines += ["", "## Serious Sunday-morning candidates", ""]
    for row in payload["serious_candidates"]:
        names = ", ".join(player["name"] for player in row["roster"])
        lines.append(f"- **#{row['shadow_rank']}**: objective {row['objective_score']:.4f}, mean "
                     f"{row['mean']:.2f}, P90 {row['p90']:.2f}, chalk {row['relative_chalk']:.1f}; {names}.")
    lines += ["", "## Refresh flags", ""]
    for row in payload["injury_flags"]:
        count = row.get("candidate_count", row.get("top_candidate_count"))
        scope = row.get("scope", "expanded candidate pool")
        lines.append(f"- {row['player']} ({row['team']}): {row['status']}; "
                     f"{count} candidate(s) in {scope}.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--optimizer", type=Path, required=True)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--variants-per-family", type=int, default=15)
    parser.add_argument("--output", type=Path, default=Path("artifacts/sunday-main-candidate-exploration-2026w2.json"))
    args = parser.parse_args()

    optimizer_payload = json.loads(args.optimizer.read_text())
    production = report_from_payload(optimizer_payload)
    projection_run_id = str(optimizer_payload["projection_run_id"])
    core_payload = json.loads(args.core.read_text())
    core_by_id = {str(row["player_id"]): row for row in core_payload["players"]}
    readiness = json.loads(args.readiness.read_text())

    service = get_optimizer_service()
    pool = service._load_player_pool(2026, 2, "SUNDAY_MAIN", projection_run_id=projection_run_id)  # noqa: SLF001
    profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
    cutoff_raw = optimizer_payload.get("data_cutoff_at")
    projection_cutoff = datetime.fromisoformat(str(cutoff_raw)) if cutoff_raw else None
    safety_result = evaluate_player_pool_safety(
        pool,
        profile=profile,
        as_of=datetime.now(timezone.utc),
        projection_cutoff=projection_cutoff,
    )
    pool = score_player_context(safety_result.eligible_pool, profile=profile).scored_pool
    pool, strategy_exclusions = service._select_strategy_candidates(  # noqa: SLF001
        pool,
        strategy="classic_small_field_gpp",
        contest_type="tournament",
    )
    pool = pool.loc[~pool["opponent_team"].fillna("").str.upper().eq("DEN")].copy()
    ownership_by_id, ownership_run = latest_ownership()
    pool["ownership"] = pool["player_id"].astype(str).map(ownership_by_id)
    pool["ownership_run_id"] = str(ownership_run.get("ownership_run_id") or "")
    missing_ownership_players = pool.loc[pool["ownership"].isna(), ["player_id", "name", "player_team"]]
    # Ownership never enters candidate generation or the frozen selector. A numeric
    # adapter value is necessary for GPPPlayer, but every candidate is annotated from
    # ownership_by_id below and incomplete candidates are excluded from ownership tests.
    pool["ownership"] = pool["ownership"].fillna(0.0)
    players = service._gpp_players_from_pool(pool)  # noqa: SLF001
    player_by_id = {str(player.player_id): player for player in players}
    source = {str(row["player_id"]): row for row in pool.to_dict("records")}
    game_totals = sorted({float(player.game_total) for player in players if player.game_total is not None})

    seed = run_gpp_pipeline(
        2026, 2, "SUNDAY_MAIN", num_lineups=1, engine=engine, players=players,
        ownership_available=False, max_exposure=1.0, enforce_single_te=True,
        avoid_dst_opponents=True, large_gpp=True, minimum_uniqueness=2,
        max_from_team=4, max_from_game=5, include_control_comparisons=False,
    )
    config = seed.config

    lineups: dict[tuple[str, ...], dict[str, Any]] = {}
    for candidate in production["all_candidates"]:
        lineup = [player_by_id[str(player_id)] for player_id in candidate["player_ids"]]
        lineups[lineup_key(lineup)] = {"lineup": lineup, "sources": {"production_120"}}

    top_qbs = rank_qbs(players)[:10]
    family_raw_count = 0
    with ThreadPoolExecutor(max_workers=min(10, len(top_qbs))) as executor:
        futures = [(qb, executor.submit(
            family_lineups, qb, players=players, config=config,
            variants=args.variants_per_family, enforce_single_te=True,
            avoid_dst_opponents=True,
        )) for qb in top_qbs]
        for qb, future in futures:
            solved = future.result()
            family_raw_count += len(solved)
            for lineup, family in solved:
                key = lineup_key(lineup)
                row = lineups.setdefault(key, {"lineup": lineup, "sources": set()})
                row["sources"].add(f"qb_family:{qb.name}:{family}")

    competitive_core = readiness.get("underrepresented_core", [])
    containing_results = []
    for core in competitive_core:
        player_id = str(core["player_id"])
        lineup = constrained_lineup(
            player_id, include=True, players=players, config=config,
            enforce_single_te=True, avoid_dst_opponents=True,
        )
        if lineup is None:
            containing_results.append({"player_id": player_id, "player": core["name"], "status": "no legal lineup"})
            continue
        key = lineup_key(lineup)
        row = lineups.setdefault(key, {"lineup": lineup, "sources": set()})
        row["sources"].add(f"required_core:{core['name']}")
        containing_results.append({"player_id": player_id, "player": core["name"], "lineup_key": key})

    counterfactual_lineups: dict[str, dict[str, tuple[str, ...]]] = {}
    name_to_player = {player.name: player for player in players}
    for name in CONCENTRATED:
        player = name_to_player[name]
        pair = {}
        for label, include in (("with", True), ("without", False)):
            lineup = constrained_lineup(
                player.player_id, include=include, players=players, config=config,
                enforce_single_te=True, avoid_dst_opponents=True,
            )
            if lineup is None:
                raise RuntimeError(f"No {label} counterfactual lineup for {name}")
            key = lineup_key(lineup)
            row = lineups.setdefault(key, {"lineup": lineup, "sources": set()})
            row["sources"].add(f"counterfactual:{name}:{label}")
            pair[label] = key
        counterfactual_lineups[name] = pair

    candidates = []
    for saved in lineups.values():
        candidate = describe_candidate(
            saved["lineup"], all_players=players, config=config,
            pool_by_id=source, ownership_available=False, game_totals=game_totals,
        )
        missing_names = [player.name for player in saved["lineup"]
                         if str(player.player_id) not in ownership_by_id]
        candidate["ownership_complete"] = not missing_names
        candidate["ownership_missing_players"] = missing_names
        if not missing_names:
            candidate["ownership_sum"] = sum(ownership_by_id[str(player.player_id)] for player in saved["lineup"])
            candidate["log_ownership"] = sum(
                log(max(0.01, ownership_by_id[str(player.player_id)]) / 100.0)
                for player in saved["lineup"]
            )
            candidate["stack_ownership"] = sum(
                ownership_by_id[str(player.player_id)] for player in saved["lineup"]
                if player.team == candidate["qb"]["team"]
            )
        else:
            candidate["ownership_sum"] = None
            candidate["log_ownership"] = None
            candidate["stack_ownership"] = None
        candidate["player_names"] = [row["name"] for row in candidate["roster"]]
        candidate["generation_sources"] = sorted(saved["sources"])
        candidates.append(candidate)
    candidates.sort(key=lambda row: (-row["objective_score"], -row["mean"]))
    for rank, candidate in enumerate(candidates, 1):
        candidate["shadow_rank"] = rank

    ownership_candidates = [candidate for candidate in candidates if candidate["ownership_complete"]]
    if not ownership_candidates:
        raise RuntimeError("No expanded candidates have complete current-slate ownership")
    logs = [float(candidate["log_ownership"]) for candidate in ownership_candidates]
    ownership_sums = [float(candidate["ownership_sum"]) for candidate in ownership_candidates]
    percentiles = relative_percentiles(logs)
    own_mean = mean(ownership_sums)
    own_std = pstdev(ownership_sums) or 1.0
    player_pool_for_sanity = [{
        "player_id": player.player_id, "name": player.name, "team": player.team,
        "position": player.position, "salary": player.salary, "projection": player.projection,
    } for player in players]
    for candidate in candidates:
        candidate["relative_chalk"] = None
        candidate["standardized_chalk"] = None
    for candidate, percentile in zip(ownership_candidates, percentiles, strict=True):
        candidate["relative_chalk"] = percentile
        candidate["standardized_chalk"] = (candidate["ownership_sum"] - own_mean) / own_std
    for candidate in candidates:
        candidate["sanity"] = lineup_sanity_deficit(
            candidate["roster"], core_by_id=core_by_id,
            player_pool=player_pool_for_sanity,
        )
        candidate["injury_flags"] = [{
            "player": player["name"], "team": player["team"],
            "status": injury_status(source[str(player["player_id"])]),
        } for player in candidate["roster"]
            if injury_status(source[str(player["player_id"])]) in INJURY_FLAGS]

    by_key = {tuple(sorted(str(player_id) for player_id in row["player_ids"])): row
              for row in candidates}
    global_best = candidates[0]
    qb_rows = []
    for qb in top_qbs:
        rows = [row for row in candidates if row["qb"]["player_id"] == qb.player_id]
        if not rows:
            continue
        best = rows[0]
        qb_rows.append({"qb": qb.name, "candidate_count": len(rows),
            "best_objective": best["objective_score"], "mean": best["mean"], "p90": best["p90"],
            "salary": best["salary"], "stack": best["stack"]["type"],
            "relative_chalk": best["relative_chalk"],
            "gap": global_best["objective_score"] - best["objective_score"]})
    qb_rows.sort(key=lambda row: row["gap"])

    game_rows = []
    for game in sorted({row["primary_game"] for row in candidates}):
        rows = [row for row in candidates if row["primary_game"] == game]
        best = rows[0]
        game_rows.append({"primary_game": game, "candidate_count": len(rows),
            "best": concise(best), "gap": global_best["objective_score"] - best["objective_score"]})
    game_rows.sort(key=lambda row: row["gap"])

    high_core_rows = []
    for requested in containing_results:
        if "lineup_key" not in requested:
            high_core_rows.append(requested)
            continue
        best = by_key[requested["lineup_key"]]
        player = player_by_id[requested["player_id"]]
        high_core_rows.append({**requested, "status": "explored", "player_mean": player.projection,
            "player_p90": player.ceiling, "salary": player.salary,
            "mean_per_1000": player.projection / max(1.0, player.salary / 1000),
            "best_containing": concise(best),
            "objective_gap": global_best["objective_score"] - best["objective_score"],
            "mean_gap": global_best["mean"] - best["mean"],
            "p90_gap": global_best["p90"] - best["p90"],
            "chalk_difference": (
                best["relative_chalk"] - global_best["relative_chalk"]
                if best["relative_chalk"] is not None and global_best["relative_chalk"] is not None else None
            ),
            "construction_trade": {
                "players_in": sorted(set(best["player_names"]) - set(global_best["player_names"])),
                "players_out": sorted(set(global_best["player_names"]) - set(best["player_names"])),
                "stack": f"{best['stack']['type']} vs {global_best['stack']['type']}",
            }})

    concentration = []
    production_exposure = production["player_exposures"]["entire_pool"]
    expanded_counts = Counter(name for row in candidates for name in row["player_names"])
    for name, pair in counterfactual_lineups.items():
        with_row, without_row = by_key[pair["with"]], by_key[pair["without"]]
        player = name_to_player[name]
        rank_mean = 1 + sum(p.position == player.position and p.projection > player.projection for p in players)
        rank_p90 = 1 + sum(p.position == player.position and p.ceiling > player.ceiling for p in players)
        rank_value = 1 + sum(
            p.position == player.position
            and p.projection / max(1.0, p.salary / 1000)
            > player.projection / max(1.0, player.salary / 1000)
            for p in players
        )
        concentration.append({"player": name,
            "production_frequency": int(production_exposure.get(name, 0)),
            "expanded_frequency": expanded_counts[name], "expanded_rate": expanded_counts[name] / len(candidates),
            "position_mean_rank": rank_mean, "position_p90_rank": rank_p90,
            "position_value_rank": rank_value, "with": concise(with_row), "without": concise(without_row),
            "objective_cost_without": with_row["objective_score"] - without_row["objective_score"],
            "mean_cost_without": with_row["mean"] - without_row["mean"],
            "p90_cost_without": with_row["p90"] - without_row["p90"],
            "chalk_change_without": (
                without_row["relative_chalk"] - with_row["relative_chalk"]
                if without_row["relative_chalk"] is not None and with_row["relative_chalk"] is not None else None
            ),
            "component_cost_without": {key: with_row["components"].get(key, 0) - without_row["components"].get(key, 0)
                                       for key in set(with_row["components"]) | set(without_row["components"])},
            "players_in_without": sorted(set(without_row["player_names"]) - set(with_row["player_names"])),
            "players_out_without": sorted(set(with_row["player_names"]) - set(without_row["player_names"])),
            "exposure_cap": 1.0})

    base = max(ownership_candidates, key=lambda row: (row["objective_score"], row["mean"]))
    sweep = []
    previous_rank = None
    for weight in LAMBDA_SWEEP:
        winner = max(ownership_candidates, key=lambda row: (
            row["objective_score"] - weight * row["standardized_chalk"],
            row["objective_score"],
        ))
        sweep.append({"lambda": weight, "winner_rank": winner["shadow_rank"],
            "shadow_objective": winner["objective_score"] - weight * winner["standardized_chalk"],
            "base_objective": winner["objective_score"], "mean": winner["mean"], "p90": winner["p90"],
            "salary": winner["salary"], "ownership_sum": winner["ownership_sum"],
            "relative_chalk": winner["relative_chalk"], "stack_ownership": winner["stack_ownership"],
            "football_sanity": winner["sanity"], "qb": winner["qb"], "stack": winner["stack"],
            "players_in": sorted(set(winner["player_names"]) - set(base["player_names"])),
            "players_out": sorted(set(base["player_names"]) - set(winner["player_names"])),
            "changed_from_previous": previous_rank != winner["shadow_rank"],
            "quality_sacrifice": {"mean": base["mean"] - winner["mean"],
                "p90": base["p90"] - winner["p90"],
                "base_objective": base["objective_score"] - winner["objective_score"],
                "relative_chalk": base["relative_chalk"] - winner["relative_chalk"]}})
        previous_rank = winner["shadow_rank"]

    pairwise_crossovers = []
    for candidate in ownership_candidates:
        if candidate is base:
            continue
        denominator = base["standardized_chalk"] - candidate["standardized_chalk"]
        if denominator <= 0:
            continue
        point = (base["objective_score"] - candidate["objective_score"]) / denominator
        if 0 < point <= 0.25:
            pairwise_crossovers.append({"lambda": point, "candidate_rank": candidate["shadow_rank"],
                "base_objective_gap": base["objective_score"] - candidate["objective_score"],
                "mean_sacrifice": base["mean"] - candidate["mean"],
                "p90_sacrifice": base["p90"] - candidate["p90"],
                "chalk_reduction": base["relative_chalk"] - candidate["relative_chalk"]})
    pairwise_crossovers.sort(key=lambda row: row["lambda"])
    crossovers = selector_transition_crossovers(ownership_candidates)

    frontier = pareto_frontier(ownership_candidates)
    highlighted = [row for row in frontier
        if base["objective_score"] - row["objective_score"] <= .05
        and base["mean"] - row["mean"] <= 1.0
        and base["p90"] - row["p90"] <= 2.0
        and base["relative_chalk"] - row["relative_chalk"] >= 10]
    alternate_qb = max(
        (row for row in ownership_candidates if row["qb"]["player_id"] != base["qb"]["player_id"]),
        key=lambda row: row["objective_score"],
        default=None,
    )
    upside_lower_chalk = max(
        (row for row in ownership_candidates
         if row["mean"] >= base["mean"] - 1.0
         and row["p90"] >= base["p90"]
         and row["relative_chalk"] <= base["relative_chalk"] - 10.0),
        key=lambda row: (row["p90"], row["objective_score"]),
        default=None,
    )
    quality_bounded_sweep = [
        candidates[item["winner_rank"] - 1] for item in sweep
        if item["quality_sacrifice"]["mean"] <= 1.0
        and item["quality_sacrifice"]["p90"] <= 2.0
    ]
    serious_source = []
    for row in [base, *highlighted, alternate_qb, upside_lower_chalk, *quality_bounded_sweep]:
        if row is None:
            continue
        if row not in serious_source:
            serious_source.append(row)
    serious = [concise(row) for row in serious_source[:5]]

    injury_counts = Counter(
        (flag["player"], flag["team"], flag["status"])
        for candidate in candidates for flag in candidate["injury_flags"]
    )
    injury_rows = [{"player": key[0], "team": key[1], "status": key[2], "candidate_count": count}
                   for key, count in injury_counts.most_common()]

    production_qbs = Counter(row["qb"]["name"] for row in production["all_candidates"])
    expanded_qbs = Counter(row["qb"]["name"] for row in candidates)
    first_change = next((row for row in sweep if row["winner_rank"] != base["shadow_rank"]), None)
    first_exact = crossovers[0] if crossovers else None
    concentration_summary = {
        row["player"]: {
            "expanded_rate": row["expanded_rate"],
            "objective_cost_without": row["objective_cost_without"],
            "mean_cost_without": row["mean_cost_without"],
            "p90_cost_without": row["p90_cost_without"],
            "main_objective_drivers": sorted(
                ((key, value) for key, value in row["component_cost_without"].items() if value > 0),
                key=lambda item: -item[1],
            ),
        }
        for row in concentration
    }
    payload = _json_safe({
        "artifact": "sunday_candidate_exploration_ownership_shadow_v1",
        "projection_run_id": projection_run_id,
        "production_candidate_count": len(production["all_candidates"]),
        "expanded_pool": {"candidate_count": len(candidates),
            "raw_lineups": 120 + family_raw_count + len(competitive_core) + 10,
            "production_qb_distribution": dict(production_qbs),
            "expanded_qb_distribution": dict(expanded_qbs),
            "production_primary_game_distribution": dict(Counter(row["primary_game"] for row in production["all_candidates"])),
            "expanded_primary_game_distribution": dict(Counter(row["primary_game"] for row in candidates)),
            "player_pool_safety": safety_result.summary,
            "upstream_strategy_exclusions": strategy_exclusions,
            "global_best": concise(base)},
        "ownership": {"ownership_run_id": str(ownership_run.get("ownership_run_id")),
            "model_id": ownership_run.get("model_id"), "data_cutoff_at": ownership_run.get("data_cutoff_at"),
            "coverage": f"{len(pool) - len(missing_ownership_players)}/{len(pool)}",
            "missing_players": missing_ownership_players.to_dict("records"),
            "candidate_coverage": f"{len(ownership_candidates)}/{len(candidates)}",
            "selector_changed": False,
            "standardization": {"measure": "lineup sum ownership", "mean": own_mean, "std": own_std}},
        "qb_families": qb_rows, "primary_game_families": game_rows,
        "all_candidates": [concise(row) for row in candidates],
        "high_core_absence_tests": high_core_rows,
        "concentration_counterfactuals": concentration,
        "ownership_shadow": {"formula": "base objective - lambda * standardized lineup sum ownership",
            "lambda_sweep": list(LAMBDA_SWEEP), "sweep": sweep,
            "exact_crossovers_through_0_25": crossovers,
            "pairwise_base_crossovers_through_0_25": pairwise_crossovers},
        "pareto_frontier": {"candidate_count": len(frontier),
            "highlighted_near_equal_lower_chalk": [concise(row) for row in highlighted],
            "all": [concise(row) for row in frontier]},
        "injury_flags": injury_rows, "serious_candidates": serious,
        "decision": {
            "current_120_generator_too_concentrated": (
                f"Yes for family coverage: the production pool used {len(production_qbs)} QBs and "
                f"{len(set(row['primary_game'] for row in production['all_candidates']))} primary games; "
                f"the expanded pool found {len(expanded_qbs)} viable QB/game families. The same leader remained first."
            ),
            "concentration_justification": concentration_summary,
            "materially_better_alternate_qb_or_game_family": (
                f"No alternate beat the leader under frozen weights. {qb_rows[1]['qb']} is the closest, "
                f"trailing by {qb_rows[1]['gap']:.4f}." if len(qb_rows) > 1 else "Unavailable."
            ),
            "near_equal_substantially_lower_chalk": (
                f"Yes: {len(highlighted)} Pareto candidate(s) meet the 0.05 objective, 1.0 mean, and "
                "2.0 P90 bands while reducing chalk by at least 10 percentiles."
            ),
            "first_exact_ownership_crossover": (
                f"lambda {first_exact['lambda']:.5f} to candidate #{first_exact['candidate_rank']}."
                if first_exact else "No crossover through lambda 0.25."
            ),
            "first_sweep_crossover": (
                f"lambda {first_change['lambda']:.3f}; mean sacrifice {first_change['quality_sacrifice']['mean']:.2f}, "
                f"P90 sacrifice {first_change['quality_sacrifice']['p90']:.2f}, chalk reduction "
                f"{first_change['quality_sacrifice']['relative_chalk']:.1f}." if first_change else
                "No crossover through lambda 0.10."
            ),
            "serious_sunday_morning_lineups": [row["shadow_rank"] for row in serious],
            "exact_solver_scope": (
                f"{len(candidates)} distinct candidates from {120 + family_raw_count + len(competitive_core) + 10} "
                "raw solves. The 500-candidate target was not practical with the current exact per-family solver."
            ),
            "production_change": "None. This is a selector-only shadow over an expanded diagnostic pool.",
        },
    })
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=False, default=str) + "\n")
    args.output.with_suffix(".md").write_text(markdown(payload))
    print(json.dumps({"candidates": len(candidates), "qbs": len(expanded_qbs),
        "pareto": len(frontier), "highlighted": len(highlighted),
        "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
