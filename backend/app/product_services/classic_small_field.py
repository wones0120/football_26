"""Diagnostic-first Classic small-field selection over legal GPP candidates."""

from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC
from math import ceil, exp, floor, isfinite, log
from multiprocessing import get_context
import os
from time import perf_counter
from typing import Any, Sequence

import pulp

from .gpp_optimizer import GPPOptimizerResult, ObjectiveWeights, Player, StackRules, _build_lineup, _portfolio_stats, tag_players
from .cbc_solver import make_cbc_solver
from .lineup_correlation_scoring import (build_format_specific_terms,
    build_lineup_correlation_terms, score_lineup_correlations)
from .rule_library import resolve_strategy_profile


_DISCOVERY_CONTEXT: dict[str, Any] = {}
_REFILL_CONTEXT: dict[str, Any] = {}
_SEED_CONTEXT: dict[str, Any] = {}


def _initialize_seed_worker(players: list[Player], config: Any,
                            enforce_single_te: bool, avoid_dst_opponents: bool,
                            solver_backend: str, candidate_caps: dict[str, float],
                            elevated_ids: set[str], max_elevated: int) -> None:
    _SEED_CONTEXT.clear()
    _SEED_CONTEXT.update(players=players, config=config,
                         enforce_single_te=enforce_single_te,
                         avoid_dst_opponents=avoid_dst_opponents,
                         solver_backend=solver_backend, candidate_caps=candidate_caps,
                         elevated_ids=elevated_ids, max_elevated=max_elevated)


def _solve_seed_shard(request: tuple[int, int, tuple[str, ...], int],
                      context: dict[str, Any] | None = None) -> dict:
    context = context or _SEED_CONTEXT
    shard_index, shard_count, qb_ids, worker_count = request
    players = [player for player in context["players"]
               if player.position != "QB" or player.player_id in qb_ids]
    config = context["config"]
    profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
    correlation_terms = build_lineup_correlation_terms(players, profile=profile)
    format_terms = build_format_specific_terms(players, profile=profile)
    caps = context["candidate_caps"]
    counts: Counter = Counter()
    excluded: list[set[int]] = []
    lineups: list[list[str]] = []
    infeasible = 0
    templates = config.stack_templates or ((config.stack_rules.min_pass_catchers,
                                            config.stack_rules.min_bring_backs),)
    for offset in range(shard_count):
        remaining = {player.player_id: floor(shard_count * caps.get(player.player_id, 1.0))
                     - counts[player.player_id] for player in players}
        catchers, backs = templates[(offset * worker_count + shard_index) % len(templates)]
        rules = replace(config.stack_rules, min_pass_catchers=int(catchers),
                        min_bring_backs=int(backs))
        indexes = _build_lineup(
            players, config, remaining, excluded,
            enforce_single_te=context["enforce_single_te"],
            avoid_dst_opponents=context["avoid_dst_opponents"],
            stack_rules=rules,
            maximum_player_groups=[(context["elevated_ids"], context["max_elevated"])],
            precomputed_correlation_terms=correlation_terms,
            precomputed_format_terms=format_terms,
            solver_backend=context["solver_backend"],
        )
        if indexes is None:
            infeasible += 1
            break
        excluded.append(set(indexes))
        lineup = [players[index].player_id for index in indexes]
        lineups.append(lineup)
        counts.update(lineup)
    return {"shard": shard_index, "lineups": lineups,
            "infeasible_solver_attempts": infeasible}


def generate_parallel_seeds(result: GPPOptimizerResult, players: Sequence[Player], *,
                            count: int, max_workers: int, starting_qb_ids: set[str],
                            candidate_caps: dict[str, float], elevated_ids: set[str],
                            max_elevated: int, enforce_single_te: bool,
                            avoid_dst_opponents: bool, solver_backend: str) -> GPPOptimizerResult:
    """Generate deterministic, cap-safe Classic seed shards across QB paths."""
    if not 2 <= max_workers <= 4:
        raise ValueError("Parallel Classic seeds require two to four workers")
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise ValueError("Parallel Classic seeds require PYTHONHASHSEED=0")
    pool = list(players)
    qbs = [player.player_id for player in pool if player.position == "QB"
           and player.player_id in starting_qb_ids]
    if len(qbs) < max_workers:
        raise ValueError("Parallel Classic seeds require at least one starting QB per worker")
    groups = [tuple(qbs[index::max_workers]) for index in range(max_workers)]
    sizes = [count // max_workers + (index < count % max_workers)
             for index in range(max_workers)]
    requests = [(index, sizes[index], groups[index], max_workers)
                for index in range(max_workers)]
    with ProcessPoolExecutor(
        max_workers=max_workers, mp_context=get_context("spawn"),
        initializer=_initialize_seed_worker,
        initargs=(pool, result.config, enforce_single_te, avoid_dst_opponents,
                  solver_backend, candidate_caps, elevated_ids, max_elevated),
    ) as executor:
        shards = list(executor.map(_solve_seed_shard, requests))
    by_id = {player.player_id: player for player in pool}
    combined = [lineup for offset in range(max(sizes)) for shard in shards
                for lineup in shard["lineups"][offset:offset + 1]]
    result.lineups = [[by_id[player_id] for player_id in lineup] for lineup in combined]
    index_by_id = {player.player_id: index for index, player in enumerate(pool)}
    result.portfolio = _portfolio_stats(pool, [
        [index_by_id[player_id] for player_id in lineup] for lineup in combined
    ])
    result.generation_funnel = {
        "requested": count, "solved": len(combined), "legal": len(combined),
        "duplicate": 0, "accepted": len(combined),
        "remaining_deficit": count - len(combined),
        "infeasible_solver_attempts": sum(row["infeasible_solver_attempts"] for row in shards),
        "status": "complete" if len(combined) == count else "CANDIDATE_POOL_UNDERFILLED",
        "method": "parallel_qb_shards", "workers": max_workers,
        "shards": [{"index": row["shard"], "requested": sizes[row["shard"]],
                    "accepted": len(row["lineups"])} for row in shards],
    }
    result.status = "completed" if len(combined) == count else "failed"
    result.message = f"Generated {len(combined)}/{count} Classic candidates in {max_workers} QB shards"
    return result


def _initialize_discovery_worker(
    pool: list[Player], config: Any, correlation_terms: Sequence[Any],
    format_terms: Sequence[Any], enforce_single_te: bool,
    avoid_dst_opponents: bool, locked_player_ids: set[str], solver_backend: str,
) -> None:
    _DISCOVERY_CONTEXT.clear()
    _DISCOVERY_CONTEXT.update(
        pool=pool, config=config, correlation_terms=correlation_terms,
        format_terms=format_terms, enforce_single_te=enforce_single_te,
        avoid_dst_opponents=avoid_dst_opponents,
        locked_player_ids=locked_player_ids, solver_backend=solver_backend,
    )


def _solve_discovery_request(request: tuple) -> list[int] | None:
    return _solve_discovery_request_with_context(request, _DISCOVERY_CONTEXT)


def _solve_discovery_request_with_context(request: tuple, context: dict[str, Any]) -> list[int] | None:
    _, qb_id, family, quality = request
    pool = context["pool"]
    config = context["config"]
    if quality:
        weights = ObjectiveWeights(projection=float(quality == "mean"),
                                   ceiling=float(quality == "p90"),
                                   leverage=0.0, correlation=0.0)
        solve_config = replace(config, objective_weights=weights,
                               correlation_bonus=0.0)
        solve_players = [replace(player, optimizer_context_adjustment=0.0)
                         for player in pool]
    else:
        solve_config, solve_players = config, pool
    rules = (replace(config.stack_rules, min_pass_catchers=family[0],
                     min_bring_backs=family[1]) if family else None)
    required = set(context["locked_player_ids"])
    if qb_id:
        required.add(qb_id)
    return _build_lineup(
        solve_players, solve_config, None, [],
        enforce_single_te=context["enforce_single_te"],
        avoid_dst_opponents=context["avoid_dst_opponents"],
        stack_rules=rules, required_player_ids=required,
        exact_pass_catchers=family[0] if family else None,
        exact_bring_backs=family[1] if family else None,
        precomputed_correlation_terms=context["correlation_terms"],
        precomputed_format_terms=context["format_terms"],
        solver_backend=context["solver_backend"],
    )


def _initialize_refill_worker(players: list[Player], config: Any,
                              correlation_terms: Sequence[Any], format_terms: Sequence[Any],
                              enforce_single_te: bool, avoid_dst_opponents: bool,
                              solver_backend: str) -> None:
    _REFILL_CONTEXT.clear()
    _REFILL_CONTEXT.update(players=players, config=config,
                           correlation_terms=correlation_terms, format_terms=format_terms,
                           enforce_single_te=enforce_single_te,
                           avoid_dst_opponents=avoid_dst_opponents,
                           solver_backend=solver_backend)


def _solve_refill_request(request: tuple, context: dict[str, Any] | None = None) -> list[int] | None:
    context = context or _REFILL_CONTEXT
    (template, remaining, excluded_rosters, minimum_mean, minimum_p90,
     elevated, max_elevated) = request
    config = context["config"]
    catchers, backs = template
    stack_rules = replace(config.stack_rules, min_pass_catchers=int(catchers),
                          min_bring_backs=int(backs))
    return _build_lineup(
        context["players"], config, remaining, excluded_rosters,
        enforce_single_te=context["enforce_single_te"],
        avoid_dst_opponents=context["avoid_dst_opponents"],
        stack_rules=stack_rules, minimum_mean=minimum_mean,
        minimum_p90=minimum_p90,
        maximum_player_groups=[(elevated, max_elevated)],
        precomputed_correlation_terms=context["correlation_terms"],
        precomputed_format_terms=context["format_terms"],
        solver_backend=context["solver_backend"],
    )


def contest_reporting_snapshot(urls: Sequence[str], manual: Any = None) -> dict | None:
    """Collect optional contest context without invalidating a lineup solve."""
    if not urls:
        return None
    try:
        if len(urls) != 1:
            raise ValueError("Classic small-field reporting accepts one DraftKings contest URL")
        from .showdown_contests import fetch_contests

        contest = fetch_contests(urls, manual=manual)[0]
        return {key: contest.get(key) for key in (
            "contest_id", "url", "name", "slate", "entry_fee", "capacity",
            "current_entries", "maximum_entries", "paid_places", "prize_pool",
            "payout_ladder", "lock_time", "economics", "unavailable_fields",
            "error", "observed_at", "source",
        )}
    except ValueError as exc:
        return {"error": str(exc), "source": "unavailable"}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def expand_candidate_discovery(
    result: GPPOptimizerResult, players: Sequence[Player], *,
    enforce_single_te: bool = False, avoid_dst_opponents: bool = False,
    locked_player_ids: set[str] | None = None,
    starting_qb_ids: set[str] | None = None,
    max_workers: int = 1, solver_backend: str = "bundled",
) -> tuple[list[list[Player]], dict]:
    """Add exact legal quality and QB-family solves to the sequential pool.

    Exposure limits apply at portfolio selection, never to these discovery
    solves. Canonical IDs determine identity and deduplication.
    """
    pool = list(players)
    by_key = {tuple(sorted(player.player_id for player in lineup)): list(lineup)
              for lineup in result.lineups}
    sequential_keys = set(by_key)
    sources: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for key in sequential_keys:
        sources[key].append("sequential")
    profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
    correlation_terms = build_lineup_correlation_terms(pool, profile=profile)
    format_terms = build_format_specific_terms(pool, profile=profile)
    requests = [("global_highest_mean", None, None, "mean"),
                ("global_highest_p90", None, None, "p90"),
                ("global_highest_selector", None, None, None)]
    families = ((1, 0), (1, 1), (2, 0), (2, 1))
    for qb in (player for player in pool if player.position == "QB"
               and (starting_qb_ids is None or player.player_id in starting_qb_ids)):
        requests.append((f"qb_family:{qb.player_id}", qb.player_id, None, None))
        for catchers, bring_back in families:
            requests.append((f"qb_construction:{qb.player_id}:{catchers}:{bring_back}",
                             qb.player_id, (catchers, bring_back), None))
    if not 1 <= max_workers <= 4:
        raise ValueError("classic_candidate_workers must be between 1 and 4")
    if max_workers > 1 and os.environ.get("PYTHONHASHSEED") != "0":
        raise ValueError("Parallel discovery requires PYTHONHASHSEED=0 at process start")
    initializer_args = (pool, result.config, correlation_terms, format_terms,
                        enforce_single_te, avoid_dst_opponents,
                        set(locked_player_ids or ()), solver_backend)
    local_context = dict(zip((
        "pool", "config", "correlation_terms", "format_terms",
        "enforce_single_te", "avoid_dst_opponents", "locked_player_ids",
        "solver_backend",
    ), initializer_args))
    if max_workers == 1:
        solved = [_solve_discovery_request_with_context(request, local_context)
                  for request in requests]
    else:
        globals_solved = [_solve_discovery_request_with_context(request, local_context)
                          for request in requests[:3]]
        with ProcessPoolExecutor(max_workers=max_workers,
                                 mp_context=get_context("spawn"),
                                 initializer=_initialize_discovery_worker,
                                 initargs=initializer_args) as executor:
            # map retains request order, so canonical deduplication matches serial.
            qb_solved = list(executor.map(_solve_discovery_request, requests[3:]))
        solved = globals_solved + qb_solved
    injections = []
    for (label, _, _, _), indexes in zip(requests, solved):
        if indexes is None:
            injections.append({"source": label, "status": "infeasible"})
            continue
        lineup = [pool[index] for index in indexes]
        key = tuple(sorted(player.player_id for player in lineup))
        by_key.setdefault(key, lineup)
        sources[key].append(label)
        injections.append({"source": label, "status": "legal",
                           "player_ids": list(key),
                           "absent_from_sequential": key not in sequential_keys})
    return list(by_key.values()), {
        "sequential_count": len(sequential_keys), "unique_count": len(by_key),
        "solver_backend": solver_backend, "max_workers": max_workers,
        "injections": injections,
        "global_raw_quality_absent_from_sequential": [
            row["source"] for row in injections
            if row["source"] in {"global_highest_mean", "global_highest_p90"}
            and row.get("absent_from_sequential")
        ],
        "sources_by_lineup": {"|".join(key): value for key, value in sources.items()},
    }


