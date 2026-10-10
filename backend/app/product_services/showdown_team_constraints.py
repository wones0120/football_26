"""Explicit team-count preferences; football assessments remain unchanged."""


def showdown_team_limit(params: dict) -> int:
    value = params.get("max_players_per_team", 5)
    if value is None:
        value = 5
    if type(value) is not int or value not in (3, 4, 5):
        raise ValueError("Showdown max_players_per_team must be an integer from 3 to 5")
    return value


def team_constraint_report(params: dict) -> dict:
    limit = showdown_team_limit(params)
    return {
        "max_players_per_team": limit,
        "counts_captain_and_flex": True,
        "allowed_team_splits": [[count, 6 - count] for count in range(1, 6)
                                if count <= limit and 6 - count <= limit],
        "category": "user_preference" if limit < 5 else "roster_legality",
        "reason_code": "user_max_players_per_team" if limit < 5 else None,
        "model_assessments_preserved": True,
    }
