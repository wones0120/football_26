from copy import deepcopy
import pytest
from backend.app.product_services.screen_matchup_response import build_screen_matchup_response
from backend.app.product_services.coverage_receiver_performance import VERSION as PARENT_VERSION


def fixture():
    expected=[];events=[];charts=[]
    for week in range(1,9):
        gid=f'2023_{week:02d}_BUF_MIA';expected.append(dict(game_id=gid,season=2023,week=week,game_date=f'2023-09-{week:02d}',sides=['BUF','MIA']))
        for play,off,defense in(('100','BUF','MIA'),('101','MIA','BUF')):
            epa=(2 if off=='BUF'else-2)if week<4 else(-10 if week==4 else-20)if off=='BUF'else 20
            events.append(dict(game_id=gid,play_id=play,offense=off,defense=defense,eligible_target_attempt=True,complete_pass=off=='BUF',target_play_EPA=epa))
            charts.append(dict(game_id=gid,play_id=play,season=2023,week=week,flags=dict(is_screen_pass=True)))
    parent=dict(version=PARENT_VERSION,season=2023,before_period=202607,expected_games=expected,event_basis=events,missing_PBP_game_ids=[],semantic_sha256='parent',pregame_serving_eligible=False)
    chart=dict(source=dict(snapshot_id='native',content_sha256='a'*64,source_uri='https://github.com/nflverse/nflverse-data/releases/download/ftn_charting/ftn_charting_2023.parquet'),rows=charts)
    return parent,chart


def build(p=None,c=None):
    a,b=fixture();return build_screen_matchup_response(p or a,c or b)


def profile(r):return next(p for p in r['profiles']if p['team']=='BUF')


def test_actual_opponent_strict_lag_response_reference_and_pooled_units():
    r=build();p=profile(r)
    assert p['strong_minus_weak_screen_EPA']==-10
    assert p['strong_minus_weak_screen_completion']==0
    assert r['reference']['known_defenses']==2
    row=next(x for x in r['game_rows']if x['team']=='BUF'and x['week']==4)
    assert row['opposing_prior_screen_defense']['max_contributing_period']==202303
    assert row['opposing_prior_screen_defense']['strength_group']=='weak'
    assert row['offense']['EPA_per_screen_attempt']==-10
    assert r['pregame_serving_eligible']is False and r['forecast']is None


def test_target_outcome_does_not_change_own_prior_opponent_context_or_reference():
    p,c=fixture();r=build(p,c);p['event_basis'][6]['target_play_EPA']=100
    changed=build(p,c)
    old=next(x for x in r['game_rows']if x['team']=='BUF'and x['week']==4)
    new=next(x for x in changed['game_rows']if x['team']=='BUF'and x['week']==4)
    assert old['opposing_prior_screen_defense']==new['opposing_prior_screen_defense']
    assert r['reference']==changed['reference']


def test_unknown_screen_flag_masks_eligible_exposure_never_air_yard_proxy():
    p,c=fixture();c['rows'][6]['flags']['is_screen_pass']=None
    r=build(p,c);row=next(x for x in r['game_rows']if x['team']=='BUF'and x['week']==4)
    assert row['offense']['unknown_screen_membership']==1 and row['offense']['exact_screen_attempts']is None
    assert row['offense']['known_screen_attempts']==0


def test_known_nonscreen_excludes_even_missing_attempt_or_outcome():
    p,c=fixture();p['event_basis'][6]['eligible_target_attempt']=None;p['event_basis'][6]['target_play_EPA']=None;c['rows'][6]['flags']['is_screen_pass']=False
    row=next(x for x in build(p,c)['game_rows']if x['team']=='BUF'and x['week']==4)
    assert row['offense']['exact_screen_attempts']==0 and row['offense']['EPA_per_screen_attempt']is None


def test_missing_native_source_does_not_skip_prior_scheduled_game():
    p,c=fixture();p['missing_PBP_game_ids']=['2023_02_BUF_MIA'];p['event_basis']=[e for e in p['event_basis']if e['game_id']!='2023_02_BUF_MIA']
    row=next(x for x in build(p,c)['game_rows']if x['team']=='BUF'and x['week']==4)
    lag=row['opposing_prior_screen_defense']
    assert '2023_02_BUF_MIA'in lag['contributing_game_ids']and lag['missing_source_games']==1
    assert lag['strength_group']is None


def test_unknown_condition_masks_exact_cells_in_addition_to_final_contrast():
    p,c=fixture();c['rows'][8]['flags']['is_screen_pass']=None
    r=build(p,c);a=profile(r)
    assert a['unknown_opponent_condition_game_ids']
    assert all(cell['EPA_per_screen_attempt']is None for cell in a['cells'].values())
    assert a['strong_minus_weak_screen_EPA']is None
    assert any(cell['known_screen_attempts']for cell in a['known_condition_sample'].values())