def _contribution_group(rule: dict) -> str:
    code = str(rule.get("reason_code") or rule.get("rule_id") or "").lower()
    if float(rule.get("objective_contribution") or 0) < 0:
        return "penalties"
    if "bring_back" in code or "bringback" in code:
        return "bring_back"
    if "qb_" in code and ("stack" in code or "pass_catcher" in code or "receiving_back" in code):
        return "qb_stack"
    if "game" in code or "shootout" in code:
        return "game_environment"
    return "correlation"


def _opportunity(row: dict) -> dict:
    fields = (
        "roster_status", "player_status", "pregame_availability_probability",
        "pregame_start_probability", "depth_chart_position", "pregame_role_label",
        "pregame_expected_snaps", "pregame_expected_routes", "pregame_expected_carries",
        "pregame_expected_targets", "snap_share_mean_3", "carries_mean_3",
        "targets_mean_3", "target_share_mean_3", "team_targets_mean_3",
        "receptions_mean_3", "receiving_yards_mean_3",
        "pregame_carry_share", "pregame_target_share",
        "pregame_red_zone_share", "pregame_goal_line_share",
        "pregame_injury_created_opportunity",
    )
    values = {}
    for field in fields:
        value = row.get(field)
        if value is None or value is not None and str(value).lower() in {"nan", "nat", "<na>"}:
            values[field] = None
        elif isinstance(value, (str, int, float, bool)):
            values[field] = value
        else:
            values[field] = str(value)
    diagnostic = row.get("opportunity_diagnostic") or {}
    values["explicit_role_signal"] = diagnostic.get("explicit_role_signal")
    values["fallback_threshold_met"] = diagnostic.get("low_salary_fallback_threshold_met")
    values["retention_reason"] = diagnostic.get("retention_reason", "not evaluated")
    current = diagnostic.get("explicit_role_signal") is True
    inferred = any(
        (_number(row.get(field)) or 0) > 0
        for field in ("targets_mean_3", "carries_mean_3", "snap_share_mean_3")
    )
    values["evidence_class"] = (
        "clearly_low_opportunity" if diagnostic.get("excluded_by_gate") else
        "verified_opportunity" if current else
        "inferred_opportunity" if inferred else
        "insufficient_role_data"
    )
    return values


def _football_sanity(
    candidate: dict, *, players: Sequence[Player], source: dict[str, dict],
    candidate_counts: Counter, selected_counts: Counter, candidate_total: int,
    selected_total: int, candidates: Sequence[dict] = (),
) -> dict:
    """Explain football evidence after selection without changing feasibility or score."""
    roster_ids = set(candidate["player_ids"])
    qb = candidate["qb"]
    driving = [
        {"player_id": p.player_id, "name": p.name, "team": p.team,
         "position": p.position, "importance": _number(source.get(str(p.player_id), {}).get("offensive_role_importance")),
         "role_class": source.get(str(p.player_id), {}).get("offensive_role_class"),
         "role_confidence": source.get(str(p.player_id), {}).get("offensive_role_confidence")}
        for p in players if p.player_id in roster_ids and p.position in {"RB", "WR", "TE"}
    ]
    driving.sort(key=lambda row: (row["importance"] is None, -(row["importance"] or 0), row["name"]))
    cheap = []
    for p in players:
        if p.player_id not in roster_ids or p.position not in {"RB", "WR", "TE"} or p.salary > 4500:
            continue
        opportunity = _opportunity(source.get(str(p.player_id), {}))
        cheap.append({"player_id": p.player_id, "name": p.name, "salary": p.salary,
                      "evidence_class": opportunity["evidence_class"],
                      "retention_reason": opportunity["retention_reason"],
                      "role_signals": {key: opportunity[key] for key in (
                          "pregame_expected_snaps", "pregame_expected_routes", "pregame_expected_carries",
                          "pregame_expected_targets", "snap_share_mean_3", "carries_mean_3",
                          "targets_mean_3", "pregame_injury_created_opportunity")}})
    by_team: dict[str, list[Player]] = defaultdict(list)
    for p in players:
        if p.position in {"RB", "WR", "TE"}:
            by_team[p.team].append(p)
    omitted = []
    disagreements = []
    represented_offenses = {row["team"] for row in driving} | {qb["team"]}
    for team, members in by_team.items():
        if team not in represented_offenses:
            continue
        role_rank = {p.player_id: index for index, p in enumerate(sorted(
            members, key=lambda p: -(_number(source.get(str(p.player_id), {}).get("offensive_role_importance")) or -1)
        ), 1)}
        mean_rank = {p.player_id: index for index, p in enumerate(sorted(members, key=lambda p: -p.projection), 1)}
        p90_rank = {p.player_id: index for index, p in enumerate(sorted(members, key=lambda p: -p.ceiling), 1)}
        for p in members:
            evidence = source.get(str(p.player_id), {})
            importance = _number(evidence.get("offensive_role_importance"))
            confidence = evidence.get("offensive_role_confidence")
            if importance is None or confidence not in {"high", "medium"}:
                continue
            measured_central = evidence.get("offensive_role_class") in {"offensive centerpiece", "primary option"}
            if not measured_central:
                continue
            rank_gap = min(mean_rank[p.player_id], p90_rank[p.player_id]) - role_rank[p.player_id]
            if rank_gap >= 3:
                disagreements.append({"player_id": p.player_id, "name": p.name, "team": team,
                    "importance": importance, "role_rank": role_rank[p.player_id],
                    "mean_rank": mean_rank[p.player_id], "p90_rank": p90_rank[p.player_id],
                    "status": "measured role exceeds both team projection ranks; review inputs"})
            if p.player_id in roster_ids:
                continue
            count = candidate_counts[str(p.player_id)]
            alternatives = [row for row in candidates if str(p.player_id) in row["player_ids"]]
            best_alternative = max(alternatives, key=lambda row: row["objective_score"], default=None)
            objective_gap = (candidate["objective_score"] - best_alternative["objective_score"]
                             if best_alternative is not None else None)
            same_position = [member for member in players if member.position == p.position]
            value = p.projection / max(1.0, p.salary / 1000)
            value_rank = 1 + sum(
                member.projection / max(1.0, member.salary / 1000) > value
                for member in same_position
            )
            explanation = (
                f"Best generated candidate containing this player scored {objective_gap:.3f} "
                "below this lineup; this is a whole-lineup comparison, not a causal swap"
                if objective_gap is not None else
                "No generated candidate contained this player; a legal counterfactual solve is needed"
            )
            omitted.append({"player_id": p.player_id, "name": p.name, "team": team,
                "importance": importance, "role_class": evidence.get("offensive_role_class"),
                "salary": p.salary, "mean": p.projection, "p90": p.ceiling,
                "ownership": p.ownership, "candidate_count": count,
                "candidate_total": candidate_total, "selected_count": selected_counts[str(p.player_id)],
                "selected_total": selected_total, "explanation": explanation,
                "best_candidate_with_player_rank": best_alternative.get("rank") if best_alternative else None,
                "whole_lineup_objective_gap": objective_gap,
                "projection_reason": f"Mean {p.projection:.2f}; P90 {p.ceiling:.2f}; team mean rank {mean_rank[p.player_id]}, P90 rank {p90_rank[p.player_id]}",
                "salary_value_reason": f"Salary ${p.salary:,}; mean per $1,000 {value:.2f}; position value rank {value_rank}/{len(same_position)}",
                "stack_correlation_reason": (
                    f"Best containing candidate stack {best_alternative['stack']['type']} versus selected {candidate['stack']['type']}"
                    if best_alternative else "No containing candidate for construction comparison"
                ),
                "ownership_reason": (
                    f"Ownership input {p.ownership:.1f}%; causal effect not isolated" if candidate.get("ownership_sum") is not None and p.ownership is not None else
                    "Ownership unavailable; no ownership cause assigned"
                )})
    stack = candidate["stack"]
    script = (f"{qb['team']} passing through {stack['partner_count']} QB stack partner(s)"
              f" with {stack['bring_back_count']} opposing skill-player bring-back(s)"
              f" in {candidate['game_environment']['label']} game conditions")
    missing_role = [
        {"player_id": p.player_id, "name": p.name, "team": p.team,
         "missing": [field for field in ("offensive_role_importance", "offensive_role_confidence")
                     if (_number(source.get(str(p.player_id), {}).get(field)) is None
                         if field == "offensive_role_importance"
                         else source.get(str(p.player_id), {}).get(field) in {None, "unavailable"})]}
        for p in players if p.player_id in roster_ids and p.position in {"RB", "WR", "TE"}
        and _number(source.get(str(p.player_id), {}).get("offensive_role_importance")) is None
    ]
    return {"script": script, "driving_players": driving[:8], "cheap_players": cheap,
            "omitted_central_players": omitted, "role_projection_disagreements": disagreements,
            "missing_role_evidence": missing_role,
            "status": "partial" if missing_role else "available",
            "flags": [*(["cheap_role_evidence_missing"] if any(
                row["evidence_class"] == "insufficient_role_data" for row in cheap) else []),
                *(["role_evidence_missing"] if missing_role else []),
                *(["role_projection_disagreement"] if disagreements else [])],
            "diagnostic_only": True}


def _team_reconciliation(players: Sequence[Player], source: dict[str, dict]) -> list[dict]:
    """Show measured and allocated usage separately; never invent team attempt forecasts."""
    by_team: dict[str, list[Player]] = defaultdict(list)
    for player in players:
        if player.position in {"RB", "WR", "TE"}:
            by_team[player.team].append(player)
    teams = []
    for team, members in sorted(by_team.items()):
        def distribution(field: str) -> list[dict]:
            return sorted(({"player_id": p.player_id, "name": p.name,
                            "value": _number(source.get(str(p.player_id), {}).get(field))}
                           for p in members if _number(source.get(str(p.player_id), {}).get(field)) is not None),
                          key=lambda row: -row["value"])
        target = distribution("projected_targets")
        carries = distribution("projected_carries")
        red_zone = distribution("pregame_red_zone_share")
        roles = sorted(({"player_id": p.player_id, "name": p.name,
                         "importance": _number(source.get(str(p.player_id), {}).get("offensive_role_importance")),
                         "role_class": source.get(str(p.player_id), {}).get("offensive_role_class"),
                         "confidence": source.get(str(p.player_id), {}).get("offensive_role_confidence")}
                        for p in members),
                       key=lambda row: (row["importance"] is None, -(row["importance"] or 0)))
        missing = [p.name for p in members
                   if _number(source.get(str(p.player_id), {}).get("offensive_role_importance")) is None]
        evidence = [source.get(str(p.player_id), {}) for p in members]
        team_targets = next((_number(row.get("team_targets_mean_3")) for row in evidence
                             if _number(row.get("team_targets_mean_3")) is not None), None)
        team_carries = next((_number(row.get("team_carries_mean_3")) for row in evidence
                             if _number(row.get("team_carries_mean_3")) is not None), None)
        teams.append({"team": team, "expected_pass_attempts": None,
                      "expected_rush_attempts": None,
                      "lagged_team_targets_proxy": team_targets,
                      "lagged_rb_carries_proxy": team_carries,
                      "target_distribution": target,
                      "carry_distribution": carries,
                      "red_zone_distribution": red_zone,
                      "top_roles": roles[:5], "missing_role_players": missing,
                      "role_coverage": (len(members) - len(missing)) / len(members),
                      "volume_note": "Targets and RB carries are reconciled lagged allocations; pass/rush attempts and red-zone volume are unavailable without independent pregame evidence"})
    return teams


