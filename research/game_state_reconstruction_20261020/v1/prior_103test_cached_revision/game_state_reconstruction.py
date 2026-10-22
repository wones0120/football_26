"""Pure retained-source game-state reconstruction; never a prediction policy.

All native rows survive, including controls and excluded official opportunities.
Adjacent observations are labels, not an inferred physical post-play state.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import re

from .factual_designation import clock
from .fumble_event_components import _flag, _eligibility
from .market_snapshots import canonical_team
from .personnel_package_continuity import physical_membership
from .play_caller_package_choices import classify_choice

VERSION = 'game_state_reconstruction_v1'
SCOPE_FIELDS = ('game_id', 'play_id', 'season', 'week', 'season_type', 'home_team', 'away_team',
                'order_sequence', 'drive', 'fixed_drive', 'series')
STATE_FIELDS = ('posteam', 'defteam', 'qtr', 'game_half', 'quarter_seconds_remaining',
                'half_seconds_remaining', 'game_seconds_remaining', 'time', 'down', 'ydstogo',
                'goal_to_go', 'yardline_100', 'posteam_score', 'defteam_score',
                'posteam_score_post', 'defteam_score_post', 'total_home_score', 'total_away_score',
                'home_timeouts_remaining', 'away_timeouts_remaining')
EVENT_FIELDS = ('play_type', 'play_type_nfl', 'no_play', 'play_deleted', 'desc', 'penalty',
                'penalty_type', 'penalty_team', 'penalty_yards', 'first_down_penalty',
                'first_down_pass', 'first_down_rush', 'third_down_converted', 'fourth_down_converted',
                'replay_or_challenge', 'replay_or_challenge_result', 'aborted_play',
                'quarter_end', 'pass_attempt', 'rush_attempt', 'sack', 'qb_dropback', 'qb_scramble',
                'qb_kneel', 'qb_spike', 'complete_pass', 'incomplete_pass', 'interception',
                'fumble', 'fumble_lost', 'touchdown', 'pass_touchdown', 'rush_touchdown',
                'return_touchdown', 'safety', 'punt_attempt', 'punt_blocked', 'kickoff_attempt', 'field_goal_attempt',
                'field_goal_result', 'extra_point_attempt', 'extra_point_result', 'two_point_attempt',
                'two_point_conv_result', 'defensive_two_point_attempt', 'defensive_two_point_conv',
                'defensive_extra_point_attempt', 'defensive_extra_point_conv', 'return_team',
                'yards_gained', 'passing_yards', 'rushing_yards', 'receiving_yards', 'return_yards',
                'lateral_rush', 'lateral_reception', 'lateral_return', 'lateral_recovery', 'fourth_down_failed')
ACTOR_FIELDS = ('passer_player_id', 'rusher_player_id', 'receiver_player_id', 'td_player_id',
                'td_team', 'lateral_rusher_player_id', 'lateral_receiver_player_id',
                'lateral_rushing_yards', 'lateral_receiving_yards', 'lateral_return_yards',
                'lateral_sack_player_id', 'lateral_interception_player_id', 'lateral_punt_returner_player_id',
                'lateral_kickoff_returner_player_id', 'lateral_fumble_recovery_player_id', 'kicker_player_id',
                'punter_player_id', 'kickoff_returner_player_id', 'punt_returner_player_id',
                'fumbled_1_player_id', 'fumbled_1_team', 'fumbled_2_player_id', 'fumbled_2_team',
                'fumble_recovery_1_player_id', 'fumble_recovery_1_team',
                'fumble_recovery_2_player_id', 'fumble_recovery_2_team')
BOUNDARY_FIELDS = ('drive_play_id_started', 'drive_play_id_ended', 'drive_start_transition',
                   'drive_end_transition', 'drive_start_yard_line', 'drive_end_yard_line',
                   'end_clock_time', 'end_yard_line')
PROJECTION_FIELDS = tuple(dict.fromkeys((*SCOPE_FIELDS, *STATE_FIELDS, *EVENT_FIELDS,
                                        *ACTOR_FIELDS, *BOUNDARY_FIELDS)))


def number(value):
    if value in (None, '') or type(value) is bool:
        return None
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return float(value) if value.is_finite() else None


def integer(value):
    value = number(value)
    return int(value) if value is not None and value == int(value) else None


def _side(value, sides):
    team = canonical_team(value) if value not in (None, '') else None
    return sides.index(team) if team in sides else None


def _phase(raw):
    if _flag(raw.get('two_point_attempt')) is True or _flag(raw.get('extra_point_attempt')) is True:
        return 'try'
    kind = raw.get('play_type')
    if kind == 'kickoff':
        return 'kickoff'
    if kind in {'pass', 'run', 'qb_kneel', 'qb_spike', 'punt', 'field_goal'}:
        return 'scrimmage'
    if kind == 'no_play' or _flag(raw.get('no_play')) is True:
        return 'penalty_or_no_play'
    if raw.get('play_type_nfl') in {'GAME_START', 'END_QUARTER', 'END_GAME', 'TIMEOUT'} or kind in {'quarter_end', 'time_out'}:
        return 'control'
    return 'unknown'


def state_before(raw, sides):
    """Scores use declared possession pre-scores, never game final-score columns."""
    problems = []
    off, defense = (_side(raw.get(k), sides) for k in ('posteam', 'defteam'))
    if off is None or defense is None or off == defense:
        problems.append('unknown_or_conflicting_sides')
    qtr = integer(raw.get('qtr'))
    half = 1 if qtr in (1, 2) else 2 if qtr in (3, 4) else None
    if half is None:
        problems.append('overtime_or_unknown_regulation_period')
    if raw.get('game_half') != ('Half1' if half == 1 else 'Half2' if half == 2 else None):
        problems.append('unknown_or_conflicting_half')
    remaining = number(raw.get('half_seconds_remaining'))
    quarter = number(raw.get('quarter_seconds_remaining'))
    game = number(raw.get('game_seconds_remaining'))
    if remaining is None or not 0 <= remaining <= 1800 or quarter is None or not 0 <= quarter <= 900:
        problems.append('invalid_half_or_quarter_clock')
    elif qtr in (1, 2, 3, 4) and remaining != quarter + (900 if qtr in (1, 3) else 0):
        problems.append('quarter_half_clock_disagreement')
    if half and (game is None or remaining is None or game != remaining + (1800 if half == 1 else 0)):
        problems.append('game_half_clock_disagreement')
    scores = [None, None]
    if off is not None and defense is not None and off != defense:
        for key, side in (('posteam_score', off), ('defteam_score', defense)):
            value = integer(raw.get(key))
            scores[side] = value if value is not None and value >= 0 else None
    if None in scores:
        problems.append('unknown_preplay_scores')
    phase = _phase(raw)
    down, distance, field = integer(raw.get('down')), number(raw.get('ydstogo')), number(raw.get('yardline_100'))
    if (field is None or not 0 <= field <= 100) and phase != 'control':
        problems.append('unknown_field_position')
    if phase == 'scrimmage' and (down not in (1, 2, 3, 4) or distance is None or distance < 0):
        problems.append('unknown_scrimmage_down_distance')
    if phase == 'unknown':
        problems.append('unknown_phase')
    return dict(possession_side=off, defense_side=defense, qtr=qtr, half=half,
                half_seconds_remaining=remaining, quarter_seconds_remaining=quarter,
                game_seconds_remaining=game, scores=scores, phase=phase, yardline100=field,
                down=down, distance=distance, problems=problems)


def _reported_post_scores(raw, state):
    values = [None, None]
    if state['possession_side'] is not None and state['defense_side'] is not None and state['possession_side'] != state['defense_side']:
        for key, side in (('posteam_score_post', state['possession_side']), ('defteam_score_post', state['defense_side'])):
            n = integer(raw.get(key))
            values[side] = n if n is not None and n >= 0 else None
    return values


def _typed_points(raw, state, sides):
    """Points belong to the native scorer's team, not to the initial offense."""
    points = [0, 0]
    reasons = []
    flags = {k:_flag(raw.get(k)) for k in ('touchdown', 'safety', 'field_goal_attempt',
             'extra_point_attempt', 'two_point_attempt', 'defensive_two_point_conv',
             'defensive_extra_point_conv')}
    if any(v is None for v in flags.values()):
        return None, ['unknown_scoring_event_flags']
    if flags['touchdown']:
        side = _side(raw.get('td_team'), sides)
        if side is None:
            reasons.append('unknown_touchdown_scoring_side')
        else:
            points[side] += 6
    for attempt, result, success, count in (
        ('field_goal_attempt', 'field_goal_result', 'made', 3),
        ('extra_point_attempt', 'extra_point_result', 'good', 1),
        ('two_point_attempt', 'two_point_conv_result', 'success', 2),
    ):
        if not flags[attempt]:
            continue
        value = raw.get(result)
        if value == success:
            side = state['possession_side']
            if side is None:
                reasons.append('unknown_kick_or_try_scoring_side')
            else:
                points[side] += count
        elif value not in {'missed', 'failed', 'failure', 'blocked', 'aborted'}:
            reasons.append('unknown_kick_or_try_result')
    if flags['safety']:
        side = state['defense_side']
        if side is None:
            reasons.append('unknown_safety_scoring_side')
        else:
            points[side] += 2
    if flags['defensive_two_point_conv'] or flags['defensive_extra_point_conv']:
        side = state['defense_side']
        if side is None:
            reasons.append('unknown_defensive_try_scoring_side')
        else:
            points[side] += 2
    if flags['defensive_two_point_conv'] and flags['defensive_extra_point_conv']:
        reasons.append('conflicting_defensive_try_types')
    return (None if reasons else points), reasons


