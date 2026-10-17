from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.app.product_services.espn_markets import parse_scoreboard
from backend.app.product_services.showdown_data_readiness import refresh_live_sources

NOW = datetime(2026, 10, 10, 20, tzinfo=UTC)
GAME = {'game_id': '2026_05_CHI_GB', 'home_team': 'GB', 'away_team': 'CHI',
        'kickoff_at': '2026-10-11T17:00:00Z'}


def payload():
    return {'season': {'year': 2026, 'type': 2}, 'week': {'number': 5}, 'events': [{
        'id': 'espn-1', 'competitions': [{
            'date': GAME['kickoff_at'], 'status': {'type': {'state': 'pre'}},
            'competitors': [{'homeAway': 'home', 'team': {'abbreviation': 'GB'}},
                            {'homeAway': 'away', 'team': {'abbreviation': 'CHI'}}],
            'odds': [{'provider': {'id': '100', 'name': 'DraftKings'}, 'overUnder': 46.5,
                      'pointSpread': {'home': {'close': {'line': '+1.5'}, 'open': {'line': '-3'}},
                                      'away': {'close': {'line': '-1.5'}}},
                      'total': {'over': {'close': {'line': 'o46.5'}},
                                'under': {'close': {'line': 'u46.5'}}}}]}]}]}


def parse(p, games=None, now=NOW):
    return parse_scoreboard(p, schedule=games or [GAME], season=2026, week=5, captured_at=now)


def test_current_lines_keep_home_underdog_sign_and_original_provenance():
    rows, rejected = parse(payload())
    assert not rejected
    row = rows[0]
    assert row.home_spread == 1.5 and row.game_total == 46.5
    assert row.home_implied_total == 22.5 and row.away_implied_total == 24
    assert row.source == 'espn_draftkings' and row.source_game_id == 'espn-1'
    assert row.observed_at == NOW and row.provider_updated_at is None


@pytest.mark.parametrize('case', ['missing', 'duplicate', 'kickoff', 'live', 'book', 'no_current',
                                  'spread', 'total', 'nan', 'unknown_team'])
def test_invalid_or_incomplete_lines_do_not_qualify(case):
    p = payload(); c = p['events'][0]['competitions'][0]; q = c['odds'][0]
    if case == 'missing': p['events'] = []
    elif case == 'duplicate': p['events'].append(deepcopy(p['events'][0]))
    elif case == 'kickoff': c['date'] = '2026-10-11T20:25:00Z'
    elif case == 'live': c['status']['type']['state'] = 'in'
    elif case == 'book': q['provider']['name'] = 'Other'
    elif case == 'no_current': del q['pointSpread']['home']['close']
    elif case == 'spread': q['pointSpread']['away']['close']['line'] = '+1.5'
    elif case == 'total': q['total']['under']['close']['line'] = 'u44.5'
    elif case == 'nan': q['pointSpread']['home']['close']['line'] = 'NaN'
    elif case == 'unknown_team': c['competitors'][0]['team']['abbreviation'] = 'UNKNOWN'
    rows, rejected = parse(p)
    assert not rows and len(rejected) == 1


def test_wrong_week_and_postlock_rejected_and_complete_scope_required():
    p = payload(); p['week']['number'] = 4
    with pytest.raises(ValueError, match='season/week'): parse(p)
    rows, rejected = parse(payload(), now=NOW + timedelta(days=1))
    assert not rows and rejected
    rows, rejected = parse(payload(), games=[GAME, {**GAME, 'game_id': 'missing', 'away_team': 'DAL'}])
    assert len(rows) == 1 and rejected[0]['game_id'] == 'missing'


@pytest.mark.parametrize('label', ['Classic', 'Showdown'])
def test_failed_refresh_blocks_build_instead_of_reusing_old_lines(label):
    with patch('backend.app.product_services.slate_preparation.slate_games', return_value=[GAME]), \
         patch('backend.app.product_services.slate_preparation.require_prelock', return_value=NOW + timedelta(days=1)), \
         patch('backend.app.product_services.slate_preparation.capture_source', side_effect=ValueError('missing total')), \
         patch('backend.app.product_services.showdown_data_readiness._refresh_player_sources') as players, \
         patch('backend.app.product_services.slate_preparation.execute_preparation') as build:
        result = refresh_live_sources(SimpleNamespace(engine=None), season=2026, week=5,
                                      slate='SUNDAY_MAIN', params={}, label=label)
    assert result['projection_run_id'] is None
    assert result['report']['projection']['status'] == 'blocked'
    assert 'missing total' in result['report']['projection']['reason']
    players.assert_not_called(); build.assert_not_called()


@pytest.mark.parametrize('name', ['DraftKings', 'Draft Kings'])
def test_draftkings_provider_display_names_require_canonical_provider_id(name):
    p = payload()
    q = p['events'][0]['competitions'][0]['odds'][0]
    q['provider']['name'] = name
    rows, rejected = parse(p)
    assert len(rows) == 1 and not rejected
    q['provider']['id'] = 'other'
    rows, rejected = parse(p)
    assert not rows and rejected


def test_duplicate_draftkings_display_names_remain_ambiguous():
    p = payload()
    odds = p['events'][0]['competitions'][0]['odds']
    odds.append(deepcopy(odds[0]))
    odds[1]['provider']['name'] = 'Draft Kings'
    rows, rejected = parse(p)
    assert not rows and 'ambiguous' in rejected[0]['reason']