def _role_projection_anomalies(
    players: Sequence[Player], source: dict[str, dict], candidate_counts: Counter,
    candidate_total: int,
) -> list[dict]:
    """Flag high-confidence role/rank gaps across the full eligible pool.

    The evidence fields describe possible drivers; they do not attribute a causal
    share of a lineup decision to any one input.
    """
    skill = [p for p in players if p.position in {"RB", "WR", "TE"}]
    by_team: dict[str, list[Player]] = defaultdict(list)
    by_position: dict[str, list[Player]] = defaultdict(list)
    for player in skill:
        by_team[player.team].append(player)
        by_position[player.position].append(player)
    rows = []
    for player in skill:
        evidence = source.get(str(player.player_id), {})
        importance = _number(evidence.get("offensive_role_importance"))
        if (importance is None or evidence.get("offensive_role_confidence") != "high"
                or evidence.get("offensive_role_class") not in {"offensive centerpiece", "primary option"}):
            continue
        team = by_team[player.team]
        role_rank = 1 + sum(
            (_number(source.get(str(other.player_id), {}).get("offensive_role_importance")) or -1) > importance
            for other in team
        )
        if role_rank > 2:
            continue
        mean_rank = 1 + sum(other.projection > player.projection for other in team)
        p90_rank = 1 + sum(other.ceiling > player.ceiling for other in team)
        value = player.projection / max(1.0, player.salary / 1000)
        value_rank = 1 + sum(
            other.projection / max(1.0, other.salary / 1000) > value
            for other in by_position[player.position]
        )
        exposure = candidate_counts[str(player.player_id)] / max(1, candidate_total)
        if (max(mean_rank - role_rank, p90_rank - role_rank) < 2
                and exposure >= 0.1 and value_rank <= len(by_position[player.position]) / 2):
            continue
        recent_targets = _number(evidence.get("targets_mean_3"))
        recent_carries = _number(evidence.get("carries_mean_3"))
        projected_targets = _number(evidence.get("projected_targets"))
        projected_carries = _number(evidence.get("projected_carries"))
        rows.append({
            "player_id": str(player.player_id), "name": player.name, "team": player.team,
            "position": player.position, "role_class": evidence.get("offensive_role_class"),
            "role_importance": importance, "role_confidence": "high",
            "team_role_rank": role_rank, "team_mean_rank": mean_rank,
            "team_p90_rank": p90_rank, "position_value_rank": value_rank,
            "position_value_count": len(by_position[player.position]),
            "mean": player.projection, "p90": player.ceiling,
            "salary": player.salary, "mean_per_1000_salary": value,
            "candidate_count": candidate_counts[str(player.player_id)],
            "candidate_total": candidate_total, "candidate_exposure": exposure,
            "possible_drivers": {
                "salary_value": {"salary": player.salary, "position_value_rank": value_rank},
                "matchup_context": {"opponent": player.opponent, "game_total": player.game_total,
                                    "team_total": player.team_total, "spread": player.spread},
                "recent_volume": {"targets_mean_3": recent_targets, "carries_mean_3": recent_carries},
                "allocated_volume_proxy": {"projected_targets": projected_targets,
                                           "projected_carries": projected_carries,
                                           "source": evidence.get("projected_opportunity_source")},
                "recent_efficiency_proxy": {"player_roll3_mean": _number(evidence.get("player_roll3_mean"))},
                "touchdown_expectation": "not separately identified in the current model",
                "optimizer_construction": "candidate exposure reflects joint salary and stack constraints; causal effect unisolated",
                "ownership": _number(evidence.get("ownership")),
            },
            "diagnostic_only": True,
        })
    return sorted(rows, key=lambda row: (row["candidate_exposure"],
                                          -row["role_importance"], row["name"]))


def _receiving_role(row: dict) -> dict:
    """Describe receiving usage using only observed current or lagged inputs."""
    current_share = _number(row.get("pregame_target_share"))
    current_targets = _number(row.get("pregame_expected_targets"))
    current_routes = _number(row.get("pregame_expected_routes"))
    lagged_share = _number(row.get("target_share_mean_3"))
    lagged_targets = _number(row.get("targets_mean_3"))
    share = current_share if current_share is not None else lagged_share
    targets = current_targets if current_targets is not None else lagged_targets
    routes = current_routes
    inputs = [value for value in (share, targets, routes) if value is not None]
    strength_terms = []
    if share is not None:
        strength_terms.append(min(1.0, max(0.0, share / 0.28)))
    if targets is not None:
        strength_terms.append(min(1.0, max(0.0, targets / 8.0)))
    if routes is not None:
        strength_terms.append(min(1.0, max(0.0, routes / 32.0)))
    strength = max(strength_terms, default=None)
    return {
        "strength": strength,
        "source": ("current_pregame" if any(value is not None for value in (current_share, current_targets, current_routes))
                   else "lagged_three_game" if inputs else "unavailable"),
        "expected_targets": current_targets, "target_share": share,
        "expected_routes": current_routes, "recent_targets_mean_3": lagged_targets,
        "recent_target_share_mean_3": lagged_share,
        "receptions_mean_3": _number(row.get("receptions_mean_3")),
        "receiving_yards_mean_3": _number(row.get("receiving_yards_mean_3")),
        "receiving_fantasy_points": None,
        "receiving_fantasy_points_reason": "Unavailable: no receiving-point decomposition in the projection snapshot",
    }


def _rushing_qb(qb: Player, source: dict) -> dict:
    carries = _number(source.get("pregame_expected_carries"))
    if carries is None:
        carries = _number(source.get("carries_mean_3"))
    strength = _number(qb.optimizer_rushing_role_strength)
    if carries is not None:
        label = "high-rushing-upside QB" if carries >= 5 else "moderate rushing QB" if carries >= 2 else "pocket-oriented QB"
        basis = "expected or recent carries"
    elif strength is not None and strength > 0:
        label = "high-rushing-upside QB" if strength >= 0.67 else "moderate rushing QB" if strength >= 0.33 else "pocket-oriented QB"
        basis = "existing rushing-role strength"
    else:
        label, basis = "rushing role unavailable", "no usable rushing evidence"
    return {"label": label, "basis": basis, "carries": carries, "rushing_role_strength": strength}


def _game_environment(qb: Player, all_game_totals: list[float]) -> dict:
    safe = qb.market_context_point_in_time_safe is True
    total = _number(qb.game_total) if safe else None
    spread = _number(qb.spread) if safe else None
    if total is None or spread is None or total <= 0:
        label = "market environment unavailable"
    elif all_game_totals and total >= sorted(all_game_totals)[int(0.75 * (len(all_game_totals) - 1))] and spread is not None and abs(spread) <= 4:
        label = "high-total competitive"
    elif spread is not None and spread <= -4:
        label = "favored offense"
    elif spread is not None and spread >= 4:
        label = "underdog passing"
    else:
        label = "other"
    return {"label": label, "game_total": total, "team_spread": spread, "team_total": _number(qb.team_total),
            "market_safe": safe and total is not None and total > 0 and spread is not None}


def _bring_back_evaluation(qb: Player, player: Player, correlation_rules: list[dict], multiplier: float,
                           ownership_available: bool) -> dict:
    """Explain the existing competitive-shootout rule for one structural bring-back."""
    safe = qb.market_context_point_in_time_safe is True
    total = _number(qb.game_total) if safe else None
    spread = _number(qb.spread) if safe else None
    eligible_position = player.position in {"WR", "TE"} or (
        player.position == "RB" and player.optimizer_receiving_role_strength > 0
    )
    high_total = min(1.0, max(0.0, (total - 44.0) / 10.0)) if total is not None else None
    competitive = min(1.0, max(0.0, 1.0 - abs(spread) / 7.0)) if spread is not None else None
    fired = [rule for rule in correlation_rules
             if rule.get("reason_code") == "competitive_shootout_bring_back"
             and {member.get("player_id") for member in rule.get("players", [])} == {qb.player_id, player.player_id}]
    raw = sum(float(rule.get("score_contribution") or 0) for rule in fired)
    return {
        "player_id": player.player_id, "name": player.name, "position": player.position,
        "ownership": player.ownership if ownership_available else None,
        "game": f"{qb.team}–{qb.opponent}", "game_total": total, "team_spread": spread,
        "rule_id": "correlation.shootout_bring_back_v1",
        "rule_fired": bool(fired), "raw_rule_value": raw if total is not None and spread is not None else None,
        "selector_contribution": sum(float(rule.get("objective_contribution") or 0) for rule in fired),
        "objective_multiplier": multiplier,
        "high_total_signal": high_total, "competitive_signal": competitive,
        "eligible_pass_game_option": eligible_position,
        "reason": ("fired" if fired else "market data unavailable" if not safe or total is None or spread is None
                   else "RB receiving role not established" if not eligible_position
                   else "game spread not competitive" if competitive == 0
                   else "game total not above 44" if high_total == 0
                   else "rule did not fire"),
    }