PRODUCTION_FIELDS = ('official_pass_attempts', 'official_carries', 'official_targets', 'physical_plays',
                     'passing_yards', 'receiving_yards', 'rushing_yards', 'passing_TD',
                     'receiving_TD', 'rushing_TD', 'possessions')


def _production(raw, physical, choice, official, state, td_flags):
    """Numeric linked team credits or explicit unknown, never a missing-to-zero fill."""
    out = [dict.fromkeys(PRODUCTION_FIELDS, 0) for _ in range(2)]
    basis = {}; reasons = []; off = state['possession_side']
    if off is None:
        return [dict.fromkeys(PRODUCTION_FIELDS) for _ in range(2)], {}, ['production_side_unknown']
    c = out[off]
    c.update(official_pass_attempts=official['pass_attempts'], official_carries=official['rush_attempts'],
             official_targets=official['targets'], physical_plays=int(physical) if physical is not None else None,
             possessions=None)
    basis['possessions'] = 'PENDING_ORIGINAL_DRIVE_START_PROOF'
    for channel, field in (('pass_attempts','passing_yards'),('rush_attempts','rushing_yards')):
        n = official[channel]; value = number(raw.get(field))
        if n == 0:
            c[field] = 0
            basis[field] = 'source_proven_inapplicable_official_channel'
            if value not in (None, 0):
                reasons.append('positive_or_signed_yards_without_official_' + channel)
                c[field] = None
        elif n == 1 and channel == 'rush_attempts':
            c[field] = value
            basis[field] = 'source_official_rushing_yards' if value is not None else 'UNKNOWN'
        elif n == 1:
            complete, incomplete, intercepted = (_flag(raw.get(k)) for k in ('complete_pass','incomplete_pass','interception'))
            if complete is True and (incomplete is True or intercepted is True):
                c[field] = None
                reasons.append('conflicting_completion_outcome')
            elif complete is True and incomplete is False and intercepted is False:
                c[field] = value
                basis[field] = 'source_completed_pass_yards' if value is not None else 'UNKNOWN'
            elif choice == 'spike' or complete is False and (incomplete is True or intercepted is True):
                c[field] = 0 if value in (None, 0) else None
                basis[field] = 'explicit_noncompletion_or_spike_no_passing_yards'
            else:
                c[field] = None
                basis[field] = 'UNKNOWN_COMPLETION_OUTCOME'
        else:
            c[field] = None
            basis[field] = 'UNKNOWN_ELIGIBILITY'
    receive = number(raw.get('receiving_yards'))
    if c['official_pass_attempts'] == 0:
        c['receiving_yards'] = 0 if receive in (None, 0) else None
        basis['receiving_yards'] = 'source_proven_no_official_pass'
    elif c['passing_yards'] == 0 and (choice == 'spike' or _flag(raw.get('complete_pass')) is False and
                                   (_flag(raw.get('incomplete_pass')) is True or _flag(raw.get('interception')) is True)):
        c['receiving_yards'] = 0 if receive in (None, 0) else None
        basis['receiving_yards'] = 'explicit_noncompletion_or_spike_no_receiving_yards'
    elif _flag(raw.get('complete_pass')) is True and official['targets'] == 1:
        c['receiving_yards'] = receive
        basis['receiving_yards'] = 'source_initial_recipient_yards'
    else:
        c['receiving_yards'] = None
        basis['receiving_yards'] = 'UNKNOWN_RECEIVING_CREDIT'
    if c['passing_yards'] != c['receiving_yards']:
        reasons.append('linked_pass_receiving_yards_disagree')
    generic = _flag(raw.get('touchdown'))
    for field, flag, exposure in (('passing_TD','pass_touchdown','pass_attempts'),('rushing_TD','rush_touchdown','rush_attempts')):
        if td_flags[flag] is True:
            c[field] = 1
        elif generic is False or official[exposure] == 0:
            c[field] = 0
        elif td_flags[flag] is False:
            c[field] = 0
        else:
            c[field] = None
    c['receiving_TD'] = c['passing_TD'] if c['passing_TD'] == 0 or official['targets'] == 1 and _flag(raw.get('complete_pass')) is True else None
    for field, value in c.items():
        if field != 'possessions' and value is None:
            reasons.append('unknown_production_' + field)
    return out, basis, reasons


