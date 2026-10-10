"""Bounded tail-coverage credits; never edits forecasts or eligibility.

Conditional marginal ceilings are sensitivity evidence, not event probabilities.
Credits are measured against the ordinary feasible portfolio and paid at most
once per condition. Identical roster labels cannot earn a credit.
"""
from __future__ import annotations

from statistics import median
import math


POLICY_ID = "bounded_marginal_scenario_coverage_v1"
MAX_CREDIT_RATE = 0.02
CONDITIONED_QUALITY_FRACTION = 0.95
FULL_UPLIFT_FRACTION = 0.10


def scenario_credits(metrics: list[dict], rosters: list[list[dict]],
                     ordinary: list[int], eligible: list[int], requested: int) -> list[dict]:
    """Return candidate credits in production selector units.

2% of the ordinary portfolio's median selector is the maximum credit per
condition, independent of entry count. Conditional strength, positive ceiling
uplift, roster novelty, and winner construction all discount that bound.
"""
    credits = [{"credit": 0.0, "reason": "baseline candidate"} for _ in metrics]
    if requested <= 1 or not ordinary:
        return [{"credit": 0.0, "reason": "no portfolio diversification for a single entry"}
                for _ in metrics]
    scale = max(0.0, median(metrics[i]["selector"] for i in ordinary)) * MAX_CREDIT_RATE
    ids = [{str(p["player_id"]) for p in roster} for roster in rosters]
    captain_teams = [next(str(p.get("player_team") or "").upper() for p in roster
                          if p["roster_position"] == "CPT") for roster in rosters]

    def team_weight(index: int, team: str) -> float:
        return sum(1.5 if p["roster_position"] == "CPT" else 1.0 for p in rosters[index]
                   if str(p.get("player_team") or "").upper() == team)

    for i, row in enumerate(metrics):
        if row["scenario_id"] == "baseline":
            continue
        credit = {"credit": 0.0, "reason": "fails common baseline quality screen"}
        credits[i] = credit
        if i not in eligible:
            continue
        condition = rosters[i][0].get("showdown_scenario") or {}
        winner = str(condition.get("conditioned_winner") or "").upper()
        if not winner or any(row.get(field) is None or not math.isfinite(float(row[field]))
                             for field in ("conditioned_mean", "conditioned_p90")):
            credit["reason"] = "conditional evidence unavailable"
            continue
        family = [m for m in metrics if m["scenario_id"] == row["scenario_id"]
                  and all(m.get(field) is not None and math.isfinite(float(m[field]))
                          for field in ("conditioned_mean", "conditioned_p90"))]
        best_mean = max(m["conditioned_mean"] for m in family)
        best_p90 = max(m["conditioned_p90"] for m in family)
        if min(best_mean, best_p90, row["baseline_p90"]) <= 0:
            credit["reason"] = "conditional quality unavailable"
            continue
        quality = min(row["conditioned_mean"] / best_mean, row["conditioned_p90"] / best_p90)
        uplift = max(0.0, row["conditioned_p90"] / row["baseline_p90"] - 1)
        changes = min(len(ids[i] - ids[j]) for j in ordinary)
        new_captain = (captain_teams[i] == winner and row["captain_player_id"] not in
                       {metrics[j]["captain_player_id"] for j in ordinary})
        winner_count = sum(str(p.get("player_team") or "").upper() == winner for p in rosters[i])
        shift = team_weight(i, winner) - max(team_weight(j, winner) for j in ordinary)
        credit.update(conditioned_quality_ratio=quality, ceiling_uplift_fraction=uplift,
                      minimum_player_changes=changes, new_winner_captain=new_captain,
                      winner_slot_weight_shift=shift, maximum_credit=scale)
        if quality < CONDITIONED_QUALITY_FRACTION:
            credit["reason"] = "below conditional mean/ceiling frontier"
        elif uplift <= 0:
            credit["reason"] = "no positive conditional ceiling uplift"
        elif changes < 2 and not (new_captain and changes >= 1):
            credit["reason"] = "insufficient roster differentiation from ordinary portfolio"
        elif not (new_captain and winner_count >= 3) and shift < 0.5:
            credit["reason"] = "no additional winner construction or captain coverage"
        else:
            strength = min(1.0, max(0.0, (quality - CONDITIONED_QUALITY_FRACTION) /
                                      (1 - CONDITIONED_QUALITY_FRACTION)))
            novelty = min(1.0, (changes + (0.5 if new_captain else 0.0)) / 3)
            construction = 1.0 if new_captain and winner_count >= 3 else min(1.0, shift / 2)
            credit.update(credit=scale * strength * min(1.0, uplift / FULL_UPLIFT_FRACTION)
                          * novelty * construction,
                          reason="conditional strength and differentiated winner construction",
                          strength=strength, novelty=novelty, construction=construction)
    return credits
