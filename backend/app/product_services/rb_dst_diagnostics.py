"""Informational RB projection and game-script evidence for Classic reports.

These diagnostics never change player eligibility, projections, or selector scores.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence


OFFENSE = {"QB", "RB", "WR", "TE"}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and abs(result) != float("inf") else None


def _receiving_strength(source: Mapping[str, Any]) -> float | None:
    share = _number(source.get("pregame_target_share"))
    targets = _number(source.get("pregame_expected_targets"))
    routes = _number(source.get("pregame_expected_routes"))
    if share is None:
        share = _number(source.get("target_share_mean_3"))
    if targets is None:
        targets = _number(source.get("targets_mean_3"))
    terms = []
    for value, maximum in ((share, .28), (targets, 8), (routes, 32)):
        if value is not None:
            terms.append(min(1.0, max(0.0, value / maximum)))
    return max(terms) if terms else None


def _script(spread: float | None) -> str:
    if spread is None:
        return "market unavailable"
    if spread <= -6:
        return "favored by at least 6"
    if spread < -2:
        return "favored by 2–5.5"
    if spread <= 2:
        return "near pick'em"
    if spread < 6:
        return "underdog by 2–5.5"
    return "underdog by at least 6"


def build_rb_dst_diagnostics(
    candidates: Sequence[dict], selected_indices: Sequence[int],
    source: Mapping[str, Mapping[str, Any]],
) -> dict:
    """Attach reproducible warning-only evidence to saved candidate rows."""
    player_why = []
    for player_id, row in source.items():
        if str(row.get("position") or "").upper() != "RB":
            continue
        mean = _number(row.get("projection"))
        salary = _number(row.get("salary"))
        carries = _number(row.get("carries_mean_3"))
        targets = _number(row.get("targets_mean_3"))
        if not (mean is not None and (mean >= 9 or (salary or 0) >= 6000
                                      or (carries or 0) >= 10 or (targets or 0) >= 3)):
            continue
        player_why.append({
            "player_id": player_id,
            "name": row.get("name") or row.get("player_name"),
            "team": row.get("player_team"), "salary": salary,
            "mean": mean, "p90": _number(row.get("p90")),
            "role_class": row.get("offensive_role_class"),
            "snap_share_mean_3": _number(row.get("snap_share_mean_3")),
            "carries_mean_3": carries, "targets_mean_3": targets,
            "target_share_mean_3": _number(row.get("target_share_mean_3")),
            "receiving_role_strength": _receiving_strength(row),
            "team_implied_total": _number(row.get("team_implied_total")),
            "spread": _number(row.get("team_spread_line")),
            "game_total": _number(row.get("game_total_line")),
            "trend": {key: _number(row.get(key)) for key in (
                "snap_share_last", "snap_share_prior3", "snap_share_trend",
                "rush_share_last", "rush_share_prior3", "rush_share_trend",
                "target_share_last", "target_share_prior3", "target_share_trend")},
            "model_version": row.get("projection_model_version"),
            "model_explanation": row.get("role_counterfactual_grid"),
            "explanation_limit": "Saved one-feature role counterfactuals, not causal effects or SHAP; market-input rescores unavailable",
            "external_benchmark": {"status": "unavailable", "reason": "No saved same-slate benchmark attached to this optimizer run"},
        })
    player_why.sort(key=lambda row: (-row["mean"], str(row["name"])))

    def has_members(candidate: dict, ids: set[str]) -> bool:
        return ids <= set(candidate["player_ids"])

    selected_counter: Counter[str] = Counter()
    for index, candidate in enumerate(candidates):
        roster = candidate["roster"]
        dst = next((member for member in roster if member["position"] == "DST"), None)
        flags = []
        if dst:
            for member in roster:
                if member["position"] != "RB" or member["team"] != dst["team"]:
                    continue
                source_row = source.get(str(member["player_id"]), {})
                spread = _number(source_row.get("team_spread_line"))
                implied = _number(source_row.get("team_implied_total"))
                rule = [item for item in candidate.get("correlation_rules", [])
                        if item.get("reason_code") == "same_team_running_back_dst"
                        and {str(player.get("player_id")) for player in item.get("players", [])}
                        >= {str(member["player_id"]), str(dst["player_id"])}]
                bonus = sum(_number(item.get("objective_contribution")) or 0.0 for item in rule)
                flags.append({
                    "kind": "same_team_rb_dst", "key": f"same_team_rb_dst:{member['player_id']}:{dst['player_id']}",
                    "label": f"{member['name']} + {dst['name']}: {_script(spread)}",
                    "status": "informational", "production_impacting": False,
                    "why": (f"Same-team RB and DST; team spread {spread:+.1f}, implied total {implied:.1f}. "
                            f"Current RB+DST selector bonus {bonus:+.4f}."
                            if spread is not None and implied is not None else
                            "Same-team RB and DST; pregame market evidence incomplete."),
                    "rb_player_id": str(member["player_id"]), "dst_player_id": str(dst["player_id"]),
                    "spread": spread, "team_implied_total": implied,
                    "recent_carries": _number(source_row.get("carries_mean_3")),
                    "recent_targets": _number(source_row.get("targets_mean_3")),
                    "receiving_role_strength": _receiving_strength(source_row),
                    "correlation_selector_contribution": bonus,
                    "avoid_ids": [str(member["player_id"]), str(dst["player_id"])],
                })
        by_team: dict[str, list[dict]] = {}
        for member in roster:
            if member["position"] in OFFENSE:
                by_team.setdefault(str(member["team"]), []).append(member)
        for team, members in by_team.items():
            source_row = source.get(str(members[0]["player_id"]), {})
            implied = _number(source_row.get("team_implied_total"))
            safe = source_row.get("market_context_point_in_time_safe") is True
            if safe and implied is not None and implied < 20 and len(members) >= 2:
                flags.append({
                    "kind": "low_team_total_offense", "key": f"low_team_total_offense:{team}",
                    "label": f"{team}: {len(members)} offensive players at {implied:.1f} implied points",
                    "status": "informational", "production_impacting": False,
                    "why": "Multiple offensive players from a team with a pregame implied total below 20.",
                    "avoid_ids": [str(member["player_id"]) for member in members],
                    "team": team, "team_implied_total": implied,
                })
        for member in roster:
            if member["position"] != "RB":
                continue
            source_row = source.get(str(member["player_id"]), {})
            implied = _number(source_row.get("team_implied_total"))
            mean = _number(source_row.get("projection"))
            if (source_row.get("market_context_point_in_time_safe") is True
                    and implied is not None and mean is not None
                    and implied < 20 and mean >= 15):
                flags.append({
                    "kind": "projection_market_tension",
                    "key": f"projection_market_tension:{member['player_id']}",
                    "label": f"{member['name']}: {mean:.2f} mean / {implied:.1f} team total",
                    "status": "informational", "production_impacting": False,
                    "why": "High RB projection in a low implied team total; receiving and workload evidence should be inspected.",
                    "avoid_ids": [str(member["player_id"])],
                    "team": member["team"], "team_implied_total": implied,
                })
        for flag in flags:
            ids = set(flag.pop("avoid_ids"))
            if flag["kind"] == "low_team_total_offense":
                alternative = next((other for other in candidates
                                    if other is not candidate and sum(
                                        member["position"] in OFFENSE
                                        and member["team"] == flag["team"]
                                        for member in other["roster"]) < 2), None)
            else:
                alternative = next((other for other in candidates
                                    if other is not candidate and not has_members(other, ids)), None)
            flag["strongest_candidate_without_flag"] = (
                {"rank": alternative.get("rank"), "player_ids": alternative["player_ids"],
                 "mean": alternative["mean"], "p90": alternative["p90"],
                 "selector": alternative["objective_score"],
                 "mean_cost": candidate["mean"]-alternative["mean"],
                 "p90_cost": candidate["p90"]-alternative["p90"],
                 "selector_cost": candidate["objective_score"]-alternative["objective_score"],
                 "scope": "saved_candidate_universe"}
                if alternative else None
            )
            if index in selected_indices:
                selected_counter[flag["key"]] += 1
        candidate["rb_dst_football_sanity_flags"] = flags
    return {
        "player_why": player_why,
        "selected_flag_exposure": [
            {"key": key, "appearances": count, "selected_count": len(selected_indices)}
            for key, count in selected_counter.most_common()
        ],
        "warning_only": True,
        "candidate_alternative_scope": "saved_candidate_universe",
    }