def _event(raw, state, sides):
    """Keep source actors/yard units; a target recipient census remains tri-state."""
    barriers = []
    physical = physical_membership(raw)
    choice = classify_choice(raw, physical)
    live, _ = _eligibility(raw)
    if state['phase'] == 'kickoff' or raw.get('play_type') in {'punt', 'field_goal', 'extra_point'}:
        if live is not True:
            barriers.append('unproven_native_kick_or_try_class')
    if physical is None or physical is True and choice is None:
        barriers.append('unknown_physical_or_call_shape')
    if _flag(raw.get('play_deleted')) is True:
        barriers.append('deleted_source_row')
    elif 'play_deleted' in raw and _flag(raw.get('play_deleted')) is None:
        barriers.append('unknown_deleted_status')
    if _flag(raw.get('replay_or_challenge')) is True:
        barriers.append('replay_or_challenge_not_independently_resolved')
    elif _flag(raw.get('replay_or_challenge')) is None:
        barriers.append('unknown_replay_status')
    p, r, sack = (_flag(raw.get(k)) for k in ('pass_attempt', 'rush_attempt', 'sack'))
    official = {'pass_attempts': None, 'rush_attempts': None, 'targets': None}
    excluded = raw.get('play_type') == 'no_play' or _flag(raw.get('no_play')) is True or _flag(raw.get('two_point_attempt')) is True
    if excluded or physical is False:
        official = dict.fromkeys(official, 0)
    elif physical is True and choice is not None:
        official['pass_attempts'] = int(p is True and sack is False)
        official['rush_attempts'] = int(r is True)
        if not official['pass_attempts'] or choice == 'spike':
            official['targets'] = 0
        elif re.fullmatch(r'00-\d{7}', str(raw.get('receiver_player_id') or '')):
            official['targets'] = 1
        else:
            barriers.append('unknown_target_recipient_census')
    for channel, field in (('pass_attempts', 'passer_player_id'), ('rush_attempts', 'rusher_player_id')):
        if official[channel] == 1 and not re.fullmatch(r'00-\d{7}', str(raw.get(field) or '')):
            barriers.append('unknown_' + channel + '_credit')
    for name in ('lateral_rush', 'lateral_reception', 'lateral_return', 'lateral_recovery'):
        if _flag(raw.get(name)) is not False:
            barriers.append('lateral_credit_chain_unproven')
    if any(raw.get(k) not in (None, '') for k in ACTOR_FIELDS if k.startswith('lateral_') and k.endswith('_id')) or any(number(raw.get(k)) not in (None, 0) for k in ACTOR_FIELDS if k.startswith('lateral_') and k.endswith('_yards')):
        barriers.append('reported_lateral_credit_evidence_unproven')
    post = _reported_post_scores(raw, state)
    delta = [b - a for a, b in zip(state['scores'], post)] if None not in state['scores'] + post else None
    if delta is None or any(v < 0 for v in delta):
        barriers.append('unknown_or_corrected_score_delta')
    typed_points, scoring_problems = _typed_points(raw, state, sides)
    barriers.extend(scoring_problems)
    if typed_points is not None and delta != typed_points:
        barriers.append('typed_event_vs_reported_score_disagreement')
    if (raw.get('play_type') == 'no_play' or _flag(raw.get('no_play')) is True) and typed_points != [0, 0]:
        barriers.append('no_play_scoring_conflict')
    if _flag(raw.get('fumble')) is True:
        barriers.append('unproven_full_fumble_possession_chain')
    td_flags = {k:_flag(raw.get(k)) for k in ('pass_touchdown', 'rush_touchdown', 'return_touchdown')}
    if sum(v is True for v in td_flags.values()) > 1:
        barriers.append('conflicting_physical_touchdown_types')
    if any(v is True for v in td_flags.values()) and _flag(raw.get('touchdown')) is not True:
        barriers.append('touchdown_subtype_without_physical_touchdown')
    if any(td_flags[k] is True for k in ('pass_touchdown', 'rush_touchdown')):
        if _side(raw.get('td_team'), sides) != state['possession_side'] or physical is not True:
            barriers.append('offensive_touchdown_side_or_physical_conflict')
    if td_flags['pass_touchdown'] is True and not (official['pass_attempts'] == 1 and official['targets'] == 1 and _flag(raw.get('complete_pass')) is True):
        barriers.append('passing_touchdown_without_completed_target_attempt')
    if td_flags['rush_touchdown'] is True and official['rush_attempts'] != 1:
        barriers.append('rushing_touchdown_without_official_carry')
    primary = sum(_flag(raw.get(k)) is True for k in ('touchdown','safety')) + int(_flag(raw.get('field_goal_attempt')) is True and raw.get('field_goal_result') == 'made')
    tries = sum(_flag(raw.get(k)) is True for k in ('extra_point_attempt','two_point_attempt'))
    if primary > 1 or tries > 1 or primary and tries:
        barriers.append('incompatible_primary_scoring_or_try_shapes')
    if sum(_flag(raw.get(k)) is True for k in ('punt_attempt','kickoff_attempt','field_goal_attempt','extra_point_attempt','two_point_attempt')) > 1:
        barriers.append('incompatible_kick_or_try_attempts')
    if _flag(raw.get('touchdown')) is True and not any(v is True for v in td_flags.values()):
        barriers.append('unknown_physical_touchdown_subtype')
    if (_flag(raw.get('punt_attempt')) is True or _flag(raw.get('kickoff_attempt')) is True or _flag(raw.get('field_goal_attempt')) is True or tries) and physical is True:
        barriers.append('kick_or_try_with_official_offensive_opportunity')
    if _flag(raw.get('penalty')) is None:
        barriers.append('unknown_penalty_status')
    elif _flag(raw.get('penalty')) is True and (number(raw.get('penalty_yards')) is None or not raw.get('penalty_type')):
        barriers.append('unknown_penalty_details')
    stats = [dict(), dict()]
    off = state['possession_side']
    if off is not None:
        stats[off] = dict(**official, physical_offensive_snaps=int(physical) if physical is not None else None,
                          net_offensive_yards=number(raw.get('yards_gained')) if physical is True else 0,
                          sacks=int(_flag(raw.get('sack'))) if _flag(raw.get('sack')) is not None else None)
        if physical is True and stats[off]['net_offensive_yards'] is None:
            barriers.append('unknown_signed_physical_yards')
        for key, flag in (('passing_tds', 'pass_touchdown'), ('rushing_tds', 'rush_touchdown')):
            stats[off][key] = int(td_flags[flag]) if td_flags[flag] is not None else None
    production, production_basis, production_barriers = _production(raw, physical, choice, official, state, td_flags)
    barriers.extend(production_barriers)
    if off is not None:
        stats[off].update(passing_tds=production[off]['passing_TD'],
                          receiving_tds=production[off]['receiving_TD'], rushing_tds=production[off]['rushing_TD'])
    point_types = [dict(), dict()]
    scorer = _side(raw.get('td_team'), sides)
    if _flag(raw.get('touchdown')) is True and scorer is not None:
        kind = next((name for name, flag in td_flags.items() if flag is True), 'other_touchdown')
        point_types[scorer][kind] = 6
    for attempt, result, success, name, points in (
        ('field_goal_attempt', 'field_goal_result', 'made', 'field_goal', 3),
        ('extra_point_attempt', 'extra_point_result', 'good', 'extra_point', 1),
        ('two_point_attempt', 'two_point_conv_result', 'success', 'two_point', 2),
    ):
        if _flag(raw.get(attempt)) is True and raw.get(result) == success and off is not None:
            point_types[off][name] = points
    defense = state['defense_side']
    if defense is not None:
        if _flag(raw.get('safety')) is True:
            point_types[defense]['safety'] = 2
        if _flag(raw.get('defensive_two_point_conv')) is True or _flag(raw.get('defensive_extra_point_conv')) is True:
            point_types[defense]['defensive_try'] = 2
    return dict(physical_offensive_snap=physical, choice=choice, official_counts=official,
                reported_post_scores=post, score_delta=delta, typed_points=typed_points,
                team_stats_by_side=stats, production_by_side=production, production_basis=production_basis,
                points_by_type=point_types,
                raw_actors={k:raw.get(k) for k in ACTOR_FIELDS},
                source_signed_yards={k:number(raw.get(k)) for k in ('yards_gained', 'passing_yards', 'rushing_yards', 'receiving_yards', 'return_yards')},
                barriers=barriers)


