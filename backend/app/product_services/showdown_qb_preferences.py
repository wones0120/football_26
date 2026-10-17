"""User lineup constraints, kept separate from football/model assessments."""

QB_PREFERENCE_LABELS = {
    "no_qb_captain": "No QB Captain",
    "no_two_qbs": "No 2 QBs in the lineup",
    "no_qbs": "No QBs in the lineup",
}


def validate_showdown_qb_preferences(params: dict, *, showdown: bool) -> None:
    for key, label in QB_PREFERENCE_LABELS.items():
        if key in params and type(params[key]) is not bool:
            raise ValueError(f"params.{key} must be an explicit boolean")
        if params.get(key, False) and not showdown:
            raise ValueError(f"{label} requires Showdown format")


def showdown_qb_preference_report(params: dict) -> dict:
    no_qbs = params.get("no_qbs", False)
    maximum = 0 if no_qbs else 1 if params.get("no_two_qbs", False) else 2
    captain_allowed = not (no_qbs or params.get("no_qb_captain", False) or params.get("captain_positions"))
    return {
        **{key: params.get(key, False) for key in QB_PREFERENCE_LABELS},
        "allow_qb_captain": captain_allowed,
        "named_captain_position_exception_ids": params.get("captain_position_exception_ids", []),
        "max_starting_qbs_per_lineup": maximum,
        "requested_portfolio_size": int(params.get("num_lineups", 1)),
        "effective_qb_captain_limit": int(captain_allowed),
        "effective_starting_qb_lineup_limit": maximum,
        "overridden_construction_requirements": (
            ["require_starting_qb", "hard_qb_correlations"] if no_qbs else []
        ),
        "exclusions": [
            {"reason_code": f"user_{key}", "category": "user_preference",
             "reason": label, "scope": "captain" if key == "no_qb_captain" else "lineup"}
            for key, label in QB_PREFERENCE_LABELS.items() if params.get(key, False)
        ],
        "model_assessments_preserved": True,
    }
