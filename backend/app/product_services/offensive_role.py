"""Pregame, evidence-based offensive role diagnostics.

All inputs must be known before the scored game. Missing evidence remains null;
measured zero is a valid observation. Salary is deliberately excluded.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


ROLE_INPUTS = {
    "RB": {"carry_share_mean_3": 0.55, "target_share_mean_3": 0.25, "snap_share_mean_3": 0.20},
    "WR": {"target_share_mean_3": 0.75, "snap_share_mean_3": 0.25},
    "TE": {"target_share_mean_3": 0.75, "snap_share_mean_3": 0.25},
}


def attach_offensive_role(frame: pd.DataFrame) -> pd.DataFrame:
    """Score measured opportunity shares and expose the evidence used."""
    rows = frame.copy()
    scores: list[float] = []
    completeness: list[float] = []
    evidence: list[list[str]] = []
    labels: list[str | None] = []
    reasons: list[str] = []
    confidences: list[str] = []
    sources: list[str] = []
    for _, row in rows.iterrows():
        inputs = ROLE_INPUTS.get(str(row.get("position", "")).upper())
        if inputs is None:
            scores.append(np.nan)
            completeness.append(0.0)
            evidence.append([])
            labels.append(None)
            reasons.append("offensive role metric applies to RB/WR/TE")
            confidences.append("unavailable")
            sources.append("unavailable")
            continue
        known: list[tuple[str, float, float]] = []
        for name, weight in inputs.items():
            value = pd.to_numeric(row.get(name), errors="coerce")
            available = row.get(f"{name}_available")
            if available is False or pd.isna(value):
                continue
            # A recorded zero is evidence; an absent lagged source is not.
            known.append((name, weight, float(np.clip(value, 0.0, 1.0))))
        coverage = sum(weight for _, weight, _ in known)
        if not known:
            scores.append(np.nan)
            completeness.append(0.0)
            evidence.append([])
            labels.append(None)
            reasons.append("no prior or current opportunity-share evidence")
            confidences.append("unavailable")
            sources.append("unavailable")
            continue
        score = sum(weight * value for _, weight, value in known) / coverage
        label = (
            "offensive centerpiece" if score >= 0.55 else
            "primary option" if score >= 0.40 else
            "major secondary option" if score >= 0.27 else
            "regular contributor" if score >= 0.16 else
            "rotational contributor" if score >= 0.07 else
            "low-opportunity player"
        )
        scores.append(score)
        completeness.append(coverage)
        evidence.append([name for name, _, _ in known])
        labels.append(label)
        reasons.append(", ".join(f"{name}={value:.3f}" for name, _, value in known))
        games = pd.to_numeric(row.get("player_games_history"), errors="coerce")
        games = 0.0 if pd.isna(games) else float(games)
        confidences.append(
            "high" if coverage >= 0.75 and games >= 3 else
            "medium" if coverage >= 0.5 and games >= 1 else "low"
        )
        current_share = any(
            pd.notna(row.get(column))
            for column in (
                "pregame_effective_carry_share", "pregame_effective_target_share",
            )
        )
        sources.append("current_share_or_expected_count_plus_lagged" if current_share else "lagged_three_games")
    rows["offensive_role_importance"] = scores
    rows["offensive_role_completeness"] = completeness
    rows["offensive_role_evidence"] = evidence
    rows["offensive_role_class"] = labels
    rows["offensive_role_reason"] = reasons
    rows["offensive_role_confidence"] = confidences
    rows["offensive_role_source"] = sources
    return rows


def rank_team_roles(frame: pd.DataFrame) -> pd.DataFrame:
    """Rank role and projections within each team without imputing missing role."""
    rows = frame.copy()
    team = "recent_team" if "recent_team" in rows else "team"
    skill = rows["position"].fillna("").astype(str).str.upper().isin(ROLE_INPUTS)
    rows["offensive_role_rank"] = rows.loc[skill].groupby(team)[
        "offensive_role_importance"
    ].rank(ascending=False, method="min")
    for value, rank in (("predicted_mean", "team_mean_rank"), ("predicted_p90", "team_p90_rank")):
        if value in rows:
            rows[rank] = rows.loc[skill].groupby(team)[value].rank(
                ascending=False, method="min"
            )
    rows = rows.sort_values([team, "offensive_role_rank"], na_position="last")
    for source, output in (
        ("target_share_mean_3", "team_cumulative_target_share"),
        ("carry_share_mean_3", "team_cumulative_rb_carry_share"),
    ):
        if source in rows:
            rows[output] = rows.groupby(team)[source].cumsum()
    if "team_mean_rank" in rows and "team_p90_rank" in rows:
        rows["role_projection_disagreement"] = (
            rows["offensive_role_rank"].le(3)
            & (rows["team_mean_rank"] - rows["offensive_role_rank"] >= 3)
            & (rows["team_p90_rank"] - rows["offensive_role_rank"] >= 3)
        )
    return rows
