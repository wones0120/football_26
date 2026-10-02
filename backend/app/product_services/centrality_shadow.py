"""Pure selector-only football centrality shadow scoring.

This module never creates candidates or changes production optimizer scores.
"""
from __future__ import annotations

from itertools import combinations
from typing import Any, Iterable, Mapping

import numpy as np

SKILL_POSITIONS = {"RB", "WR", "TE"}


def candidate_id(candidate: Mapping[str, Any]) -> str:
    return "|".join(sorted(str(value) for value in candidate.get("player_ids", [])))


def lineup_football_metrics(
    candidate: Mapping[str, Any],
    core_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize football involvement without changing the saved candidate."""
    skill = [
        row for row in candidate.get("roster", [])
        if str(row.get("position") or "").upper() in SKILL_POSITIONS
    ]
    rows = []
    for player in skill:
        player_id = str(player.get("player_id"))
        core = dict(core_by_id.get(player_id, {}))
        centrality = core.get("overall_centrality")
        centrality = float(centrality) if centrality is not None else None
        confidence = str(core.get("current_evidence_confidence") or "unavailable")
        high_current = confidence == "high_current"
        rows.append({
            "player_id": player_id,
            "name": player.get("name"),
            "position": player.get("position"),
            "centrality": centrality,
            "high_current": high_current,
            "core": core,
        })
    denominator = len(rows)
    high_current_values = [
        row["centrality"] for row in rows
        if row["high_current"] and row["centrality"] is not None
    ]
    football_centrality = (
        float(np.mean(high_current_values)) if high_current_values else 0.0
    )
    observed = [row["centrality"] for row in rows if row["centrality"] is not None]
    average_overall = float(np.mean(observed)) if observed else None
    return {
        "skill_player_count": denominator,
        "high_current_evidence_count": len(high_current_values),
        "football_centrality": football_centrality,
        "average_overall_centrality": average_overall,
        "high_current_core_count": sum(
            row["high_current"] and bool(row["core"].get("overall_core")) for row in rows
        ),
        "receiving_core_count": sum(bool(row["core"].get("receiving_core")) for row in rows),
        "rushing_core_count": sum(bool(row["core"].get("rushing_core")) for row in rows),
        "offensive_centerpiece_count": sum(
            row["core"].get("football_classification") == "offensive centerpiece"
            for row in rows
        ),
        "peripheral_count": sum(
            row["core"].get("football_classification") == "peripheral" for row in rows
        ),
        "stale_evidence_count": sum(
            row["core"].get("current_evidence_confidence") == "stale_2025_primary"
            for row in rows
        ),
        "non_high_current_count": sum(not row["high_current"] for row in rows),
    }


def prepare_candidates(
    candidates: Iterable[Mapping[str, Any]],
    core_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    output = []
    for source in candidates:
        row = dict(source)
        row["candidate_id"] = candidate_id(row)
        row["base_objective"] = float(row["objective_score"])
        row["football"] = lineup_football_metrics(row, core_by_id)
        output.append(row)
    values = np.array([row["football"]["football_centrality"] for row in output], dtype=float)
    mean = float(values.mean()) if len(values) else 0.0
    std = float(values.std(ddof=0)) if len(values) else 0.0
    for row in output:
        row["football_z"] = (
            (row["football"]["football_centrality"] - mean) / std if std > 0 else 0.0
        )
    return output, {"mean": mean, "std": std, "candidate_count": len(output)}


def ranked_at_lambda(candidates: Iterable[Mapping[str, Any]], weight: float) -> list[dict]:
    rows = []
    for source in candidates:
        row = dict(source)
        row["lambda"] = float(weight)
        row["football_contribution"] = float(weight) * float(row["football_z"])
        row["shadow_objective"] = row["base_objective"] + row["football_contribution"]
        rows.append(row)
    return sorted(rows, key=lambda row: (-row["shadow_objective"], row["candidate_id"]))


def crossover_points(
    candidates: list[Mapping[str, Any]],
    *,
    maximum_lambda: float = 10.0,
) -> list[dict[str, Any]]:
    """Return exact upper-envelope winner changes for nonnegative lambda."""
    intersections = {0.0, float(maximum_lambda)}
    for left, right in combinations(candidates, 2):
        denominator = float(left["football_z"]) - float(right["football_z"])
        if abs(denominator) < 1e-12:
            continue
        point = (float(right["base_objective"]) - float(left["base_objective"])) / denominator
        if 0.0 < point < maximum_lambda:
            intersections.add(float(point))
    ordered = sorted(intersections)
    changes = []
    prior_winner = None
    for index in range(len(ordered) - 1):
        left, right = ordered[index], ordered[index + 1]
        midpoint = (left + right) / 2.0
        winner = ranked_at_lambda(candidates, midpoint)[0]
        if winner["candidate_id"] == prior_winner:
            continue
        if prior_winner is None:
            crossover = 0.0
        else:
            previous = next(row for row in candidates if row["candidate_id"] == prior_winner)
            delta_z = float(winner["football_z"]) - float(previous["football_z"])
            crossover = (
                (float(previous["base_objective"]) - float(winner["base_objective"])) / delta_z
                if delta_z > 0 else left
            )
        changes.append({
            "lambda": max(0.0, float(crossover)),
            "candidate_id": winner["candidate_id"],
            "candidate": winner,
        })
        prior_winner = winner["candidate_id"]
    return changes