ADMIN_FLAGS = ('pass_attempt','rush_attempt','sack','qb_dropback','qb_scramble','qb_kneel','qb_spike',
               'complete_pass','incomplete_pass','touchdown','pass_touchdown','rush_touchdown',
               'return_touchdown','fumble','fumble_lost','interception','safety','punt_attempt',
               'kickoff_attempt','field_goal_attempt','extra_point_attempt','two_point_attempt',
               'defensive_two_point_attempt','defensive_two_point_conv','defensive_extra_point_attempt',
               'defensive_extra_point_conv','first_down_pass','first_down_rush','first_down_penalty',
               'third_down_converted','fourth_down_converted','fourth_down_failed','penalty',
               'replay_or_challenge','play_deleted','aborted_play','no_play','punt_blocked','lateral_rush','lateral_reception',
               'lateral_return','lateral_recovery')


def _typed_admin_shape(step):
    """NULL means structural NA only for these exact native zero-action markers."""
    r = step['raw']; kind = r.get('play_type_nfl')
    expected = {'GAME_START': (1, 'Half1', 900, 1800, 3600),
                'END_QUARTER': (2, 'Half1', 0, 0, 1800)}.get(kind)
    if expected is None:
        return None
    values = (integer(r.get('qtr')), r.get('game_half'), number(r.get('quarter_seconds_remaining')),
              number(r.get('half_seconds_remaining')), number(r.get('game_seconds_remaining')))
    if values != expected or r.get('play_type') not in (None, '', 'quarter_end'):
        return None
    if kind == 'END_QUARTER' and _flag(r.get('quarter_end')) is not True:
        return None
    if kind == 'GAME_START' and r.get('quarter_end') not in (None, '') and _flag(r.get('quarter_end')) is not False:
        return None
    # Missing values are not accepted generically: the native class and exact
    # phase/clock above are the only reason these event fields are structural NA.
    if any(r.get(k) not in (None, '') and _flag(r.get(k)) is not False for k in ADMIN_FLAGS):
        return None
    if any(r.get(k) not in (None, '') for k in ACTOR_FIELDS if not k.endswith('_yards')):
        return None
    if any(r.get(k) not in (None, '') and number(r.get(k)) != 0 for k in
           ('yards_gained','passing_yards','rushing_yards','receiving_yards','return_yards',
            'lateral_rushing_yards','lateral_receiving_yards','lateral_return_yards','penalty_yards')):
        return None
    if r.get('penalty_type') not in (None, '') or r.get('penalty_team') not in (None, '') or r.get('replay_or_challenge_result') not in (None, ''):
        return None
    if any(r.get(k) not in (None, '') for k in ('field_goal_result','extra_point_result','two_point_conv_result','return_team')):
        return None
    for field in ('posteam_score','defteam_score','posteam_score_post','defteam_score_post','total_home_score','total_away_score'):
        if r.get(field) not in (None, ''):
            value = integer(r[field])
            if value is None or value < 0 or kind == 'GAME_START' and value != 0:
                return None
    for before, after in (('posteam_score','posteam_score_post'),('defteam_score','defteam_score_post')):
        if r.get(before) not in (None, '') and r.get(after) not in (None, '') and number(r[before]) != number(r[after]):
            return None
    return kind


