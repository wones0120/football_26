"""Read-only Classic candidate and portfolio diagnostics.

This module deliberately does not alter the production optimizer configuration.
"""

from __future__ import annotations

from collections import defaultdict
from math import log
from typing import Any, Mapping, Sequence

import pulp


def lineup_key(candidate: Mapping[str, Any]) -> tuple[str, ...]:
    """Canonical identity signature, independent of roster display order."""
    return tuple(sorted(str(player_id) for player_id in candidate["player_ids"]))


def candidate_ownership(
    candidate: Mapping[str, Any], ownership_by_id: Mapping[str, float],
    optimal_probability_by_id: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Evaluate ownership only when every player has an observed projection."""
    ids = [str(player_id) for player_id in candidate["player_ids"]]
    missing = [player_id for player_id in ids if player_id not in ownership_by_id]
    if missing:
        return {"status": "unavailable", "missing_player_ids": missing,
                "ownership_sum": None, "log_ownership": None,
                "relative_chalk": None, "leverage_sum": None,
                "high_owned_count": None, "low_owned_count": None}
    values = [float(ownership_by_id[player_id]) for player_id in ids]
    optimal = optimal_probability_by_id or {}
    return {
        "status": "available", "missing_player_ids": [],
        "ownership_sum": sum(values),
        "log_ownership": sum(log(max(0.01, value) / 100.0) for value in values),
        "relative_chalk": None,
        "leverage_sum": (
            sum(float(optimal[player_id]) - owner for player_id, owner in zip(ids, values))
            if all(player_id in optimal for player_id in ids) else None
        ),
        "high_owned_count": sum(value >= 25 for value in values),
        "low_owned_count": sum(value < 10 for value in values),
    }


def add_relative_chalk(candidates: Sequence[dict[str, Any]]) -> None:
    complete = sorted(float(row["ownership"]["log_ownership"]) for row in candidates
                      if row["ownership"]["status"] == "available")
    for row in candidates:
        own = row["ownership"]
        if own["status"] == "available":
            own["relative_chalk"] = (
                100.0 * complete.index(float(own["log_ownership"])) / max(1, len(complete) - 1)
            )


def select_portfolio(
    candidates: Sequence[Mapping[str, Any]], count: int, *, max_overlap: int,
    max_same_qb: int | None = None, min_distinct_qbs: int = 0,
    distinct_primary_paths: bool = False,
    objective_values: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Maximize selector quality under explicit path and overlap constraints."""
    if not 1 <= count <= 5:
        raise ValueError("portfolio count must be 1 through 5")
    if not 0 <= max_overlap <= 8:
        raise ValueError("max_overlap must be 0 through 8")
    n = len(candidates)
    if objective_values is not None and len(objective_values) != n:
        raise ValueError("objective_values length must match candidates")
    model = pulp.LpProblem("classic_diagnostic_portfolio", pulp.LpMaximize)
    chosen = pulp.LpVariable.dicts("candidate", range(n), cat="Binary")
    values = (list(objective_values) if objective_values is not None else
              [float(candidate["objective_score"]) for candidate in candidates])
    model += pulp.lpSum(values[i] * chosen[i] for i in range(n))
    model += pulp.lpSum(chosen.values()) == count
    by_qb: dict[str, list[int]] = defaultdict(list)
    by_path: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    ids = [set(lineup_key(candidate)) for candidate in candidates]
    for i, candidate in enumerate(candidates):
        qb_id = str(candidate["qb"]["player_id"])
        by_qb[qb_id].append(i)
        by_path[(qb_id, str(candidate.get("primary_game")),
                 str(candidate.get("stack", {}).get("type")))].append(i)
    if distinct_primary_paths:
        for indexes in by_path.values():
            model += pulp.lpSum(chosen[i] for i in indexes) <= 1
    if max_same_qb is not None:
        for indexes in by_qb.values():
            model += pulp.lpSum(chosen[i] for i in indexes) <= max_same_qb
    if min_distinct_qbs:
        active = pulp.LpVariable.dicts("qb", range(len(by_qb)), cat="Binary")
        for q, indexes in enumerate(by_qb.values()):
            model += pulp.lpSum(chosen[i] for i in indexes) >= active[q]
            model += pulp.lpSum(chosen[i] for i in indexes) <= count * active[q]
        model += pulp.lpSum(active.values()) >= min_distinct_qbs
    conflict_count = 0
    for i in range(n):
        for j in range(i + 1, n):
            if len(ids[i] & ids[j]) > max_overlap:
                model += chosen[i] + chosen[j] <= 1
                conflict_count += 1
    status = model.solve(pulp.PULP_CBC_CMD(msg=False))
    if status != pulp.LpStatusOptimal:
        return {"status": pulp.LpStatus[status], "indices": [], "score_sum": None,
                "conflict_count": conflict_count}
    selected = sorted((i for i in range(n) if pulp.value(chosen[i]) > .9),
                      key=lambda i: -float(candidates[i]["objective_score"]))
    return {"status": "optimal", "indices": selected,
            "score_sum": sum(float(candidates[i]["objective_score"]) for i in selected),
            "optimized_objective_sum": sum(values[i] for i in selected),
            "conflict_count": conflict_count}
