"""Candidate-level quality and exposure selection for Showdown portfolios."""

from __future__ import annotations

import math
from collections import Counter

import pulp

from .showdown_scenario_value import POLICY_ID, scenario_credits


def signature(lineup: list[dict]) -> tuple[str, tuple[str, ...]]:
    captain = next(row for row in lineup if row["roster_position"] == "CPT")
    return (str(captain["player_id"]), tuple(sorted(str(row["player_id"]) for row in lineup)))


def candidate_metrics(lineup: list[dict]) -> dict:
    captain = next(row for row in lineup if row["roster_position"] == "CPT")
    captain_objective_score = float(captain.get("objective_score") or 0)
    captain_prior_multiplier = float(captain.get("captain_objective_multiplier") or 1)
    ownership = [row.get("ownership") for row in lineup]
    ownership_complete = all(
        value is not None and math.isfinite(float(value)) and float(value) > 0
        for value in ownership
    )
    return {
        "scenario_id": str(lineup[0].get("showdown_scenario_id") or "baseline"),
        "candidate_source": str(lineup[0].get("showdown_candidate_source") or "legacy"),
        "captain_player_id": str(captain["player_id"]),
        "captain_name": str(captain.get("name") or captain.get("player_name") or captain["player_id"]),
        "salary": sum(float(row.get("salary") or 0) for row in lineup),
        "mean": sum(float(row.get("projection") or 0) for row in lineup),
        "p90": sum(float(row.get("p90") or 0) for row in lineup),
        "baseline_mean": sum(float(row.get("baseline_projection", row.get("projection")) or 0) for row in lineup),
        "baseline_p90": sum(float(row.get("baseline_p90", row.get("p90")) or 0) for row in lineup),
        "conditioned_mean": sum(float(row["conditioned_projection"]) for row in lineup)
        if all(row.get("conditioned_projection") is not None for row in lineup) else None,
        "conditioned_p90": sum(float(row["conditioned_p90"]) for row in lineup)
        if all(row.get("conditioned_p90") is not None for row in lineup) else None,
        "conditioned_selector": lineup[0].get("conditioned_selector"),
        "comparison_basis": str(lineup[0].get("showdown_comparison_basis") or "common_baseline"),
        "team_split": "/".join(
            f"{team} {sum(str(row.get('player_team') or '').upper() == team for row in lineup)}"
            for team in sorted({str(row.get("player_team") or "").upper() for row in lineup})
        ),
        "selector": float(lineup[0].get("solver_objective_value") or 0),
        "captain_objective_score": captain_objective_score,
        "captain_objective_multiplier": captain_prior_multiplier,
        "captain_position_prior_contribution": captain_objective_score * (1 - 1 / captain_prior_multiplier),
        "correlation": float((lineup[0].get("lineup_correlation_summary") or {}).get("total_adjustment") or 0),
        "captain_ownership": captain.get("ownership"),
        "ownership_complete": ownership_complete,
        "lineup_ownership": sum(float(value) for value in ownership) if ownership_complete else None,
        "missing_ownership_players": [
            str(row.get("name") or row.get("player_name") or row["player_id"])
            for row in lineup if row.get("ownership") is None
        ],
    }


def captain_family_summaries(report: dict) -> list[dict]:
    """Explain all retained family rows without solving or changing selection."""
    metrics = report.get("ranked_metrics", [])
    selected = set(report.get("selected_ranks", []))
    reasons = report.get("omission_reasons", {})
    families = []
    for captain_id in sorted({row["captain_player_id"] for row in metrics}):
        rows = sorted((row for row in metrics if row["captain_player_id"] == captain_id),
                      key=lambda row: row["rank"])
        best = rows[0]
        eligible = next((row for row in rows if row["quality_eligible"]), None)
        family_selected = any(row["rank"] in selected for row in rows)
        reason_row = eligible or best
        reason = ("Selected candidate" if reason_row["rank"] in selected else
                  reasons.get(reason_row["rank"], reasons.get(str(reason_row["rank"]), "Reason unavailable")))
        families.append({**best, "best_unscreened_rank": best["rank"],
                         "best_eligible_candidate": eligible,
                         "best_eligible_reason": reason if eligible else None,
                         "selected": family_selected,
                         "reason": reason if eligible else f"No family candidate passed the joint screen. {reason}"})
    return sorted(families, key=lambda row: row["rank"])


