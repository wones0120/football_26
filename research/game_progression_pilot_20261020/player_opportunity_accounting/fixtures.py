"""Invented counts and roles for mechanics checks; no historical player claims."""
from copy import deepcopy

from .allocation import CHANNELS

CUTOFF = '2023-09-01T00:00:00Z'


def inputs():
    def actor(n, shares):
        return dict(player_master_id=f'00000000-0000-0000-0000-{n:012d}',
                    availability='available', shares=dict(zip(CHANNELS, shares)))
    return dict(budgets=dict(pass_attempts=30, rush_attempts=20, targets=25),
        role_snapshot=dict(snapshot_id='synthetic-full-team-v1', evidence_kind='synthetic_fixture',
            game_id='fixture-game', team='fixture-team', as_of=CUTOFF,
            actors=[actor(1, (1, .1, 0)), actor(2, (0, .6, .2)),
                    actor(3, (0, .1, .4)), actor(4, (0, 0, .2))]),
        game_id='fixture-game', team='fixture-team', cutoff=CUTOFF)


def cases():
    baseline = inputs()
    result = [('partial_full_team', baseline)]
    for name in ('unknown_team_budget', 'unknown_role', 'unknown_availability',
                 'unavailable_vacancy', 'zero_budget'):
        case = deepcopy(baseline)
        actors = case['role_snapshot']['actors']
        if name == 'unknown_team_budget': case['budgets']['targets'] = None
        if name == 'unknown_role': actors[2]['shares']['targets'] = None
        if name == 'unknown_availability': actors[2]['availability'] = 'unknown'
        if name == 'unavailable_vacancy':
            actors[2].update(availability='unavailable', shares=dict.fromkeys(CHANNELS, 0))
        if name == 'zero_budget': case['budgets'] = dict.fromkeys(CHANNELS, 0)
        result.append((name, case))
    return result
