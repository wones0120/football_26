"""Matched, per-selection soft-rule ablations with self-contained solver replay."""
from __future__ import annotations

import hashlib
import json
import math

import pulp

from .lineup_correlation_scoring import score_lineup_correlations


def solve_control(model: pulp.LpProblem, objective: pulp.LpAffineExpression) -> dict:
    """Clone the exact feasible region; never change the production solve or its values."""
    snapshot = model.toDict()
    snapshot["objective"] = {"name": "control", "coefficients": objective.toDict()}
    for variable in snapshot["variables"]:
        variable["varValue"] = None
        variable["dj"] = None
    for constraint in snapshot["constraints"]:
        constraint["pi"] = None
    variables, control = pulp.LpProblem.fromDict(snapshot)
    status = control.solve(pulp.PULP_CBC_CMD(msg=False))
    if status != pulp.LpStatusOptimal:
        raise RuntimeError("Matched control did not reach an optimal solution")
    values = {name: float(variable.value() or 0) for name, variable in variables.items()}
    control_scored_objective = float(model.objective.constant) + sum(
        float(coefficient) * values.get(variable.name, 0)
        for variable, coefficient in model.objective.items()
    )
    return {
        "solver": "PULP_CBC_CMD",
        "pulp_version": pulp.__version__,
        "scored_objective": float(pulp.value(model.objective) or 0),
        "control_scored_objective": control_scored_objective,
        "model": snapshot,
        "model_sha256": hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest(),
        "values": values,
        "control_objective": float(pulp.value(control.objective) or 0),
        "scored_base_objective": float(pulp.value(objective) or 0),
    }


def replay_control(replay: dict) -> dict:
    """Re-solve persisted coefficients without querying mutable slate data."""
    digest = hashlib.sha256(json.dumps(replay["model"], sort_keys=True).encode()).hexdigest()
    if digest != replay["model_sha256"]:
        raise ValueError("Control model checksum mismatch")
    variables, model = pulp.LpProblem.fromDict(replay["model"])
    if model.solve(pulp.PULP_CBC_CMD(msg=False)) != pulp.LpStatusOptimal:
        raise RuntimeError("Persisted control did not reach an optimal solution")
    return {
        "objective": float(pulp.value(model.objective) or 0),
        "selected_players": [player for name, player in replay["variable_players"].items()
                             if (variables[name].value() or 0) >= 0.9],
    }


def _number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def _metrics(lineup):
    result = {}
    for label, fields in {
        "mean": ("projection", "predicted_mean"),
        "individual_ceiling_sum": ("p90", "ceiling"),
        "salary": ("salary",),
        "ownership_sum": ("ownership", "projected_ownership"),
        "leverage_sum": ("leverage_score", "leverage"),
    }.items():
        values = [next((_number(row[key]) for key in fields if _number(row.get(key)) is not None), None) for row in lineup]
        result[label] = sum(values) if all(value is not None for value in values) else None
    return result


def build_comparison(scored, control, replay, *, profile, context_multiplier=1.0,
                     correlation_multiplier=1.0):
    """Report a joint ablation, not unsupported causal attribution to one rule."""
    def identity(row):
        return str(row["player_id"]), "CPT" if row.get("roster_position") == "CPT" else "FLEX"

    def players(rows):
        return [{key: row.get(key) for key in ("player_id", "name", "position", "roster_position", "salary", "projection", "p90")}
                for row in rows]

    def contributions(rows):
        totals = {}
        for row in rows:
            multiplier = context_multiplier
            if row.get("roster_position") == "CPT":
                multiplier *= 1.5 * (_number(row.get("captain_objective_multiplier")) or 1.0)
            for trigger in (row.get("optimizer_context_rule_evaluation") or {}).get("triggered_rules", []):
                key = "context:" + str(trigger["rule_id"])
                totals[key] = totals.get(key, 0) + (_number(trigger.get("score_contribution")) or 0) * multiplier
        if profile is not None:
            summary = score_lineup_correlations(rows, profile=profile, objective_multiplier=correlation_multiplier)
            for trigger in summary["triggered_rules"]:
                key = "correlation:" + str(trigger["rule_id"])
                totals[key] = totals.get(key, 0) + trigger["objective_contribution"]
        return totals

    scored_metrics, control_metrics = _metrics(scored), _metrics(control)
    scored_rules, control_rules = contributions(scored), contributions(control)
    scored_ids, control_ids = set(map(identity, scored)), set(map(identity, control))
    return {
        "contract": "optimizer_matched_control_v1",
        "status": "completed",
        "scope": "same_selection_step",
        "interpretation": "Joint context/correlation ablation; per-rule deltas are contributions, not individual causal effects. Controls are alternatives at each scored portfolio step, not a separately playable portfolio.",
        "ceiling_label": "Individual Ceiling Sum (not a joint lineup quantile)",
        "selection_changed": scored_ids != control_ids,
        "selection_effect": (
            "unchanged" if scored_ids == control_ids else
            "rules_preferred_selection" if replay["scored_objective"] - replay["control_scored_objective"] > 1e-6 else
            "alternate_optimum"
        ),
        "selected_only": players([row for row in scored if identity(row) not in control_ids]),
        "control_only": players([row for row in control if identity(row) not in scored_ids]),
        "control_lineup": players(control),
        "scored_metrics": scored_metrics,
        "control_metrics": control_metrics,
        "deltas_scored_minus_control": {key: scored_metrics[key] - value if value is not None and scored_metrics[key] is not None else None for key, value in control_metrics.items()},
        "base_objective_opportunity_cost": replay["control_objective"] - replay["scored_base_objective"],
        "rule_contributions": [{"rule_id": key, "scored": scored_rules.get(key, 0), "control_if_enabled": control_rules.get(key, 0),
                                "delta": scored_rules.get(key, 0) - control_rules.get(key, 0)}
                               for key in sorted(scored_rules.keys() | control_rules.keys())],
        "replay": replay,
    }
