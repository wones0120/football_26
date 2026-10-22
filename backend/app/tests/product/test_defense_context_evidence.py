from copy import deepcopy

import pytest

from backend.app.product_services.opportunity_events import build_event_evidence
from backend.app.product_services.defense_context_evidence import build_defense_context_evidence

CUTOFF='2026-10-19T20:00:00Z'
SOURCE=dict(snapshot_id='frozen-test',content_sha256='a'*64,captured_at='2026-10-19T19:00:00Z',
    received_at='2026-10-19T19:00:00Z',verification='snapshot_artifact_sha256_verified')
IDS={'q':'00000000-0000-0000-0000-000000000001','w':'00000000-0000-0000-0000-000000000002'}


def play(number=1,**changes):
    return dict(dict(game_id='2026_01_BUF_MIA',play_id=number,season=2026,week=1,season_type='REG',
        posteam='BUF',defteam='MIA',play_type='pass',pass_attempt=1,rush_attempt=0,sack=0,
        qb_dropback=1,qb_spike=0,qb_kneel=0,qb_scramble=0,two_point_attempt=0,
        passer_player_id='q',receiver_player_id='w',rusher_player_id='q',yardline_100=5,
        yards_gained=20,epa=0.5,rush_touchdown=0),**changes)


def build(rows,source=None,**kwargs):
    receipt=dict(event_evidence=build_event_evidence(rows,canonical_ids=IDS,source_receipt=source or SOURCE,cutoff=CUTOFF))
    return build_defense_context_evidence(receipt,before_period=202606,cutoff=CUTOFF,**kwargs)


def metric(result,key):
    return result['team_windows'][0]['metrics'][key]


def test_pass_explosive_separate_from_dropback_and_scramble_rushing_td():
    result=build([play(),play(2,sack=1,yards_gained=-8,epa=-1),
        play(3,play_type='run',pass_attempt=0,rush_attempt=1,qb_scramble=1,yards_gained=25,epa=1,rush_touchdown=1),
        play(4,qb_spike=1,epa=-0.5),
        play(5,play_type='run',pass_attempt=0,rush_attempt=1,qb_dropback=0,qb_kneel=1,epa=-1),
        play(6,two_point_attempt=1),play(7,play_type='no_play')])
    assert metric(result,'G14-M07')['eligible_events']==1
    assert metric(result,'G14-M07')['observed_known_mean']==1
    assert metric(result,'G14-M09')['eligible_events']==3
    assert metric(result,'G14-M09')['observed_known_mean']==pytest.approx(2/3)
    assert metric(result,'G15-M01')['eligible_events']==1
    assert metric(result,'G15-M09')['observed_known_mean']==1
    assert result['forecast'] is None


def test_per_metric_denominators_and_missing_outcomes_are_not_zero():
    result=build([play(1,play_type='run',pass_attempt=0,rush_attempt=1,qb_dropback=0,epa=None,yards_gained=0,rush_touchdown=None),
        play(2,play_type='run',pass_attempt=0,rush_attempt=1,qb_dropback=0,epa=0,yards_gained=None,yardline_100=None),
        play(3,play_type='run',pass_attempt=0,rush_attempt=1,qb_dropback=0,qb_kneel=None)])
    success=metric(result,'G15-M01');stuff=metric(result,'G15-M04');td=metric(result,'G15-M09')
    assert success['eligible_events']==2 and success['unknown_eligibility_events']==1
    assert success['known_outcome_events']==1 and success['observed_known_mean']==0
    assert success['unknown_outcome_events']==1 and success['all_eligible_mean'] is None
    assert stuff['observed_known_mean']==1 and stuff['unknown_outcome_events']==1
    assert td['unknown_eligibility_events']==2 and td['unknown_outcome_events']==1
    assert metric(result,'G14-M07')['observed_known_mean'] is None


def test_window_pools_exposures_instead_of_averaging_game_rates():
    rows=[play(1,yards_gained=0),play(2,game_id='2026_02_BUF_MIA',week=2),play(3,game_id='2026_02_BUF_MIA',week=2),
        play(4,game_id='2026_02_BUF_MIA',week=2)]
    result=build(rows)
    assert metric(result,'G14-M07')['observed_known_mean']==0.75
    assert metric(build(rows,last_n_games=1),'G14-M07')['observed_known_mean']==1
    assert result['team_windows'][0]['observed_games']==2
    assert 'unverified' in result['full_game_coverage']


def test_missing_defteam_retains_explicit_native_pair_inference():
    result=build([play(defteam=None)])
    identity=result['game_rows'][0]['defense_identity']
    assert identity['missing_defteam_inferred_from_native_pair_events']==1
    assert identity['explicit_defteam_events']==0
    with pytest.raises(ValueError,match='conflicts'):build([play(defteam='GB')])


def test_unchanged_order_and_capture_clocks_stable_material_epa_and_quality_change_hash():
    rows=[play(),play(2,yards_gained=0,epa=-1)]
    first=build(rows);later=deepcopy(SOURCE);later['captured_at']=later['received_at']='2026-10-19T19:30:00Z'
    assert first['semantic_measurements_sha256']==build(list(reversed(rows)),source=later)['semantic_measurements_sha256']
    rows[0]['epa']=-2
    assert first['semantic_measurements_sha256']!=build(rows)['semantic_measurements_sha256']
    later['full_game_coverage']='independently verified'
    assert first['semantic_measurements_sha256']!=build([play(),play(2,yards_gained=0,epa=-1)],source=later)['semantic_measurements_sha256']


def test_scope_future_and_checksum_rejected():
    with pytest.raises(ValueError,match='future game'):build([play(week=6,game_id='2026_06_BUF_MIA')])
    receipt=dict(event_evidence=build_event_evidence([play()],canonical_ids=IDS,source_receipt=SOURCE,cutoff=CUTOFF))
    receipt['event_evidence']['events'][0]['raw_flags']['epa']=99
    with pytest.raises(ValueError,match='checksum'):build_defense_context_evidence(receipt,before_period=202606,cutoff=CUTOFF)


def test_empty_no_sample_and_invalid_window():
    result=build([])
    assert result['game_rows']==[] and result['team_windows']==[]
    for size in (0,33,True,1.5):
        with pytest.raises(ValueError,match='window'):build([],last_n_games=size)


def test_known_outside5_independently_excludes_unknown_rush_eligibility():
    outside=play(1,play_type=None,pass_attempt=None,rush_attempt=None,sack=None,yardline_100=35)
    inside=play(2,play_type=None,pass_attempt=None,rush_attempt=None,sack=None,yardline_100=5)
    result=build([outside,inside])
    assert metric(result,'G15-M01')['unknown_eligibility_events']==2
    assert metric(result,'G15-M09')['unknown_eligibility_events']==1
    assert metric(result,'G15-M09')['eligible_events']==0


def test_epa_accumulation_stable_under_nonassociative_provider_row_order():
    rows=[play(1,epa=10),play(2,epa=1e-15),play(3,epa=-10)]
    first=build(rows);reordered=build([rows[0],rows[2],rows[1]])
    assert first['semantic_measurements_sha256']==reordered['semantic_measurements_sha256']
    assert metric(first,'dropback_epa_support')==metric(reordered,'dropback_epa_support')
