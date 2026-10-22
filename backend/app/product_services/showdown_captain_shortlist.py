"""Pregame captain selection policy; never changes model projections."""

import numpy as np
import pandas as pd

from .showdown_captain_preferences import captain_preference_exclusions
from .captain_workload import assess_captain_workload, POLICY_ID as WORKLOAD_POLICY_ID


POLICY_ID = "showdown_top_four_p90_v1"


def build_captain_shortlist(
    pool: pd.DataFrame, *, params: dict, flex_only_ids: set[str]
) -> tuple[pd.DataFrame, dict]:
    frame = pool.copy()
    learned = params.get('workload_comparison') in {'learned_counts','learned_yards','scenario_first'}
    merged = params.get("analyst_strategy") == "MERGED_SCENARIOS" or bool(params.get("workload_comparison"))
    limit = len(frame) if merged else 4
    report = {
        "policy_id": "analyst_scenario_all_eligible_captains_v1" if merged else POLICY_ID,
        "limit": limit,
        "ranking": "unmultiplied_pregame_p90_desc_canonical_player_id_asc",
        "captain_score": "1.5 * pregame_p90",
        "flex_score": "pregame_mean",
        "captain_salary_multiplier": 1.5,
        "flex_eligibility_unchanged": True,
        "shortlist": [],
        "exclusions": [],
        "workload_policy_id": WORKLOAD_POLICY_ID if merged else None,
    }
    if params.get("workload_comparison"):
        report.update(policy_id="offensive_comparison_all_workload_qualified_captains_v1",
            ranking="pregame_P90_display_order_only; all workload-qualified actors retained before count-domain coverage",
            captain_score="1.5 * weighted_projected_yards" if params["workload_comparison"]=="learned_yards" else "1.5 * normalized_count_utility" if params["workload_comparison"] != "offensive_mean_control" else "1.5 * supported_domain_FP_mean",
            flex_score="weighted_projected_yards" if params["workload_comparison"]=="learned_yards" else "normalized_count_utility" if params["workload_comparison"] != "offensive_mean_control" else "supported_domain_FP_mean")
    if learned:
        report.update(policy_id='learned_opportunities_supported_captains_v1',
            ranking='canonical_player_id_asc; no points ranking or qualification',
            workload_policy_id='complete_learned_counts_positive_utility_v1')
    if params.get('workload_comparison')=='scenario_first':
        report.update(policy_id='scenario_first_supported_captains_v1',captain_score='shared-case Captain score ×1.5',
            flex_score='shared-case physical-event DK score',workload_policy_id='supported_shared_scoring_cases_v1')
    if frame.empty:
        return frame, report
    # player_id is the canonical player_master_id at the optimizer boundary.
    frame["showdown_captain_p90"] = pd.to_numeric(frame["p90"], errors="coerce")
    frame["showdown_flex_mean"] = pd.to_numeric(frame["projection"], errors="coerce")
    ordered = frame.assign(_canonical_id=frame["player_id"].astype(str)).sort_values(
        ["_canonical_id"] if learned else ["showdown_captain_p90", "_canonical_id"],
        ascending=True if learned else [False, True], na_position="last"
    ).drop_duplicates("_canonical_id")
    shortlisted = set()
    eligible_rank = 0
    for model_rank, row in enumerate(ordered.to_dict("records"), start=1):
        player_id = str(row["player_id"])
        position = str(row.get("position") or "").strip().upper()
        reasons = captain_preference_exclusions(params, position, player_id)
        for excluded, code in (
            (player_id in flex_only_ids, "user_flex_only"),
            (position == "QB" and params.get("no_qb_captain"), "user_no_qb_captain"),
            (position == "QB" and params.get("no_qbs"), "user_no_qbs"),
        ):
            if excluded:
                reasons.append({"reason_code": code, "category": "user_preference", "scope": "captain"})
        p90 = row["showdown_captain_p90"]
        if not learned and not np.isfinite(p90):
            reasons.append({"reason_code": "missing_finite_pregame_p90", "category": "model_eligibility", "scope": "captain"})
        if learned:
            receipt=(params.get('prepared_input_evidence') or {}).get('workload_forecast') or {}
            actor=next((p for p in receipt.get('players',[]) if p['player_master_id']==player_id),{})
            value=actor.get('utility')
            workload=dict(eligible=bool(receipt.get('learned_opportunities') and value is not None and value>0),
                reason_code='complete_learned_counts_positive_utility' if value is not None and value>0 else 'learned_counts_unknown_or_no_opportunity',
                policy_id='complete_learned_counts_positive_utility_v1')
        else:
            workload = assess_captain_workload(row) if merged else None
        if workload is not None and not workload['eligible']:
            reasons.append({"reason_code": workload['reason_code'], "category": "football_role_eligibility", "scope": "captain"})
        rank = None
        if not reasons:
            eligible_rank += 1
            rank = eligible_rank
            if rank > limit:
                reasons.append({"reason_code": "outside_top_four_p90", "category": "optimizer_policy", "scope": "captain"})
        entry = {
            "player_id": player_id, "name": row.get("name"),
            "team": row.get("player_team"), "position": position,
            "pregame_p90": float(p90) if np.isfinite(p90) else None,
            "model_p90_rank": model_rank, "eligible_p90_rank": rank,
            "exclusions": reasons,
            "captain_workload": workload,
        }
        if reasons:
            report["exclusions"].append(entry)
        else:
            shortlisted.add(player_id)
            report["shortlist"].append(entry)
    frame["showdown_captain_shortlisted"] = frame["player_id"].astype(str).isin(shortlisted)
    return frame, report