def test_missing_completion_epa_are_distinct_outcome_masks():
    p,c=fixture();p['event_basis'][6]['complete_pass']=None
    row=next(x for x in build(p,c)['game_rows']if x['team']=='BUF'and x['week']==4)
    assert row['offense']['completion_rate']is None and row['offense']['EPA_per_screen_attempt']==-10
    p['event_basis'][6]['complete_pass']=True;p['event_basis'][6]['target_play_EPA']=None
    row=next(x for x in build(p,c)['game_rows']if x['team']=='BUF'and x['week']==4)
    assert row['offense']['completion_rate']==1 and row['offense']['EPA_per_screen_attempt']is None


def test_missing_sides_mask_both_native_candidates_not_assign_by_target():
    p,c=fixture();p['event_basis'][6]['offense']=None;p['event_basis'][6]['defense']=None
    r=build(p,c)
    assert all(x['offense']['unknown_screen_membership']==1 for x in r['game_rows']if x['week']==4)


def test_raw_label_and_phase_native_key_contracts():
    p,c=fixture();c['rows'][0]['week']=2
    with pytest.raises(ValueError,match='period'):build(p,c)
    p,c=fixture();c['rows'].append(deepcopy(c['rows'][0]))
    with pytest.raises(ValueError,match='Duplicate FTN'):build(p,c)
    p,c=fixture();p['event_basis'].append(deepcopy(p['event_basis'][0]))
    with pytest.raises(ValueError,match='Unique expected'):build(p,c)
    p,c=fixture();c['source']['source_uri']='https://example.com/ftn_charting_2024.parquet'
    with pytest.raises(ValueError,match='exact-season'):build(p,c)


def test_degenerate_reference_and_zero_exposures_keep_undefined_groups():
    p,c=fixture()
    for e in p['event_basis']:e['target_play_EPA']=0
    r=build(p,c);assert r['reference']['nondegenerate']is False
    assert all(x['strong_minus_weak_screen_EPA']is None for x in r['profiles'])
    for row in c['rows']:row['flags']['is_screen_pass']=False
    r=build(p,c);assert r['reference']['known_defenses']==0
    assert all(x['offense']['EPA_per_screen_attempt']is None for x in r['game_rows'])


def test_prior_window_is_last_eight_scheduled_games_not_all_history():
    p,c=fixture()
    for week in(9,10):
        gid=f'2023_{week:02d}_BUF_MIA';p['expected_games'].append(dict(game_id=gid,season=2023,week=week,game_date=f'2023-09-{week:02d}',sides=['BUF','MIA']))
        for play,off,defense in(('100','BUF','MIA'),('101','MIA','BUF')):
            p['event_basis'].append(dict(game_id=gid,play_id=play,offense=off,defense=defense,eligible_target_attempt=True,complete_pass=True,target_play_EPA=1))
            c['rows'].append(dict(game_id=gid,play_id=play,season=2023,week=week,flags=dict(is_screen_pass=True)))
    row=next(r for r in build(p,c)['game_rows']if r['week']==10 and r['team']=='BUF')
    lag=row['opposing_prior_screen_defense']
    assert len(lag['contributing_game_ids'])==8
    assert lag['contributing_game_ids'][0]=='2023_02_BUF_MIA' and lag['max_contributing_period']==202309


def test_positive_screen_label_cannot_certify_unknown_official_eligibility():
    p,c=fixture();p['event_basis'][6]['eligible_target_attempt']=None
    row=next(r for r in build(p,c)['game_rows']if r['week']==4 and r['team']=='BUF')
    assert row['offense']['unknown_screen_membership']==1 and row['offense']['exact_screen_attempts']is None


def test_reference_cutpoints_cannot_label_pre_reference_game_contexts():
    p,c=fixture();original=build(p,c)
    for event in p['event_basis']:
        if event['game_id']=='2023_03_BUF_MIA':event['target_play_EPA']=1000
    changed=build(p,c)
    assert original['reference']!=changed['reference']
    for result in(original,changed):
        for row in result['game_rows']:
            if row['week']<4:
                for key in('lagged_screen_defense','opposing_prior_screen_defense'):
                    assert row[key]['strength_group']is None and row[key]['reference_ready']is False
                    assert row[key]['reference_available_from_period']==202304
        week2=next(row for row in result['game_rows']if row['team']=='BUF'and row['week']==2)
        assert week2['lagged_screen_defense']['EPA_per_screen_attempt']==-2 # Raw strict-prior measurement remains available.
