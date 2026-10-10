"""Permanent opportunity membership, window, conservation and anchor regressions."""
import pandas as pd
import pytest
from backend.app.product_services.canonical_projection_inputs import attach_lagged_opportunity_features, apply_pregame_projection_context
from backend.app.product_services.predictions import apply_opportunity_point_adjustment, TARGET_COL
from backend.app.config import Settings

CUTOFF=pd.Timestamp('2026-10-09T21:56:16Z')

def stat(pid,team,week,carries=0,targets=0,season=2026,**extra):
 return dict(player_master_id=pid,source_player_id=pid,season=season,week=week,team=team,position='RB',carries=carries,targets=targets,created_at='2026-10-01T00:00:00Z',**extra)

def matrix(ids,team='SEA',week=5):
 return pd.DataFrame([dict(player_master_id=p,player_id=p,season=2026,week=week,team=team,recent_team=team,position='RB',snap_share_mean_3=.5,player_games_history=5,roster_status='ACT',expected_depth_role='expected_starter') for p in ids])

def features(frame,stats):
 return attach_lagged_opportunity_features(frame,pd.DataFrame(stats),cutoff=CUTOFF,policy='team_window_v2')[0]

def test_previous_team_role_never_enters_new_team_denominator():
 stats=[stat('starter','SEA',w,18,4) for w in (2,3,4)]+[stat('backup','SEA',w,2,1) for w in (2,3,4)]+[stat('transfer','KC',w,22,6,2025) for w in (16,17,18)]
 rows=features(matrix(['starter','backup','transfer']),stats)
 rows.loc[rows.player_id.eq('transfer'),'player_status']='OUT'
 updated,audit=apply_pregame_projection_context(rows)
 by=updated.set_index('player_id')
 assert by.loc['starter','carries_mean_3']==18
 assert by.loc['starter','carry_share_mean_3']==.9
 assert by.loc['transfer','opportunity_history_status']=='no_same_team_window_history'
 assert not by.loc['transfer','carry_share_mean_3_available']
 assert not by.loc['starter','pregame_opportunity_context_applied']
 carry=next(a for a in audit['allocations'] if a['opportunity']=='carry')
 assert carry['removed_share']==0 and carry['unallocated_volume']==0

def test_midseason_transfer_uses_only_new_team_games_in_common_window():
 stats=[stat('transfer','KC',2,30,10),stat('transfer','SEA',3,6,2),stat('transfer','SEA',4,9,4)]
 stats += [stat('other','SEA',w,12,6) for w in (2,3,4)]
 row=features(matrix(['transfer']),stats).iloc[0]
 assert row.carries_mean_3==5 # absent from new team's week 2 is not imported KC volume
 assert row.targets_mean_3==2
 assert row.opportunity_history_observed_games==2
 assert row.carry_share_mean_3==pytest.approx(5/17)

def test_shared_team_window_drops_stale_overlapping_player_histories():
 stats=[stat('active','SEA',w,10,2) for w in (2,3,4)]+[stat('old','SEA',1,80,20),stat('older','SEA',18,90,20,2025)]
 rows=features(matrix(['active','old','older']),stats)
 assert rows.carries_mean_3.tolist()==[10,0,0]
 assert rows.carry_share_mean_3.sum()==1
 assert rows.team_carries_mean_3.tolist()==[10]*3
 assert all([x['week'] for x in win]==[2,3,4] for win in rows.opportunity_history_window)

def test_real_unavailable_same_team_work_remains_explicitly_unallocated():
 stats=[stat('out','SEA',w,12,6) for w in (2,3,4)]+[stat('active','SEA',w,8,4) for w in (2,3,4)]
 rows=features(matrix(['out','active']),stats);rows.loc[0,'player_status']='OUT'
 updated,audit=apply_pregame_projection_context(rows)
 assert updated.carries_mean_3.tolist()==[0,8]
 a=next(x for x in audit['allocations'] if x['opportunity']=='carry')
 assert a['removed_share']==.6 and a['unallocated_volume']==12
 assert a['player_projected_volume_sum']+a['unallocated_volume']==a['team_volume']
 assert updated.pregame_opportunity_context_applied.all()

def test_supported_backup_expansion_consumes_budget_without_automatic_full_redistribution():
 stats=[stat('out','SEA',w,12,6) for w in (2,3,4)]+[stat('backup','SEA',w,2,1) for w in (2,3,4)]+[stat('other','SEA',w,6,3) for w in (2,3,4)]
 rows=features(matrix(['out','backup','other']),stats);rows.loc[0,'player_status']='OUT'
 context=pd.DataFrame([dict(player_master_id='backup',expected_carries=10,source='sourced_role')])
 updated,audit=apply_pregame_projection_context(rows,pregame_context=context)
 assert updated.carries_mean_3.tolist()==[0,10,6]
 a=next(x for x in audit['allocations'] if x['opportunity']=='carry')
 assert a['unallocated_volume']==4
 assert a['removed_share']==.6