def _marker_scores_match(step, scores, sides):
    r = step['raw']
    for key, side in (('total_home_score',0),('total_away_score',1)):
        if r.get(key) not in (None, '') and integer(r[key]) != scores[side]:
            return False
    for team_field, keys in (('posteam',('posteam_score','posteam_score_post')),('defteam',('defteam_score','defteam_score_post'))):
        side = _side(r.get(team_field), sides)
        if r.get(team_field) not in (None, '') and side is None:
            return False
        for key in keys:
            if r.get(key) not in (None, '') and (side is None or integer(r[key]) != scores[side]):
                return False
    return True


def _qualified_kickoff(step, half):
    state = step['state_before']
    return (state['qtr'] == (1 if half == 1 else 3) and state['half'] == half
            and state['half_seconds_remaining'] == 1800 and state['phase'] == 'kickoff'
            and _flag(step['raw'].get('kickoff_attempt')) is True
            and not state['problems'] and not step['event']['barriers'])


def _certify_typed_admin_markers(steps, sides):
    """Corroborated zero markers are deterministic links, never sampled drives."""
    shapes = [_typed_admin_shape(s) for s in steps]
    for index, step in enumerate(steps):
        kind = shapes[index]
        if kind is None:
            continue
        if kind == 'GAME_START':
            following = index + 1
            while following < len(steps) and shapes[following] == 'GAME_START':
                following += 1
            if any(k != 'GAME_START' for k in shapes[:index]) or following == len(steps):
                continue
            nxt = steps[following]
            if not _qualified_kickoff(nxt, 1) or nxt['state_before']['scores'] != [0, 0]:
                continue
            scores = [0, 0]; previous = None
            intervening = steps[:following]
        else:
            previous = index - 1
            while previous >= 0 and shapes[previous] == 'END_QUARTER':
                previous -= 1
            following = index + 1
            while following < len(steps) and shapes[following] == 'END_QUARTER':
                following += 1
            if previous < 0 or following == len(steps):
                continue
            prev, nxt = steps[previous], steps[following]
            if (prev['state_before']['half'] != 1 or prev['state_before']['problems'] or prev['event']['barriers']
                    or not _qualified_kickoff(nxt, 2)):
                continue
            scores = prev['event']['reported_post_scores']
            if None in scores or scores != nxt['state_before']['scores']:
                continue
            intervening = steps[previous+1:following]
        if not all(_marker_scores_match(m, scores, sides) for m in intervening):
            continue
        boundary = dict(possession_side=None, defense_side=None, qtr=2 if kind == 'END_QUARTER' else 1,
                        half=1, half_seconds_remaining=0 if kind == 'END_QUARTER' else 1800,
                        quarter_seconds_remaining=0 if kind == 'END_QUARTER' else 900,
                        game_seconds_remaining=1800 if kind == 'END_QUARTER' else 3600,
                        scores=list(scores), phase='halftime' if kind == 'END_QUARTER' else 'game_start',
                        yardline100=None, down=None, distance=None, problems=[])
        step['typed_admin_marker'] = dict(certified=True, kind=kind, zero_official_counts=True,
            zero_physical_plays=True, zero_event_points=True, zero_event_seconds=True,
            source_only_not_pregame=True, null_event_fields='STRUCTURAL_NA_EXACT_NATIVE_MARKER_ONLY',
            preceding_score_play_id=steps[previous]['play_id'] if previous is not None else None,
            corroborating_kickoff_play_id=nxt['play_id'], scores=list(scores), boundary_state=boundary,
            raw_state_not_filled=True, deterministic_admin_marker_exclusion=True)


