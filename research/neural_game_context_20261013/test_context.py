import importlib.util
from pathlib import Path
import copy
import numpy as np,pandas as pd,pytest
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('game_context',HERE/'context.py');context=importlib.util.module_from_spec(s);s.loader.exec_module(context)

def snapshot():
 return dict(roster_coverage={'DEN':{'universe_complete':True},'KC':{'universe_complete':True}},source_id='original_receipt',source_sha256='a'*64,game_id='game1',published_at='2026-10-11T15:00:00Z',observed_at='2026-10-11T15:01:00Z',roster_members=[dict(player_master_id='canonical1',team='DEN',position='WR',effective_from='2026-10-01T00:00:00Z'),dict(player_master_id='canonical2',team='DEN',position='WR',effective_from='2026-10-01T00:00:00Z')],reports=[dict(player_master_id='canonical1',team='DEN',position='WR',status='out',published_at='2026-10-11T15:00:00Z')])

def test_actual_missing_remains_unknown_and_not_healthy():
 members=context.validate_availability(snapshot(),game_id='game1',cutoff='2026-10-11T16:00:00Z')
 assert [r['status'] for r in members]==['out','unknown']
 agg=context.aggregate_availability(members,'DEN',{'canonical1':{'targets':8}})
 assert agg['receiving_out_count']==1 and agg['receiving_unknown_count']==1 and agg['receiving_out_prior_targets']==8

@pytest.mark.parametrize('change',[{'observed_at':'2026-10-11T17:00:00Z'},{'published_at':'2026-10-11T17:00:00Z'},{'published_at':None},{'game_id':'game2'}])
def test_availability_rejects_missing_and_future_provenance(change):
 source=snapshot();source.update(change)
 with pytest.raises(ValueError):context.validate_availability(source,game_id='game1',cutoff='2026-10-11T16:00:00Z')

def test_availability_never_name_joins_or_uses_current_team():
 for change in [{'player_master_id':'unknown','full_name':'canonical1'},{'team':'KC'},{'position':'RB'}]:
  source=snapshot();source['reports'][0].update(change)
  with pytest.raises(ValueError):context.validate_availability(source,game_id='game1',cutoff='2026-10-11T16:00:00Z')

def game(gid,kickoff,**extra):
 kick=pd.Timestamp(kickoff)
 return dict(game_id=gid,season=2026,week=1,home_team='DEN',away_team='KC',kickoff_at=kick,cutoff_at=kick-pd.Timedelta(hours=1),completed_at=kick+pd.Timedelta(hours=8),stadium_id='DEN00',roof='outdoors',location='Home')|extra

def test_no_target_roof_or_weather_and_prior_rest_only():
 prior=game('past','2026-10-04T20:25:00Z');target=game('target','2026-10-11T20:25:00Z',roof='closed',temp=99)
 future=game('future','2026-10-18T20:25:00Z',roof='dome');games={r['game_id']:r for r in [prior,target,future]}
 values=context.schedule_context(target,'DEN',games)
 assert values['ctx_open_air']==1 and values['ctx_retractable']==0 and values['ctx_rest_days']==7
 target['roof']='dome';assert context.schedule_context(target,'DEN',games)==values

def test_dst_local_clock_and_neutral_unknown_home():
 summer=game('summer','2026-10-25T17:00:00Z',location='Neutral');winter=game('winter','2026-11-08T18:00:00Z')
 a=context.schedule_context(summer,'DEN',{});b=context.schedule_context(winter,'DEN',{})
 assert a['ctx_et_sin']==pytest.approx(b['ctx_et_sin']) and a['ctx_local_sin']==pytest.approx(b['ctx_local_sin'])
 assert np.isnan(a['ctx_home']) and a['ctx_neutral']==1 and np.isnan(a['ctx_rest_days'])

