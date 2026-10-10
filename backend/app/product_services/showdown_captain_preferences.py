"""Captain eligibility preferences, separate from player/model assessments."""

CAPTAIN_POSITIONS = ("WR", "RB", "TE")


def allowed_captain_positions(params: dict) -> list[str]:
    values = params.get("captain_positions", [])
    if not isinstance(values, list) or any(
        not isinstance(value, str) or value not in CAPTAIN_POSITIONS for value in values
    ):
        raise ValueError("params.captain_positions must be a list containing only WR, RB or TE")
    return [position for position in CAPTAIN_POSITIONS if position in values]


def validate_showdown_captain_preferences(params: dict, *, showdown: bool) -> None:
    if allowed_captain_positions(params) and not showdown:
        raise ValueError("Captain position restriction requires Showdown format")


def captain_preference_exclusions(params: dict, position: str) -> list[dict]:
    allowed = allowed_captain_positions(params)
    if not allowed or position.strip().upper() in allowed:
        return []
    return [{
        "reason_code": "user_captain_positions",
        "reason": "Captain position restricted to " + ", ".join(allowed) + "; FLEX remains eligible",
        "category": "user_preference",
        "scope": "captain",
    }]


def captain_preference_report(params: dict) -> dict:
    allowed = allowed_captain_positions(params)
    return {
        "allowed_positions": allowed,
        "restricted": bool(allowed),
        "scope": "captain",
        "reason_code": "user_captain_positions" if allowed else None,
        "category": "user_preference" if allowed else None,
        "flex_eligibility_unchanged": True,
        "model_assessments_preserved": True,
    }
