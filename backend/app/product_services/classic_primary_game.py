"""Canonical QB-led primary-game identity and optional portfolio concentration."""
from collections import Counter


def canonical_primary_game(team: str, opponent: str) -> str:
    pair = sorted((str(team or "").strip().upper(), str(opponent or "").strip().upper()))
    if not all(pair) or pair[0] == pair[1]:
        raise ValueError("Primary game requires two distinct known teams")
    return "-".join(pair)


def resolve_primary_game_cap(value):
    if value is not None and (type(value) is not int or value < 1):
        raise ValueError("max_lineups_per_primary_game must be null or a positive integer")
    return value


def primary_game_exposure(lineups, *, strict=False):
    games = Counter()
    for lineup in lineups:
        qb = next((player for player in lineup if player.position == "QB"), None)
        if qb is None:
            raise ValueError("Classic lineup has no primary QB")
        try:
            game = canonical_primary_game(qb.team, qb.opponent)
        except ValueError:
            if strict:
                raise
            game = "UNAVAILABLE"
        games[game] += 1
    return dict(sorted(games.items()))


def candidate_primary_game(row, *, strict=False):
    """Use canonical QB teams; permit legacy display pairs only in reports."""
    qb = row.get("qb") or {}
    if qb.get("team") and qb.get("opponent"):
        return canonical_primary_game(qb["team"], qb["opponent"])
    if strict:
        raise ValueError("Primary-game cap requires saved QB team and opponent")
    pair = str(row.get("primary_game") or "").replace("–", "-").split("-")
    if len(pair) == 2:
        try:
            return canonical_primary_game(*pair)
        except ValueError:
            pass
    return "UNAVAILABLE"
