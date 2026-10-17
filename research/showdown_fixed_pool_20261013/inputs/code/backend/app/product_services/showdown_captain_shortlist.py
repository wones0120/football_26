"""Pregame captain selection policy; never changes model projections."""

import numpy as np
import pandas as pd

from .showdown_captain_preferences import captain_preference_exclusions


POLICY_ID = "showdown_top_four_p90_v1"


def build_captain_shortlist(
    pool: pd.DataFrame, *, params: dict, flex_only_ids: set[str]
) -> tuple[pd.DataFrame, dict]:
    frame = pool.copy()
    report = {
        "policy_id": POLICY_ID,
        "limit": 4,
        "ranking": "unmultiplied_pregame_p90_desc_canonical_player_id_asc",
        "captain_score": "1.5 * pregame_p90",
        "flex_score": "pregame_mean",
        "captain_salary_multiplier": 1.5,
        "flex_eligibility_unchanged": True,
        "shortlist": [],
        "exclusions": [],
    }
    if frame.empty:
        return frame, report
    # player_id is the canonical player_master_id at the optimizer boundary.
    frame["showdown_captain_p90"] = pd.to_numeric(frame["p90"], errors="coerce")
    frame["showdown_flex_mean"] = pd.to_numeric(frame["projection"], errors="coerce")
    ordered = frame.assign(_canonical_id=frame["player_id"].astype(str)).sort_values(
        ["showdown_captain_p90", "_canonical_id"], ascending=[False, True], na_position="last"
    ).drop_duplicates("_canonical_id")
    shortlisted = set()
    eligible_rank = 0
    for model_rank, row in enumerate(ordered.to_dict("records"), start=1):
        player_id = str(row["player_id"])
        position = str(row.get("position") or "").strip().upper()
        reasons = captain_preference_exclusions(params, position)
        for excluded, code in (
            (player_id in flex_only_ids, "user_flex_only"),
            (position == "QB" and params.get("no_qb_captain"), "user_no_qb_captain"),
            (position == "QB" and params.get("no_qbs"), "user_no_qbs"),
        ):
            if excluded:
                reasons.append({"reason_code": code, "category": "user_preference", "scope": "captain"})
        p90 = row["showdown_captain_p90"]
        if not np.isfinite(p90):
            reasons.append({"reason_code": "missing_finite_pregame_p90", "category": "model_eligibility", "scope": "captain"})
        rank = None
        if not reasons:
            eligible_rank += 1
            rank = eligible_rank
            if rank > 4:
                reasons.append({"reason_code": "outside_top_four_p90", "category": "optimizer_policy", "scope": "captain"})
        entry = {
            "player_id": player_id, "name": row.get("name"),
            "team": row.get("player_team"), "position": position,
            "pregame_p90": float(p90) if np.isfinite(p90) else None,
            "model_p90_rank": model_rank, "eligible_p90_rank": rank,
            "exclusions": reasons,
        }
        if reasons:
            report["exclusions"].append(entry)
        else:
            shortlisted.add(player_id)
            report["shortlist"].append(entry)
    frame["showdown_captain_shortlisted"] = frame["player_id"].astype(str).isin(shortlisted)
    return frame, report