def test_named_redistribution_is_capped_after_explicit_expansion():
 stats=[stat('out','SEA',w,12,6) for w in (2,3,4)]+[stat('backup','SEA',w,8,4) for w in (2,3,4)]
 rows=features(matrix(['out','backup']),stats);rows.loc[0,'player_status']='OUT'
 context=pd.DataFrame([dict(player_master_id='out',evidence_json={'carry_redistribution_fraction':1}),dict(player_master_id='backup',expected_carries=18,evidence_json={'redistribution_opportunities':['carry']})])
 updated,audit=apply_pregame_projection_context(rows,pregame_context=context)
 assert updated.carries_mean_3.tolist()==[0,20]
 a=next(x for x in audit['allocations'] if x['opportunity']=='carry')
 assert a['requested_redistribution_share']==.6
 assert a['redistributed_share']==pytest.approx(.1)
 assert a['unallocated_volume']==0

def test_no_same_team_history_requires_evidence_before_anchor_can_activate():
 stats=[stat('out','SEA',w,20,10) for w in (2,3,4)]+[stat('new','KC',w,20,10) for w in (2,3,4)]
 rows=features(matrix(['out','new']),stats);rows.loc[0,'player_status']='OUT'
 updated,_=apply_pregame_projection_context(rows)
 train=pd.DataFrame([{'position':'RB','carries_mean_3':5,'targets_mean_3':1,TARGET_COL:5},{'position':'RB','carries_mean_3':20,'targets_mean_3':5,TARGET_COL:20}])
 means,detail=apply_opportunity_point_adjustment([10,10],train,updated)
 assert means[1]==10 and detail.loc[1,'pregame_opportunity_point_weight']==0
 context=pd.DataFrame([dict(player_master_id='new',expected_carries=10)])
 supported,_=apply_pregame_projection_context(rows,pregame_context=context)
 _,detail=apply_opportunity_point_adjustment([10,10],train,supported)
 assert detail.loc[1,'pregame_opportunity_point_weight']==.55

def test_future_game_and_late_revisions_cannot_change_prelock_window():
 stats=[stat('active','SEA',w,10,2,raw_nfl_weekly_stat_id=w) for w in (2,3,4,5)]
 late=stat('active','SEA',4,99,99,raw_nfl_weekly_stat_id=40);late['created_at']='2026-10-10T00:00:00Z'
 rows=features(matrix(['active']),stats+[late])
 assert rows.carries_mean_3.tolist()==[10]
 assert [x['week'] for x in rows.loc[0,'opportunity_history_window']]==[2,3,4]

def test_explicit_overcommit_rejected_and_measured_zero_distinct_from_missing():
 stats=[stat('zero','SEA',w,0,0) for w in (2,3,4)]+[stat('other','SEA',w,20,10) for w in (2,3,4)]
 rows=features(matrix(['zero','other','missing']),stats)
 assert rows.loc[0,'carry_share_mean_3_available'] and not rows.loc[2,'carry_share_mean_3_available']
 context=pd.DataFrame([dict(player_master_id='zero',expected_carries=30)])
 with pytest.raises(ValueError,match='exceeds'):apply_pregame_projection_context(rows,pregame_context=context)

def test_absent_sources_and_default_settings_do_not_promote_repair():
 rows=features(matrix(['new']),[])
 assert rows.loc[0,'opportunity_allocation_policy']=='team_window_v2'
 assert not rows.loc[0,'carry_share_mean_3_available']
 assert Settings(_env_file=None).player_opportunity_allocation_policy=='legacy_v1'


def test_fullback_source_and_draftkings_running_back_share_one_denominator():
 stats=[stat('back','SEA',w,18,4) for w in (2,3,4)]
 stats += [dict(stat('fullback','SEA',w,2,1),position='FB') for w in (2,3,4)]
 rows=features(matrix(['back','fullback']),stats)
 assert rows.team_carries_mean_3.tolist()==[20,20]
 assert rows.team_targets_mean_3.tolist()==[5,5]
 assert rows.carry_share_mean_3.sum()==1
 assert rows.target_share_mean_3.sum()==1
 updated,audit=apply_pregame_projection_context(rows)
 assert updated.carries_mean_3.sum()==20


