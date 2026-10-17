from copy import deepcopy
from datetime import datetime,UTC
import pytest
from backend.app.product_services.dst_scoring_reconciliation import (score_game,REQUIRED,DstScoringUnresolved,apply_research_corrections,require_completed_schedule_scores)
A='00000000-0000-4000-8000-000000000001';B='00000000-0000-4000-8000-000000000002';IDS={'PHI':A,'CAR':B}
def play(n,**kw):
 r={k:None for k in REQUIRED};r.update(game_id='2026_06_CAR_PHI',play_id=n,order_sequence=n,home_team='PHI',away_team='CAR',home_score=0,away_score=0,total_home_score=0,total_away_score=0,posteam='CAR',defteam='PHI',play_deleted=0,desc='Observed play',play_type='pass')
 for k in ['sack','interception','safety','touchdown','pass_touchdown','rush_touchdown','punt_attempt','kickoff_attempt','field_goal_attempt','extra_point_attempt','two_point_attempt','punt_blocked','defensive_two_point_conv','defensive_extra_point_conv']:r[k]=0
 r.update(kw);return r
def score(rows):
 rows=deepcopy(rows);last=rows[-1];final={'PHI':last['total_home_score'],'CAR':last['total_away_score']}
 for r in rows:r.update(home_score=final['PHI'],away_score=final['CAR'])
 rows.append(play(999,desc='END GAME',play_type=None,total_home_score=final['PHI'],total_away_score=final['CAR'],home_score=final['PHI'],away_score=final['CAR']))
 return {r['team']:r for r in score_game(rows,expected_game_id='2026_06_CAR_PHI',expected_teams=['PHI','CAR'],canonical_player_ids=IDS,expected_score=final)}
def test_defensive_td_excluded_but_its_xp_still_charged_and_not_seven_point_approximation():
 r=score([play(1,interception=1,touchdown=1,td_team='PHI',total_home_score=6),play(2,posteam='PHI',defteam='CAR',play_type='extra_point',extra_point_attempt=1,extra_point_result='good',total_home_score=7)])
 assert r['PHI']['components']['defensive_touchdowns']==1
 assert r['CAR']['components']['points_allowed']==1 and r['CAR']['dk_points']==7
 assert r['PHI']['dk_points']==18
@pytest.mark.parametrize('kind',['punt_attempt','kickoff_attempt','field_goal_attempt'])
def test_special_teams_return_td_counts_once_and_is_charged_to_opposing_dst(kind):
 r=score([play(1,**{kind:1},touchdown=1,td_team='PHI',total_home_score=6)])
 assert r['PHI']['components']['special_teams_touchdowns']==1 and r['PHI']['components']['defensive_touchdowns']==0
 assert r['CAR']['components']['points_allowed']==6

def test_fumble_recovery_on_offense_after_defensive_turnover_is_awarded_to_dst():
 r=score([play(1,interception=1,fumbled_1_team='PHI',fumble_recovery_1_team='CAR')])
 assert r['CAR']['components']['fumble_recoveries']==1 and r['PHI']['components']['interceptions']==1

def test_second_fumble_possession_and_own_recovery_do_not_double_count():
 r=score([play(1,fumbled_1_team='CAR',fumble_recovery_1_team='CAR',fumble_recovery_2_team='PHI')])
 assert r['PHI']['components']['fumble_recoveries']==1 and r['CAR']['components']['fumble_recoveries']==0

def test_blocks_safety_conversion_return_and_nullified_event_are_separate():
 r=score([play(1,safety=1,total_home_score=2),play(2,play_type='extra_point',extra_point_attempt=1,extra_point_result='blocked',defensive_extra_point_conv=1,total_home_score=4)])
 assert r['PHI']['components']['safeties']==1 and r['PHI']['components']['blocked_kicks']==1 and r['PHI']['components']['conversion_returns']==1
 assert r['CAR']['components']['points_allowed']==2
 p=play(1,desc='Touchdown NULLIFIED by Penalty - No Play',sack=None,interception=None,safety=None,touchdown=None)
 assert score([p])['PHI']['dk_points']==10

