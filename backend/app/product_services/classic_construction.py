"""Roster-based Classic taxonomy. Descriptive only; never changes selection."""
from collections import Counter, defaultdict
from dataclasses import asdict, is_dataclass

from .classic_primary_game import canonical_primary_game

RESEARCH_SCOPE = ("Historical success means top 10%, not first place or ROI: 15 contests across "
    "10 slates; entry limits and payout categories unknown; qualified markets on only three "
    "slates; ownership is realized contest ownership. Descriptive research, not a validated "
    "Large-GPP strategy or optimizer backtest.")
DEFINITIONS = ("Counts use actual rosters. Pass catchers are WR/TE; RB bring-backs are separate. "
    "QB-team offense includes QB and excludes DST. Game and maximum-team counts include DST; "
    "offense-only concentration is also shown. Secondary mini-stacks count distinct non-QB "
    "games with offense on both teams. True unrelated one-offs are offensive singletons "
    "outside the QB game and outside the DST game. Template counts are minimums, not exact counts.")


def classify_roster(players):
    rows = [asdict(p) if is_dataclass(p) else dict(p) for p in players]
    positions = Counter(str(p.get('position', '')).upper().replace('DEF', 'DST') for p in rows)
    if positions.get('D'):
        positions['DST'] += positions.pop('D')
    ids = [str(p.get('player_id') or '') for p in rows]
    valid = (len(rows) == 9 and len(set(ids)) == 9 and all(ids) and positions['QB'] == 1
        and positions['DST'] == 1 and positions['RB'] >= 2 and positions['WR'] >= 3
        and positions['TE'] >= 1 and sum(positions.values()) == 9
        and set(positions) <= {'QB', 'RB', 'WR', 'TE', 'DST'})
    if not valid:
        return {'status': 'unavailable', 'reason': 'Not a legal nine-distinct-player Classic roster'}
    for p in rows:
        p['position'] = str(p['position']).upper()
        if p['position'] in {'D', 'DEF'}: p['position'] = 'DST'
        p['team'] = str(p.get('team') or p.get('player_team') or '').strip().upper()
        p['opponent'] = str(p.get('opponent') or p.get('opponent_team') or '').strip().upper()
        try: p['game'] = canonical_primary_game(p['team'], p['opponent'])
        except ValueError:
            return {'status': 'unavailable', 'reason': 'Team/opponent context unavailable; no name-based inference'}
    qb = next(p for p in rows if p['position'] == 'QB')
    dst = next(p for p in rows if p['position'] == 'DST')
    offense = [p for p in rows if p['position'] != 'DST']
    same = [p for p in offense if p['team'] == qb['team']]
    pcs = [p for p in same if p['position'] in {'WR', 'TE'}]
    bring = [p for p in offense if p['team'] == qb['opponent']]
    outside = [p for p in offense if p['game'] != qb['game']]
    counts = Counter(p['game'] for p in outside)
    by_game = defaultdict(set)
    for p in outside: by_game[p['game']].add(p['team'])
    return {'status': 'available', 'flex_position': 'RB' if positions['RB'] == 3 else 'TE' if positions['TE'] == 2 else 'WR',
        'composition': dict(positions), 'qb_team_offense_including_qb': len(same),
        'qb_pass_catchers': len(pcs), 'qb_same_team_rb': any(p['position'] == 'RB' for p in same),
        'bring_backs': len(bring), 'bring_back_positions': sorted(p['position'] for p in bring),
        'qb_game_all_players': sum(p['game'] == qb['game'] for p in rows),
        'secondary_opposing_game_count': sum(len(teams) > 1 for teams in by_game.values()),
        'true_unrelated_oneoffs': sum(counts[p['game']] == 1 and p['game'] != dst['game'] for p in outside),
        'max_team_all': max(Counter(p['team'] for p in rows).values()),
        'max_team_offense': max(Counter(p['team'] for p in offense).values()),
        'primary_game': qb['game']}


def construction_summary(lineups, contract=None):
    frozen = {p['player_id']: p for p in (contract or {}).get('effective', {}).get('players', [])}
    rows = []
    for lineup in lineups:
        players = [{**frozen.get(str(p.get('player_id')), {}), **p} for p in lineup]
        rows.append(classify_roster(players))
    keys = ('flex_position', 'qb_team_offense_including_qb', 'qb_pass_catchers', 'qb_same_team_rb',
        'bring_backs', 'qb_game_all_players', 'secondary_opposing_game_count', 'true_unrelated_oneoffs',
        'max_team_all', 'max_team_offense')
    return {'lineups': rows, 'selected_count': len(rows), 'definitions': DEFINITIONS,
        'research_scope': RESEARCH_SCOPE,
        'distributions': {key: dict(Counter(str(row[key]) for row in rows if row['status'] == 'available')) for key in keys},
        'coverage': ('Sequential accepted lineups are the selected portfolio; no broad candidate universe retained. '
            'Selected counts are not discovery coverage. Feasible but unselected families are not proven uncompetitive.'
            if (contract or {}).get('strategy_id') == 'classic_large_gpp_v1' else
            'Actual selected entries only; candidate discovery coverage is not inferred from these counts.')}