def test_proxy_uses_canonical_prior_only_excludes_focal_and_distinguishes_unknown():
 p=lambda pid,targets:dict(player_master_id=pid,position='WR',targets=targets,carries=0)
 history=[[p('a',8),p('b',5)],[p('a',10)],[p('b',7)]]
 values=context.participation_proxy(history,exclude_player='b')
 assert values['receiving_absent_last_targets']==9 and values['receiving_returned_last_targets']==0
 assert np.isnan(values['ol_absent_last_snaps'])
 returned=context.participation_proxy(history);assert returned['receiving_returned_last_targets']==7
 assert np.isnan(context.participation_proxy([])['receiving_absent_last_targets'])

def test_retractable_state_always_unmodeled():
 prior=game('past','2026-10-04T20:25:00Z',roof='closed');target=game('target','2026-10-11T20:25:00Z',roof='open')
 values=context.schedule_context(target,'DEN',{'past':prior,'target':target});assert values['ctx_retractable']==1
 assert not any('roof_open' in key for key in values)

def test_scoring_contract_rejects_same_game_future_history_and_missing_opponent():
 import sys
 sys.path.insert(0,str(HERE));from availability import availability_inputs
 source=snapshot();source['roster_members'].append(dict(player_master_id='opponent1',team='KC',position='QB',effective_from='2026-10-01T00:00:00Z'))
 valid=dict(game_id='prior',completed_at='2026-10-05T03:00:00Z',targets=8)
 result=availability_inputs(source,{'canonical1':valid},game_id='game1',cutoff='2026-10-11T16:00:00Z',team='DEN',player_master_id='canonical2')
 assert result['teammate']['receiving_out_prior_targets']==8
 for change in [dict(game_id='game1'),dict(game_id=None),dict(completed_at='2026-10-11T17:00:00Z'),dict(completed_at=None),dict(prior_status='out')]:
  with pytest.raises(ValueError):availability_inputs(source,{'canonical1':valid|change},game_id='game1',cutoff='2026-10-11T16:00:00Z',team='DEN',player_master_id='canonical2')
 with pytest.raises(ValueError):availability_inputs(snapshot(),{},game_id='game1',cutoff='2026-10-11T16:00:00Z',team='DEN',player_master_id='canonical2')

def test_flat_neural_availability_contract_includes_known_returning_workload():
 import sys
 sys.path.insert(0,str(HERE));from availability import availability_feature_row
 source=snapshot();source['reports'][0]['status']='available';source['roster_members'].append(dict(player_master_id='opponent1',team='KC',position='QB',effective_from='2026-10-01T00:00:00Z'))
 row=availability_feature_row(source,{'canonical1':dict(game_id='prior',completed_at='2026-10-05T03:00:00Z',targets=8,prior_status='out',prior_status_observed_at='2026-10-04T15:00:00Z')},game_id='game1',cutoff='2026-10-11T16:00:00Z',team='DEN',player_master_id='canonical2')
 assert row['availability_teammate_receiving_returning_prior_targets']==8
 assert row['availability_teammate_receiving_returning_count']==1
 assert row['availability_opponent_qb_unknown_count']==1
 assert np.isnan(row['availability_opponent_qb_returning_prior_snaps'])


def test_actual_roster_incomplete_rejected_in_scoring_contract():
 import sys
 sys.path.insert(0,str(HERE));from availability import availability_inputs
 source=snapshot();source['roster_members'].append(dict(player_master_id='opponent1',team='KC',position='QB',effective_from='2026-10-01T00:00:00Z'));source['roster_coverage']['KC']['universe_complete']=False
 with pytest.raises(ValueError):availability_inputs(source,{},game_id='game1',cutoff='2026-10-11T16:00:00Z',team='DEN',player_master_id='canonical2')


def test_scoring_receipt_cannot_contain_report_published_after_capture():
 import sys
 sys.path.insert(0,str(HERE));from availability import availability_inputs
 source=snapshot();source['reports'][0]['published_at']='2026-10-11T15:30:00Z';source['roster_members'].append(dict(player_master_id='opponent1',team='KC',position='QB',effective_from='2026-10-01T00:00:00Z'))
 with pytest.raises(ValueError):availability_inputs(source,{},game_id='game1',cutoff='2026-10-11T16:00:00Z',team='DEN',player_master_id='canonical2')
