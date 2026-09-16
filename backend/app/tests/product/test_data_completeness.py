from backend.app.product_services.data_completeness import historical_actual_plan, salary_identity_plan


def fixtures():
    aliases = [dict(source_system='nflreadpy', source_key='gsis1', player_master_id='canonical1')]
    raw = dict(raw_nfl_weekly_stat_id=1, ingest_run_id='raw-run', player_id='gsis1', player_name='Example',
               season=2025, week=17, team='DAL', opponent='WAS', position='WR', game_id=None,
               raw_row_json={'receptions':5,'receiving_yards':46})
    game = dict(season=2025, week=17, home_team_id='WAS', away_team_id='DAL', game_id='game1')
    return aliases, raw, game


def test_history_uses_native_identity_and_game_context():
    aliases, raw, game = fixtures()
    plan = historical_actual_plan([raw], [game], aliases, [])
    assert plan[0]['status'] == 'missing'
    assert plan[0]['record']['player_id'] == 'canonical1'
    assert abs(plan[0]['record']['dk_points'] - 9.6) < 1e-8
    assert plan[0]['raw_id'] == 1


def test_history_preserves_existing_and_rejects_conflicting_games():
    aliases, raw, game = fixtures()
    existing = [dict(season=2025, week=17, player_id='canonical1', game_id='game1')]
    assert historical_actual_plan([raw], [game], aliases, existing)[0]['status'] == 'existing'
    raw['game_id'] = 'wrong_game'
    assert historical_actual_plan([raw], [game], aliases, [])[0]['status'] == 'game_review'


def test_history_does_not_resolve_by_display_name():
    aliases, raw, game = fixtures()
    raw['player_id'] = 'unknown'
    assert historical_actual_plan([raw], [game], aliases, [])[0]['status'] == 'identity_review'


def test_history_quarantines_conflicting_source_snapshots():
    aliases, raw, game = fixtures()
    conflicting = {**raw,'raw_nfl_weekly_stat_id':2,'raw_row_json':{'receptions':8}}
    assert historical_actual_plan([raw,conflicting], [game], aliases, [])[0]['status'] == 'conflicting_source_review'


def test_salary_requires_same_week_team_position_then_native_roster_id():
    aliases, _, _ = fixtures()
    salary = dict(season=2026, week=1, team='NO', position='RB', player_name='Example Jr.', source_player_key='dk1')
    roster = dict(season=2026, week=1, team='NO', position='RB', player_name='Example', gsis_id='gsis1',
                  raw_nfl_weekly_roster_id=1, ingest_run_id='roster-run')
    assert salary_identity_plan([salary], [roster], aliases)[0]['player_master_id'] == 'canonical1'
    assert salary_identity_plan([salary], [{**roster,'team':'JAX'}], aliases)[0]['status'] == 'review'
    assert salary_identity_plan([salary], [{**roster,'week':2}], aliases)[0]['status'] == 'review'
    assert salary_identity_plan([salary], [{**roster,'position':'WR'}], aliases)[0]['status'] == 'review'


def test_salary_unidentified_roster_collision_stays_in_review():
    aliases, _, _ = fixtures()
    salary = dict(season=2026, week=1, team='NO', position='RB', player_name='Example', source_player_key='dk1')
    roster = dict(season=2026, week=1, team='NO', position='RB', player_name='Example', gsis_id='gsis1',
                  raw_nfl_weekly_roster_id=1, ingest_run_id='roster-run')
    assert salary_identity_plan([salary], [roster,{**roster,'gsis_id':None}], aliases)[0]['status'] == 'review'


def test_unique_schedule_repairs_relocated_self_opponent():
    aliases, raw, game = fixtures()
    raw.update(team='OAK',opponent='LV')
    game.update(home_team_id='LV',away_team_id='LAC')
    result=historical_actual_plan([raw],[game],aliases,[])[0]
    assert result['record']['team_id']=='LV'
    assert result['record']['opponent_team_id']=='LAC'
    assert result['game_policy']=='unique_schedule_game_corrects_self_opponent'


def test_persisted_alias_still_requires_team_and_position():
    aliases, _, _ = fixtures()
    aliases[0].update(alias_name='Example',team='NO',position='RB')
    salary=dict(season=2026,week=1,team='NO',position='RB',player_name='Example Jr.',source_player_key='dk1')
    assert salary_identity_plan([salary],[],aliases)[0]['player_master_id']=='canonical1'
    assert salary_identity_plan([{**salary,'team':'JAX'}],[],aliases)[0]['status']=='review'


def test_actual_scoring_retains_negatives_and_does_not_penalize_missed_kicks():
    from backend.app.product_services.data_completeness import archived_dk_points
    from backend.app.services.simulation import calculate_dk_points
    assert archived_dk_points({'fumbles_lost':1}, 'WR') == -1
    assert calculate_dk_points({'fumbles_lost':1}) == 0  # legacy model behavior is unchanged
    assert archived_dk_points({'fg_made_50_59':1,'fg_missed':2,'pat_made':2}, 'K') == 7


def test_multiple_native_players_cannot_share_historical_canonical_identity():
    aliases, raw, game = fixtures()
    aliases.append(dict(source_system='nflreadpy',source_key='different-person',player_master_id='canonical1'))
    other={**raw,'raw_nfl_weekly_stat_id':2,'player_id':'different-person','team':'WAS','opponent':'DAL'}
    plan=historical_actual_plan([raw,other],[game],aliases,[])
    assert [row['status'] for row in plan]==['identity_review','identity_review']
    assert all('record' not in row for row in plan)
