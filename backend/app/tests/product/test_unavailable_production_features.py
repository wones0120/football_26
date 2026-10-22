from copy import deepcopy
import pandas as pd
import pytest
from backend.app.product_services.player_role_features import VERSION
from backend.app.product_services.unavailable_production_features import build_unavailable_production_features

PID='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
OTHER='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
CUTOFF='2026-10-19T20:00:00+00:00'


def history():
    return pd.DataFrame([dict(player_master_id=pid,source_player_id=pid,team='WAS',position='RB',period=202600+w,
        pass_attempts=0,rush_attempts=10,targets=2,receptions=1,passing_yards=0,rushing_yards=-2,receiving_yards=5,
        source_id=w*10+i,imported_at='2026-10-19T18:00:00+00:00') for w in (3,4,5) for i,pid in enumerate((PID,OTHER))])


def roles():
    return dict(version=VERSION,season=2026,week=6,provenance=dict(decision_cutoff_at=CUTOFF),
        players=[dict(player_master_id=PID,team='WAS',position='RB',availability_state='UNAVAILABLE'),
                 dict(player_master_id=OTHER,team='WAS',position='RB',availability_state='AVAILABLE')],
        teams=[dict(team='WAS',roster_complete=True)])


def run(h=None,r=None):
    return build_unavailable_production_features(history() if h is None else h,roles() if r is None else r,
        before_period=202606,cutoff=CUTOFF)


def test_unavailable_reference_not_forecast_donation_and_signed_yards():
    result=run();a=result['actors'][0]
    assert a['unavailable_reference']['rush_attempts']==10
    assert a['unavailable_reference']['rushing_yards']==-2
    assert a['forecast'] is None
    assert result['actors'][1]['unavailable_reference'] is None
    assert result['teams'][0]['metrics']['G18-M09']['channels']['targets']['exact_unavailable_reference_mean']==2


def test_unknown_current_status_and_incomplete_roster_mask_exact():
    r=roles();r['players'][1]['availability_state']='UNKNOWN'
    channel=run(r=r)['teams'][0]['metrics']['G18-M09']['channels']['targets']
    assert channel['exact_unavailable_reference_mean'] is None
    assert channel['known_actor_reference_sum']==2
    r=roles();r['teams'][0]['roster_complete']=False
    assert run(r=r)['teams'][0]['metrics']['G18-M09']['channels']['targets']['exact_unavailable_reference_mean'] is None


def test_missing_inactive_period_not_zero_or_last_positive():
    h=history();h=h.loc[~(h.player_master_id.eq(PID)&h.period.eq(202604))]
    a=run(h=h)['actors'][0]
    assert a['unavailable_reference']['rush_attempts'] is None
    assert a['reference_coverage']['rush_attempts']['unknown_periods']==[202604]


def test_transfer_history_and_prior_season_do_not_fill_same_team_window():
    h=history();h.loc[h.player_master_id.eq(PID)&h.period.eq(202603),'team']='SF'
    assert run(h=h)['actors'][0]['unavailable_reference']['targets'] is None


def test_measured_zero_differs_from_missing_channel():
    h=history();h.loc[h.player_master_id.eq(PID),'targets']=0
    assert run(h=h)['actors'][0]['unavailable_reference']['targets']==0
    h['receptions']=None
    assert run(h=h)['actors'][0]['unavailable_reference']['receptions'] is None
    h=history();h['receptions']=-1
    with pytest.raises(ValueError,match='Negative observed reception'):run(h=h)


def test_unknown_position_masks_group_exact():
    r=roles();r['players'][1]['position']='UNKNOWN'
    value=run(r=r)['teams'][0]['metrics']['G18-M09']['channels']['targets']
    assert value['exact_unavailable_reference_mean'] is None
    assert value['unknown_position_actors']==1


def test_boundary_and_duplicate_identity():
    r=roles();r['week']=5
    with pytest.raises(ValueError,match='scoped availability'):run(r=r)
    r=roles();r['players'].append(deepcopy(r['players'][0]))
    with pytest.raises(ValueError,match='Duplicate canonical role'):run(r=r)
    h=history();h['imported_at']=None
    with pytest.raises(ValueError,match='receipt clocks'):run(h=h)


def test_recapture_lineage_kept_out_of_measurement_semantics():
    h=history();baseline=run(h=h)
    h['source_id']+=1000
    assert run(h=h)['semantic_sha256']==baseline['semantic_sha256']