def describe_candidate(
    lineup: Sequence[Player], *, all_players: Sequence[Player], config: Any,
    pool_by_id: dict[str, dict], ownership_available: bool,
    game_totals: list[float],
    candidate_aware_ownership: bool = False,
) -> dict:
    """Reconstruct the existing solver objective; hard caps are reported separately."""
    if candidate_aware_ownership:
        ownership_available = all(player.ownership is not None for player in lineup)
    qb = next(player for player in lineup if player.position == "QB")
    same_team = [p for p in lineup if p.team == qb.team and p.position in {"WR", "TE"}]
    bring_backs = [p for p in lineup if p.team == qb.opponent and p.position in {"RB", "WR", "TE"}]
    game_stack = [p for p in lineup if p.team in {qb.team, qb.opponent}]
    weights = config.objective_weights
    max_mean = max(1.0, *(p.projection + p.optimizer_context_adjustment for p in all_players))
    max_p90 = max(1.0, *(p.ceiling + p.optimizer_context_adjustment for p in all_players))
    max_leverage = max(1.0, *(abs(p.leverage) for p in all_players))
    mean = sum(p.projection for p in lineup)
    p90 = sum(p.ceiling for p in lineup)
    context = sum(p.optimizer_context_adjustment for p in lineup)
    normalizer_mean = max_mean if config.normalize_objective else 1.0
    normalizer_p90 = max_p90 if config.normalize_objective else 1.0
    normalizer_leverage = max_leverage if config.normalize_objective else 1.0
    components = {
        "mean": weights.projection * mean / normalizer_mean,
        "p90": weights.ceiling * p90 / normalizer_p90,
        "context": context * (weights.projection / normalizer_mean + weights.ceiling / normalizer_p90),
        "leverage": weights.leverage * sum(p.leverage for p in lineup) / normalizer_leverage,
        "qb_stack": 0.0, "bring_back": 0.0, "game_environment": 0.0,
        "correlation": 0.0, "ownership_chalk": 0.0, "duplication": 0.0,
        "penalties": 0.0, "other_residual": 0.0,
    }
    profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
    correlation = score_lineup_correlations(
        lineup, profile=profile,
        objective_multiplier=weights.correlation * config.correlation_bonus,
    )
    for rule in correlation["triggered_rules"]:
        components[_contribution_group(rule)] += float(rule.get("objective_contribution") or 0)
    score = sum(components.values())
    ownership_available = (ownership_available or candidate_aware_ownership) and all(
        p.ownership is not None for p in lineup
    )
    market_available = (qb.market_context_point_in_time_safe is True and
                        qb.game_total is not None and qb.spread is not None and
                        qb.team_total is not None and qb.game_total > 0)
    component_statuses = {}
    for key, value in components.items():
        if key in {"ownership_chalk", "duplication"}:
            component_statuses[key] = {"status": "DISABLED", "value": None,
                                       "reason": "ownership is diagnostic, not a soft selector term"}
        elif key == "leverage" and not all(p.optimal_lineup_probability is not None for p in lineup):
            component_statuses[key] = {"status": "UNAVAILABLE", "value": None,
                                       "reason": "leverage evidence missing"}
        elif key in {"context", "bring_back", "game_environment", "correlation"} and not market_available and value == 0:
            component_statuses[key] = {"status": "UNAVAILABLE", "value": None,
                                       "reason": "market data missing"}
        else:
            component_statuses[key] = {"status": "ACTIVE" if value else "ACTIVE_ZERO",
                                       "value": value, "reason": None}
    owners = [max(0.01, p.ownership) for p in lineup] if ownership_available else []
    log_ownership = sum(log(value / 100.0) for value in owners) if owners else None
    multiplier = weights.correlation * config.correlation_bonus
    bring_back_evaluations = [
        _bring_back_evaluation(qb, player, correlation["triggered_rules"], multiplier,
                               ownership_available)
        for player in bring_backs
    ]
    environment_raw = sum(
        float(rule.get("score_contribution") or 0)
        for rule in correlation["triggered_rules"]
        if _contribution_group(rule) == "game_environment"
    )
    rb = [p for p in lineup if p.position == "RB"]
    wr_te = [p for p in lineup if p.position in {"WR", "TE"}]
    dst = next(p for p in lineup if p.position in {"DST", "D", "DEF"})
    flex = "RB" if len(rb) == 3 else "WR" if sum(p.position == "WR" for p in lineup) == 4 else "TE"
    stack_type = f"QB+{len(same_team)}" + ("+bring-back" if bring_backs else "")
    return {
        "player_ids": [p.player_id for p in lineup],
        "roster": [{"player_id": p.player_id, "name": p.name, "team": p.team, "position": p.position,
                    "salary": p.salary, "ownership": p.ownership if ownership_available else None} for p in lineup],
        "salary": sum(p.salary for p in lineup), "mean": mean, "p90": p90,
        "objective_score": score,
        "ownership_derived_terms": {
            "status": "available" if ownership_available else "unavailable",
            "ownership_chalk": components["ownership_chalk"] if ownership_available else None,
            "duplication": components["duplication"] if ownership_available else None,
            "leverage": (components["leverage"] if ownership_available
                         and all(p.optimal_lineup_probability is not None for p in lineup)
                         else None),
            "reason": (None if ownership_available else
                       "at least one lineup player lacks an ownership projection"),
        },
        "base_solver": sum(components[key] for key in ("mean", "p90", "context", "leverage")),
        "components": components,
        "component_statuses": component_statuses,
        "correlation_positive": sum(max(0.0, float(r.get("objective_contribution") or 0)) for r in correlation["triggered_rules"]),
        "correlation_negative": sum(min(0.0, float(r.get("objective_contribution") or 0)) for r in correlation["triggered_rules"]),
        "correlation_rules": correlation["triggered_rules"],
        "qb": {"player_id": qb.player_id, "name": qb.name, "team": qb.team,
               "ownership": qb.ownership if ownership_available else None,
               **_rushing_qb(qb, pool_by_id.get(qb.player_id, {}))},
        "stack": {
            "type": stack_type, "partners": [{"name": p.name, "position": p.position,
                "ownership": p.ownership if ownership_available else None} for p in same_team],
            "partner_count": len(same_team), "bring_backs": [
                {"name": p.name, "position": p.position, "projection": p.projection, "p90": p.ceiling,
                 "ownership": p.ownership if ownership_available else None}
                for p in bring_backs
            ],
            "bring_back_evaluations": bring_back_evaluations,
            "bring_back_count": len(bring_backs), "game_stack_size": len(game_stack),
            "game_stack_salary": sum(p.salary for p in game_stack),
            "game_stack_ownership": sum(p.ownership for p in game_stack) if ownership_available else None,
            "game_stack_log_ownership": sum(log(max(0.01, p.ownership) / 100.0) for p in game_stack) if ownership_available else None,
            "bring_back_correlation_contribution": components["bring_back"],
        },
        "primary_game": f"{qb.team}–{qb.opponent}",
        "games_represented": sorted({str(p.game_id) for p in lineup if p.game_id}),
        "game_environment": {**_game_environment(qb, game_totals),
            "raw_rule_score": environment_raw if market_available else None,
            "selector_contribution": components["game_environment"] if market_available else None,
            "reason": ("market environment unavailable" if not market_available else
                       "Active game-related correlation rule" if components["game_environment"] else
                       "No standalone primary-game bonus in the current Classic objective; no game-related pair rule fired")},
        "ownership_sum": sum(p.ownership for p in lineup) if ownership_available else None,
        "log_ownership": log_ownership,
        "ownership_product": exp(log_ownership) if log_ownership is not None else None,
        "relative_chalk": None,
        "leverage_available": all(p.optimal_lineup_probability is not None for p in lineup) and ownership_available,
        "leverage_sum": sum(p.leverage for p in lineup) if ownership_available and all(p.optimal_lineup_probability is not None for p in lineup) else None,
        "high_owned_count": sum(p.ownership >= 25 for p in lineup) if ownership_available else None,
        "low_owned_count": sum(p.ownership < 10 for p in lineup) if ownership_available else None,
        "dst_ownership": dst.ownership if ownership_available else None,
        "rbs": [{
            "name": p.name, "team": p.team, "salary": p.salary, "projection": p.projection,
            "p90": p.ceiling, "ownership": p.ownership if ownership_available else None,
            "spread": p.spread, "team_total": p.team_total,
            "same_team_dst": p.team == dst.team, "opposing_dst": p.team == dst.opponent,
            "in_qb_game": p.team in {qb.team, qb.opponent},
            "receiving_role_strength": _receiving_role(pool_by_id.get(p.player_id, {}))["strength"],
            "receiving_role_diagnostic": _receiving_role(pool_by_id.get(p.player_id, {})),
            "opportunity": _opportunity(pool_by_id.get(p.player_id, {})),
        } for p in rb],
        "rb_construction": {
            "same_game_pair": any(left.game_id and left.game_id == right.game_id
                                  for index, left in enumerate(rb) for right in rb[index + 1:]),
            "high_owned_pair": sum(p.ownership >= 25 for p in rb) >= 2 if ownership_available else None,
        },
        "pass_catchers": {
            "salary": sum(p.salary for p in wr_te),
            "high_owned_count": sum(p.ownership >= 25 for p in wr_te) if ownership_available else None,
            "low_owned_count": sum(p.ownership < 10 for p in wr_te) if ownership_available else None,
            "one_offs": [p.name for p in wr_te if p.team not in {qb.team, qb.opponent}],
            "te_in_qb_stack": any(p.team == qb.team and p.position == "TE" for p in wr_te),
            "flex_position": flex,
        },
        "cheap_skill_opportunity": [{"name": p.name, "position": p.position, "salary": p.salary, **_opportunity(pool_by_id.get(p.player_id, {}))}
            for p in wr_te + rb if p.salary <= 4500],
    }


def _select_global(
    candidates: list[dict], count: int, max_exposure: float,
    locked_player_ids: set[str], maximum_exposure_by_player: dict[str, float],
    minimum_exposure_by_player: dict[str, float],
    solver_backend: str = "bundled",
    max_lineup_overlap: int | None = None,
    distinct_qb_paths: bool = False,
    max_objective_loss: float | None = None,
    max_lineups_with_any_player_ids: tuple[set[str], float] | None = None,
    enforce_maximum_for_locked_ids: set[str] | None = None,
    minimum_qb_paths: int = 1,
    minimum_stack_families: int = 1,
) -> list[int]:
    if max_lineup_overlap is not None and (type(max_lineup_overlap) is not int
                                           or not 0 <= max_lineup_overlap <= 8):
        raise ValueError("max_lineup_overlap must be an integer from 0 to 8")
    if type(distinct_qb_paths) is not bool:
        raise ValueError("distinct_qb_paths must be a boolean")
    if max_objective_loss is not None and (isinstance(max_objective_loss, bool)
                                           or not isfinite(float(max_objective_loss))
                                           or float(max_objective_loss) < 0):
        raise ValueError("max_objective_loss must be a finite non-negative number")
    model = pulp.LpProblem("classic_small_field_selection", pulp.LpMaximize)
    chosen = pulp.LpVariable.dicts("lineup", range(len(candidates)), cat="Binary")
    model += pulp.lpSum(candidates[i]["objective_score"] * chosen[i] for i in chosen)
    model += pulp.lpSum(chosen.values()) == count
    if max_objective_loss is not None and candidates:
        objective_floor = max(row["objective_score"] for row in candidates) - float(max_objective_loss)
        for i, row in enumerate(candidates):
            if row["objective_score"] < objective_floor:
                model += chosen[i] == 0
    if max_lineup_overlap is not None:
        rosters = [set(row["player_ids"]) for row in candidates]
        for i, left in enumerate(rosters):
            for j in range(i + 1, len(rosters)):
                if len(left & rosters[j]) > max_lineup_overlap:
                    model += chosen[i] + chosen[j] <= 1
    if distinct_qb_paths:
        for qb_id in sorted({str(row["qb"]["player_id"]) for row in candidates}):
            model += pulp.lpSum(chosen[i] for i, row in enumerate(candidates)
                                  if str(row["qb"]["player_id"]) == qb_id) <= 1
    for minimum, key, label in (
        (minimum_qb_paths, lambda row: str(row["qb"]["player_id"]), "qb_path"),
        (minimum_stack_families, lambda row: str(row["stack"]["type"]), "stack_family"),
    ):
        if minimum > 1:
            groups = sorted({key(row) for row in candidates})
            active = pulp.LpVariable.dicts(label, range(len(groups)), cat="Binary")
            for group_index, group in enumerate(groups):
                members = pulp.lpSum(chosen[i] for i, row in enumerate(candidates)
                                       if key(row) == group)
                model += members >= active[group_index]
                model += members <= count * active[group_index]
            model += pulp.lpSum(active.values()) >= minimum
    if max_lineups_with_any_player_ids is not None:
        risk_ids, share = max_lineups_with_any_player_ids
        if not 0 <= share <= 1:
            raise ValueError("risk portfolio budget must be in [0, 1]")
        model += pulp.lpSum(chosen[i] for i, row in enumerate(candidates)
                            if risk_ids.intersection(row["player_ids"])) <= floor(count * share)
    player_ids = sorted({pid for row in candidates for pid in row["player_ids"]})
    limit = max(1, ceil(count * max_exposure))
    for pid in player_ids:
        if pid in locked_player_ids and pid not in (enforce_maximum_for_locked_ids or set()):
            continue
        appearances = pulp.lpSum(chosen[i] for i, row in enumerate(candidates) if pid in row["player_ids"])
        player_limit = min(limit, int(count * maximum_exposure_by_player.get(pid, 1.0)))
        model += appearances <= player_limit
        minimum = ceil(count * minimum_exposure_by_player.get(pid, 0.0))
        if minimum:
            model += appearances >= minimum
    if model.solve(make_cbc_solver(solver_backend)) != pulp.LpStatusOptimal:
        return []
    return sorted((i for i in chosen if pulp.value(chosen[i]) >= 0.9), key=lambda i: -candidates[i]["objective_score"])


def _admit_candidate_caps(candidates: list[dict], lineups: list[list[Player]],
                          caps: dict[str, float], elevated_ids: set[str],
                          target: int, max_elevated: int,
                          solver_backend: str = "bundled") -> tuple[list[dict], list[list[Player]], dict]:
    """Choose the largest jointly cap-feasible subset of already solved rosters."""
    seen: set[tuple[str, ...]] = set()
    eligible: list[tuple[dict, list[Player]]] = []
    funnel: Counter = Counter(requested=target, solved=len(candidates), legal=len(candidates),
                              duplicate=0, rejected_by_injury_cap=0,
                              rejected_by_family_constraint=0)
    for row, lineup in zip(candidates, lineups):
        ids = set(row["player_ids"])
        key = tuple(sorted(ids))
        if key in seen:
            funnel["duplicate"] += 1
            continue
        seen.add(key)
        if len(ids & elevated_ids) > max_elevated:
            funnel["rejected_by_injury_cap"] += 1
            continue
        eligible.append((row, lineup))
    if not eligible:
        funnel["accepted"] = 0
        funnel["remaining_deficit"] = target
        return [], [], {**funnel, "rejected_by_quality": 0,
                        "rejected_by_family_constraint": 0,
                        "status": "CANDIDATE_POOL_UNDERFILLED"}

    model = pulp.LpProblem("classic_candidate_admission", pulp.LpMaximize)
    chosen = pulp.LpVariable.dicts("admit", range(len(eligible)), cat="Binary")
    count = pulp.lpSum(chosen.values())
    model += count
    model += count <= target
    for pid, cap in sorted(caps.items()):
        if cap >= 1:
            continue
        model += pulp.lpSum(chosen[i] for i, (row, _) in enumerate(eligible)
                            if pid in row["player_ids"]) <= float(cap) * count
    if model.solve(make_cbc_solver(solver_backend)) != pulp.LpStatusOptimal:
        raise ValueError("Joint candidate admission could not establish a cap-feasible solution")
    maximum_count = round(pulp.value(count))
    model += count == maximum_count
    model.sense = pulp.LpMaximize
    model.setObjective(pulp.lpSum(
        (float(row["objective_score"]) - i * 1e-9) * chosen[i]
        for i, (row, _) in enumerate(eligible)
    ))
    if model.solve(make_cbc_solver(solver_backend)) != pulp.LpStatusOptimal:
        raise ValueError("Joint candidate admission could not rank the cap-feasible solution")
    accepted = [pair for i, pair in enumerate(eligible) if pulp.value(chosen[i]) >= .9]
    funnel["rejected_by_player_cap"] = len(eligible) - len(accepted)
    funnel["admission_method"] = "joint_max_count_then_selector_score"
    funnel["accepted"] = len(accepted)
    funnel["remaining_deficit"] = target - len(accepted)
    return ([row for row, _ in accepted], [lineup for _, lineup in accepted],
            {**funnel, "rejected_by_quality": 0, "rejected_by_family_constraint": 0,
             "status": "CANDIDATE_POOL_UNDERFILLED" if len(accepted) < target else "complete"})


