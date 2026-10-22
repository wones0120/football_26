from copy import deepcopy
import pytest

from backend.app.tests.product.test_defense_context_evidence import play, SOURCE, CUTOFF, IDS
from backend.app.product_services.opportunity_events import build_event_evidence
from backend.app.product_services.environment_context_evidence import build_environment_context_evidence


def event(number=1,**changes):
    return play(number,**(dict(fixed_drive=1,qtr=1,game_seconds_remaining=3500-number*20,
        score_differential=0,down=1,no_huddle=0,xpass=0.6,pass_oe=40)|changes))


def build(rows,**kwargs):
    receipt=dict(event_evidence=build_event_evidence(rows,canonical_ids=IDS,source_receipt=SOURCE,cutoff=CUTOFF))
    return build_environment_context_evidence(receipt,before_period=202606,cutoff=CUTOFF,**kwargs)


def m(result,key):return result['team_windows'][0]['metrics'][key]


def test_physical_snap_union_call_scramble_sack_spike_kneel_no_double_add():
    rows=[event(),event(2,sack=1),event(3,play_type='run',pass_attempt=0,rush_attempt=1,qb_scramble=1),
        event(4,play_type='run',pass_attempt=0,rush_attempt=1,qb_dropback=0),event(5,qb_spike=1),
        event(6,play_type='run',pass_attempt=0,rush_attempt=1,qb_dropback=0,qb_kneel=1),
        event(7,two_point_attempt=1),event(8,play_type='no_play')]
    result=build(rows);team=result['team_windows'][0]
    assert team['offensive_play_volume']['known_offensive_snaps']==6
    assert m(result,'G02-M01')['known_outcome_events']==4
    assert m(result,'G02-M01')['observed_known_mean']==0.75
    assert team['observed_drive_volume']['observed_native_drives']==1


def test_clock_start_proxy_no_skipping_unknown_and_explicit_drive_quarter_rejections():
    result=build([event(),event(2),event(3,play_type=None),event(4),event(5,fixed_drive=2),event(6,fixed_drive=2,qtr=2)])
    assert m(result,'G01-M04')['known_outcome_events']==1
    assert m(result,'G01-M04')['observed_known_mean']==20
    assert m(result,'G01-M04')['unknown_eligibility_events']==2
    assert result['game_rows'][0]['interval_rejections']['drive_change']==1
    assert result['game_rows'][0]['interval_rejections']['quarter_unknown_or_change']==1


def test_same_offense_key_cannot_skip_opponent_interruption():
    result=build([event(),event(2,posteam='MIA',defteam='BUF',passer_player_id='other-q',receiver_player_id='other-w'),event(3)])
    assert all(t['metrics']['G01-M04']['known_outcome_events']==0 for t in result['team_windows'])


def test_zero_clock_interval_retained_nonmonotonic_and_missing_not_zero():
    result=build([event(game_seconds_remaining=3500),event(2,game_seconds_remaining=3500),
        event(3,game_seconds_remaining=3510),event(4,game_seconds_remaining=None)])
    assert m(result,'G01-M04')['known_outcome_events']==1
    assert m(result,'G01-M04')['observed_known_mean']==0
    assert m(result,'G01-M04')['unknown_outcome_events']==2


def test_preplay_neutral_leading_trailing_down_zone_known_and_unknown():
    rows=[event(),event(2,score_differential=8,down=3,yardline_100=40),
        event(3,score_differential=-3,down=2,yardline_100=5),event(4,qtr=4,score_differential=0),
        event(5,qtr=None,score_differential=None,down=None,yardline_100=None)]
    result=build(rows)
    assert m(result,'G02-M02')['known_outcome_events']==2
    assert m(result,'G02-M02')['unknown_eligibility_events']==1
    assert m(result,'G02-M09')['known_outcome_events']==1
    assert m(result,'G02-M10')['known_outcome_events']==1
    assert m(result,'G02-M04')['known_outcome_events']==3
    assert m(result,'G02-M08')['known_outcome_events']==3


def test_vendor_xpass_is_supplied_measurement_not_fitted_model_and_missing_remains_null():
    result=build([event(xpass=0.75),event(2,play_type='run',pass_attempt=0,rush_attempt=1,qb_dropback=0,xpass=0.25),
        event(3,xpass=None),event(4,xpass=2)])
    assert m(result,'G02-M03')['observed_known_mean']==0
    assert m(result,'G02-M03')['known_outcome_events']==2
    assert m(result,'G02-M03')['unknown_outcome_events']==2
    assert result['game_rows'][0]['vendor_fields']['pass_oe_known']==4
    assert result['forecast'] is None


def test_observed_windows_pool_exposure_missing_drive_and_no_complete_possessions():
    result=build([event(),event(2,game_id='2026_02_BUF_MIA',week=2),
        event(3,game_id='2026_02_BUF_MIA',week=2,fixed_drive=None)])
    team=result['team_windows'][0]
    assert team['offensive_play_volume']['known_snaps_per_observed_log']==1.5
    assert team['observed_drive_volume']['observed_native_drives']==2
    assert team['observed_drive_volume']['unknown_drive_snap_ids']==1
    assert build([event(),event(2,game_id='2026_02_BUF_MIA',week=2)],last_n_games=1)['team_windows'][0]['offensive_play_volume']['observed_game_logs']==1


def test_event_order_stable_native_numeric_order_and_material_context_changes_hash():
    rows=[event(1,game_seconds_remaining=3500),event(2,game_seconds_remaining=3480),event(10,game_seconds_remaining=3460)]
    a=build(rows);b=build(list(reversed(rows)))
    assert a['semantic_measurements_sha256']==b['semantic_measurements_sha256']
    assert m(a,'G01-M04')['observed_known_mean']==20
    rows[1]['score_differential']=10
    assert a['semantic_measurements_sha256']!=build(rows)['semantic_measurements_sha256']


def test_future_scope_checksum_and_window_validation():
    with pytest.raises(ValueError,match='future'):build([event(week=6,game_id='2026_06_BUF_MIA')])
    for size in (0,True,33):
        with pytest.raises(ValueError,match='window'):build([],last_n_games=size)
    assert build([])['team_windows']==[]


@pytest.mark.parametrize('group',['unscoped_nonoffensive_rows','scoped_administrative_rows'])
def test_actual_outer_retained_controls_break_timeline_without_fake_offense(group):
    receipt=dict(event_evidence=build_event_evidence([event(1),event(3)],canonical_ids=IDS,source_receipt=SOURCE,cutoff=CUTOFF))
    receipt[group]=[dict(game_id='2026_01_BUF_MIA',play_id='2',season=2026,week=1,season_type='REG',posteam=None,play_type='no_play')]
    result=build_environment_context_evidence(receipt,before_period=202606,cutoff=CUTOFF)
    assert m(result,'G01-M04')['known_outcome_events']==0
    assert result['team_windows'][0]['offensive_play_volume']['known_offensive_snaps']==2
    assert result['adjacency_control_breaks'][0]['play_id']=='2'
    assert result['game_rows'][0]['interval_rejections']['source_control_break']==1
    receipt[group][0]['week']=6
    with pytest.raises(ValueError,match='prior native scope'):
        build_environment_context_evidence(receipt,before_period=202606,cutoff=CUTOFF)
