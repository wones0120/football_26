from copy import deepcopy
import pytest
from backend.app.product_services.historical_native_pace_diagnostic import build_historical_pace_diagnostic as build
from backend.app.product_services.personnel_package_continuity import PHYSICAL_VERSION


def fixture():
    schedule=[dict(game_id='2025_01_SF_LA',season=2025,week=1,game_type='REG',home_team='LAR',away_team='SF')]
    rows=[];projection=[]
    for play,order,clock in [(100,1,1000),(10,2,980),(50,3,970)]:
        raw=dict(game_id=schedule[0]['game_id'],play_id=play,season=2025,week=1,season_type='REG',posteam='SF',defteam='LAR',play_type='pass',play_type_nfl='PASS',no_play=0,two_point_attempt=0,pass_attempt=1,rush_attempt=0,sack=0,qb_dropback=1,qb_spike=0,qb_kneel=0,qb_scramble=0)
        rows.append(raw);projection.append(dict(game_id=raw['game_id'],play_id=play,season=2025,week=1,season_type='REG',order_sequence=order,fixed_drive=1,qtr=2,game_seconds_remaining=clock))
    return projection,dict(version=PHYSICAL_VERSION,season=2025,pregame_serving_eligible=False,rows=rows),schedule


def run(a):return build(*a,season=2025)
def metric(b):return next(r['metrics']['G01-M04'] for r in b['pace_rows'] if r['team']=='SF')


def test_native_order_not_play_id_sort_and_pooled_seconds():
    b=run(fixture());m=metric(b)
    assert m['known_outcome_events']==2 and m['observed_outcome_sum']==30 and m['value']==15
    assert b['native_order_proof']['game_proofs'][0]['play_id_order_matches_native_order'] is False


def test_zero_clock_interval_retained_not_missing():
    a=fixture();a[0][1]['game_seconds_remaining']=1000
    m=metric(run(a));assert m['known_outcome_events']==2 and m['observed_outcome_sum']==30


def test_all_native_controls_break_adjacency():
    a=fixture();a[1]['rows'][1].update(play_type=None,play_type_nfl='TIMEOUT',pass_attempt=0,qb_dropback=0)
    m=metric(run(a));assert m['known_outcome_events']==0 and m['unknown_eligibility_events']==0 and m['value'] is None


def test_positive_control_is_unknown_not_quiet_break():
    a=fixture();a[1]['rows'][1].update(play_type=None,play_type_nfl='TIMEOUT',pass_attempt=0,first_down_pass=1)
    m=metric(run(a));assert m['unknown_eligibility_events']==2 and m['value'] is None


@pytest.mark.parametrize('field,value',[('fixed_drive',None),('qtr',None),('game_seconds_remaining',None),('game_seconds_remaining',1001)])
def test_unknown_or_increasing_clock_masks_exact(field,value):
    a=fixture();a[0][1][field]=value
    m=metric(run(a));assert m['unknown_eligibility_events']>0 and m['value'] is None


@pytest.mark.parametrize('field',['fixed_drive','qtr'])
def test_known_boundary_does_not_create_interval(field):
    a=fixture();a[0][1][field]=3;a[0][2][field]=3
    m=metric(run(a));assert m['known_outcome_events']==1 and m['value']==10


def test_missing_or_duplicate_native_order_masks_whole_game():
    for value in (None,1):
        a=fixture();a[0][1]['order_sequence']=value
        m=metric(run(a));assert m['native_order_verified'] is False and m['value'] is None


def test_missing_control_key_cannot_silently_shrink_universe():
    a=fixture();a[0].pop(1)
    with pytest.raises(ValueError,match='Entire REG'):run(a)


def test_duplicate_play_key_is_rejected():
    a=fixture();a[0].append(deepcopy(a[0][0]))
    with pytest.raises(ValueError,match='Duplicate'):run(a)


def test_unknown_offense_possible_physical_masks_both_candidates():
    a=fixture();a[1]['rows'][1]['posteam']=None
    b=run(a)
    assert all(r['metrics']['G01-M04']['unknown_eligibility_events'] for r in b['pace_rows'])
    pair=b['physical_pair_rows'][0]
    assert pair['values']==[None,None]


def test_missing_opposite_source_log_is_not_known_zero():
    b=run(fixture());assert b['physical_pair_rows'][0]['values']==[None,3]
    assert next(r for r in b['pace_rows'] if r['team']=='LAR')['metrics']['G01-M04']['value'] is None


def test_source_phase_and_boundary_not_backfilled():
    a=fixture()
    post=deepcopy(a[0][0]);post.update(game_id='2025_19_SF_LA',week=19,season_type='POST');a[0].append(post)
    assert run(a)['source_keys']==3


def test_reference_labels_not_exported_before_week4():
    b=run(fixture());row=b['joint_diagnostic']['game_rows'][0]
    assert row['home_prior_group'] is None and row['away_prior_group'] is None
