"""Requested/effective Classic policy and independent canonical-roster checks."""
from collections import Counter
from itertools import combinations
from math import ceil, floor

CONTRACT = "classic_requested_effective_policy_v1"


def resolve_overlap(requested: dict, production: bool) -> int | None:
    value = requested.get("max_lineup_overlap", 6 if production else None)
    if value is not None and (type(value) is not int or not 0 <= value <= 8):
        raise ValueError("max_lineup_overlap must be an integer from 0 to 8")
    # Explicit null is omission, never a way to disable production safety.
    return 6 if production and value is None else value


def build_contract(*, requested, count, max_exposure, maximums, minimums,
                   locked, controls, minimum_qbs, minimum_stacks, tradeoffs, frontier=None):
    production = bool(controls)
    overlap = resolve_overlap(requested, production)
    risks = (controls or {}).get("classifications", {})
    policy = (controls or {}).get("policy", {})
    enforced_locked = {pid for pid, risk in risks.items()
                       if risk["bucket"].startswith("questionable")}
    limits = {pid: (count if pid in locked and pid not in enforced_locked else
                    min(max(1, ceil(count * max_exposure)), floor(count * cap)))
              for pid, cap in maximums.items()}
    return {
        "contract_id": CONTRACT, "version": 1,
        "requested": {"entry_count": count, "global_max_exposure": max_exposure,
                      "portfolio_constraints": dict(requested)},
        "resolved_defaults": {"max_lineup_overlap": 6 if production else None,
                              "distinct_qb_paths": False, "canonical_game_cap": None},
        "sources": {"entry_count": "request", "max_lineup_overlap":
                    "request" if requested.get("max_lineup_overlap") is not None else "production_default" if production else "none",
                    "distinct_qb_paths": "request" if "distinct_qb_paths" in requested else "default",
                    "minimum_qb_paths": "automatic_quality_budget" if production else "none",
                    "minimum_stack_families": "automatic_quality_budget" if production else "none",
                    "canonical_game_cap": "request" if requested.get("canonical_game_cap") is not None else "none",
                    "skill_max_appearances": "request" if requested.get("skill_max_appearances") is not None else "none"},
        "automatic_decisions": {"quality_loss_rate_per_entry":
                                (tradeoffs or {}).get("quality_loss_tolerance_per_lineup"),
                                "entry_count_multiplier": count,
                                "total_quality_budget": count * (tradeoffs or {}).get("quality_loss_tolerance_per_lineup", 0),
                                "measured_tradeoffs": tradeoffs},
        "effective": {"entry_count": count, "max_lineup_overlap": overlap,
                      "distinct_qb_paths": requested.get("distinct_qb_paths", False),
                      "minimum_qb_paths": minimum_qbs, "minimum_stack_families": minimum_stacks,
                      "global_max_exposure": max_exposure,
                      "selected_player_maximums": dict(maximums),
                      "selected_player_appearance_limits": limits,
                      "selected_player_minimums": dict(minimums),
                      "locked_player_ids": sorted(locked),
                      "risk_enforced_locked_ids": sorted(enforced_locked),
                      "max_objective_loss": requested.get("max_objective_loss"),
                      "selector_frontier": frontier,
                      "canonical_game_cap": requested.get("canonical_game_cap"),
                      "skill_max_appearances": requested.get("skill_max_appearances"),
                      "availability_risk_policy": dict(policy),
                      "elevated_player_ids": sorted(pid for pid, r in risks.items() if r["bucket"] == "questionable_elevated")},
        "candidate_admission": {"scope": "candidate_pool_only",
                                "caps": (controls or {}).get("candidate_caps", {})},
    }


def validate_portfolio(rows, contract):
    """Validate final canonical rosters independently of solver variables."""
    e = contract["effective"]; count = e["entry_count"]; reasons = []
    sets = [set(r["player_ids"]) for r in rows]
    if len(rows) != count: reasons.append("entry_count")
    if any(len(s) != 9 for s in sets): reasons.append("canonical_roster_size")
    if len({tuple(sorted(s)) for s in sets}) != len(rows): reasons.append("duplicate_roster")
    overlap = max((len(a & b) for a, b in combinations(sets, 2)), default=0)
    if e["max_lineup_overlap"] is not None and overlap > e["max_lineup_overlap"]: reasons.append("overlap")
    exposure = Counter(pid for s in sets for pid in s)
    for pid, n in exposure.items():
        limit = e["selected_player_appearance_limits"].get(pid, max(1, ceil(count * e["global_max_exposure"])))
        if pid in e["locked_player_ids"] and pid not in e["risk_enforced_locked_ids"]: limit = count
        if n > limit: reasons.append("exposure:" + pid)
    for pid, cap in e["selected_player_minimums"].items():
        if exposure[pid] < ceil(count * cap): reasons.append("minimum_exposure:" + pid)
    if any(exposure[pid] != count for pid in e["locked_player_ids"]): reasons.append("lock")
    if e["max_objective_loss"] is not None and e["selector_frontier"] is not None:
        if any(r["objective_score"] < e["selector_frontier"] - float(e["max_objective_loss"]) - 1e-9 for r in rows): reasons.append("quality_floor")
    qbs = Counter(str(r["qb"]["player_id"]) for r in rows)
    if e.get("canonical_game_cap") is not None:
        from .classic_primary_game import canonical_primary_game
        games = Counter(canonical_primary_game(r["qb"]["team"], r["qb"]["opponent"]) for r in rows)
        if max(games.values(),default=0)>e["canonical_game_cap"]: reasons.append("canonical_game_cap")
    if e.get("skill_max_appearances") is not None:
        skill_ids = {p["player_id"] for r in rows for p in r["roster"] if p["position"] in {"RB","WR","TE"}}
        if any(exposure[pid]>e["skill_max_appearances"] for pid in skill_ids): reasons.append("skill_max_appearances")
    if len(qbs) < e["minimum_qb_paths"]: reasons.append("minimum_qb_paths")
    if e["distinct_qb_paths"] and max(qbs.values(), default=0) > 1: reasons.append("distinct_qb_paths")
    if len({r["stack"]["type"] for r in rows}) < e["minimum_stack_families"]: reasons.append("minimum_stack_families")
    elevated = set(e["elevated_player_ids"]); risk = e["availability_risk_policy"]
    if risk:
        if any(len(s & elevated) > risk["max_elevated_per_lineup"] for s in sets): reasons.append("elevated_per_lineup")
        if sum(bool(s & elevated) for s in sets) > floor(count * risk["selected_lineups_with_elevated_cap"]): reasons.append("elevated_portfolio_budget")
    return {"status": "verified" if not reasons else "failed", "violations": reasons,
            "actual_entry_count": len(rows), "actual_max_overlap": overlap,
            "actual_qb_paths": len(qbs), "player_appearances": dict(exposure)}