def reconstruct_game_transitions(rows, *, source_lineage, max_rows=200000):
    """Pure all-row projection. It deliberately has no source or model I/O."""
    read = clock(source_lineage.get('actual_read_at'))
    capture = clock(source_lineage.get('captured_at'))
    if read is None or capture is None or capture > read or not re.fullmatch(r'[a-f0-9]{64}', str(source_lineage.get('sha256', ''))):
        raise ValueError('Immutable source hash/capture/read clocks required')
    if source_lineage.get('all_source_rows_retained') is not True:
        raise ValueError('Explicit complete source projection receipt required')
    games, quarantine = defaultdict(list), []
    def quarantine_row(ordinal, raw, reason):
        gid = raw.get('game_id')
        native_game = isinstance(gid, str) and bool(re.fullmatch(r'(2023|2024|2026)_\d{2}_[A-Z]+_[A-Z]+', gid))
        native_year = integer(gid[:4]) if isinstance(gid, str) else None
        year = integer(raw.get('season'))
        explicit_outside = (raw.get('season_type') in {'PRE', 'POST'} or
                            year is not None and year not in (2023, 2024, 2026) and native_year == year)
        threat = 'EXPLICIT_OUT_OF_SCOPE' if explicit_outside else 'KNOWN_GAME' if native_game else 'GLOBAL_POSSIBLE_REG'
        quarantine.append(dict(source_ordinal=ordinal, raw=raw, reason=reason, threat=threat,
                               threatened_game_id=gid if threat == 'KNOWN_GAME' else None,
                               threatened_original_drive=integer(raw.get('drive'))))
    for ordinal, raw in enumerate(rows):
        if ordinal >= max_rows:
            raise ValueError('Reconstruction row cap exceeded')
        raw = deepcopy(raw)
        year, week, play = (integer(raw.get(k)) for k in ('season', 'week', 'play_id'))
        gid = raw.get('game_id')
        pieces = gid.split('_') if isinstance(gid, str) else []
        valid = (year in (2023, 2024, 2026) and week is not None and 1 <= week <= 18 and play is not None
                 and len(pieces) == 4 and pieces[:2] == [str(year), f'{week:02}'] and raw.get('season_type') == 'REG')
        if not valid:
            quarantine_row(ordinal, raw, 'invalid_or_out_of_contract_native_scope')
            continue
        home, away = (canonical_team(raw.get(k)) if raw.get(k) else None for k in ('home_team', 'away_team'))
        if home is None or away is None or home == away or {home, away} != {canonical_team(t) for t in pieces[2:]}:
            quarantine_row(ordinal, raw, 'invalid_native_home_away')
            continue
        state = state_before(raw, [home, away])
        step = dict(source_ordinal=ordinal, game_id=gid, play_id=str(play), source_order=number(raw.get('order_sequence')),
                    original_drive=integer(raw.get('drive')), fixed_drive=integer(raw.get('fixed_drive')),
                    raw=raw, state_before=state, event=_event(raw, state, [home, away]), next_observed_state=None,
                    next_play_id=None, elapsed_to_next=None, barriers=[])
        step['barriers'].extend(state['problems'] + step['event']['barriers'])
        games[gid].append(step)
    output = []
    global_threat = any(q['threat'] == 'GLOBAL_POSSIBLE_REG' for q in quarantine)
    for gid, steps in sorted(games.items()):
        threats = [q for q in quarantine if q['threatened_game_id'] == gid]
        keys = Counter(s['play_id'] for s in steps)
        orders = [s['source_order'] for s in steps]
        order_ok = None not in orders and len(set(orders)) == len(orders) and max(keys.values()) == 1
        sides = [[canonical_team(s['raw']['home_team']), canonical_team(s['raw']['away_team'])] for s in steps]
        if any(pair != sides[0] for pair in sides):
            order_ok = False
        if order_ok:
            steps.sort(key=lambda s:s['source_order'])
            if not threats and not global_threat:
                _certify_typed_admin_markers(steps, sides[0])
        for i, step in enumerate(steps):
            if threats:
                step['barriers'].append('possible_REG_quarantine_in_game')
            if global_threat:
                step['barriers'].append('unscopable_possible_REG_source_mass')
            if not order_ok:
                step['barriers'].append('unverified_game_order_or_side_orientation')
                continue
            if i + 1 == len(steps):
                step['barriers'].append('no_next_observed_row')
                continue
            nxt = steps[i+1]
            a = step['state_before']
            marker = nxt.get('typed_admin_marker')
            b = marker['boundary_state'] if marker and marker['kind'] == 'END_QUARTER' else nxt['state_before']
            step.update(next_observed_state=deepcopy(b), next_play_id=nxt['play_id'])
            step['next_state_binding'] = dict(kind='CERTIFIED_TYPED_ADMIN_BOUNDARY' if marker and marker['kind'] == 'END_QUARTER' else 'IMMEDIATE_NATIVE_ROW',
                                              source_play_id=nxt['play_id'])
            if a['half'] is None or a['half'] != b['half']:
                step['barriers'].append('half_or_regulation_boundary')
            elif a['half_seconds_remaining'] is None or b['half_seconds_remaining'] is None:
                step['barriers'].append('unknown_elapsed_clock')
            else:
                elapsed = a['half_seconds_remaining'] - b['half_seconds_remaining']
                if elapsed < 0:
                    step['barriers'].append('reversed_or_corrected_clock')
                else:
                    step['elapsed_to_next'] = elapsed
            if step['event']['reported_post_scores'] != b['scores']:
                step['barriers'].append('reported_post_vs_next_pre_score_disagreement')
            if b['problems']:
                step['barriers'].append('next_state_unqualified')
        output.append(dict(game_id=gid, sides=sides[0], native_order_verified=order_ok, rows=steps,
                           quarantine_threat_ordinals=[q['source_ordinal'] for q in threats],
                           global_quarantine_threat=global_threat))
    input_rows = sum(len(g['rows']) for g in output)+len(quarantine)
    if source_lineage.get('projected_rows') is not None and source_lineage['projected_rows'] != input_rows:
        raise ValueError('Source projection cardinality differs')
    return dict(version=VERSION, games=output, quarantine=quarantine, source_lineage=deepcopy(source_lineage),
                input_rows=input_rows,
                global_possible_REG_rows=sum(q['threat'] == 'GLOBAL_POSSIBLE_REG' for q in quarantine),
                explicit_out_of_scope_rows=sum(q['threat'] == 'EXPLICIT_OUT_OF_SCOPE' for q in quarantine),
                prediction_use='OBSERVED_STATE_LABELS_ONLY_NOT_PREGAME_FEATURES')


def _support(state):
    return dict(possession_side=state['possession_side'], phase=state['phase'],
                yardline100=state['yardline100'], half=state['half'])


def _terminal_proven(label, last):
    raw = last['raw']
    phase = last['state_before']['phase']
    if label == 'TOUCHDOWN':
        return _flag(raw.get('touchdown')) is True and last['event']['typed_points'] is not None
    if label in {'FIELD_GOAL', 'MISSED_FG'}:
        return phase == 'scrimmage' and _flag(raw.get('field_goal_attempt')) is True and raw.get('field_goal_result') == ('made' if label == 'FIELD_GOAL' else 'missed')
    if label == 'PUNT':
        return raw.get('play_type') == 'punt' and _flag(raw.get('punt_attempt')) is True and _flag(raw.get('punt_blocked')) is False
    if label == 'INTERCEPTION':
        return last['event']['official_counts']['pass_attempts'] == 1 and _flag(raw.get('interception')) is True
    if label == 'DOWNS':
        return _flag(raw.get('fourth_down_failed')) is True and last['event']['physical_offensive_snap'] is True
    if label == 'SAFETY':
        return _flag(raw.get('safety')) is True and last['event']['typed_points'] is not None
    if label in {'END_HALF', 'END_GAME'}:
        state = last['state_before']
        if (label == 'END_HALF' and last.get('next_state_binding', {}).get('kind') == 'CERTIFIED_TYPED_ADMIN_BOUNDARY'
                and last.get('next_observed_state', {}).get('phase') == 'halftime'):
            return True
        return (state['qtr'] == (2 if label == 'END_HALF' else 4)
                and state['half_seconds_remaining'] == 0
                and raw.get('play_type_nfl') in ({'END_QUARTER'} if label == 'END_HALF' else {'END_QUARTER', 'END_GAME'})
                and last['event']['typed_points'] == [0, 0])
    # Fumble/blocked-kick possession and half/game boundary composition require
    # separate proof, rather than metadata or a clock reaching zero alone.
    return False


