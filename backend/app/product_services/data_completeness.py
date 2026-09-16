"""Evidence-only plans for archived actuals and unresolved salary identities."""
from collections import defaultdict

from Database.player_identity import strip_name_suffix
from backend.app.services.simulation import calculate_dk_points, _num


def archived_dk_points(raw, position):
    # Actual results retain negative points. Legacy model callers keep their
    # existing zero-floor default. Missed kicks do not deduct DK fantasy points.
    points = calculate_dk_points(raw, floor_at_zero=False)
    if position == 'K':
        points += 3 * sum(_num(raw, key) for key in ('fg_made_0_19', 'fg_made_20_29', 'fg_made_30_39'))
        points += 4 * _num(raw, 'fg_made_40_49')
        points += 5 * (_num(raw, 'fg_made_50_59') + _num(raw, 'fg_made_60_'))
        points += _num(raw, 'pat_made')
    return points


def team(value):
    value = str(value or '').strip().upper()
    return {'LA': 'LAR', 'STL': 'LAR', 'SD': 'LAC', 'OAK': 'LV', 'JAC': 'JAX'}.get(value, value)


def salary_identity_plan(salaries, rosters, aliases):
    native = defaultdict(set)
    for alias in aliases:
        native[(alias['source_system'], alias['source_key'])].add(alias['player_master_id'])
    alias_index = defaultdict(list)
    for alias in aliases:
        if alias.get('alias_name') and alias.get('team') and alias.get('position'):
            alias_index[(team(alias['team']), alias['position'], strip_name_suffix(alias['alias_name']))].append(alias)
    roster_index = defaultdict(list)
    for row in rosters:
        roster_index[(row['season'], row['week'], team(row['team']), row['position'],
                      strip_name_suffix(row['player_name'] or ''))].append(row)
    decisions = []
    for salary in salaries:
        evidence = []
        ids = native[('draftkings', salary['source_player_key'])].copy()
        policy = 'existing_draftkings_source_id'
        if not ids:
            policy = 'same_week_roster_team_position_alias_to_gsis'
            key = (salary['season'], salary['week'], team(salary['team']), salary['position'],
                   strip_name_suffix(salary['player_name']))
            for roster in roster_index[key]:
                matched = native[('nflreadpy', roster['gsis_id'])]
                evidence.append({'roster_id': roster['raw_nfl_weekly_roster_id'],
                                 'ingest_run_id': roster['ingest_run_id'], 'gsis_id': roster['gsis_id'],
                                 'canonical_ids': sorted(matched)})
                ids.update(matched)
            # An unidentified roster candidate must not be silently discarded.
            if any(len(row['canonical_ids']) != 1 for row in evidence):
                ids = set()
        if not ids and not evidence:
            policy = 'persisted_alias_team_position_unique'
            matched_aliases = alias_index[(team(salary['team']), salary['position'], strip_name_suffix(salary['player_name']))]
            ids = {alias['player_master_id'] for alias in matched_aliases}
            evidence = [{'source_system': alias['source_system'], 'source_key': alias['source_key'],
                         'canonical_id': alias['player_master_id']} for alias in matched_aliases]
        decisions.append({'salary': salary, 'player_master_id': next(iter(ids)) if len(ids) == 1 else None,
                          'status': 'resolved' if len(ids) == 1 else 'review',
                          'policy': policy, 'evidence': evidence})
    return decisions


def historical_actual_plan(raw_rows, games, aliases, existing):
    native = defaultdict(set)
    for alias in aliases:
        if alias['source_system'] == 'nflreadpy':
            native[alias['source_key']].add(alias['player_master_id'])
    reverse_native = defaultdict(set)
    tracked_ids = {row['player_id'] for row in raw_rows}
    for source_id, master_ids in native.items():
        if source_id in tracked_ids:
            for master_id in master_ids:
                reverse_native[master_id].add(source_id)
    game_index = defaultdict(set)
    team_games = defaultdict(list)
    for game in games:
        for home, away in [(game['home_team_id'], game['away_team_id']),
                           (game['away_team_id'], game['home_team_id'])]:
            game_index[(game['season'], game['week'], team(home), team(away))].add(game['game_id'])
            team_games[(game['season'], game['week'], team(home))].append((game['game_id'], team(away)))
    existing_index = defaultdict(set)
    for row in existing:
        existing_index[(row['season'], row['week'], row['player_id'])].add(row['game_id'])
    seen = defaultdict(list)
    for row in raw_rows:
        seen[(row['season'], row['week'], row['player_id'])].append(row)
    decisions = []
    for raw_group in seen.values():
        raw = max(raw_group, key=lambda row: row['raw_nfl_weekly_stat_id'])
        ids = native[raw['player_id']]
        candidates = game_index[(raw['season'], raw['week'], team(raw['team']), team(raw['opponent']))]
        opponent = team(raw['opponent'])
        game_policy = 'season_week_team_opponent'
        if team(raw['team']) == opponent and not raw['game_id']:
            # Some old source transforms wrote the team's relocated abbreviation
            # as its own opponent. A unique schedule game supplies the opponent.
            scheduled = team_games[(raw['season'], raw['week'], team(raw['team']))]
            if len(scheduled) == 1:
                candidates = {scheduled[0][0]}
                opponent = scheduled[0][1]
                game_policy = 'unique_schedule_game_corrects_self_opponent'
        if raw['game_id']:
            candidates = candidates.intersection({raw['game_id']})
        status = 'missing'
        if len(ids) != 1 or any(len(reverse_native[canonical]) != 1 for canonical in ids):
            status = 'identity_review'
        elif len(candidates) != 1:
            status = 'game_review'
        elif any(row['raw_row_json'] != raw['raw_row_json'] for row in raw_group):
            status = 'conflicting_source_review'
        canonical = next(iter(ids)) if len(ids) == 1 else None
        game_id = next(iter(candidates)) if len(candidates) == 1 else None
        if status == 'missing' and existing_index[(raw['season'], raw['week'], canonical)]:
            status = 'existing' if game_id in existing_index[(raw['season'], raw['week'], canonical)] else 'existing_game_review'
        decision = {'raw_id': raw['raw_nfl_weekly_stat_id'], 'ingest_run_id': raw['ingest_run_id'],
                    'source_player_id': raw['player_id'], 'player_name': raw['player_name'],
                    'season': raw['season'], 'week': raw['week'], 'status': status, 'game_policy': game_policy,
                    'canonical_id': canonical, 'native_ids_for_canonical': sorted(reverse_native[canonical]) if canonical else []}
        if status == 'missing':
            decision['record'] = dict(season=raw['season'], week=raw['week'], game_id=game_id,
                player_id=canonical, team_id=team(raw['team']), opponent_team_id=opponent,
                position=raw['position'], dk_points=archived_dk_points(raw['raw_row_json'], raw['position']))
        decisions.append(decision)
    return decisions