def classic_entry_readiness(*, players: Sequence[Player], selected: Sequence[Sequence[Player]],
                            candidates: Sequence[dict], source: dict[str, dict],
                            salary_identity: dict, production_funnel: dict | None,
                            controls: dict | None, first_kickoff_at: str | None,
                            decision_at: Any, requested_count: int,
                            market_fresh_hours: float = 6, market_stale_hours: float = 24,
                            market_stale_policy: str = "warning") -> dict:
    """A saved pre-entry decision, with missing inputs separate from corrupt inputs."""
    from .classic_prospective import _timestamp

    if not 0 < market_fresh_hours < market_stale_hours:
        raise ValueError("market freshness thresholds must satisfy 0 < fresh < stale")
    if market_stale_policy not in {"warning", "blocker"}:
        raise ValueError("market_stale_policy must be warning or blocker")

    checks: dict[str, dict] = {}
    def add(name: str, severity: str, reason: str = "") -> None:
        checks[name] = {"status": severity, "reason": reason}

    salary_ok = bool(players) and all(p.salary > 0 for p in players)
    add("Salary/slate integrity", "PASS" if salary_ok else "BLOCKER",
        "positive saved salaries" if salary_ok else "missing or invalid salary/slate")
    identity_ok = (salary_identity.get("status") == "PASS" and
                   all(p.team and p.opponent and p.team != p.opponent and p.game_id for p in players))
    add("Player/team/opponent identity", "PASS" if identity_ok else "BLOCKER",
        "saved salary identities match" if identity_ok else "saved salary or game identity mismatch")
    kickoff = _timestamp(first_kickoff_at)
    cutoff = _timestamp(decision_at)
    if kickoff is not None and kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=UTC)
    if cutoff is not None and cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=UTC)
    if kickoff is None or cutoff is None:
        add("Kickoff/pre-lock evidence", "DEVELOPMENT_PREVIEW", "kickoff or decision timestamp missing")
    elif cutoff >= kickoff:
        add("Kickoff/pre-lock evidence", "BLOCKER", "decision at or after first kickoff")
    else:
        add("Kickoff/pre-lock evidence", "PASS")
    projected = [p for p in players if p.projection > 0 and p.ceiling > 0]
    add("Projection coverage", "PASS" if len(projected) == len(players) and len(players) >= 100
        else "DEVELOPMENT_PREVIEW", f"{len(projected)}/{len(players)} eligible projections")
    eligible_own = sum(p.ownership is not None for p in players)
    candidate_own = sum(all(source.get(pid, {}).get("ownership") is not None
                            for pid in row["player_ids"]) for row in candidates)
    selected_players = {p.player_id: p for lineup in selected for p in lineup}
    selected_own = sum(p.ownership is not None for p in selected_players.values())
    ownership_complete = bool(selected_players) and selected_own == len(selected_players)
    add("Ownership coverage", "DEVELOPMENT_PREVIEW" if not ownership_complete else
        "WARNING" if eligible_own < len(players) or candidate_own < len(candidates) else "PASS",
        f"eligible {eligible_own}/{len(players)}; candidate lineups {candidate_own}/{len(candidates)}; "
        f"selected players {selected_own}/{len(selected_players)}")
    market_games: dict[str, list[Player]] = defaultdict(list)
    for player in players:
        market_games[str(player.game_id)].append(player)
    market_missing = []
    market_corrupt = []
    market_stale = []
    market_aging = []
    market_fresh = []
    market_observations = []
    market_game_details = []
    for game_id, members in market_games.items():
        observations = [_timestamp(source.get(p.player_id, {}).get("market_observed_at"))
                        for p in members]
        game_detail = {"game_id": game_id, "player_count": len(members),
                       "source": source.get(members[0].player_id, {}).get("market_source_system"),
                       "observed_at": observations[0].isoformat() if observations[0] else None,
                       "age_hours": None}
        values = {(p.game_total, p.spread, p.team_total) for p in members}
        complete = all(p.market_context_point_in_time_safe is True and
                       p.game_total is not None and p.spread is not None and
                       p.team_total is not None for p in members)
        if not complete or any(value is None for value in observations):
            market_missing.append(game_id)
            market_game_details.append({**game_detail, "status": "missing"})
            continue
        observed = observations[0]
        if (len(set(observations)) != 1 or any(not isfinite(float(v)) for triple in values for v in triple)
                or any(p.game_total <= 0 or p.game_total > 80 or abs(p.spread) > 30
                       or p.team_total <= 0 or
                       abs(p.team_total - (p.game_total - p.spread) / 2) > .01
                       for p in members)
                or cutoff and observed > cutoff or kickoff and observed >= kickoff):
            market_corrupt.append(game_id)
            market_game_details.append({**game_detail, "status": "invalid"})
            continue
        market_observations.append(observed)
        age_hours = (cutoff - observed).total_seconds() / 3600 if cutoff else None
        if age_hours is None or age_hours > market_stale_hours:
            market_stale.append(game_id)
            game_status = "stale"
        elif age_hours > market_fresh_hours:
            market_aging.append(game_id)
            game_status = "aging"
        else:
            market_fresh.append(game_id)
            game_status = "fresh"
        market_game_details.append({**game_detail, "status": game_status,
                                    "age_hours": age_hours})
    market_coverage = {"total_games": len(market_games),
                       "sourced_games": len(market_games) - len(market_missing) - len(market_corrupt),
                       "fresh_games": market_fresh, "aging_games": market_aging,
                       "stale_games": market_stale, "missing_games": market_missing,
                       "invalid_games": market_corrupt,
                       "games": market_game_details,
                       "oldest_observed_at": min(market_observations).isoformat() if market_observations else None,
                       "newest_observed_at": max(market_observations).isoformat() if market_observations else None,
                       "fresh_hours": market_fresh_hours, "stale_hours": market_stale_hours,
                       "stale_policy": market_stale_policy}
    stale_severity = ("BLOCKER" if market_stale_policy == "blocker" or
                      kickoff and cutoff and (kickoff - cutoff).total_seconds() <= 6 * 3600
                      else "WARNING")
    add("Market/game environment", "BLOCKER" if market_corrupt else
        "DEVELOPMENT_PREVIEW" if market_missing else stale_severity if market_stale else "PASS",
        f"coverage {market_coverage['sourced_games']}/{market_coverage['total_games']} games; "
        f"fresh {len(market_fresh)}, aging {len(market_aging)}, stale {len(market_stale)}, "
        f"missing {len(market_missing)}, invalid {len(market_corrupt)}")
    risk = (controls or {}).get("classifications") or {}
    availability_missing = [pid for pid, item in risk.items()
                            if item["bucket"].startswith("questionable") and
                            not item.get("evidence_timestamp")]
    add("Availability evidence", "DEVELOPMENT_PREVIEW" if availability_missing else "PASS",
        f"questionable with undated evidence: {len(availability_missing)}")
    underfill = (production_funnel or {}).get("remaining_deficit", 0)
    add("Candidate-pool size", "BLOCKER" if underfill or len(candidates) < 100 else "PASS",
        f"{len(candidates)} candidates; deficit {underfill}")
    candidate_counts = Counter(pid for row in candidates for pid in row["player_ids"])
    selected_counts = Counter(p.player_id for lineup in selected for p in lineup)
    candidate_violations = []
    selected_violations = []
    elevated = {pid for pid, item in risk.items() if item["bucket"] == "questionable_elevated"}
    caps = (controls or {}).get("candidate_caps") or {}
    for pid, cap in caps.items():
        if candidate_counts[pid] > floor(cap * len(candidates)):
            candidate_violations.append(pid)
    for pid, item in risk.items():
        cap = (controls or {}).get("overrides", {}).get(pid, {}).get("selected_cap")
        if cap is None:
            cap = {"questionable_elevated": .40, "questionable_full_role": .60}.get(item["bucket"])
        if cap is not None and selected_counts[pid] > floor(cap * len(selected)):
            selected_violations.append(pid)
    if any(sum(p.player_id in elevated for p in lineup) > 1 for lineup in selected):
        selected_violations.append("multiple_elevated_in_lineup")
    if sum(any(p.player_id in elevated for p in lineup) for lineup in selected) > floor(.60 * len(selected)):
        selected_violations.append("aggregate_elevated_budget")
    add("Questionable-player risk", "BLOCKER" if selected_violations or candidate_violations else "PASS",
        f"candidate violations {candidate_violations}; selected violations {selected_violations}")
    unexplained_high = [pid for pid, appearances in candidate_counts.items()
                        if controls and candidates and appearances / len(candidates) > .80 and
                        (controls or {}).get("core_classes", {}).get(pid) != "elite_high_confidence" and
                        pid not in (controls or {}).get("overrides", {}) and
                        pid not in (controls or {}).get("locked_ids", [])]
    add("Candidate concentration", "BLOCKER" if candidate_violations or unexplained_high else "PASS",
        f"cap violations {candidate_violations}; unexplained >80% {unexplained_high}")
    locked = set((controls or {}).get("locked_ids", []))
    selected_exposure_errors = []
    elite_cores = []
    for pid, appearances in selected_counts.items():
        if pid in locked:
            continue
        player = selected_players[pid]
        limit = .60 if player.position == "QB" else (
            .80 if player.position in {"RB", "WR", "TE"} and
            (controls or {}).get("core_classes", {}).get(pid) != "elite_high_confidence" else 1.0
        )
        if appearances > max(1, floor(limit * len(selected))):
            selected_exposure_errors.append(pid)
        if (appearances == len(selected) and
                (controls or {}).get("core_classes", {}).get(pid) == "elite_high_confidence"):
            elite_cores.append(pid)
    add("Selected player exposure", "BLOCKER" if selected_exposure_errors else
        "WARNING" if elite_cores else "PASS",
        f"cap violations {selected_exposure_errors}; 100% elite cores {elite_cores}")
    skill_approval_ids = [pid for pid, appearances in selected_counts.items()
                          if len(selected) > 1 and appearances == len(selected)
                          and selected_players[pid].position in {"RB", "WR", "TE"}]
    add("100% skill-player exposure approval", "APPROVAL_REQUIRED" if skill_approval_ids else "PASS",
        f"players requiring pre-lock approval: {skill_approval_ids}")
    overlaps = [len({p.player_id for p in left} & {p.player_id for p in right})
                for i, left in enumerate(selected) for right in selected[i + 1:]]
    add("Portfolio overlap", "BLOCKER" if any(value > 6 for value in overlaps) else "PASS",
        f"maximum {max(overlaps, default=0)}/9")
    qb_paths = {next((p.player_id for p in lineup if p.position == "QB"), None) for lineup in selected}
    qb_paths.discard(None)
    add("QB/game-path diversity", "BLOCKER" if len(selected) > 1 and len(qb_paths) < 2 else
        "WARNING" if len(selected) >= 5 and len(qb_paths) < 3 else "PASS",
        f"{len(qb_paths)} distinct paths")
    legal = len(selected) == requested_count and all(len(lineup) == 9 and
            sum(p.salary for p in lineup) <= 50000 for lineup in selected)
    add("Legal lineup validation", "PASS" if legal else "BLOCKER",
        f"{len(selected)}/{requested_count} selected lineups")
    status = ("BLOCKED" if any(row["status"] == "BLOCKER" for row in checks.values()) else
              "DEVELOPMENT_PREVIEW" if any(row["status"] == "DEVELOPMENT_PREVIEW" for row in checks.values()) else
              "ENTRY_READY_WITH_APPROVAL_REQUIRED" if skill_approval_ids else "ENTRY_READY")
    return {"status": status, "entry_ready": status == "ENTRY_READY", "checks": checks,
            "market_coverage": market_coverage, "skill_approval_player_ids": skill_approval_ids,
            "reasons": [f"{name}: {row['reason']}" for name, row in checks.items()
                        if row["status"] in {"BLOCKER", "DEVELOPMENT_PREVIEW", "APPROVAL_REQUIRED"}]}