def test_offensive_fumble_recovery_td_is_not_a_dst_td_but_is_points_allowed():
 r=score([play(1,touchdown=1,td_team='CAR',total_away_score=6)])
 assert r['CAR']['components']['offensive_fumble_touchdowns']==1 and r['CAR']['components']['special_teams_touchdowns']==0
 assert r['PHI']['components']['points_allowed']==6

def test_missing_duplicate_or_wrong_game_is_not_a_verified_zero():
 with pytest.raises(DstScoringUnresolved):score_game([],expected_game_id='x',expected_teams=['PHI','CAR'],canonical_player_ids=IDS)
 with pytest.raises(DstScoringUnresolved,match='Duplicate'):score([play(1),play(1)])
 p=play(1);p['game_id']='wrong'
 with pytest.raises(DstScoringUnresolved,match='game mismatch'):score([p])
 p=play(1,sack=None)
 with pytest.raises(DstScoringUnresolved,match='Missing event counters'):score([p])

def test_research_correction_is_separate_and_requires_uuid_team_opponent_game():
 old=[dict(player_game_feature_matrix_id=1,season=2026,week=6,team='PHI',opponent='CAR',player_master_id=A,game_id=None,dk_points=0)]
 new=[dict(season=2026,week=6,team='PHI',opponent='CAR',player_master_id=A,game_id='2026_06_CAR_PHI',dk_points=5,source_sha256='abc')]
 result=apply_research_corrections(old,new);assert old[0]['dk_points']==0 and result['rows'][0]['dk_points']==5
 bad=deepcopy(new);bad[0]['player_master_id']=B;assert apply_research_corrections(old,bad)['receipts'][0]['status']=='unresolved_identity_or_source'

def test_completed_missing_final_blocks_but_future_and_genuine_score_zero_do_not():
 now=datetime(2026,10,15,tzinfo=UTC);row=dict(game_id='x',raw_row_json=dict(gameday='2026-10-11',gametime='13:00',home_score=None,away_score=None))
 with pytest.raises(DstScoringUnresolved,match='refusing zero'):require_completed_schedule_scores([row],now=now)
 future=deepcopy(row);future['raw_row_json']['gameday']='2026-10-18';assert require_completed_schedule_scores([future],now=now)['future_games']==1
 row['raw_row_json'].update(home_score=0,away_score=0);assert require_completed_schedule_scores([row],now=now)['completed_games']==1

def test_legacy_builder_guard_blocks_before_defaulting_missing_completed_result_to_zero():
 from types import SimpleNamespace
 from unittest.mock import MagicMock
 from backend.app.services.lineup_learning import LineupLearningService
 service=LineupLearningService.__new__(LineupLearningService);service._dst_actual_cache={};service.session=MagicMock()
 row=SimpleNamespace(game_id='2024_01_CAR_PHI',raw_row_json=dict(gameday='2024-09-08',gametime='13:00',home_score=None,away_score=None))
 service.session.execute.return_value.scalars.return_value.all.return_value=[row]
 with pytest.raises(DstScoringUnresolved,match='refusing zero'):service._compute_dst_actual_points(season=2024,week=1)
 assert service._dst_actual_cache=={} and service.session.execute.call_count==1

def test_verified_zero_dst_score_is_retained_as_a_real_outcome():
 rows=[];total=0
 for i in range(3):
  total+=6;rows.append(play(2*i+1,rush_touchdown=1,touchdown=1,td_team='CAR',total_away_score=total))
  total+=1;rows.append(play(2*i+2,play_type='extra_point',extra_point_attempt=1,extra_point_result='good',total_away_score=total))
 result=score(rows)['PHI'];assert result['dk_points']==0 and result['coverage']=='complete_final_event_scoring'

def test_replay_adjusted_sequence_not_numeric_play_id_controls_score_timeline():
 td=play(100,order_sequence=1,touchdown=1,rush_touchdown=1,td_team='CAR',total_away_score=6,away_score=7)
 xp=play(50,order_sequence=2,play_type='extra_point',extra_point_attempt=1,extra_point_result='good',total_away_score=7,away_score=7)
 end=play(999,order_sequence=3,play_type=None,desc='END GAME',total_away_score=7,away_score=7)
 result=score_game([xp,td,end],expected_game_id='2026_06_CAR_PHI',expected_teams=['CAR','PHI'],canonical_player_ids=IDS)
 assert next(r for r in result if r['team']=='PHI')['components']['points_allowed']==7
