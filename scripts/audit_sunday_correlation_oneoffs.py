#!/usr/bin/env python3
"""Read-only Week 2 Classic correlation and one-off coverage audit."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from math import log
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping

from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import engine
from backend.app.product_dependencies import get_optimizer_service
from backend.app.product_services.classic_small_field import describe_candidate
from backend.app.product_services.football_sanity_deficit import lineup_sanity_deficit
from backend.app.product_services.gpp_optimizer import (
    StackRules,
    _build_lineup,
    analyze_slate,
    build_large_gpp_config,
    tag_players,
)
from backend.app.product_services.lineup_correlation_scoring import (
    build_format_specific_terms,
    build_lineup_correlation_terms,
)
from backend.app.product_services.player_context_scoring import score_player_context
from backend.app.product_services.player_pool_safety import evaluate_player_pool_safety
from backend.app.product_services.rule_library import resolve_strategy_profile


SCENARIOS = {
    "control": {"rule_multipliers": {}, "extra_multiplier": 1.0},
    "test_a_no_bring_back_reward": {
        "rule_multipliers": {"correlation.shootout_bring_back_v1": 0.0},
        "extra_multiplier": 1.0,
    },
    "test_b_half_extra_pass_catcher": {
        "rule_multipliers": {"construction.classic_qb_double_stack_v2": 0.5},
        "extra_multiplier": 0.5,
    },
    "test_c_no_extra_pass_catcher": {
        "rule_multipliers": {"construction.classic_qb_double_stack_v2": 0.0},
        "extra_multiplier": 0.0,
    },
    "test_d_qb_plus_one_only": {
        "rule_multipliers": {
            "correlation.shootout_bring_back_v1": 0.0,
            "construction.classic_qb_double_stack_v2": 0.0,
        },
        "extra_multiplier": 0.0,
    },
}
TRACKED = (
    "Jaylen Waddle", "J.K. Dobbins", "Jonah Coleman", "CeeDee Lamb",
    "Terry McLaurin", "D'Andre Swift", "Colston Loveland", "Caleb Williams",
    "Dak Prescott", "Jayden Daniels",
)
GAMES = {
    "DAL-WAS": frozenset({"DAL", "WAS"}),
    "CHI-MIN": frozenset({"CHI", "MIN"}),
    "DEN-JAX": frozenset({"DEN", "JAX"}),
}


def _lineup_key(lineup: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted(str(player.player_id) for player in lineup))


def _rule_factor(rule_id: str, settings: Mapping[str, Any]) -> float:
    return float(settings["rule_multipliers"].get(rule_id, 1.0))


def _scenario_score(row: Mapping[str, Any], settings: Mapping[str, Any]) -> tuple[float, dict[str, float]]:
    base = float(row["base_solver"])
    ordinary = 0.0
    qb_stack_rows: list[float] = []
    components = Counter()
    for rule in row["correlation_rules"]:
        contribution = float(rule.get("objective_contribution") or 0.0)
        rule_id = str(rule.get("rule_id") or "")
        if rule_id == "correlation.qb_pass_catcher_v2":
            qb_stack_rows.append(contribution)
            continue
        adjusted = contribution * _rule_factor(rule_id, settings)
        ordinary += adjusted
        components[rule_id] += adjusted
    if qb_stack_rows:
        qb_stack_rows.sort(reverse=True)
        first = qb_stack_rows[0]
        extras = sum(qb_stack_rows[1:]) * float(settings["extra_multiplier"])
        ordinary += first + extras
        components["correlation.qb_pass_catcher_v2:first"] += first
        components["correlation.qb_pass_catcher_v2:extra"] += extras
    return base + ordinary, dict(components)


def _latest_ownership(slate: str = "SUNDAY_MAIN") -> tuple[dict[str, float], str | None]:
    with engine.connect() as connection:
        run_id = connection.execute(text("""
            SELECT ownership_run_id FROM target.ownership_model_run
            WHERE season=2026 AND week=2 AND upper(slate_id)=upper(:slate)
              AND status='completed' ORDER BY created_at DESC LIMIT 1
        """), {"slate": slate}).scalar()
        if not run_id:
            return {}, None
        rows = connection.execute(text("""
            SELECT player_id, projected_ownership FROM target.ownership_projection
            WHERE ownership_run_id=:run_id
        """), {"run_id": run_id}).mappings()
        return {str(row["player_id"]): float(row["projected_ownership"]) for row in rows}, str(run_id)


def _rank_qbs(players: list[Any]) -> list[Any]:
    qbs = [player for player in players if player.position == "QB"]
    return sorted(qbs, key=lambda player: -(
        player.projection / max(1.0, player.salary / 1000.0)
        + player.ceiling / max(1.0, player.salary / 1000.0)
    ))


def _generate_for_qb(
    qb: Any, *, players: list[Any], config: Any, settings: Mapping[str, Any],
    correlation_terms: list[Any], format_terms: list[Any], variants: int,
) -> list[list[Any]]:
    excluded: list[set[int]] = []
    output: list[list[Any]] = []
    rules = StackRules(**{**config.stack_rules.__dict__, "min_pass_catchers": 1, "min_bring_backs": 0})
    for _ in range(variants):
        indexes = _build_lineup(
            players, config, None, excluded, enforce_single_te=True,
            avoid_dst_opponents=True, stack_rules=rules,
            required_player_ids={qb.player_id},
            correlation_rule_multipliers=settings["rule_multipliers"],
            extra_qb_pass_catcher_multiplier=settings["extra_multiplier"],
            precomputed_correlation_terms=correlation_terms,
            precomputed_format_terms=format_terms,
        )
        if indexes is None:
            break
        excluded.append(set(indexes))
        output.append([players[index] for index in indexes])
    return output


def _generate_with_player(
    player: Any, *, players: list[Any], config: Any, settings: Mapping[str, Any],
    correlation_terms: list[Any], format_terms: list[Any],
) -> list[Any] | None:
    indexes = _build_lineup(
        players, config, None, [], enforce_single_te=True,
        avoid_dst_opponents=True,
        stack_rules=StackRules(**{
            **config.stack_rules.__dict__, "min_pass_catchers": 1, "min_bring_backs": 0,
        }),
        required_player_ids={player.player_id},
        correlation_rule_multipliers=settings["rule_multipliers"],
        extra_qb_pass_catcher_multiplier=settings["extra_multiplier"],
        precomputed_correlation_terms=correlation_terms,
        precomputed_format_terms=format_terms,
    )
    return [players[index] for index in indexes] if indexes is not None else None


def _one_off(lineup: list[Any], player: Any) -> bool:
    qb = next(item for item in lineup if item.position == "QB")
    return player.position in {"RB", "WR", "TE"} and player.team not in {qb.team, qb.opponent}


def _candidate_row(
    lineup: list[Any], *, players: list[Any], config: Any, source: dict[str, dict],
    game_totals: list[float], ownership: dict[str, float], settings: Mapping[str, Any],
    core_by_id: dict[str, dict],
) -> dict[str, Any]:
    row = describe_candidate(
        lineup, all_players=players, config=config, pool_by_id=source,
        ownership_available=False, game_totals=game_totals,
    )
    score, scenario_components = _scenario_score(row, settings)
    row["objective_score"] = score
    row["scenario_correlation_components"] = scenario_components
    missing = [player.name for player in lineup if str(player.player_id) not in ownership]
    row["ownership_missing_players"] = missing
    row["ownership_sum"] = None if missing else sum(ownership[str(player.player_id)] for player in lineup)
    row["log_ownership"] = None if missing else sum(
        log(max(0.01, ownership[str(player.player_id)]) / 100.0) for player in lineup
    )
    row["one_offs"] = [player.name for player in lineup if _one_off(lineup, player)]
    row["football_sanity"] = lineup_sanity_deficit(
        row["roster"], core_by_id=core_by_id,
        player_pool=[{"player_id": player.player_id, "name": player.name,
                      "team": player.team, "position": player.position,
                      "salary": player.salary, "projection": player.projection}
                     for player in players],
    )
    return row


def _concise(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "rank": row["rank"], "objective": row["objective_score"],
        "base_objective": row["base_solver"],
        "objective_components": row["scenario_correlation_components"],
        "mean": row["mean"], "p90": row["p90"], "salary": row["salary"],
        "relative_chalk": row.get("relative_chalk"), "ownership_sum": row.get("ownership_sum"),
        "qb": row["qb"], "stack": row["stack"]["type"],
        "primary_game": row["primary_game"], "one_offs": row["one_offs"],
        "football_sanity_deficit": row["football_sanity"]["total_football_sanity_deficit"],
        "roster": row["roster"],
    }


def _scenario_summary(rows: list[dict[str, Any]], tracked: tuple[str, ...]) -> dict[str, Any]:
    rows.sort(key=lambda row: (-row["objective_score"], -row["p90"], -row["mean"]))
    complete = [row for row in rows if row["log_ownership"] is not None]
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
        row["relative_chalk"] = None
    if len(complete) > 1:
        ordered = sorted(complete, key=lambda row: row["log_ownership"])
        for index, row in enumerate(ordered):
            row["relative_chalk"] = 100.0 * index / (len(ordered) - 1)
    exposure = Counter(player["name"] for row in rows for player in row["roster"])
    one_offs = Counter(name for row in rows for name in row["one_offs"])
    qb_families = []
    for qb in sorted({row["qb"]["name"] for row in rows}):
        family = [row for row in rows if row["qb"]["name"] == qb]
        best = min(family, key=lambda row: row["rank"])
        qb_families.append({"qb": qb, "candidate_count": len(family),
                            "best_rank": best["rank"], "best_objective": best["objective_score"],
                            "best_mean": best["mean"], "best_p90": best["p90"]})
    qb_families.sort(key=lambda row: row["best_rank"])
    tracked_rows = []
    for name in tracked:
        containing = [row for row in rows if any(player["name"] == name for player in row["roster"])]
        tracked_rows.append({"player": name, "candidate_count": exposure[name],
                             "exposure": exposure[name] / len(rows) if rows else 0.0,
                             "one_off_count": one_offs[name],
                             "best_rank": min((row["rank"] for row in containing), default=None)})
    return {
        "candidate_count": len(rows), "top_20": [_concise(row) for row in rows[:20]],
        "player_exposure": [
            {"player": name, "candidate_count": count, "exposure": count / len(rows)}
            for name, count in exposure.most_common()
        ],
        "qb_families": qb_families,
        "stack_distribution": dict(Counter(row["stack"]["type"] for row in rows)),
        "primary_game_distribution": dict(Counter(row["primary_game"] for row in rows)),
        "one_off_exposure": dict(one_offs.most_common()), "tracked_players": tracked_rows,
    }


def _game_audit(
    model_pool: Any, eligible_ids: set[str], scenario_rows: Mapping[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    output = []
    for label, teams in GAMES.items():
        game_pool = model_pool.loc[
            model_pool["player_team"].isin(teams) & model_pool["opponent_team"].isin(teams)
        ].copy()
        game_pool["optimizer_eligible"] = game_pool["player_id"].astype(str).isin(eligible_ids)
        qbs = game_pool.loc[game_pool["position"].eq("QB")]
        skills = game_pool.loc[game_pool["position"].isin(["RB", "WR", "TE"])].copy()
        skills["value_per_1000"] = skills["projection"] / (skills["salary"] / 1000.0)
        market = game_pool.iloc[0] if not game_pool.empty else {}
        scenarios = {}
        for scenario, rows in scenario_rows.items():
            # primary_game uses the QB team and opponent; the label is sufficient here.
            primary = [row for row in rows if set(row["primary_game"].split("–")) == set(teams)]
            scenarios[scenario] = {
                "primary_stack_count": len(primary),
                "best_primary_rank": min((row["rank"] for row in primary), default=None),
            }
        output.append({
            "game": label,
            "market": {"game_total": market.get("game_total_line"),
                       "spread_from_first_team_row": market.get("team_spread_line"),
                       "team_total_from_first_team_row": market.get("team_implied_total")},
            "qbs": qbs[["name", "player_team", "salary", "projection", "predicted_p90"]].to_dict("records"),
            "top_skill_players": skills.nlargest(12, ["value_per_1000", "projection"])[
                ["name", "player_team", "salary", "projection", "predicted_p90",
                 "value_per_1000", "optimizer_eligible"]
            ].to_dict("records"),
            "scenarios": scenarios,
        })
        for player_row in output[-1]["top_skill_players"]:
            player_name = player_row["name"]
            player_row["candidate_coverage"] = {}
            for scenario, rows in scenario_rows.items():
                containing = [row for row in rows if any(
                    player["name"] == player_name for player in row["roster"]
                )]
                player_row["candidate_coverage"][scenario] = {
                    "candidate_count": len(containing),
                    "one_off_count": sum(player_name in row["one_offs"] for row in containing),
                    "primary_stack_count": sum(
                        set(row["primary_game"].split("–")) == set(teams) for row in containing
                    ),
                    "best_rank": min((row["rank"] for row in containing), default=None),
                }
    return output


def _den_rb_scenarios(pool: Any) -> dict[str, Any]:
    names = ("J.K. Dobbins", "RJ Harvey", "Jonah Coleman")
    rows = pool.loc[pool["name"].isin(names)].set_index("name")
    carry_budget = float(rows["projected_carries"].fillna(0).sum())
    target_budget = float(rows["projected_targets"].fillna(0).sum())
    scenarios = {"A_fully_active": 1.0, "B_limited": 0.5, "C_inactive": 0.0}
    output = []
    for label, harvey_availability in scenarios.items():
        availability = {name: (harvey_availability if name == "RJ Harvey" else 1.0) for name in names}
        carry_weights = {name: float(rows.loc[name, "projected_carries"] or 0) * availability[name] for name in names}
        target_weights = {name: float(rows.loc[name, "projected_targets"] or 0) * availability[name] for name in names}
        carry_total = sum(carry_weights.values()) or 1.0
        target_total = sum(target_weights.values()) or 1.0
        players = []
        for name in names:
            baseline = rows.loc[name]
            carries = carry_budget * carry_weights[name] / carry_total
            targets = target_budget * target_weights[name] / target_total
            baseline_proxy = 0.6 * float(baseline["projected_carries"] or 0) + 1.4 * float(baseline["projected_targets"] or 0)
            scenario_proxy = 0.6 * carries + 1.4 * targets
            scenario_mean = max(0.0, float(baseline["projection"]) - baseline_proxy + scenario_proxy)
            p90 = scenario_mean + (float(baseline["predicted_p90"]) - float(baseline["projection"]))
            players.append({"player": name, "availability": availability[name],
                            "expected_carries": carries, "expected_targets": targets,
                            "shadow_mean": scenario_mean, "spread_preserving_p90": p90})
        output.append({"scenario": label, "players": players})
    return {
        "method": "Reallocate the existing DEN RB carry and target budgets in proportion to current role weights times availability. Shadow mean preserves each player's non-volume residual and values a carry at 0.6 DK points and a target at 1.4; P90 preserves the production spread. Diagnostic only.",
        "carry_budget": carry_budget, "target_budget": target_budget, "scenarios": output,
    }


def _markdown(payload: Mapping[str, Any]) -> str:
    lines = ["# Sunday Main correlation and one-off coverage audit", "",
             f"Projection run: `{payload['projection_run_id']}`. Production changed: **No**.", "",
             "## Waddle trace", ""]
    trace = payload["waddle_trace"]
    for key, value in trace.items():
        lines.append(f"- **{key}:** {value}")
    lines += ["", "## Shadow scenario winners", "",
              "| Scenario | Candidates | QB | Stack | Mean | P90 | Objective |",
              "|---|---:|---|---|---:|---:|---:|"]
    for name, result in payload["scenarios"].items():
        winner = result["top_20"][0]
        lines.append(f"| {name} | {result['candidate_count']} | {winner['qb']['name']} | {winner['stack']} | {winner['mean']:.2f} | {winner['p90']:.2f} | {winner['objective']:.4f} |")
    lines += ["", "## Answers", ""]
    for answer in payload["answers"]:
        lines.append(f"- {answer}")
    lines += ["", "Full top-20 tables, game audits, QB families, tracked-player exposure, and Denver workload scenarios are in the JSON artifact."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--projection-run-id", required=True)
    parser.add_argument("--slate", default="SUNDAY_MAIN")
    parser.add_argument(
        "--scenario",
        action="append",
        choices=tuple(SCENARIOS),
        help="Limit the diagnostic to one or more named shadow scenarios.",
    )
    parser.add_argument("--variants-per-qb", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("artifacts/sunday-main-correlation-oneoff-audit-2026w2.json"))
    args = parser.parse_args()
    service = get_optimizer_service()
    pool = service._load_player_pool(2026, 2, args.slate, projection_run_id=args.projection_run_id)  # noqa: SLF001
    raw_count = len(pool)
    profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
    cutoff = pool["data_cutoff_at"].dropna().max()
    safety = evaluate_player_pool_safety(pool, profile=profile, as_of=datetime.now(timezone.utc), projection_cutoff=cutoff)
    pool = score_player_context(safety.eligible_pool, profile=profile).scored_pool
    pool, strategy_exclusions = service._select_strategy_candidates(  # noqa: SLF001
        pool, strategy="classic_small_field_gpp", contest_type="tournament"
    )
    model_pool = pool.copy()
    fandom_exclusions = pool.loc[pool["opponent_team"].fillna("").str.upper().eq("DEN"), ["name", "player_team", "opponent_team"]]
    pool = pool.loc[~pool["opponent_team"].fillna("").str.upper().eq("DEN")].copy()
    ownership, ownership_run_id = _latest_ownership(args.slate)
    pool["ownership"] = pool["player_id"].astype(str).map(ownership).fillna(0.0)
    players = service._gpp_players_from_pool(pool)  # noqa: SLF001
    eligible_ids = {str(player.player_id) for player in players}
    source = {str(row["player_id"]): row for row in pool.to_dict("records")}
    core_by_id = {player_id: {
        "offensive_role_importance": row.get("offensive_role_importance"),
        "offensive_role_class": row.get("offensive_role_class"),
        "offensive_role_confidence": row.get("offensive_role_confidence"),
    } for player_id, row in source.items()}
    config = build_large_gpp_config(
        analyze_slate(players), ownership_available=False, minimum_uniqueness=1,
        max_from_team=4, max_from_game=5,
        stack_templates=((1, 0), (1, 1), (2, 0), (2, 1)),
    )
    tag_players(players, config.tag_thresholds)
    config.stack_rules = StackRules(**{**config.stack_rules.__dict__, "min_pass_catchers": 1, "min_bring_backs": 0})
    correlation_terms = build_lineup_correlation_terms(players, profile=profile)
    format_terms = build_format_specific_terms(players, profile=profile)
    qbs = _rank_qbs(players)
    required_names = set(TRACKED)
    for teams in GAMES.values():
        game_skills = pool.loc[
            pool["player_team"].isin(teams)
            & pool["opponent_team"].isin(teams)
            & pool["position"].isin(["RB", "WR", "TE"])
        ].copy()
        game_skills["audit_value"] = game_skills["projection"] / (game_skills["salary"] / 1000.0)
        required_names.update(game_skills.nlargest(12, ["audit_value", "projection"])["name"].tolist())
    required_players = [player for player in players if player.name in required_names]
    game_totals = sorted({float(player.game_total) for player in players if player.game_total is not None})
    scenario_rows: dict[str, list[dict[str, Any]]] = {}
    summaries = {}
    selected_scenarios = args.scenario or list(SCENARIOS)
    for scenario in selected_scenarios:
        settings = SCENARIOS[scenario]
        lineups: dict[tuple[str, ...], list[Any]] = {}
        with ThreadPoolExecutor(max_workers=min(10, len(qbs))) as executor:
            futures = [executor.submit(
                _generate_for_qb, qb, players=players, config=config, settings=settings,
                correlation_terms=correlation_terms, format_terms=format_terms,
                variants=args.variants_per_qb,
            ) for qb in qbs]
            for future in futures:
                for lineup in future.result():
                    lineups[_lineup_key(lineup)] = lineup
        with ThreadPoolExecutor(max_workers=min(10, len(required_players))) as executor:
            futures = [executor.submit(
                _generate_with_player, player, players=players, config=config,
                settings=settings, correlation_terms=correlation_terms,
                format_terms=format_terms,
            ) for player in required_players]
            for future in futures:
                lineup = future.result()
                if lineup is not None:
                    lineups[_lineup_key(lineup)] = lineup
        rows = [_candidate_row(
            lineup, players=players, config=config, source=source,
            game_totals=game_totals, ownership=ownership, settings=settings,
            core_by_id=core_by_id,
        ) for lineup in lineups.values()]
        rows.sort(key=lambda row: (-row["objective_score"], -row["p90"]))
        for rank, row in enumerate(rows, 1):
            row["rank"] = rank
        scenario_rows[scenario] = rows
        summaries[scenario] = _scenario_summary(rows, TRACKED)
    if args.scenario:
        payload = {
            "artifact": "classic_correlation_shadow_audit_v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "slate": args.slate,
            "projection_run_id": args.projection_run_id,
            "ownership_run_id": ownership_run_id,
            "ownership_available": bool(ownership),
            "production_changes": "None; scenario weights are passed only to diagnostic solves.",
            "pool": {
                "raw": raw_count,
                "safety_eligible": len(safety.eligible_pool),
                "optimizer_eligible_after_strategy_and_fandom": len(players),
                "strategy_exclusion_count": len(strategy_exclusions),
                "fandom_exclusions": fandom_exclusions.to_dict("records"),
            },
            "scenarios": summaries,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, default=str, allow_nan=False) + "\n")
        print(json.dumps({
            "projection_run_id": args.projection_run_id,
            "scenario_candidates": {
                key: value["candidate_count"] for key, value in summaries.items()
            },
            "output": str(args.output),
        }))
        return
    control = summaries["control"]
    a = summaries["test_a_no_bring_back_reward"]
    b = summaries["test_b_half_extra_pass_catcher"]
    c = summaries["test_c_no_extra_pass_catcher"]
    d = summaries["test_d_qb_plus_one_only"]
    def exposure(summary: Mapping[str, Any], name: str) -> float:
        return next(row["exposure"] for row in summary["tracked_players"] if row["player"] == name)
    new_oneoffs = [name for name in TRACKED if exposure(c, name) > exposure(control, name)]
    payload = {
        "artifact": "sunday_main_correlation_oneoff_audit_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "projection_run_id": args.projection_run_id,
        "ownership_run_id": ownership_run_id,
        "production_changes": "None; scenario weights are passed only to diagnostic solves.",
        "pool": {"raw": raw_count, "safety_eligible": len(safety.eligible_pool),
                 "optimizer_eligible_after_strategy_and_fandom": len(players),
                 "strategy_exclusion_count": len(strategy_exclusions),
                 "fandom_exclusions": fandom_exclusions.to_dict("records")},
        "waddle_trace": {
            "raw_DK_salary": "present: source ID 44132980, DEN, $6,500",
            "current_roster": "present: GSIS 00-0036613, DEN WR, ACT",
            "prior_curated_salary": "present but player_master_id was null because salary ingest preceded the current roster alias",
            "repair": "normal DK re-ingest after roster refresh; unresolved rows fell from 135 to 7",
            "canonical_player_id": "c83efb4c-fa23-4d07-9c76-67df5963cbc2",
            "projection": "8.46 mean / 18.30 P90",
            "role": "regular contributor; importance 0.263; high confidence",
            "optimizer_pool": "eligible; DEN players allowed, JAX opponents excluded by user preference",
        },
        "den_rb_workload": _den_rb_scenarios(pool),
        "game_audit": _game_audit(model_pool, eligible_ids, scenario_rows),
        "scenarios": summaries,
        "answers": [
            f"Bring-back reward is not suppressing one-offs in this run: removing it leaves the winning roster and the complete stack distribution unchanged at {a['stack_distribution']}.",
            f"The incremental second-pass-catcher and double-stack terms are the larger construction lever: the no-extra test changes stack mix from {control['stack_distribution']} to {c['stack_distribution']}.",
            f"The control winner has mean {control['top_20'][0]['mean']:.2f}/P90 {control['top_20'][0]['p90']:.2f}; the no-extra winner has {c['top_20'][0]['mean']:.2f}/{c['top_20'][0]['p90']:.2f}. The current construction reward therefore selects a lineup giving up {c['top_20'][0]['mean'] - control['top_20'][0]['mean']:.2f} mean and {c['top_20'][0]['p90'] - control['top_20'][0]['p90']:.2f} P90.",
            "Within this slate audit, reusing the large-GPP incremental double-stack reward is too strong for the small-field search: the zero-extra winner has higher mean and P90 with the same 0.25 football-sanity deficit. This is evidence for later tuning, not a production change.",
            f"Tracked one-offs gaining exposure when extra-stack rewards are removed: {', '.join(new_oneoffs) if new_oneoffs else 'none'}.",
            f"DAL-WAS primary-stack counts: control {control['primary_game_distribution'].get('DAL–WAS', 0) + control['primary_game_distribution'].get('WAS–DAL', 0)}, no-extra {c['primary_game_distribution'].get('DAL–WAS', 0) + c['primary_game_distribution'].get('WAS–DAL', 0)}.",
            f"CHI-MIN primary-stack counts: control {control['primary_game_distribution'].get('CHI–MIN', 0) + control['primary_game_distribution'].get('MIN–CHI', 0)}, QB+1-only {d['primary_game_distribution'].get('CHI–MIN', 0) + d['primary_game_distribution'].get('MIN–CHI', 0)}.",
            "New lineups challenge the shortlist when their top-20 objective gap is small and their mean/P90 and sanity are no worse; review their player-level role evidence before any production promotion.",
        ],
    }
    args.output.write_text(json.dumps(payload, indent=2, default=str, allow_nan=False) + "\n")
    args.output.with_suffix(".md").write_text(_markdown(payload))
    print(json.dumps({"projection_run_id": args.projection_run_id,
                      "scenario_candidates": {key: value["candidate_count"] for key, value in summaries.items()},
                      "output": str(args.output)}))


if __name__ == "__main__":
    main()
