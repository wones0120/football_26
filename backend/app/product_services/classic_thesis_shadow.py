"""Pregame-only thesis analysis of a saved Classic small-field candidate universe.

This module reads frozen optimizer evidence. It never changes production selection.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime
from math import ceil, floor
from statistics import mean
from typing import Any, Mapping, Sequence

import pulp

from .cbc_solver import make_cbc_solver, resolve_cbc_backend
from .classic_prospective import digest_payload, validate_solver_snapshot


CONTRACT = "classic_dynamic_thesis_shadow_v3"
TOLERANCES = (0.05, 0.10, 0.15, 0.20)
PORTFOLIO_SIZES = (1, 3, 5, 10, 20)


def canonical_game(game_id: str | None, qb_team: str, opponent: str) -> dict[str, str]:
    """Keep one game key for opposite QB directions; retain sourced away/home display."""
    teams = tuple(sorted((qb_team.upper(), opponent.upper())))
    if not all(teams) or teams[0] == teams[1]:
        raise ValueError("A thesis requires two distinct canonical teams")
    matchup = (game_id or "").split(" ", 1)[0].upper().replace("–", "-")
    away_home = matchup.split("@")
    if len(away_home) == 2 and set(away_home) == set(teams):
        display = f"{away_home[0]}@{away_home[1]}"
    else:
        display = f"{teams[0]}–{teams[1]}"
    return {"key": "|".join(teams), "display": display}


def _candidate_view(row: Mapping[str, Any], pool_by_id: Mapping[str, Mapping[str, Any]],
                    risk_by_id: Mapping[str, Mapping[str, Any]]) -> dict:
    qb = row["qb"]
    qb_id = str(qb["player_id"])
    qb_source = pool_by_id.get(qb_id)
    if not qb_source:
        raise ValueError(f"Candidate QB {qb_id} is absent from frozen pool")
    game = canonical_game(qb_source.get("game_id"), str(qb["team"]),
                          str(qb_source.get("opponent_team") or ""))
    stack = row.get("stack") or {}
    partners = int(stack.get("partner_count") or 0)
    bringbacks = int(stack.get("bring_back_count") or 0)
    if partners < 1:
        raise ValueError("Classic thesis candidate has no QB stack partner")
    family_id = f"{game['key']}|{qb_id}|QB+{partners}|BB{int(bringbacks > 0)}"
    player_ids = sorted(str(value) for value in row["player_ids"])
    if len(player_ids) != 9 or len(set(player_ids)) != 9:
        raise ValueError("Classic thesis candidate must contain nine canonical players")
    elevated = [pid for pid in player_ids
                if risk_by_id.get(pid, {}).get("bucket") == "questionable_elevated"]
    questionable = [pid for pid in player_ids
                    if str(risk_by_id.get(pid, {}).get("bucket", "")).startswith("questionable")]
    evidence_gaps = [pid for pid in player_ids if risk_by_id.get(pid, {}).get("evidence_gap")]
    cheap_fragile = [pid for pid in player_ids
                     if (source := pool_by_id.get(pid)) and source.get("position") in {"RB", "WR", "TE"}
                     and source.get("salary") is not None and float(source["salary"]) <= 4500
                     and (source.get("pregame_role_uncertain") is True
                          or not any(source.get(key) is not None for key in
                                     ("pregame_expected_routes", "pregame_expected_targets",
                                      "pregame_expected_carries")))]
    environment = row.get("game_environment") or {}
    market_safe = environment.get("market_safe") is True and bool(qb_source.get("market_source_system"))
    roster = {str(player["player_id"]): {
        "name": player.get("name"), "position": player.get("position"),
        "team": player.get("team"), "salary": player.get("salary")}
        for player in row.get("roster") or []}
    return {
        "rank": int(row["rank"]), "player_ids": player_ids, "roster": roster,
        "thesis_id": family_id, "game_key": game["key"], "game": game["display"],
        "qb_id": qb_id, "qb": qb["name"], "qb_team": qb["team"],
        "stack_family": f"QB+{partners}", "partner_count": partners,
        "bring_back_count": bringbacks,
        "bring_back_roles": sorted(str(item.get("position")) for item in stack.get("bring_backs") or []),
        "bring_back_player_ids": sorted(str(item.get("player_id")) for item in
                                        stack.get("bring_back_evaluations") or [] if item.get("player_id")),
        "market_archetype": environment.get("label") if market_safe else None,
        "market_evidence": {"source": qb_source.get("market_source_system"),
                            "observed_at": qb_source.get("market_observed_at"),
                            "total": environment.get("game_total"),
                            "team_spread": environment.get("team_spread")} if market_safe else None,
        "selector": float(row["objective_score"]), "mean": float(row["mean"]),
        "p90": float(row["p90"]), "salary": int(row["salary"]),
        "questionable_ids": questionable, "elevated_ids": elevated,
        "availability_evidence_gap_ids": evidence_gaps,
        "fragile_cheap_ids": cheap_fragile,
        "ownership_complete": row.get("ownership_sum") is not None,
        "active_components": sorted(key for key, state in (row.get("component_statuses") or {}).items()
                                    if state.get("status") == "ACTIVE"),
        "components": {key: float(value) for key, value in (row.get("components") or {}).items()
                       if value is not None},
    }


def _family_metrics(rows: Sequence[dict], global_rows: Sequence[dict], best_score: float) -> dict:
    ordered = sorted(rows, key=lambda row: (-row["selector"], row["rank"]))
    best = ordered[0]
    top_counts = {f"top_{fraction}%": sum(row["rank"] <= ceil(len(global_rows) * fraction / 100)
                                                for row in rows) for fraction in (5, 10, 20)}
    near = {f"within_{tolerance:.2f}": sum(best_score - row["selector"] <= tolerance + 1e-9
                                            for row in rows) for tolerance in TOLERANCES}
    def nth(index: int) -> dict | None:
        return ordered[index - 1] if len(ordered) >= index else None
    def drop(index: int, key: str) -> float | None:
        return round(best[key] - ordered[index - 1][key], 6) if len(ordered) >= index else None
    return {
        "thesis_id": best["thesis_id"], "game_key": best["game_key"], "game": best["game"],
        "qb_id": best["qb_id"], "qb": best["qb"], "qb_team": best["qb_team"],
        "stack_family": best["stack_family"], "bring_back_presence": bool(best["bring_back_count"]),
        "bring_back_count_distribution": dict(sorted(Counter(row["bring_back_count"] for row in rows).items())),
        "bring_back_roles": sorted({role for row in rows for role in row["bring_back_roles"]}),
        "bring_back_player_ids": sorted({pid for row in rows for pid in row["bring_back_player_ids"]}),
        "market_archetype": best["market_archetype"], "market_evidence": best["market_evidence"],
        "member_ranks": [row["rank"] for row in ordered], "count": len(rows),
        "peak_selector": best["selector"], "peak_mean": max(row["mean"] for row in rows),
        "peak_p90": max(row["p90"] for row in rows), "best_rank": min(row["rank"] for row in rows),
        "global_selector_gap": round(best_score - best["selector"], 6),
        "depth": {**near, **top_counts,
                  "ranks": {str(n): nth(n)["rank"] if nth(n) else None for n in (1, 2, 3, 5)},
                  "selector_drop_to_3": drop(3, "selector"), "selector_drop_to_5": drop(5, "selector"),
                  "mean_drop_to_3": drop(3, "mean"), "mean_drop_to_5": drop(5, "mean"),
                  "p90_drop_to_3": drop(3, "p90"), "p90_drop_to_5": drop(5, "p90")},
        "best_k": {str(k): {"count": min(k, len(ordered)),
                             "mean": mean(row["mean"] for row in ordered[:k]),
                             "p90": mean(row["p90"] for row in ordered[:k])}
                   for k in (1, 3, 5)},
        "risk": {"questionable_candidate_rate": sum(bool(row["questionable_ids"]) for row in rows) / len(rows),
                 "elevated_candidate_rate": sum(bool(row["elevated_ids"]) for row in rows) / len(rows),
                 "best_elevated_dependencies": len(best["elevated_ids"]),
                 "best_availability_evidence_gaps": len(best["availability_evidence_gap_ids"]),
                 "best_fragile_cheap_dependencies": len(best["fragile_cheap_ids"]),
                 "ownership_complete_rate": sum(row["ownership_complete"] for row in rows) / len(rows)},
        "structure": {"stack_partner_count": best["partner_count"],
                      "best_bring_back_count": best["bring_back_count"],
                      "best_active_components": best["active_components"],
                      "best_context_component": best["components"].get("context"),
                      "best_correlation_component": best["components"].get("correlation")},
    }


def _dominance(families: Sequence[dict]) -> None:
    """Annotate strict Pareto dominance on predeclared quality, depth and risk axes."""
    axes = (("peak_selector", 1), ("peak_mean", 1), ("peak_p90", 1))
    for target in families:
        target["dominated_by"] = []
        for other in families:
            if other is target:
                continue
            comparisons = [(other[key] - target[key]) * direction for key, direction in axes]
            comparisons += [other["depth"]["within_0.10"] - target["depth"]["within_0.10"],
                            target["risk"]["best_elevated_dependencies"] - other["risk"]["best_elevated_dependencies"],
                            target["risk"]["best_availability_evidence_gaps"] - other["risk"]["best_availability_evidence_gaps"],
                            other["risk"]["ownership_complete_rate"] - target["risk"]["ownership_complete_rate"]]
            if all(value >= -1e-8 for value in comparisons) and any(value > 1e-8 for value in comparisons):
                target["dominated_by"].append(other["thesis_id"])
        target["pareto_status"] = "dominated" if target["dominated_by"] else "frontier"
        target["frontier_reasons"] = [] if target["dominated_by"] else [
            name for name, key, maximize in (
                ("selector peak", "peak_selector", True), ("projected mean peak", "peak_mean", True),
                ("summed P90 peak", "peak_p90", True))
            if abs(target[key] - (max(row[key] for row in families) if maximize else min(row[key] for row in families))) < 1e-8
        ]
        if not target["dominated_by"] and not target["frontier_reasons"]:
            target["frontier_reasons"] = ["No thesis is at least as good on every quality, depth, and risk axis"]


def _overlap(left: Mapping[str, Any], right: Mapping[str, Any]) -> int:
    return len(set(left["player_ids"]) & set(right["player_ids"]))


def forced_candidate_swap_feasible(forced_ids: set[str], candidates: Sequence[dict],
                                   candidate_caps: Mapping[str, float]) -> bool:
    """Can a full fixed-size pool admit one forced roster by replacing one row?"""
    counts = Counter(str(pid) for row in candidates for pid in row["player_ids"])
    total = len(candidates)
    for row in candidates:
        removed = set(str(pid) for pid in row["player_ids"])
        if removed == forced_ids:
            continue
        if all(counts[pid] - (pid in removed) + (pid in forced_ids)
               <= floor(total * float(candidate_caps.get(pid, 1.0)) + 1e-9)
               for pid in removed | forced_ids):
            return True
    return False


def _overlap_summary(rows: Sequence[dict]) -> dict:
    within, across = [], []
    for i, left in enumerate(rows):
        for right in rows[i + 1:]:
            (within if left["thesis_id"] == right["thesis_id"] else across).append(_overlap(left, right))
    return {"within_average": mean(within) if within else None,
            "within_max": max(within) if within else None,
            "within_pairs": len(within), "across_average": mean(across) if across else None,
            "across_max": max(across) if across else None, "across_pairs": len(across)}


def _portfolio_summary(rows: Sequence[dict], candidate_count: int, *, status: str,
                       tolerance: float | None, overlap_cap: int | None) -> dict:
    rows = sorted(rows, key=lambda row: row["rank"])
    return {
        "status": status, "entries": len(rows), "quality_tolerance": tolerance,
        "max_overlap_constraint": overlap_cap,
        "selected_ranks": [row["rank"] for row in rows],
        "selector_sum": sum(row["selector"] for row in rows),
        "mean_sum": sum(row["mean"] for row in rows), "p90_sum": sum(row["p90"] for row in rows),
        "lineups": [{"rank": row["rank"], "thesis_id": row["thesis_id"],
                     "qb": row["qb"], "game": row["game"], "stack_family": row["stack_family"],
                     "bring_back_count": row["bring_back_count"], "player_ids": row["player_ids"],
                     "selector": row["selector"], "mean": row["mean"], "p90": row["p90"],
                     "elevated_ids": row["elevated_ids"]} for row in rows],
        "thesis_allocation": dict(sorted(Counter(row["thesis_id"] for row in rows).items())),
        "directional_qb_exposure": dict(sorted(Counter(row["qb"] for row in rows).items())),
        "canonical_game_exposure": dict(sorted(Counter(row["game"] for row in rows).items())),
        "player_exposure": dict(sorted(Counter(pid for row in rows for pid in row["player_ids"]).items())),
        "stack_family_exposure": dict(sorted(Counter(row["stack_family"] for row in rows).items())),
        "questionable_lineups": sum(bool(row["questionable_ids"]) for row in rows),
        "elevated_lineups": sum(bool(row["elevated_ids"]) for row in rows),
        "overlap": _overlap_summary(rows), "candidate_count": candidate_count,
    }


def _solve_portfolio(rows: Sequence[dict], families: Mapping[str, dict], count: int,
                     player_caps: Mapping[str, float], elevated_lineup_cap: float,
                     overlap_cap: int) -> tuple[list[dict], str]:
    """Joint lexicographic ILP: frontier coverage, games, then existing selector."""
    if len(rows) < count:
        return [], "too_few_quality_candidates"
    model = pulp.LpProblem("classic_thesis_shadow", pulp.LpMaximize)
    x = pulp.LpVariable.dicts("candidate", range(len(rows)), cat="Binary")
    model += pulp.lpSum(x.values()) == count
    for pid in sorted({pid for row in rows for pid in row["player_ids"]}):
        cap = max(1, floor(count * float(player_caps.get(pid, 1.0))))
        if pid in {pid for row in rows for pid in row["elevated_ids"]}:
            cap = floor(count * float(player_caps.get(pid, 0.4)))
        model += pulp.lpSum(x[i] for i, row in enumerate(rows) if pid in row["player_ids"]) <= cap
    model += pulp.lpSum(x[i] for i, row in enumerate(rows) if row["elevated_ids"]) <= floor(count * elevated_lineup_cap)
    qb_ids = sorted({row.get("qb_id") for row in rows if row.get("qb_id")})
    if count > 1 and qb_ids:
        qb_active = pulp.LpVariable.dicts("qb_path", range(len(qb_ids)), cat="Binary")
        for j, qb_id in enumerate(qb_ids):
            members = pulp.lpSum(x[i] for i, row in enumerate(rows) if row.get("qb_id") == qb_id)
            model += members >= qb_active[j]
            model += members <= count * qb_active[j]
        model += pulp.lpSum(qb_active.values()) >= 2
    for i, left in enumerate(rows):
        left_ids = set(left["player_ids"])
        for j in range(i + 1, len(rows)):
            if len(left_ids & set(rows[j]["player_ids"])) > overlap_cap:
                model += x[i] + x[j] <= 1
    frontier_ids = sorted({row["thesis_id"] for row in rows
                           if families[row["thesis_id"]]["pareto_status"] == "frontier"
                           and families[row["thesis_id"]].get("global_selector_gap", 0) <= TOLERANCES[-1] + 1e-9})
    active_thesis = pulp.LpVariable.dicts("thesis", range(len(frontier_ids)), cat="Binary")
    for j, thesis_id in enumerate(frontier_ids):
        members = pulp.lpSum(x[i] for i, row in enumerate(rows) if row["thesis_id"] == thesis_id)
        model += members >= active_thesis[j]
        model += members <= count * active_thesis[j]
    games = sorted({row["game_key"] for row in rows if row["thesis_id"] in frontier_ids})
    active_game = pulp.LpVariable.dicts("game", range(len(games)), cat="Binary")
    for j, game in enumerate(games):
        members = pulp.lpSum(x[i] for i, row in enumerate(rows)
                               if row["game_key"] == game and row["thesis_id"] in frontier_ids)
        model += members >= active_game[j]
        model += members <= count * active_game[j]
    solver = make_cbc_solver(resolve_cbc_backend("auto"))
    solver.timeLimit = 20
    def stage(objective: Any) -> bool:
        model.objective = objective
        return model.solve(solver) == pulp.LpStatusOptimal
    thesis_sum = pulp.lpSum(active_thesis.values())
    if not stage(thesis_sum):
        return [], "infeasible_or_unproven_frontier_stage"
    model += thesis_sum == round(pulp.value(thesis_sum))
    game_sum = pulp.lpSum(active_game.values())
    if not stage(game_sum):
        return [], "infeasible_or_unproven_game_stage"
    model += game_sum == round(pulp.value(game_sum))
    if not stage(pulp.lpSum(row["selector"] * x[i] for i, row in enumerate(rows))):
        return [], "infeasible_or_unproven_selector_stage"
    chosen = [row for i, row in enumerate(rows) if pulp.value(x[i]) > 0.9]
    return chosen if len(chosen) == count else [], "optimal" if len(chosen) == count else "incomplete"


def analyze_saved_candidates(*, optimizer_run_id: str, run_created_at: str,
                             snapshot: Mapping[str, Any], candidates: Sequence[dict],
                             selected_ranks: Sequence[int], risk_rows: Sequence[Mapping[str, Any]],
                             max_exposure: float, risk_policy: Mapping[str, Any],
                             first_kickoff_at: str) -> dict:
    validate_solver_snapshot(snapshot)
    if snapshot["payload"]["metadata"]["optimizer_run_id"] != optimizer_run_id:
        raise ValueError("Frozen solver snapshot belongs to a different optimizer run")
    cutoff = datetime.fromisoformat(snapshot["payload"]["metadata"]["decision_cutoff_at"])
    kickoff = datetime.fromisoformat(first_kickoff_at)
    if cutoff >= kickoff:
        raise ValueError("Thesis shadow requires a pre-lock solver decision")
    pool_by_id = {str(row["player_id"]): row for row in snapshot["payload"]["pool_rows"]}
    for source_row in pool_by_id.values():
        if source_row.get("market_source_system"):
            observed_at = source_row.get("market_observed_at")
            if not observed_at:
                raise ValueError("Sourced thesis market lacks a frozen observation timestamp")
            observed = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
            if observed > cutoff or observed >= kickoff:
                raise ValueError("Thesis shadow cannot use a post-decision or post-lock market")
    risk_by_id = {str(row["player_id"]): row for row in risk_rows}
    locked_ids = set(snapshot["payload"]["options"].get("locked_player_ids") or [])
    player_caps = {}
    for pid, player in pool_by_id.items():
        bucket = risk_by_id.get(pid, {}).get("bucket")
        cap = 1.0 if pid in locked_ids else max_exposure
        if pid not in locked_ids and player.get("position") == "QB":
            cap = min(cap, 0.60)
        if bucket == "questionable_elevated":
            cap = min(cap, float(risk_policy.get("elevated_selected_cap", 0.40)))
        elif bucket == "questionable_full_role":
            cap = min(cap, float(risk_policy.get("full_role_selected_cap", 0.60)))
        player_caps[pid] = cap
    rows = [_candidate_view(row, pool_by_id, risk_by_id) for row in candidates]
    if len({tuple(row["player_ids"]) for row in rows}) != len(rows):
        raise ValueError("Frozen candidate universe contains duplicate canonical rosters")
    rows.sort(key=lambda row: row["rank"])
    if not rows:
        raise ValueError("Saved Classic run has no candidate universe")
    best_score = max(row["selector"] for row in rows)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["thesis_id"]].append(row)
    families = [_family_metrics(members, rows, best_score) for members in grouped.values()]
    families.sort(key=lambda family: (-family["peak_selector"], family["thesis_id"]))
    _dominance(families)
    family_by_id = {family["thesis_id"]: family for family in families}
    viability = {f"{tolerance:.2f}": {
        "qualified_theses": [f["thesis_id"] for f in families
                             if f["global_selector_gap"] <= tolerance + 1e-9],
        "qualified_count": sum(f["global_selector_gap"] <= tolerance + 1e-9 for f in families),
        "frontier_count": sum(f["global_selector_gap"] <= tolerance + 1e-9 and
                              f["pareto_status"] == "frontier" for f in families)}
        for tolerance in TOLERANCES}
    portfolios = {}
    for count in PORTFOLIO_SIZES:
        chosen, solve_status, used_tolerance, used_overlap = [], "not_attempted", None, None
        for tolerance in (*TOLERANCES, None):
            eligible = [row for row in rows if tolerance is None or
                        best_score - row["selector"] <= tolerance + 1e-9]
            for overlap in ((6, 7, 8) if count >= 10 else (6,)):
                chosen, solve_status = _solve_portfolio(
                    eligible, family_by_id, count, player_caps,
                    float(risk_policy.get("selected_lineups_with_elevated_cap", 0.6)), overlap)
                if chosen:
                    used_tolerance, used_overlap = tolerance, overlap
                    break
            if chosen:
                break
        portfolios[str(count)] = _portfolio_summary(chosen, len(rows), status=solve_status,
                                                     tolerance=used_tolerance, overlap_cap=used_overlap)
    selected_set = set(selected_ranks)
    production = _portfolio_summary([row for row in rows if row["rank"] in selected_set], len(rows),
                                    status="saved_production", tolerance=None, overlap_cap=None)
    source = {"optimizer_run_id": optimizer_run_id, "run_created_at": run_created_at,
              "solver_snapshot_sha256": snapshot["sha256"],
              "candidate_universe_sha256": digest_payload({"candidates": list(candidates)}),
              "decision_cutoff_at": cutoff.isoformat(), "first_kickoff_at": kickoff.isoformat()}
    body = {"contract": CONTRACT, "source": source, "candidate_universe": rows,
            "thesis_definition": "canonical game + canonical QB ID + QB pass-catcher count + bring-back presence; bring-back identity and one-offs remain variants",
            "families": families, "viability": viability, "shadow_portfolios": portfolios,
            "production_five": production,
            "comparison_five": {"selector_delta": portfolios["5"]["selector_sum"] - production["selector_sum"],
                                "mean_delta": portfolios["5"]["mean_sum"] - production["mean_sum"],
                                "p90_delta": portfolios["5"]["p90_sum"] - production["p90_sum"]},
            "postgame_contract": {"status": "pending_actuals", "fields": [
                "actual_best_lineup_by_thesis", "actual_mean_candidate_by_thesis", "best_actual_thesis",
                "depth_reliability", "game_environment_coverage", "portfolio_score_distribution",
                "regret_vs_best_scoreable_candidate", "field_percentile_when_available"]},
            "selection_caps": {"player_caps": player_caps,
                               "minimum_qb_paths": 2,
                               "shadow_overlap_primary": 6},
            "method_limits": ["Selector weights and thesis quality tolerances are not outcome-validated.",
                              "Summed player P90 is not lineup P90.",
                              "Shadow diversifies by thesis and game before maximizing the existing selector; production user constraints are not changed."]}
    return {**body, "sha256": digest_payload(body)}


def diagnose_zero_candidate_players(*, snapshot: Mapping[str, Any],
                                    candidates: Sequence[dict],
                                    risk_rows: Sequence[Mapping[str, Any]],
                                    candidate_caps: Mapping[str, float],
                                    limit: int = 20) -> list[dict]:
    """Solve forced inclusions using only the frozen pregame solver inputs."""
    from .classic_small_field import describe_candidate
    from .gpp_optimizer import (LineupTagCaps, ObjectiveWeights, Player, PortfolioTargets,
                                SlateConfig, StackRules, TagThresholds, _build_lineup)
    from .lineup_correlation_scoring import build_format_specific_terms, build_lineup_correlation_terms
    from .rule_library import resolve_strategy_profile

    validate_solver_snapshot(snapshot)
    payload = snapshot["payload"]
    config_data = payload["resolved_config"]
    config = SlateConfig(
        stack_rules=StackRules(**config_data["stack_rules"]),
        tag_thresholds=TagThresholds(**config_data["tag_thresholds"]),
        objective_weights=ObjectiveWeights(**config_data["objective_weights"]),
        tag_caps=LineupTagCaps(**config_data["tag_caps"]),
        portfolio_targets=PortfolioTargets(**config_data["portfolio_targets"]),
        salary_cap=config_data["salary_cap"], roster_size=config_data["roster_size"],
        correlation_bonus=config_data["correlation_bonus"],
        uniqueness_overlap=config_data["uniqueness_overlap"],
        normalize_objective=config_data["normalize_objective"],
        stack_templates=[tuple(item) for item in config_data["stack_templates"]],
    )
    players = [Player(**{**data, "tags": set(data.get("tags") or [])}) for data in payload["players"]]
    source = {str(row["player_id"]): row for row in payload["pool_rows"]}
    risks = {str(row["player_id"]): row for row in risk_rows}
    zero_ids = {player.player_id for player in players} - {
        str(pid) for candidate in candidates for pid in candidate["player_ids"]}
    ordered = sorted((player for player in players if player.player_id in zero_ids
                      and player.position in {"QB", "RB", "WR", "TE"}),
                     key=lambda player: (-player.ceiling, player.player_id))[:limit]
    eligible = [player for player in players if risks.get(player.player_id, {}).get("bucket") not in
                {"out", "doubtful"}]
    elevated = {pid for pid, risk in risks.items() if risk.get("bucket") == "questionable_elevated"}
    profile = resolve_strategy_profile(contest_format="classic", objective="gpp")
    correlation_terms = build_lineup_correlation_terms(eligible, profile=profile)
    format_terms = build_format_specific_terms(eligible, profile=profile)
    game_totals = sorted({float(player.game_total) for player in players if player.game_total is not None})
    frontier = max(float(row["objective_score"]) for row in candidates)
    locked_ids = set(payload["options"].get("locked_player_ids") or [])
    options = payload["options"]
    output = []
    for player in ordered:
        record = {"player_id": player.player_id, "player": player.name,
                  "position": player.position, "salary": player.salary, "p90": player.ceiling,
                  "candidate_count": 0, "candidate_cap": candidate_caps.get(player.player_id),
                  "forced_candidate": None}
        if player not in eligible:
            record.update(cause="blocked_by_injury_risk_policy",
                          detail=risks.get(player.player_id, {}).get("bucket", "ineligible"))
            output.append(record)
            continue
        if candidate_caps.get(player.player_id, 1.0) <= 0:
            record.update(cause="blocked_by_player_core_exposure_cap", detail="zero candidate cap")
            output.append(record)
            continue
        indexes = _build_lineup(
            eligible, config, None, [],
            enforce_single_te=bool(options.get("enforce_single_te")),
            avoid_dst_opponents=bool(options.get("avoid_dst_opponents")),
            required_player_ids={player.player_id} | locked_ids,
            maximum_player_groups=[(elevated, 1)],
            precomputed_correlation_terms=correlation_terms,
            precomputed_format_terms=format_terms,
            solver_backend=resolve_cbc_backend("auto"),
        )
        if indexes is None:
            record.update(cause="no_legal_roster", detail="Forced inclusion infeasible under saved hard roster/stack rules")
            output.append(record)
            continue
        templates = set(config.stack_templates)
        def describe(indexes_to_use: list[int]) -> dict:
            return describe_candidate([eligible[index] for index in indexes_to_use],
                                      all_players=players, config=config, pool_by_id=source,
                                      ownership_available=True, game_totals=game_totals,
                                      candidate_aware_ownership=True)
        described = describe(indexes)
        structure = (int(described["stack"]["partner_count"]),
                     int(described["stack"]["bring_back_count"] > 0))
        unrestricted_selector = float(described["objective_score"])
        if structure not in templates:
            template_rows = []
            for partner_count, bring_back in sorted(templates):
                template_indexes = _build_lineup(
                    eligible, config, None, [],
                    enforce_single_te=bool(options.get("enforce_single_te")),
                    avoid_dst_opponents=bool(options.get("avoid_dst_opponents")),
                    stack_rules=replace(config.stack_rules, min_pass_catchers=partner_count,
                                        min_bring_backs=bring_back),
                    required_player_ids={player.player_id} | locked_ids,
                    exact_pass_catchers=partner_count, exact_bring_backs=bring_back,
                    maximum_player_groups=[(elevated, 1)],
                    precomputed_correlation_terms=correlation_terms,
                    precomputed_format_terms=format_terms,
                    solver_backend=resolve_cbc_backend("auto"),
                )
                if template_indexes is not None:
                    template_rows.append(describe(template_indexes))
            if template_rows:
                described = max(template_rows, key=lambda row: row["objective_score"])
        score = float(described["objective_score"])
        gap = frontier - score
        structure = (int(described["stack"]["partner_count"]),
                     int(described["stack"]["bring_back_count"] > 0))
        if structure not in templates:
            cause = "blocked_by_stack_family_construction"
        elif gap > 0.20 + 1e-9:
            cause = "legal_but_below_quality_floor"
        elif not forced_candidate_swap_feasible(set(str(pid) for pid in described["player_ids"]),
                                                candidates, candidate_caps):
            cause = "blocked_by_player_core_exposure_caps"
        else:
            cause = "candidate_budget_search_omission"
        lineup_ids = sorted(str(pid) for pid in described["player_ids"])
        record.update(cause=cause, detail="Best saved-rule forced inclusion solve",
                      forced_candidate={"player_ids": lineup_ids,
                                        "qb": described["qb"]["name"],
                                        "stack_family": described["stack"]["type"],
                                        "template_eligible": structure in templates,
                                        "unrestricted_selector": unrestricted_selector,
                                        "single_swap_cap_feasible": forced_candidate_swap_feasible(
                                            set(lineup_ids), candidates, candidate_caps),
                                        "salary": described["salary"],
                                        "selector": score, "global_equivalent_rank":
                                        1 + sum(float(row["objective_score"]) > score + 1e-9
                                                for row in candidates),
                                        "mean": described["mean"], "p90": described["p90"],
                                        "selector_gap": gap,
                                        "salary_cap_remaining": config.salary_cap - described["salary"]})
        output.append(record)
    return output