def test_historical_wide_receiver_carries_do_not_enter_running_back_pool():
 stats=[stat('back','SEA',w,18,4) for w in (2,3,4)]
 stats += [dict(stat('converted','SEA',w,2,1),position='WR') for w in (2,3,4)]
 rows=features(matrix(['back','converted']),stats)
 assert rows.carries_mean_3.tolist()==[18,0]
 assert rows.carry_share_mean_3.sum()==1


def test_prepare_inputs_does_not_publish_missing_history_as_zero_volume():
 from backend.app.tests.product.test_canonical_projection_inputs import inputs, prepare
 source,salaries=inputs()
 prepared=prepare(source,salaries,opportunity_allocation_policy='team_window_v2')
 assert prepared[1].opportunity_allocation_policy.eq('team_window_v2').all()
 assert prepared[1].projected_targets.isna().all()
 assert prepared[1].projected_opportunity_source.eq("unavailable_same_team_history").all()
 assert prepared[1].target_share_mean_3_available.eq(False).all()


def test_salary_current_team_overrides_matrix_team_before_window_allocation():
 from backend.app.tests.product.test_canonical_projection_inputs import inputs, prepare
 source,salaries=inputs();source['team']='KC';salaries['team']='SEA'
 history=pd.DataFrame([dict(stat('canonical-1','KC',18,12,7,2025),position='WR',created_at='2026-09-01T00:00:00Z')])
 prepared=prepare(source,salaries,weekly_stats=history,opportunity_allocation_policy='team_window_v2')
 row=prepared[1].iloc[0]
 assert row.recent_team=='SEA' and row.opportunity_history_team=='SEA'
 assert row.opportunity_history_status=='no_same_team_window_history'
 assert pd.isna(row.projected_targets)


def test_mixed_policy_rows_cannot_silently_use_legacy_normalization():
 rows=features(matrix(['one','two']),[stat(p,'SEA',w,10,2) for p in ['one','two'] for w in (2,3,4)])
 rows.loc[1,'opportunity_allocation_policy']='legacy_v1'
 with pytest.raises(ValueError,match='Mixed opportunity history policies'):
  apply_pregame_projection_context(rows)


@pytest.mark.parametrize('missing_flag', [float('nan'), pd.NA, False])
def test_missing_support_flag_cannot_activate_anchor(missing_flag):
 rows=matrix(['new'])
 rows['opportunity_allocation_policy']='team_window_v2'
 rows['pregame_opportunity_context_applied']=True
 rows['carry_share_mean_3_available']=missing_flag
 rows['target_share_mean_3_available']=missing_flag
 rows['carries_mean_3']=10
 rows['targets_mean_3']=3
 train=pd.DataFrame([{'position':'RB','carries_mean_3':5,'targets_mean_3':1,TARGET_COL:5},{'position':'RB','carries_mean_3':20,'targets_mean_3':5,TARGET_COL:20}])
 means,detail=apply_opportunity_point_adjustment([12],train,rows)
 assert means[0]==12
 assert detail.loc[0,'pregame_opportunity_point_weight']==0
 assert detail.loc[0,'pregame_opportunity_review_required']
 assert detail.loc[0,'pregame_opportunity_point_reason']=='historical_model_fallback_without_current_workload_support'


def test_partial_same_team_window_is_explained_without_inventing_return_workload():
 rows=features(matrix(['returning','regular']),[stat('regular','SEA',w,10,2) for w in (2,3,4)]+[stat('returning','SEA',4,15,5)])
 train=pd.DataFrame([{'position':'RB','carries_mean_3':5,'targets_mean_3':1,TARGET_COL:5},{'position':'RB','carries_mean_3':20,'targets_mean_3':5,TARGET_COL:20}])
 means,detail=apply_opportunity_point_adjustment([12,12],train,rows)
 assert means.tolist()==[12,12]
 assert detail.loc[0,'pregame_opportunity_evidence_status']=='partial_same_team_window'
 assert detail.loc[0,'pregame_opportunity_review_required']
 assert not detail.loc[1,'pregame_opportunity_review_required']


def test_prior_season_window_is_explicitly_flagged():
 rows=features(matrix(['stale']),[stat('stale','SEA',w,10,2,2025) for w in (16,17,18)])
 train=pd.DataFrame([{'position':'RB','carries_mean_3':5,'targets_mean_3':1,TARGET_COL:5},{'position':'RB','carries_mean_3':20,'targets_mean_3':5,TARGET_COL:20}])
 _,detail=apply_opportunity_point_adjustment([12],train,rows)
 assert detail.loc[0,'pregame_opportunity_evidence_status']=='prior_season_window'
 assert detail.loc[0,'pregame_opportunity_review_required']