def select_showdown_portfolio(
    candidates: list[list[dict]],
    *,
    requested: int,
    player_limits: dict[str, int],
    captain_limit: int,
    quality_fraction: float = 0.95,
    require_scenario_diversity: bool = False,
    soft_scenario_diversity: bool = False,
) -> tuple[list[list[dict]], dict]:
    """Maximize entries, then baseline selector plus optional bounded coverage.

    The quality threshold is a portfolio policy, not a projection adjustment.
    Every candidate is scored with the same production selector before entry.
    """
    if require_scenario_diversity and soft_scenario_diversity:
        raise ValueError("Legacy required coverage and soft scenario diversity are mutually exclusive")
    unique: dict[tuple[str, tuple[str, tuple[str, ...]]], list[dict]] = {}
    for lineup in candidates:
        if lineup and len(lineup) == 6:
            key = (str(lineup[0].get("showdown_scenario_id") or "baseline"), signature(lineup))
            if key not in unique or candidate_metrics(lineup)["selector"] > candidate_metrics(unique[key])["selector"]:
                unique[key] = lineup
    ranked = sorted(
        unique.values(),
        key=lambda lineup: (-candidate_metrics(lineup)["selector"], candidate_metrics(lineup)["scenario_id"], signature(lineup)),
    )
    if not ranked:
        return [], {"candidate_count": 0, "quality_eligible_count": 0, "family_rows": []}
    metrics = [candidate_metrics(lineup) for lineup in ranked]
    player_names = {
        str(row["player_id"]): str(row.get("name") or row.get("player_name") or row["player_id"])
        for lineup in ranked for row in lineup
    }
    # A conditional winner is a discovery hypothesis, not an unconditional
    # forecast. It cannot raise the common baseline quality requirement.
    best_mean = max(row["baseline_mean"] for row in metrics)
    best_p90 = max(row["baseline_p90"] for row in metrics)
    best_selector = metrics[0]["selector"]
    eligible = [
        index for index, row in enumerate(metrics)
        if row["baseline_mean"] + 1e-8 >= quality_fraction * best_mean
        and row["baseline_p90"] + 1e-8 >= quality_fraction * best_p90
    ]
    def solve(diversify: bool = False, credits: list[dict] | None = None,
              forced_index: int | None = None, target_count: int | None = None) -> list[int] | None:
        model = pulp.LpProblem("ShowdownPortfolioSelection", pulp.LpMaximize)
        choices = {index: pulp.LpVariable(f"candidate_{index}", cat="Binary") for index in eligible}
        score_span = sum(abs(metrics[index]["selector"]) for index in eligible) + 1.0
        family_vars = {}
        reward_vars = {index: pulp.LpVariable(f"reward_{index}", cat="Binary")
                       for index in eligible if credits and credits[index]["credit"] > 0}
        for index, variable in reward_vars.items():
            model += variable <= choices[index]
        for family in {metrics[index]["scenario_id"] for index in reward_vars}:
            # Pay only the best selected witness per condition. Multiple
            # similar candidates cannot accumulate label coverage rewards.
            model += pulp.lpSum(variable for index, variable in reward_vars.items()
                                if metrics[index]["scenario_id"] == family) <= 1
        score_span += sum(credits[index]["credit"] for index in reward_vars) if credits else 0
        if diversify and requested > 1:
            for family in sorted({metrics[index]["scenario_id"] for index in eligible}):
                variable = pulp.LpVariable(f"family_{family}", cat="Binary")
                family_vars[family] = variable
                model += variable <= pulp.lpSum(
                    choices[index] for index in eligible if metrics[index]["scenario_id"] == family
                )
        # Count dominates. The legacy mode puts label coverage next; soft mode
        # instead adds bounded credits to the ordinary selector objective.
        # The weights bound whole-portfolio selector swing; they do not change
        # player or lineup objective scores.
        model += (2 * len(family_vars) + 3) * score_span * pulp.lpSum(choices.values()) + (
            2 * score_span * pulp.lpSum(family_vars.values()) if family_vars else 0
        ) + pulp.lpSum(metrics[index]["selector"] * choices[index] for index in eligible) + pulp.lpSum(
            credits[index]["credit"] * variable for index, variable in reward_vars.items())
        model += pulp.lpSum(choices.values()) <= requested
        if forced_index is not None:
            model += choices[forced_index] == 1
        if target_count is not None:
            model += pulp.lpSum(choices.values()) == target_count
        for player_id, limit in player_limits.items():
            model += pulp.lpSum(
                choices[index] for index in eligible
                if player_id in signature(ranked[index])[1]
            ) <= limit
        for captain_id in {metrics[index]["captain_player_id"] for index in eligible}:
            model += pulp.lpSum(
                choices[index] for index in eligible
                if metrics[index]["captain_player_id"] == captain_id
            ) <= captain_limit
        # Different scenario variants of one roster are one entry choice.
        roster_groups: dict[tuple[str, tuple[str, ...]], list[int]] = {}
        for index in eligible:
            roster_groups.setdefault(signature(ranked[index]), []).append(index)
        for indexes in roster_groups.values():
            if len(indexes) > 1:
                model += pulp.lpSum(choices[index] for index in indexes) <= 1
        status = model.solve(pulp.PULP_CBC_CMD(msg=False))
        if status == pulp.LpStatusInfeasible and forced_index is not None:
            return None
        if status != pulp.LpStatusOptimal:
            raise RuntimeError(f"Showdown portfolio selection failed: {pulp.LpStatus[status]}")
        return sorted(index for index in eligible if choices[index].value() > 0.5)

    ordinary_indices = solve(False)
    credits = scenario_credits(metrics, ranked, ordinary_indices, eligible, requested)
    selected_indices = (solve(True) if require_scenario_diversity else
                        solve(credits=credits) if soft_scenario_diversity and any(c["credit"] > 0 for c in credits)
                        else ordinary_indices)
    selected = [ranked[index] for index in selected_indices]
    selected_set = set(selected_indices)
    selected_families = {metrics[index]["scenario_id"] for index in selected_indices}
    families = sorted({row["scenario_id"] for row in metrics})
    ordinary_score = sum(metrics[i]["selector"] for i in ordinary_indices)
    forced_portfolios = {i: solve(forced_index=i, target_count=len(ordinary_indices)) for i in eligible}
    opportunity_costs = {i: (ordinary_score - sum(metrics[j]["selector"] for j in forced))
                         if forced is not None else None for i, forced in forced_portfolios.items()}
    family_coverage = []
    for family in families:
        indexes = [index for index, row in enumerate(metrics) if row["scenario_id"] == family]
        qualifying = [index for index in indexes if index in eligible]
        best = metrics[indexes[0]]
        family_coverage.append({
            "scenario_id": family, "candidate_count": len(indexes),
            "qualifying_count": len(qualifying), "best_rank": indexes[0] + 1,
            "best_mean": max(metrics[index]["baseline_mean"] for index in indexes),
            "best_p90": max(metrics[index]["baseline_p90"] for index in indexes),
            "best_selector": best["selector"], "best_captain": best["captain_name"],
            "best_team_split": best["team_split"], "best_salary": best["salary"],
            "selected": family in selected_families,
            "reason": (
                "selected" if family in selected_families else
                "no candidate passed the joint mean/P90 floor" if not qualifying else
                "portfolio exposure, roster uniqueness, count, or selector tradeoff"
            ),
        })
    omission_reasons: dict[int, str] = {}
    for index, row in enumerate(metrics):
        if index in selected_set:
            continue
        if index not in eligible:
            omission_reasons[index + 1] = (
                f"Joint quality screen: mean short {max(0.0, quality_fraction * best_mean - row['baseline_mean']):.2f}; "
                f"P90 short {max(0.0, quality_fraction * best_p90 - row['baseline_p90']):.2f}"
            )
            continue
        if any(signature(ranked[j]) == signature(ranked[index]) for j in selected_indices):
            omission_reasons[index + 1] = "Identical physical roster already selected under another scenario; no additional coverage"
            continue
        feasible_swaps: list[int | None] = []
        blocked: set[str] = set()
        for incumbent in (selected_indices if len(selected_indices) >= requested else [None]):
            others = [j for j in selected_indices if j != incumbent]
            counts = Counter(pid for j in others for pid in signature(ranked[j])[1])
            captain_counts = Counter(metrics[j]["captain_player_id"] for j in others)
            blockers = [
                f"player exposure {player_names.get(pid, pid)}" for pid in signature(ranked[index])[1]
                if counts[pid] >= player_limits.get(pid, requested)
            ]
            if captain_counts[row["captain_player_id"]] >= captain_limit:
                blockers.append("Captain exposure")
            if any(signature(ranked[j]) == signature(ranked[index]) for j in others):
                blockers.append("identical roster already selected under another scenario")
            if blockers:
                blocked.update(blockers)
            else:
                feasible_swaps.append(incumbent)
        if feasible_swaps:
            incumbent = min(
                (j for j in feasible_swaps if j is not None),
                key=lambda j: metrics[j]["selector"], default=None,
            )
            if incumbent is None:
                omission_reasons[index + 1] = "Qualified but portfolio count was not filled; inspect solver diagnostics"
            else:
                deficit = metrics[incumbent]["selector"] - row["selector"]
                omission_reasons[index + 1] = (
                    f"Replacing selected rank #{incumbent + 1} would lose {deficit:.2f} selector points"
                    if deficit >= -1e-6 else
                    "Global portfolio interaction; single replacement raises score, inspect candidate selection"
                )
        else:
            omission_reasons[index + 1] = "; ".join(sorted(blocked))
    for index in selected_indices:
        row = metrics[index]
        higher = []
        for upper in range(index):
            if upper in selected_set:
                continue
            other = [j for j in selected_indices if j != index]
            counts = Counter(pid for j in other for pid in signature(ranked[j])[1])
            captain_counts = Counter(metrics[j]["captain_player_id"] for j in other)
            blockers = [
                f"player exposure: {player_names.get(pid, pid)}" for pid in signature(ranked[upper])[1]
                if counts[pid] >= player_limits.get(pid, requested)
            ]
            if captain_counts[metrics[upper]["captain_player_id"]] >= captain_limit:
                blockers.append("Captain exposure")
            if any(signature(ranked[j]) == signature(ranked[upper]) for j in other):
                blockers.append("identical roster already selected under another scenario")
            if upper not in eligible:
                blockers.append("joint mean/P90 quality floor")
            higher.append({"rank": upper + 1, "blockers": blockers or ["global portfolio tradeoff"]})
        diagnostic = {
            "global_candidate_rank": index + 1,
            "mean_loss": best_mean - row["baseline_mean"],
            "p90_loss": best_p90 - row["baseline_p90"],
            "selector_loss": best_selector - row["selector"],
            "scenario_diversity_changed_selection": bool(
                (require_scenario_diversity or soft_scenario_diversity)
                and signature(ranked[index]) not in {signature(ranked[i]) for i in ordinary_indices}
            ),
            "selection_reason": (
                "bounded conditional coverage value with quality and exposure constraints"
                if soft_scenario_diversity and index not in ordinary_indices else
                "legacy required scenario coverage with quality and exposure constraints"
                if require_scenario_diversity and index not in ordinary_indices
                else "highest feasible portfolio selector under quality and exposure constraints"
            ),
            "higher_ranked_skipped": higher,
            "scenario_value": credits[index],
            "forced_baseline_portfolio_opportunity_cost": opportunity_costs.get(index),
        }
        next(player for player in ranked[index] if player["roster_position"] == "CPT")[
            "showdown_selection_diagnostic"
        ] = diagnostic
    accounting = []
    for family in families:
        indexes = [i for i, m in enumerate(metrics) if m["scenario_id"] == family]
        rejected = next((i for i in indexes if i not in selected_set), None)
        eligible_rejected = next((i for i in indexes if i in eligible and i not in selected_set), None)
        accounting.append({
            "scenario_id": family, "candidates_generated": len(indexes),
            "passing_baseline_quality": sum(i in eligible for i in indexes),
            "best_baseline_selector": max(metrics[i]["selector"] for i in indexes),
            "best_conditioned_selector": max((float(metrics[i]["conditioned_selector"]) for i in indexes
                                               if metrics[i].get("conditioned_selector") is not None), default=None),
            "best_conditioned_p90_proxy": max((metrics[i]["conditioned_p90"] for i in indexes
                                               if metrics[i].get("conditioned_p90") is not None), default=None),
            "constraint_surviving_candidates": sum(forced_portfolios.get(i) is not None for i in indexes),
            "selected_lineups": sum(i in selected_set for i in indexes),
            "best_rejected_rank": rejected + 1 if rejected is not None else None,
            "best_rejected_captain": metrics[rejected]["captain_name"] if rejected is not None else None,
            "primary_rejection_reason": omission_reasons.get(rejected + 1) if rejected is not None else None,
            "replacement_opportunity_cost": opportunity_costs.get(rejected),
            "best_eligible_rejected_rank": eligible_rejected + 1 if eligible_rejected is not None else None,
            "best_eligible_rejected_opportunity_cost": opportunity_costs.get(eligible_rejected),
            "best_eligible_rejected_reason": omission_reasons.get(eligible_rejected + 1) if eligible_rejected is not None else None,
            "maximum_available_soft_credit": max(credits[i]["credit"] for i in indexes),
        })
    credited = []
    if soft_scenario_diversity:
        for family in families:
            witness = max((i for i in selected_indices if metrics[i]["scenario_id"] == family),
                          key=lambda i: credits[i]["credit"], default=None)
            if witness is not None and credits[witness]["credit"] > 0:
                credited.append({"rank": witness + 1, **credits[witness],
                                 "forced_baseline_portfolio_opportunity_cost": opportunity_costs[witness]})
    return selected, {
        "candidate_count": len(ranked),
        "quality_eligible_count": len(eligible),
        "quality_fraction": quality_fraction,
        "quality_basis": "common_baseline",
        "best_mean": best_mean,
        "best_p90": best_p90,
        "best_selector": best_selector,
        "requested": requested,
        "selected": len(selected),
        "underfill_diagnostics": {
            "requested": requested, "selected": len(selected),
            "quality_rejected": len(ranked) - len(eligible),
            "quality_eligible_rosters": len({signature(ranked[i]) for i in eligible}),
            "reason": (
                "filled" if len(selected) == requested else
                "insufficient distinct quality-eligible rosters" if len({signature(ranked[i]) for i in eligible}) < requested else
                "player/captain exposure caps prevent filling from distinct quality-eligible rosters"
            ),
            "cap_denominator": requested,
            "realized_exposure_denominator": len(selected),
        },
        "selected_ranks": [index + 1 for index in selected_indices],
        "require_scenario_diversity": require_scenario_diversity,
        "soft_scenario_diversity": soft_scenario_diversity,
        "scenario_selection_policy": POLICY_ID if soft_scenario_diversity else "legacy_required_coverage" if require_scenario_diversity else "baseline",
        "ordinary_selected_ranks": [index + 1 for index in ordinary_indices],
        "scenario_portfolio_accounting": accounting,
        "scenario_diversity_affected_portfolio": {signature(ranked[i]) for i in selected_indices} != {signature(ranked[i]) for i in ordinary_indices},
        "baseline_portfolio_selector": ordinary_score,
        "selected_portfolio_selector": sum(metrics[i]["selector"] for i in selected_indices),
        "selected_scenario_credits": credited,
        "ordinary_replaced_ranks": [i + 1 for i in ordinary_indices
                                    if signature(ranked[i]) not in {signature(ranked[j]) for j in selected_indices}],
        "scenario_added_ranks": [i + 1 for i in selected_indices
                                 if signature(ranked[i]) not in {signature(ranked[j]) for j in ordinary_indices}],
        "constraint_survival_basis": "Can belong to a full maximum-fill portfolio under unchanged quality, player/captain caps and physical uniqueness; not a single-slot swap",
        "scenario_family_coverage": family_coverage,
        "omission_reasons": omission_reasons,
        "ranked_metrics": [dict(
            row, rank=index + 1, quality_eligible=index in eligible,
            scenario=ranked[index][0].get("showdown_scenario"), scenario_value=credits[index],
            forced_baseline_portfolio_opportunity_cost=opportunity_costs.get(index),
            forced_baseline_portfolio_ranks=[i + 1 for i in forced_portfolios[index]]
            if forced_portfolios.get(index) is not None else None,
            baseline_constraint_survives=forced_portfolios.get(index) is not None,
            players=[{
                "player_id": player.get("player_id"),
                "name": player.get("name") or player.get("player_name"),
                "slot": player.get("roster_position"),
                "team": player.get("player_team"),
                "adjustment": player.get("showdown_scenario_adjustment"),
            } for player in ranked[index]],
        ) for index, row in enumerate(metrics)],
    }
