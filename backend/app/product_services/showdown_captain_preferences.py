"""Captain eligibility preferences, separate from player/model assessments."""

CAPTAIN_POSITIONS = ("WR", "RB", "TE")


def allowed_captain_positions(params: dict) -> list[str]:
    values = params.get("captain_positions", [])
    if not isinstance(values, list) or any(
        not isinstance(value, str) or value not in CAPTAIN_POSITIONS for value in values
    ):
        raise ValueError("params.captain_positions must be a list containing only WR, RB or TE")
    return [position for position in CAPTAIN_POSITIONS if position in values]


def named_preference_ids(params: dict, key: str) -> set[str]:
    values = params.get(key, [])
    if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError(f"params.{key} must be a list of canonical player IDs")
    return {v.strip() for v in values}


def validate_showdown_captain_preferences(params: dict, *, showdown: bool) -> None:
    for key in ("captain_position_exception_ids", "questionable_eligible_player_ids"):
        if named_preference_ids(params, key) and not showdown:
            raise ValueError(f"{key} requires Showdown format")
    from .classic_favored_preferences import favored_positions
    if favored_positions(params) and showdown:
        raise ValueError("Favored-team position requirements require Classic format")
    from .classic_season_rank_preferences import validate as validate_season_rank
    validate_season_rank(params, showdown=showdown)
    from .showdown_team_leader_preferences import validate_leader_preferences
    validate_leader_preferences(params, showdown=showdown)
    for key in ("minimum_qb_salary", "minimum_rb_salary"):
        value = params.get(key)
        if value is not None:
            if showdown:
                raise ValueError(f"{key} requires Classic format")
            if type(value) is not int or not 0 <= value <= 50000:
                raise ValueError(f"{key} must be a whole dollar amount from 0 to 50000")
    minimum = params.get("minimum_player_salary")
    if minimum is not None:
        if type(minimum) is not int or not 0 <= minimum <= 50000:
            raise ValueError("minimum_player_salary must be a whole dollar amount from 0 to 50000")
    if allowed_captain_positions(params) and not showdown:
        raise ValueError("Captain position restriction requires Showdown format")


def captain_preference_exclusions(params: dict, position: str, player_id: str = "") -> list[dict]:
    allowed = allowed_captain_positions(params)
    if not allowed or position.strip().upper() in allowed or player_id in named_preference_ids(params, "captain_position_exception_ids"):
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
        "named_position_exception_ids": sorted(named_preference_ids(params, "captain_position_exception_ids")),
        "restricted": bool(allowed),
        "scope": "captain",
        "reason_code": "user_captain_positions" if allowed else None,
        "category": "user_preference" if allowed else None,
        "flex_eligibility_unchanged": True,
        "model_assessments_preserved": True,
    }