def _boundary_endpoint(step):
    """A zero-clock native boundary, not the next half's field or elapsed time."""
    marker = step.get('typed_admin_marker')
    if marker and marker['certified'] and marker['kind'] == 'END_QUARTER':
        return deepcopy(marker['boundary_state'])
    label = step['raw'].get('drive_end_transition')
    if (label not in {'END_HALF', 'END_GAME'} or not _terminal_proven(label, step)
            or step['state_before']['half_seconds_remaining'] != 0
            or step['state_before']['problems'] or step['event']['barriers']
            or any(reason in step['barriers'] for reason in ('possible_REG_quarantine_in_game',
                   'unscopable_possible_REG_source_mass', 'unverified_game_order_or_side_orientation'))):
        return None
    result = deepcopy(step['state_before'])
    result.update(phase='halftime' if label == 'END_HALF' else 'regulation_end',
                  possession_side=None, defense_side=None, yardline100=None, down=None, distance=None)
    return result


def build_original_drive_blocks(reconstruction):
    """Certify contiguous source groups, never discard their unsupported mass.

    A reported drive ending at a TD does not imply the try or kickoff belongs
    to it. Their actual rows/groups remain in this ledger and need independent
    phase support. No kickoff or score default is introduced here.
    """
    if reconstruction.get('version') != VERSION:
        raise ValueError('Matched reconstruction version required')
    blocks = []; deterministic_markers = []
    for game in reconstruction['games']:
        runs = []; split = False
        for step in game['rows']:
            if step.get('typed_admin_marker', {}).get('certified'):
                deterministic_markers.append(dict(game_id=game['game_id'], play_id=step['play_id'], source_ordinal=step['source_ordinal'], source_order=step['source_order'], proof=deepcopy(step['typed_admin_marker'])))
                split = True
                continue
            if split or not runs or step['original_drive'] is None or runs[-1][0]['original_drive'] != step['original_drive']:
                runs.append([])
            runs[-1].append(step); split = False
        appearances = Counter(run[0]['original_drive'] for run in runs if run[0]['original_drive'] is not None)
        for ordinal, run in enumerate(runs):
            first, last = run[0], run[-1]
            reasons = []
            if not game['native_order_verified']:
                reasons.append('unverified_game_order')
            did = first['original_drive']
            if did is None or appearances[did] != 1:
                reasons.append('missing_or_noncontiguous_original_drive')
            for field, endpoint in (('drive_play_id_started', first), ('drive_play_id_ended', last)):
                values = {integer(s['raw'].get(field)) for s in run}
                if len(values) != 1 or None in values or str(next(iter(values))) != endpoint['play_id']:
                    reasons.append('unproven_' + field)
            start = first['state_before']
            if start['phase'] not in {'scrimmage', 'kickoff', 'try'}:
                reasons.append('unqualified_start_phase')
            physical_rows = [s for s in run if s['event']['physical_offensive_snap'] is True]
            possible_physical = any(s['event']['physical_offensive_snap'] is None for s in run)
            if not physical_rows and not possible_physical:
                possession_count, possession_basis = 0, 'source_proven_zero_offensive_phase_group'
            elif (physical_rows and not possible_physical and physical_rows[0] is first
                  and start['phase'] == 'scrimmage' and did is not None
                  and all(s['state_before']['possession_side'] == start['possession_side'] for s in physical_rows)
                  and integer(first['raw'].get('drive_play_id_started')) == integer(first['play_id'])):
                possession_count, possession_basis = 1, 'source_original_drive_first_physical_start'
            else:
                possession_count, possession_basis = None, 'UNKNOWN_OFFENSIVE_POSSESSION_START'
                reasons.append('unproven_offensive_possession_start')
            steps, prefixes = [], []
            totals = [dict(pass_attempts=0, rush_attempts=0, targets=0),
                      dict(pass_attempts=0, rush_attempts=0, targets=0)]
            points = [0, 0]
            cumulative = 0.
            prefix_ok = not reasons
            for s in run:
                local = list(s['barriers'])
                event = deepcopy(s['event'])
                for production in event['production_by_side']:
                    production['possessions'] = 0
                if s is first:
                    if start['possession_side'] is None:
                        local.append('unknown_possession_start_side')
                    else:
                        event['production_by_side'][start['possession_side']]['possessions'] = possession_count
                event['possession_start'] = dict(count=possession_count if s is first else 0,
                                                basis=possession_basis if s is first else 'not_original_drive_start')
                if any(v is None for side in event['production_by_side'] for v in side.values()):
                    local.append('unknown_runtime_production_vector')
                boundary = _boundary_endpoint(s) if s is last else None
                if boundary is not None:
                    # The boundary is certified from this row itself; a following
                    # halftime/OT/absent row does not supply its field or clock.
                    boundary_only = {'half_or_regulation_boundary', 'no_next_observed_row',
                                     'next_state_unqualified', 'reported_post_vs_next_pre_score_disagreement'}
                    local = [reason for reason in local if reason not in boundary_only]
                prefix_ok = prefix_ok and not local
                off = s['state_before']['possession_side']
                counts = s['event']['official_counts']
                if off is None or any(v is None for v in counts.values()):
                    prefix_ok = False
                    local.append('unqualified_team_official_counts')
                else:
                    for key, n in counts.items():
                        totals[off][key] += n
                delta = s['event']['score_delta']
                if delta is None:
                    prefix_ok = False
                else:
                    points = [a+b for a,b in zip(points, delta)]
                elapsed = 0. if boundary is not None else s['elapsed_to_next']
                if elapsed is None:
                    prefix_ok = False
                else:
                    cumulative += elapsed
                steps.append(dict(play_id=s['play_id'], source_ordinal=s['source_ordinal'],
                                  source_order=s['source_order'], state_before=deepcopy(s['state_before']),
                                  event=event, elapsed_to_next=elapsed,
                                  cumulative_elapsed_endpoint=cumulative if prefix_ok else None,
                                  next_observed_state=deepcopy(s['next_observed_state']),
                                  certified_endpoint=deepcopy(boundary or s['next_observed_state']), barriers=local))
                if prefix_ok:
                    prefixes.append(dict(through_play_id=s['play_id'], elapsed_seconds=cumulative,
                                         terminal_state=deepcopy(boundary or s['next_observed_state']),
                                         points_by_side=list(points), team_official_counts=deepcopy(totals)))
                reasons.extend(local)
            terminal = _boundary_endpoint(last) or last['next_observed_state']
            if terminal is None or terminal['phase'] not in {'scrimmage', 'kickoff', 'try', 'control', 'halftime', 'regulation_end'}:
                reasons.append('unqualified_terminal_observation')
            transitions = {s['raw'].get('drive_end_transition') for s in run}
            known_terminal = {'TOUCHDOWN', 'FIELD_GOAL', 'MISSED_FG', 'PUNT', 'DOWNS',
                              'INTERCEPTION', 'FUMBLE', 'END_HALF', 'END_GAME', 'SAFETY',
                              'BLOCKED_PUNT,_DOWNS', 'BLOCKED_FG,_DOWNS'}
            if len(transitions) != 1 or not transitions <= known_terminal:
                reasons.append('unproven_typed_original_drive_terminal')
            elif not _terminal_proven(next(iter(transitions)), last):
                reasons.append('terminal_metadata_without_event_proof')
            reasons = sorted(set(reasons))
            blocks.append(dict(game_id=game['game_id'], block_ordinal=ordinal, original_drive=did,
                               source_sides=list(game['sides']), source_row_count=len(run),
                               source_play_ids=[s['play_id'] for s in run],
                               physical_offensive_snap_count=sum(s['event']['physical_offensive_snap'] is True for s in run),
                               start_state=deepcopy(start), physical_start_support=_support(start),
                               steps=steps, certified_prefixes=prefixes,
                               possession_start=dict(count=possession_count, basis=possession_basis),
                               terminal_state=deepcopy(terminal), elapsed_seconds=cumulative if not reasons else None,
                               points_by_side=points if not reasons else None,
                               team_official_counts=totals if not reasons else None,
                               certified=not reasons, barriers=reasons))
    return dict(version='original_drive_trajectory_blocks_v1', blocks=blocks, deterministic_admin_markers=deterministic_markers,
                coverage=dict(deterministic_admin_marker_rows=len(deterministic_markers), all_groups=len(blocks), certified_groups=sum(b['certified'] for b in blocks),
                              uncertified_groups=sum(not b['certified'] for b in blocks),
                              quarantine_rows=len(reconstruction['quarantine']),
                              unsupported_probability='UNKNOWN_NOT_RENORMALIZED'),
                source_lineage=deepcopy(reconstruction['source_lineage']))