def portfolio_summary(selected: Sequence[dict], *, candidate_count: int,
                      constraints: dict | None = None) -> dict:
    """Report concentration and lineup theses without treating proxies as payout EV."""
    if not selected:
        return {"lineups": [], "player_exposure": [], "game_exposure": [],
                "primary_game_exposure": [],
                "overlap_matrix": [], "core_players": [], "constraints": constraints or {}}
    count = len(selected)
    player_counts = Counter(pid for row in selected for pid in set(row["player_ids"]))
    games = Counter(game for row in selected for game in set(row.get("games_represented") or []))
    primary_games = Counter(row["primary_game"] for row in selected)
    name_by_id = {str(p["player_id"]): p["name"] for row in selected for p in row["roster"]}
    lineup_rows = []
    for index, row in enumerate(selected, 1):
        unique = sorted(pid for pid in row["player_ids"] if player_counts[pid] == 1)
        qb = row["qb"]
        lineup_rows.append({
            "lineup": index, "rank": row["rank"], "qb": qb["name"],
            "qb_stack_family": row["stack"]["type"], "primary_game": row["primary_game"],
            "construction_archetype": f"{row['stack']['type']} / {row['pass_catchers']['flex_position']} FLEX",
            "projected_score": row["mean"], "ceiling_proxy": row["p90"],
            "projected_ownership_sum": row["ownership_sum"],
            "leverage_proxy": row["leverage_sum"], "selector_score": row["objective_score"],
            "unique_players": [{"player_id": pid, "name": name_by_id.get(pid, pid)} for pid in unique],
            "selection_reason": (f"QB/game path {qb['name']} / {row['primary_game']}; "
                                 f"{len(unique)} player(s) unique to this portfolio; "
                                 f"selector rank {row['rank']} of {candidate_count}."),
        })
    return {
        "lineups": lineup_rows,
        "player_exposure": [{"player_id": pid, "name": name_by_id.get(pid, pid),
                             "lineups": appearances, "percent": 100 * appearances / count}
                            for pid, appearances in player_counts.most_common()],
        "game_exposure": [{"game_id": game, "lineups": appearances,
                           "percent": 100 * appearances / count}
                          for game, appearances in games.most_common()],
        "primary_game_exposure": [{"game": game, "lineups": appearances,
                                   "percent": 100 * appearances / count}
                                  for game, appearances in primary_games.most_common()],
        "overlap_matrix": [[len(set(left["player_ids"]) & set(right["player_ids"]))
                            for right in selected] for left in selected],
        "core_players": [name_by_id.get(pid, pid) for pid, appearances in player_counts.items()
                         if appearances == count],
        "constraints": constraints or {},
    }


def _position_ranks(players: Sequence[Player]) -> dict[str, dict]:
    by_position: dict[str, list[Player]] = defaultdict(list)
    for player in players:
        by_position[player.position].append(player)
    ranks: dict[str, dict] = {}
    for group in by_position.values():
        metrics = {
            "mean": lambda player: player.projection,
            "p90": lambda player: player.ceiling,
            "value": lambda player: player.ceiling / max(1.0, player.salary / 1000),
        }
        for metric, value in metrics.items():
            for rank, player in enumerate(sorted(group, key=lambda item: (-value(item), item.player_id)), 1):
                ranks.setdefault(player.player_id, {})[f"{metric}_rank"] = rank
    return ranks


def _concentration_rows(candidates: Sequence[dict], players: Sequence[Player],
                        source: dict[str, dict] | None = None,
                        ownership_available: bool = False,
                        candidate_aware_ownership: bool = False) -> list[dict]:
    by_id = {player.player_id: player for player in players}
    ranks = _position_ranks(players)
    frequencies = Counter(pid for row in candidates for pid in row["player_ids"])
    rows = []
    for player_id, frequency in frequencies.most_common(20):
        player = by_id[player_id]
        template_required = 0
        one_off = 0
        no_comparable_swap = 0
        correlated = 0
        for candidate in candidates:
            if player_id not in candidate["player_ids"]:
                continue
            qb = candidate["qb"]
            roster = candidate["roster"]
            template = candidate.get("generation_template") or [0, 0]
            same_team_catchers = [member for member in roster if member["team"] == qb["team"] and member["position"] in {"WR", "TE"}]
            opposing_skill = [member for member in roster if member["team"] == next((p.opponent for p in players if p.player_id == qb["player_id"]), "") and member["position"] in {"RB", "WR", "TE"}]
            if ((player.position in {"WR", "TE"} and player.team == qb["team"]
                 and len(same_team_catchers) <= template[0] and template[0] > 0)
                or (player.position in {"RB", "WR", "TE"} and player.team != qb["team"]
                    and player.team == next((p.opponent for p in players if p.player_id == qb["player_id"]), "")
                    and len(opposing_skill) <= template[1] and template[1] > 0)):
                template_required += 1
            if player.position != "QB" and player.team not in {qb["team"], next((p.opponent for p in players if p.player_id == qb["player_id"]), "")}:
                one_off += 1
            slack = 50000 - candidate["salary"]
            comparable = [other for other in players if other.player_id != player_id
                          and other.position == player.position
                          and other.salary <= player.salary + slack
                          and other.projection >= player.projection
                          and other.ceiling >= player.ceiling]
            no_comparable_swap += not comparable
            correlated += any(player_id in {str(member.get("player_id")) for member in rule.get("players", [])}
                              for rule in candidate.get("correlation_rules", []))
        evidence = (source or {}).get(str(player_id), {})
        rows.append({
            "player_id": player_id, "name": player.name, "position": player.position,
            "salary": player.salary, "mean": player.projection, "p90": player.ceiling,
            "p90_per_1k": player.ceiling / max(1.0, player.salary / 1000),
            **ranks[player_id], "frequency": frequency,
            "template_boundary_count": template_required,
            "one_off_count": one_off,
            "no_comparable_swap_count": no_comparable_swap,
            "correlation_rule_count": correlated,
            "role_importance": _number(evidence.get("offensive_role_importance")),
            "role_class": evidence.get("offensive_role_class"),
            "role_confidence": evidence.get("offensive_role_confidence"),
            "role_counterfactual": evidence.get("role_counterfactual_grid"),
            "role_completeness": _number(evidence.get("offensive_role_completeness")),
            "role_source": evidence.get("offensive_role_source"),
            "role_reason": evidence.get("offensive_role_reason"),
            "roster_status": evidence.get("roster_status"),
            "depth_chart_position": evidence.get("depth_chart_position"),
            "expected_snap_share": _number(evidence.get("snap_share_mean_3")),
            "recent_carries": _number(evidence.get("carries_mean_3")),
            "recent_targets": _number(evidence.get("targets_mean_3")),
            "target_share": _number(evidence.get("target_share_mean_3")),
            "rush_share": _number(evidence.get("carry_share_mean_3")),
            "expected_routes": _number(evidence.get("pregame_expected_routes")),
            "red_zone_share": _number(evidence.get("pregame_red_zone_share")),
            "goal_line_share": _number(evidence.get("pregame_goal_line_share")),
            "ownership": player.ownership if ownership_available or candidate_aware_ownership else None,
            "frequency_explanation": "Overlapping evidence counts, not causal attribution; a counterfactual candidate rebuild is required to isolate each factor",
        "candidate_generation_exposure_cap": 1.0,
            "salary_pressure_note": "Same-position, non-worse mean/P90 swaps within salary slack; indicative only",
        })
    return rows


def _qb_family_coverage(players: list[Player], config: Any, pool_by_id: dict[str, dict],
                        ownership_available: bool, game_totals: list[float],
                        enforce_single_te: bool, avoid_dst_opponents: bool,
                        candidate_aware_ownership: bool = False,
                        solver_backend: str = "bundled") -> list[dict]:
    """Solve exact QB/stack families as diagnostics, without changing candidate selection."""
    ranks = _position_ranks(players)
    qbs = [player for player in players if player.position == "QB"]
    qbs.sort(key=lambda player: (sum(ranks[player.player_id][f"{key}_rank"] for key in ("mean", "p90", "value")),
                                 -player.ceiling, player.player_id))
    tag_players(players, config.tag_thresholds)
    families = ((1, 0), (2, 0), (1, 1), (2, 1))
    output = []
    for qb in qbs[:10]:
        family_rows = []
        same_count = sum(p.team == qb.team and p.position in {"WR", "TE"} for p in players)
        back_count = sum(p.team == qb.opponent and p.position in {"RB", "WR", "TE"} for p in players)
        for partners, bring_backs in families:
            label = f"QB+{partners}" + ("+bring-back" if bring_backs else "")
            if same_count < partners or back_count < bring_backs:
                family_rows.append({"family": label, "score": None,
                    "reason": "insufficient eligible same-team receivers or opposing skill players"})
                continue
            rules = StackRules(**{**config.stack_rules.__dict__,
                "min_pass_catchers": partners, "min_bring_backs": bring_backs})
            indexes = _build_lineup(
                players, config, None, [], enforce_single_te=enforce_single_te,
                avoid_dst_opponents=avoid_dst_opponents, stack_rules=rules,
                required_player_ids={qb.player_id}, exact_pass_catchers=partners,
                exact_bring_backs=bring_backs,
                solver_backend=solver_backend,
            )
            if indexes is None:
                family_rows.append({"family": label, "score": None,
                    "reason": "no legal salary/roster/team/ownership-cap construction"})
                continue
            candidate = describe_candidate([players[index] for index in indexes], all_players=players,
                config=config, pool_by_id=pool_by_id, ownership_available=ownership_available,
                game_totals=game_totals, candidate_aware_ownership=candidate_aware_ownership)
            family_rows.append({"family": label, "score": candidate["objective_score"],
                "mean": candidate["mean"], "p90": candidate["p90"],
                "salary": candidate["salary"], "reason": "legal diagnostic solve"})
        output.append({"player_id": qb.player_id, "qb": qb.name, "salary": qb.salary,
            "mean": qb.projection, "p90": qb.ceiling,
            "p90_per_1k": qb.ceiling / max(1.0, qb.salary / 1000),
            **ranks[qb.player_id],
            "rushing": _rushing_qb(qb, pool_by_id.get(qb.player_id, {})),
            "families": family_rows})
    return output


