"""User-only Classic eligibility; model projections and markets stay unchanged."""
import math

POSITIONS = ('QB', 'RB', 'WR', 'TE', 'DST')


def favored_positions(params):
    selected = set()
    for position in POSITIONS:
        key = 'force_favored_' + position.lower()
        value = params.get(key, False)
        if not isinstance(value, (bool, int, float)) or value not in (0, 1):
            raise ValueError(f'{key} must be true/false or 0/1')
        if value:
            selected.add(position)
    return selected


def is_favored(row):
    # Conventional team spread: negative = favored. Never infer from home/away.
    value = row.get('team_spread_line')
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value)) and float(value) < 0
    except (TypeError, ValueError):
        return False