def opening_state_evidence(reconstruction):
    """Empirical TRAIN openings only with native kickoff and beginning evidence.

    Every game/half gets a status; a first observed offensive LOS is never used
    as a substitute for an unseen kickoff or coin-toss/return trajectory.
    """
    out = []
    def quiet_beginning(step):
        if step.get('typed_admin_marker', {}).get('certified') and step['typed_admin_marker']['kind'] == 'GAME_START':
            return True
        flags = ('pass_attempt','rush_attempt','sack','qb_dropback','qb_scramble','qb_kneel','qb_spike',
                 'complete_pass','incomplete_pass',
                 'touchdown','pass_touchdown','rush_touchdown','return_touchdown','fumble','interception',
                 'punt_attempt','kickoff_attempt','field_goal_attempt','extra_point_attempt','two_point_attempt',
                 'first_down_pass','first_down_rush','first_down_penalty','third_down_converted','fourth_down_converted')
        return (step['raw'].get('play_type_nfl') == 'GAME_START'
                and all(_flag(step['raw'].get(k)) is False for k in flags)
                and all(step['raw'].get(k) in (None, '') for k in ('passer_player_id','rusher_player_id','receiver_player_id','td_player_id'))
                and not step['state_before']['problems'] and not step['event']['barriers']
                and not any('quarantine' in reason or 'unverified_game_order' in reason for reason in step['barriers']))
    for game in reconstruction['games']:
        for half in (1, 2):
            rows = [r for r in game['rows'] if r['state_before']['half'] == half]
            first_action = next((r for r in rows if r['state_before']['phase'] != 'control'), None)
            reasons = []
            if first_action is None:
                reasons.append('no_observed_half_opening_action')
            else:
                s = first_action['state_before']
                if s['qtr'] != (1 if half == 1 else 3) or s['half_seconds_remaining'] != 1800:
                    reasons.append('opening_clock_not_proven')
                if s['phase'] != 'kickoff' or _flag(first_action['raw'].get('kickoff_attempt')) is not True:
                    reasons.append('first_action_not_proven_kickoff')
                reasons.extend(s['problems'] + first_action['event']['barriers'])
                if half == 1 and s['scores'] != [0, 0]:
                    reasons.append('nonzero_or_unknown_game_opening_score')
                prior = [r for r in game['rows'] if r['source_order'] is not None and first_action['source_order'] is not None and r['source_order'] < first_action['source_order']]
                if half == 1:
                    if not prior or any(not quiet_beginning(r) for r in prior):
                        reasons.append('native_game_beginning_unproven')
                else:
                    boundaries = [r for r in prior if _boundary_endpoint(r) is not None and r['state_before']['half'] == 1]
                    boundary = max(boundaries, key=lambda r:r['source_order']) if boundaries else None
                    if boundary is None or any(not quiet_beginning(r) for r in prior if r['source_order'] > boundary['source_order']):
                        reasons.append('native_first_half_end_unproven')
            if not game['native_order_verified']:
                reasons.append('unverified_game_order')
            if game.get('quarantine_threat_ordinals') or game.get('global_quarantine_threat'):
                reasons.append('possible_REG_quarantine_threatens_opening')
            out.append(dict(game_id=game['game_id'], source_half=half,
                            source_season=integer(game['rows'][0]['raw']['season']),
                            certified=not reasons, barriers=sorted(set(reasons)),
                            row_id=first_action['play_id'] if first_action else None,
                            start_state=deepcopy(first_action['state_before']) if first_action else None))
    return out
