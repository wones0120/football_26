import copy

import pandas as pd
import pytest

from backend.app.product_services.captain_workload import assess_captain_workload
from backend.app.product_services.showdown_captain_shortlist import build_captain_shortlist


def player(position='WR', **changes):
    row=dict(player_id='canonical',name='Receiver',position=position,player_team='AAA',
        projection=12,p90=25,salary=6000,data_cutoff_at='2026-10-17T16:00:00Z',
        workload_feature_cutoff_at='2026-10-17T16:00:00Z',workload_feature_run_id='frozen',
        role_source='native_depth_chart',role_observed_at='2026-10-17T12:00:00Z',
        snap_share_last=.75,snap_share_mean_3_available=True,
        targets_mean_3_available=True,target_share_mean_3_available=True,
        carries_mean_3_available=True,carry_share_mean_3_available=True,
        pregame_base_targets_mean_3=7,pregame_base_target_share_mean_3=.22,
        target_share_last=.20,pregame_base_carries_mean_3=14,
        pregame_base_carry_share_mean_3=.55)
    return {**row,**changes}


def test_low_recent_receiving_role_does_not_pass_on_salary_snaps_p90_or_proxy():
    row=player(pregame_base_targets_mean_3=5,pregame_base_target_share_mean_3=.17,
        target_share_last=3/23,snap_share_last=.68,projected_targets=99,p90=100,salary=200)
    original=copy.deepcopy(row)
    result=assess_captain_workload(row)
    assert not result['eligible']
    assert result['reason_code']=='insufficient_supported_captain_workload'
    assert not result['projection_proxies_used_for_qualification']
    assert row==original


@pytest.mark.parametrize('field,value',[
    ('targets_mean_3_available',False),('target_share_mean_3_available',None),
    ('pregame_base_targets_mean_3',None),('workload_feature_cutoff_at',None),
    ('role_observed_at','2026-10-18T12:00:00Z'),('role_source',None)])
def test_unknown_or_future_evidence_cannot_pass(field,value):
    assert not assess_captain_workload(player(**{field:value}))['eligible']


def test_sustained_receiving_and_rushing_roles_are_position_specific():
    assert assess_captain_workload(player())['eligible']
    assert assess_captain_workload(player('RB',pregame_base_targets_mean_3=2,
        pregame_base_target_share_mean_3=.05,target_share_last=.05))['eligible']
    assert not assess_captain_workload(player('WR',pregame_base_targets_mean_3=2,
        pregame_base_target_share_mean_3=.05,target_share_last=.05))['eligible']


def test_only_sourced_verified_current_forecast_can_support_expansion():
    row=player(pregame_base_targets_mean_3=2,target_share_last=.05,
        pregame_expected_targets=8,pregame_target_share=.25,
        expected_workload_status='VERIFIED',expected_workload_source_ids=['native-news-id'],
        expected_workload_observed_at='2026-10-17T14:00:00Z',
        pregame_context_row_id=1,pregame_context_source='sourced_forecast')
    assert assess_captain_workload(row)['reason_code']=='verified_expanded_captain_workload'
    for key,value in [('expected_workload_source_ids',[]),('expected_workload_source_ids',float('nan')),
        ('expected_workload_source_ids','invented'),('expected_workload_status','UNKNOWN'),
        ('expected_workload_observed_at','2026-10-18T14:00:00Z'),('pregame_context_row_id',None)]:
        assert not assess_captain_workload({**row,key:value})['eligible']
    # Later availability refresh cannot renew an original forecast's clock.
    row['workload_feature_evidence']={'expected_workload_observed_at':'2026-10-18T14:00:00Z'}
    row['expected_workload_observed_at']='2026-10-17T14:00:00Z'
    assert not assess_captain_workload(row)['eligible']


def test_current_verified_low_workload_overrides_a_large_historical_role():
    row=player(pregame_expected_targets=3,pregame_target_share=.10,
        expected_workload_status='VERIFIED',expected_workload_source_ids=['native-news-id'],
        expected_workload_observed_at='2026-10-17T14:00:00Z',
        pregame_context_row_id=1,pregame_context_source='sourced_forecast')
    result=assess_captain_workload(row)
    assert not result['eligible']
    assert result['reason_code']=='verified_current_workload_below_captain_role'


def test_merged_broad_search_has_shared_gate_but_flex_and_legacy_comparison_remain():
    good=[player(player_id=str(i),p90=30-i) for i in range(6)]
    thin=player(player_id='thin',p90=100,pregame_base_targets_mean_3=3,target_share_last=.08)
    pool=pd.DataFrame([thin,*good]);before=pool.copy(deep=True)
    frame,report=build_captain_shortlist(pool,params={'analyst_strategy':'MERGED_SCENARIOS'},flex_only_ids=set())
    assert len(report['shortlist'])==6  # Broader than top four, no quota.
    assert not frame.loc[frame.player_id=='thin','showdown_captain_shortlisted'].iloc[0]
    assert report['exclusions'][0]['captain_workload']['reason_code']=='insufficient_supported_captain_workload'
    assert len(frame)==7 and frame.loc[frame.player_id=='thin','projection'].iloc[0]==12
    _,legacy=build_captain_shortlist(pool,params={},flex_only_ids=set())
    assert legacy['shortlist'][0]['player_id']=='thin'
    pd.testing.assert_frame_equal(pool,before)


def test_established_receiver_is_not_removed_for_one_quiet_game():
    assert assess_captain_workload(player(pregame_base_targets_mean_3=11,
        pregame_base_target_share_mean_3=.27,target_share_last=.12))['eligible']
    assert assess_captain_workload(player(pregame_base_targets_mean_3=5.5,
        pregame_base_target_share_mean_3=.17,target_share_last=.18))['eligible']


def test_named_te_and_qb_exceptions_still_require_supported_workload():
    from backend.app.product_services.showdown_qb_preferences import showdown_qb_preference_report
    rows=[player('TE',player_id='te'),player('QB',player_id='starter',is_starting_qb=True,starting_qb_source='native_qb1'),
          player('QB',player_id='backup',is_starting_qb=False,starting_qb_source='native_depth_chart'),
          player('TE',player_id='thin',pregame_base_targets_mean_3=2)]
    params={'analyst_strategy':'MERGED_SCENARIOS','captain_positions':['WR','RB'],'captain_position_exception_ids':['te','starter','backup','thin']}
    _,report=build_captain_shortlist(pd.DataFrame(rows),params=params,flex_only_ids=set())
    assert {p['player_id']for p in report['shortlist']}=={'te','starter'}
    assert showdown_qb_preference_report(params,qb_player_ids={'starter','backup'})['allow_qb_captain']
    assert not showdown_qb_preference_report({**params,'no_qb_captain':True},qb_player_ids={'starter'})['allow_qb_captain']
    assert not showdown_qb_preference_report({**params,'captain_position_exception_ids':['te']},qb_player_ids={'starter'})['allow_qb_captain']