def analyze_small_field(
    result: GPPOptimizerResult, *, pool_rows: Sequence[dict], count: int,
    max_exposure: float, ownership_available: bool, locked_player_ids: set[str] | None = None,
    maximum_exposure_by_player: dict[str, float] | None = None,
    minimum_exposure_by_player: dict[str, float] | None = None,
    requested_candidate_count: int = 120,
    strict_candidate_target: bool = False,
    run_qb_family_diagnostics: bool = False,
    enforce_single_te: bool = False,
    avoid_dst_opponents: bool = False,
    ownership_evidence: dict | None = None,
    candidate_aware_ownership: bool = False,
    discovery_diagnostics: dict | None = None,
    solver_backend: str = "bundled",
    refill_workers: int = 1,
    portfolio_constraints: dict | None = None,
    production_controls: dict | None = None,
) -> tuple[list[list[Player]], dict]:
    if portfolio_constraints is not None and not isinstance(portfolio_constraints, dict):
        raise ValueError("portfolio_constraints must be an object")
    portfolio_constraints = portfolio_constraints or {}
    supported = {"max_lineup_overlap", "distinct_qb_paths", "max_objective_loss"}
    unknown = set(portfolio_constraints) - supported
    if unknown:
        raise ValueError("Unknown Classic small-field portfolio constraints: " + ", ".join(sorted(unknown)))
    if not 1 <= refill_workers <= 4:
        raise ValueError("Classic refill workers must be between 1 and 4")
    if refill_workers > 1 and os.environ.get("PYTHONHASHSEED") != "0":
        raise ValueError("Parallel refill requires PYTHONHASHSEED=0 at process start")
    # The scoring normalizers must use the entire eligible pool, supplied by the caller.
    players = [row["gpp_player"] for row in pool_rows]
    source = {str(row["player_id"]): row for row in pool_rows}
    game_totals = sorted({float(p.game_total) for p in players if _number(p.game_total) is not None})
    candidates = [describe_candidate(lineup, all_players=players, config=result.config,
        pool_by_id=source, ownership_available=ownership_available, game_totals=game_totals,
        candidate_aware_ownership=candidate_aware_ownership)
        for lineup in result.lineups]
    for index, row in enumerate(candidates):
        templates = result.config.stack_templates
        row["generation_template"] = list(templates[index % len(templates)]) if templates else None
    if candidates:
        logs = sorted(row["log_ownership"] for row in candidates if row["log_ownership"] is not None)
        for row in candidates:
            if row["log_ownership"] is not None:
                row["relative_chalk"] = 100 * (logs.index(row["log_ownership"]) / max(1, len(logs) - 1))
    order = sorted(range(len(candidates)), key=lambda i: (-candidates[i]["objective_score"], -candidates[i]["mean"], i))
    candidates = [candidates[i] for i in order]
    lineups = [result.lineups[i] for i in order]
    for rank, row in enumerate(candidates, 1): row["rank"] = rank
    if discovery_diagnostics:
        sources = discovery_diagnostics["sources_by_lineup"]
        for row in candidates:
            row["discovery_sources"] = sources.get("|".join(sorted(row["player_ids"])), [])
    production_funnel = None
    selection_tradeoffs = None
    selected_caps = dict(maximum_exposure_by_player or {})
    if production_controls:
        policy = production_controls["policy"]
        elevated = {pid for pid, risk in production_controls["classifications"].items()
                    if risk["bucket"] == "questionable_elevated"}
        target_count = (requested_candidate_count if strict_candidate_target else
                        max(len(candidates), requested_candidate_count or 0))
        original_lineups = list(lineups)
        admission_started = perf_counter()
        candidates, lineups, production_funnel = _admit_candidate_caps(
            candidates, lineups, production_controls["candidate_caps"], elevated,
            target_count, policy["max_elevated_per_lineup"], solver_backend,
        )
        production_funnel["joint_admission_seconds"] = round(perf_counter() - admission_started, 3)
        production_funnel["initial_admitted"] = len(candidates)
        production_funnel["refill_attempts"] = 0
        production_funnel["refill_seconds"] = 0.0
        if len(candidates) < target_count:
            refill_started = perf_counter()
            refill_attempts = 0
            by_index = {player.player_id: index for index, player in enumerate(players)}
            excluded_rosters = [{by_index[player.player_id] for player in lineup}
                                for lineup in original_lineups]
            profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
            correlation_terms = build_lineup_correlation_terms(players, profile=profile)
            format_terms = build_format_specific_terms(players, profile=profile)
            candidate_counts = Counter(pid for row in candidates for pid in row["player_ids"])
            templates = result.config.stack_templates or ((result.config.stack_rules.min_pass_catchers,
                                                          result.config.stack_rules.min_bring_backs),)
            best_mean = max((row["mean"] for row in candidates), default=0)
            best_p90 = max((row["p90"] for row in candidates), default=0)
            stalled = 0
            context = dict(players=players, config=result.config,
                           correlation_terms=correlation_terms, format_terms=format_terms,
                           enforce_single_te=enforce_single_te,
                           avoid_dst_opponents=avoid_dst_opponents,
                           solver_backend=solver_backend)
            worker_pool = (ProcessPoolExecutor(
                max_workers=refill_workers, mp_context=get_context("spawn"),
                initializer=_initialize_refill_worker,
                initargs=(players, result.config, correlation_terms, format_terms,
                          enforce_single_te, avoid_dst_opponents, solver_backend),
            ) if refill_workers > 1 else nullcontext())
            with worker_pool as executor:
                while len(candidates) < target_count and stalled < len(templates):
                    remaining = {pid: floor(target_count * cap) - candidate_counts[pid]
                                 for pid, cap in production_controls["candidate_caps"].items()}
                    batch_size = min(refill_workers, len(templates), target_count - len(candidates))
                    requests = [
                        (templates[(len(candidates) + stalled + offset) % len(templates)],
                         remaining, list(excluded_rosters),
                         best_mean - policy["min_mean_from_best"],
                         best_p90 - policy["min_p90_from_best"],
                         elevated, policy["max_elevated_per_lineup"])
                        for offset in range(batch_size)
                    ]
                    refill_attempts += len(requests)
                    solved = (list(executor.map(_solve_refill_request, requests)) if executor
                              else [_solve_refill_request(request, context) for request in requests])
                    for request, indexes in zip(requests, solved):
                        if indexes is None:
                            stalled += 1
                            production_funnel["rejected_by_family_constraint"] += 1
                            continue
                        production_funnel["solved"] += 1
                        production_funnel["legal"] += 1
                        roster_indexes = set(indexes)
                        if roster_indexes in excluded_rosters:
                            stalled += 1
                            production_funnel["duplicate"] += 1
                            continue
                        excluded_rosters.append(roster_indexes)
                        lineup = [players[index] for index in indexes]
                        ids = {player.player_id for player in lineup}
                        if any(candidate_counts[pid] >= floor(target_count * production_controls["candidate_caps"].get(pid, 1.0))
                               for pid in ids):
                            stalled += 1
                            production_funnel["rejected_by_player_cap"] += 1
                            continue
                        stalled = 0
                        row = describe_candidate(lineup, all_players=players, config=result.config,
                                                 pool_by_id=source, ownership_available=ownership_available,
                                                 game_totals=game_totals,
                                                 candidate_aware_ownership=candidate_aware_ownership)
                        row["generation_template"] = list(request[0])
                        row["discovery_sources"] = ["production_cap_refill"]
                        candidates.append(row)
                        lineups.append(lineup)
                        candidate_counts.update(row["player_ids"])
                        if len(candidates) >= target_count:
                            break
            production_funnel["refill_attempts"] = refill_attempts
            production_funnel["refill_seconds"] = round(perf_counter() - refill_started, 3)
            production_funnel["refill_workers"] = refill_workers
            # A failed constrained search is reported, never answered by relaxing a cap.
            production_funnel["accepted"] = len(candidates)
            production_funnel["remaining_deficit"] = target_count - len(candidates)
            production_funnel["status"] = (
                "CANDIDATE_POOL_UNDERFILLED" if len(candidates) < target_count else "complete"
            )
            if candidates:
                ordered = sorted(zip(candidates, lineups),
                                 key=lambda pair: -pair[0]["objective_score"])
                candidates = [row for row, _ in ordered]
                lineups = [lineup for _, lineup in ordered]
        for rank, row in enumerate(candidates, 1):
            row["rank"] = rank
        for player in players:
            pid = player.player_id
            if pid in (locked_player_ids or set()):
                continue
            if player.position == "QB":
                selected_caps[pid] = min(selected_caps.get(pid, 1.0), 0.60)
            elif player.position in {"RB", "WR", "TE"} and production_controls["core_classes"][pid] != "elite_high_confidence":
                selected_caps[pid] = min(selected_caps.get(pid, 1.0), 0.80)
    def select(*, paths: int = 1, families: int = 1) -> list[int]:
        return _select_global(
            candidates, count, max_exposure, locked_player_ids or set(),
            selected_caps, minimum_exposure_by_player or {},
            solver_backend=solver_backend,
            max_lineup_overlap=(6 if production_controls else portfolio_constraints.get("max_lineup_overlap")),
            distinct_qb_paths=portfolio_constraints.get("distinct_qb_paths", False),
            max_objective_loss=portfolio_constraints.get("max_objective_loss"),
            max_lineups_with_any_player_ids=(
                (elevated, policy["selected_lineups_with_elevated_cap"])
                if production_controls and elevated else None
            ),
            enforce_maximum_for_locked_ids=(
                {pid for pid, risk in production_controls["classifications"].items()
                 if risk["bucket"].startswith("questionable")}
                if production_controls else None
            ),
            minimum_qb_paths=paths, minimum_stack_families=families,
        ) if len(candidates) >= count else []
    selected_indices = select(paths=2 if production_controls and count > 1 else 1)
    if production_controls and selected_indices:
        baseline_score = sum(candidates[i]["objective_score"] for i in selected_indices)
        tolerance = float(production_controls.get("quality_loss_tolerance", 0.10)) * count
        path_frontier = {}
        for paths in (1, 2, 3):
            indexes = select(paths=paths) if paths <= count else []
            rows = [candidates[i] for i in indexes]
            path_frontier[str(paths)] = {
                "feasible": bool(indexes), "selector_sum": sum(row["objective_score"] for row in rows),
                "mean_sum": sum(row["mean"] for row in rows),
                "p90_sum": sum(row["p90"] for row in rows),
                "max_overlap": max((len(set(left["player_ids"]) & set(right["player_ids"]))
                                    for i, left in enumerate(rows) for right in rows[i + 1:]), default=0),
            }
        third = select(paths=3) if count >= 3 else []
        if third and baseline_score - sum(candidates[i]["objective_score"] for i in third) <= tolerance:
            selected_indices = third
        family_alternative = select(paths=3 if selected_indices == third and third else 2, families=2)
        family_cost = (sum(candidates[i]["objective_score"] for i in selected_indices)
                       - sum(candidates[i]["objective_score"] for i in family_alternative)) if family_alternative else None
        if family_alternative and family_cost <= tolerance:
            selected_indices = family_alternative
        selection_tradeoffs = {"quality_loss_tolerance_per_lineup": tolerance / count,
                               "path_frontier": path_frontier,
                               "alternative_stack_family_selector_cost": family_cost,
                               "selected_stack_family_count": len({candidates[i]["stack"]["type"]
                                                                   for i in selected_indices})}
    selected = [lineups[i] for i in selected_indices]
    best_mean = max((row["mean"] for row in candidates), default=0)
    best_p90 = max((row["p90"] for row in candidates), default=0)
    best_quality = max(candidates, key=lambda row: row["components"]["mean"] + row["components"]["p90"]) if candidates else None
    for row in candidates:
        row["mean_loss_vs_best"] = best_mean - row["mean"]
        row["p90_loss_vs_best"] = best_p90 - row["p90"]
        row["mean_loss_vs_global_highest"] = row["mean_loss_vs_best"]
        row["p90_loss_vs_global_highest"] = row["p90_loss_vs_best"]
        baseline = best_quality["components"] if best_quality else {}
        raw_loss = ((baseline.get("mean", 0.0) + baseline.get("p90", 0.0))
                    - (row["components"]["mean"] + row["components"]["p90"]))
        bonus_keys = ("context", "qb_stack", "bring_back", "game_environment", "correlation")
        bonus_gain = sum(row["components"].get(key, 0.0) - baseline.get(key, 0.0)
                         for key in bonus_keys)
        row["correlation_context_objective_gain"] = bonus_gain
        row["raw_objective_quality_sacrifice"] = raw_loss
        row["raw_sacrifice_per_bonus_gain"] = raw_loss / bonus_gain if bonus_gain > 0 else None
        row["chalk_improvement_vs_best_quality"] = (
            best_quality["relative_chalk"] - row["relative_chalk"]
            if best_quality and row["relative_chalk"] is not None and best_quality["relative_chalk"] is not None else None
        )
        row["ownership_objective_gain_vs_best_quality"] = 0.0  # ownership is a cap, not a soft term
        row["large_ceiling_sacrifice_for_chalk"] = bool(
            row["p90_loss_vs_best"] >= 5 and (row["chalk_improvement_vs_best_quality"] or 0) >= 20
        )
    quality_guards = {}
    for metric, gaps in (("mean", (3, 4, 5, 6, 7)), ("p90", (3, 5, 7))):
        for gap in gaps:
            legal = [row for row in candidates
                     if row[f"{metric}_loss_vs_best"] <= gap + 1e-9]
            winner = max(legal, key=lambda row: row["objective_score"], default=None)
            quality_guards[f"{metric}_within_{gap}"] = (
                {"rank": winner["rank"], "player_ids": winner["player_ids"],
                 "mean": winner["mean"], "p90": winner["p90"],
                 "selector": winner["objective_score"]}
                if winner else None
            )
    top_qbs = Counter(row["qb"]["name"] for row in candidates)
    qb_summary = [{"qb": name, "candidate_frequency": frequency,
        "average_score": sum(row["objective_score"] for row in candidates if row["qb"]["name"] == name) / frequency,
        "best_score": max(row["objective_score"] for row in candidates if row["qb"]["name"] == name)}
        for name, frequency in top_qbs.most_common()]
    families = []
    for qb_row in sorted(qb_summary, key=lambda row: -row["best_score"])[:5]:
        family_rows = [row for row in candidates if row["qb"]["name"] == qb_row["qb"]]
        families.append({"qb": qb_row["qb"], "best_by_stack": [next((row["rank"] for row in family_rows if row["stack"]["type"] == kind), None)
            for kind in ("QB+1", "QB+2", "QB+2+bring-back", "QB+3")]})
    def exposures(rows: Sequence[dict]) -> dict[str, int]:
        return dict(Counter(player["name"] for row in rows for player in row["roster"]).most_common())
    candidate_counts = Counter(
        str(player["player_id"])
        for row in candidates for player in row["roster"]
    )
    selected_counts = Counter(
        str(player.player_id)
        for lineup in selected for player in lineup
    )
    def portfolio_metrics(indexes: Sequence[int]) -> dict:
        rows = [candidates[index] for index in indexes]
        return {"selector_sum": sum(row["objective_score"] for row in rows),
                "mean_sum": sum(row["mean"] for row in rows),
                "p90_sum": sum(row["p90"] for row in rows),
                "max_overlap": max((len(set(left["player_ids"]) & set(right["player_ids"]))
                                    for i, left in enumerate(rows) for right in rows[i + 1:]), default=0),
                "qb_paths": sorted({row["qb"]["name"] for row in rows}),
                "selected_ranks": [row["rank"] for row in rows]}
    skill_exposure_approvals = []
    if production_controls and len(selected) > 1:
        original_metrics = portfolio_metrics(selected_indices)
        current_qb_paths = len({str(candidates[i]["qb"]["player_id"]) for i in selected_indices})
        current_families = len({candidates[i]["stack"]["type"] for i in selected_indices})
        elevated_ids = {pid for pid, risk in production_controls["classifications"].items()
                        if risk["bucket"] == "questionable_elevated"}
        for player in players:
            pid = str(player.player_id)
            if player.position not in {"RB", "WR", "TE"} or selected_counts[pid] != len(selected):
                continue
            caps = {**selected_caps, pid: min(selected_caps.get(pid, 1.0), .80)}
            alternative_indexes = _select_global(
                candidates, len(selected), max_exposure, locked_player_ids or set(),
                caps, minimum_exposure_by_player or {}, solver_backend=solver_backend,
                max_lineup_overlap=6,
                max_lineups_with_any_player_ids=(
                    (elevated_ids, production_controls["policy"]["selected_lineups_with_elevated_cap"])
                    if elevated_ids else None),
                enforce_maximum_for_locked_ids={pid},
                minimum_qb_paths=current_qb_paths,
                minimum_stack_families=current_families,
            )
            alternative = portfolio_metrics(alternative_indexes) if alternative_indexes else None
            evidence = source.get(pid, {})
            skill_exposure_approvals.append({
                "player_id": pid, "player": player.name, "position": player.position,
                "selected_count": selected_counts[pid], "selected_total": len(selected),
                "mean": player.projection, "p90": player.ceiling, "salary": player.salary,
                "value": player.projection / max(1.0, player.salary / 1000),
                "ownership": player.ownership, "core_classification": production_controls["core_classes"].get(pid),
                "availability": production_controls["classifications"].get(pid, {}).get("bucket"),
                "candidate_count": candidate_counts[pid], "candidate_total": len(candidates),
                "original": original_metrics, "capped_80": alternative,
                "selector_cost": (original_metrics["selector_sum"] - alternative["selector_sum"]
                                  if alternative else None),
                "mean_cost": (original_metrics["mean_sum"] - alternative["mean_sum"]
                              if alternative else None),
                "p90_cost": (original_metrics["p90_sum"] - alternative["p90_sum"]
                             if alternative else None),
                "note": "The optimizer prefers 100% exposure. Here is the cost of reducing it.",
            })
    for row in candidates:
        row["football_sanity"] = _football_sanity(
            row, players=players, source=source, candidate_counts=candidate_counts,
            selected_counts=selected_counts, candidate_total=len(candidates),
            selected_total=len(selected), candidates=candidates,
        )
    from .rb_dst_diagnostics import build_rb_dst_diagnostics
    rb_dst_diagnostics = build_rb_dst_diagnostics(candidates, selected_indices, source)
    role_exposure = []
    for player in players:
        evidence = source.get(str(player.player_id), {})
        importance = _number(evidence.get("offensive_role_importance"))
        if player.position not in {"RB", "WR", "TE"}:
            continue
        ownership = _number(evidence.get("ownership"))
        role_exposure.append({
            "player_id": str(player.player_id), "name": player.name,
            "team": player.team, "position": player.position,
            "importance": importance,
            "role_class": evidence.get("offensive_role_class"),
            "role_confidence": evidence.get("offensive_role_confidence"),
            "role_counterfactual": evidence.get("role_counterfactual_grid"),
            "mean": float(player.projection), "p90": float(player.ceiling),
            "salary": int(player.salary),
            "opportunity_validation": {
                "recent_targets_mean_3": _number(evidence.get("targets_mean_3")),
                "recent_carries_mean_3": _number(evidence.get("carries_mean_3")),
                "projected_targets_proxy": _number(evidence.get("projected_targets")),
                "projected_carries_proxy": _number(evidence.get("projected_carries")),
                "targets_proxy_minus_recent": (
                    _number(evidence.get("projected_targets")) - _number(evidence.get("targets_mean_3"))
                    if _number(evidence.get("projected_targets")) is not None
                    and _number(evidence.get("targets_mean_3")) is not None else None
                ),
                "carries_proxy_minus_recent": (
                    _number(evidence.get("projected_carries")) - _number(evidence.get("carries_mean_3"))
                    if _number(evidence.get("projected_carries")) is not None
                    and _number(evidence.get("carries_mean_3")) is not None else None
                ),
                "source": evidence.get("projected_opportunity_source") or "unavailable",
                "context_adjusted": evidence.get("pregame_opportunity_context_applied") is True,
                "point_model_context": {
                    "game_total": _number(evidence.get("game_total_line")),
                    "team_spread": _number(evidence.get("team_spread_line")),
                    "team_implied_total": _number(evidence.get("team_implied_total")),
                    "effect": "inputs enter nonlinear mean model; separate point effect unavailable",
                },
                "note": "Lagged team-volume allocation proxy, not an independent forward opportunity forecast",
            },
            "role_trend": {
                key: _number(evidence.get(key)) for key in (
                    "snap_share_last", "snap_share_prior3", "snap_share_trend",
                    "target_share_last", "target_share_prior3", "target_share_trend",
                    "rush_share_last", "rush_share_prior3", "rush_share_trend",
                )
            },
            "mean_per_1000_salary": float(player.projection) / max(1.0, player.salary / 1000),
            "ownership": ownership if ownership_available else None,
            "candidate_count": candidate_counts[str(player.player_id)],
            "candidate_rate": candidate_counts[str(player.player_id)] / max(1, len(candidates)),
            "selected_count": selected_counts[str(player.player_id)],
            "selected_rate": selected_counts[str(player.player_id)] / max(1, len(selected)),
            "sanity_flag": (
                "measured central role absent from selected lineups; inspect construction and value"
                if evidence.get("offensive_role_confidence") in {"medium", "high"}
                and evidence.get("offensive_role_class") in {"offensive centerpiece", "primary option"}
                and selected_counts[str(player.player_id)] == 0 and selected else
                "measured low-opportunity role selected; inspect current opportunity evidence"
                if evidence.get("offensive_role_confidence") in {"medium", "high"}
                and evidence.get("offensive_role_class") == "low-opportunity player"
                and selected_counts[str(player.player_id)] > 0 else None
            ),
        })
    role_exposure.sort(key=lambda row: (
        row["importance"] is None, -(row["importance"] or 0), row["team"], row["name"]
    ))
    team_reconciliation = _team_reconciliation(players, source)
    selected_rank_set = {candidates[index]["rank"] for index in selected_indices}
    report = {
        "candidate_count": len(candidates), "requested_candidate_count": requested_candidate_count,
        "production_funnel": production_funnel,
        "production_controls": ({"mode": production_controls.get("mode"),
                                 "policy": production_controls.get("policy"),
                                 "candidate_caps": production_controls.get("candidate_caps"),
                                 "core_classes": production_controls.get("core_classes"),
                                 "overrides": production_controls.get("overrides"),
                                 "selection_tradeoffs": selection_tradeoffs}
                                if production_controls else None),
        "candidate_discovery": discovery_diagnostics,
        "pregame_coverage": None,
        "quality_guard_frontier": quality_guards,
        "quality_guard_frontier_scope": "expanded_candidate_universe",
        "candidate_pool_warning": (
            f"Only {len(candidates)} legal candidates were generated; the initial baseline requires at least 100."
            if len(candidates) < 100 else None
        ),
        "selected_count": len(selected), "selected_ranks": [candidates[i]["rank"] for i in selected_indices],
        "skill_exposure_approvals": skill_exposure_approvals,
        "selected_portfolio": portfolio_summary(
            [candidates[i] for i in selected_indices], candidate_count=len(candidates),
            constraints=portfolio_constraints),
        "scoring_config": {"weights": vars(result.config.objective_weights), "correlation_bonus": result.config.correlation_bonus,
            "ownership_policy": ("candidate-complete ownership diagnostics; zero soft ownership contribution"
                                 if candidate_aware_ownership else
                                 "hard chalk/ownership caps; zero soft ownership contribution"),
            "chalk_count_cap": result.config.tag_caps.max_chalk,
            "total_ownership_cap": result.config.tag_caps.max_total_ownership,
            "minimum_leverage_count": result.config.tag_caps.min_leverage,
            "maximum_punts": result.config.tag_caps.max_punts,
            "stack_templates": result.config.stack_templates},
        "top_20": candidates[:20], "top_50": candidates[:50],
        "all_candidates": candidates,
        "highest_p90_candidates_omitted": [
            {"rank": row["rank"], "qb": row["qb"]["name"], "mean": row["mean"],
             "p90": row["p90"], "objective_score": row["objective_score"],
             "stack_family": row["stack"]["type"]}
            for row in sorted(candidates, key=lambda candidate: -candidate["p90"])
            if row["rank"] not in selected_rank_set
        ][:10],
        "serialized_candidate_count": len(candidates),
        "top_qbs": qb_summary, "stack_types": dict(Counter(row["stack"]["type"] for row in candidates)),
        "primary_games_top_20": dict(Counter(row["primary_game"] for row in candidates[:20])),
        "player_exposures": {"top_20": exposures(candidates[:20]), "top_50": exposures(candidates[:50]), "entire_pool": exposures(candidates)},
        "role_exposure": role_exposure,
        "rb_dst_diagnostics": rb_dst_diagnostics,
        "role_projection_anomalies": _role_projection_anomalies(
            players, source, candidate_counts, len(candidates)
        ),
        "role_evidence_summary": {
            "eligible_skill_players": len(role_exposure),
            "measured_role_players": sum(row["importance"] is not None for row in role_exposure),
            "missing_by_team": {row["team"]: row["missing_role_players"]
                                for row in team_reconciliation
                                if row["missing_role_players"]},
        },
        "historical_role_calibration": next(
            (row.get("historical_role_calibration") for row in source.values()
             if isinstance(row.get("historical_role_calibration"), dict)),
            {"status": "unavailable", "reason": "selected projection has no role-class calibration history"},
        ),
        "selected_football_sanity": [candidates[index]["football_sanity"] for index in selected_indices],
        "candidate_families": families,
        "opportunity_gate": {
            "evaluated_stage": "Classic strategy candidate filter after the raw opportunity-eligible counter",
            "surviving_pool_size": len(pool_rows),
            "candidate_low_cost_skill_evidence": dict(Counter(
                _opportunity(source[member["player_id"]])["evidence_class"]
                for row in candidates for member in row["roster"]
                if member["position"] in {"RB", "WR", "TE"} and member["salary"] <= 4500
            )),
            "retention_rule": "Existing Showdown low-salary fallback; missing role fields do not imply zero opportunity",
        },
        "ownership_evidence": {
            **(ownership_evidence or {"status": "available" if ownership_available else "unavailable",
                                     "source": "target.ownership_projection"}),
            "candidate_complete_count": sum(row["ownership_sum"] is not None for row in candidates),
            "candidate_incomplete_count": sum(row["ownership_sum"] is None for row in candidates),
        },
        "concentration": _concentration_rows(candidates, players, source, ownership_available,
                                                candidate_aware_ownership),
        "team_reconciliation": team_reconciliation,
        "qb_family_coverage": (_qb_family_coverage(players, result.config, source, ownership_available,
            game_totals, enforce_single_te, avoid_dst_opponents,
            candidate_aware_ownership, solver_backend) if run_qb_family_diagnostics else []),
        "note": ("Expanded discovery injects global raw-quality, selector, and exact QB-family lineups before global selection. Candidate-complete ownership is reported separately; the fixed football objective has no soft ownership term."
                 if candidate_aware_ownership else
                 "Candidate generation uses existing Classic large-GPP weights and flexible stack templates; final selection maximizes their score globally under the configured exposure cap. Ownership affects feasibility through existing caps and leverage evidence, not a new soft chalk penalty."),
    }
    from .optimizer_coverage import pregame_coverage
    report["pregame_coverage"] = pregame_coverage(candidates, report["selected_ranks"], [
        {**row, "included": True} for row in pool_rows
    ])
    report["generation_funnel"] = {
        "eligible_player_pool": len(pool_rows),
        "sequential_unique": (discovery_diagnostics or {}).get("sequential_count", len(result.lineups)),
        "expanded_unique": len(candidates), "saved_candidates": len(candidates),
        "selected": len(selected),
        "discovery_attempts": len((discovery_diagnostics or {}).get("injections", [])),
        "discovery_infeasible": sum(row.get("status") == "infeasible" for row in
                                     (discovery_diagnostics or {}).get("injections", [])),
        "theoretical_legal_count": None,
        "note": "The solver does not enumerate all legal rosters. No quality-floor or pruning stage follows expanded discovery.",
    }
    return selected, report
