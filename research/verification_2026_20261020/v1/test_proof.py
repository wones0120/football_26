from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).parent))
from proof import *
G='2026_04_BUF_MIA';A='00-0000001';B='00-0000002';C='00-0000003'
def row(**kw):
 d=dict(game_id=G,play_id='1.0',season='2026',week='4',season_type='REG',posteam='BUF',defteam='MIA',play_type='run',play_type_nfl='RUSH',pass_attempt='0.0',rush_attempt='1.0',sack='0.0',qb_scramble='0.0',qb_spike='0.0',qb_kneel='0.0',qb_dropback='0.0',two_point_attempt='0.0',lateral_rush='0.0',rusher_player_id=A,lateral_rusher_player_id='',lateral_rushing_yards='0.0');d.update(kw);return d
S=[dict(game_id=G,home_team='MIA',away_team='BUF',week=4)]
def cell(rows,ch='rush_attempts'):return build_census(rows,S)[0][G,'BUF'][ch]
def w(n,count=1):return {n:dict(counts=dict.fromkeys(CHANNELS,count))}
def test_complete_rush_zero_and_rest():
 c=cell([row()]);g=group_proof({B},w(A),c,'rush_attempts',{A:'pa',B:'pb'});assert g['canonical_group_complete']and g['candidate_labels'][0]['count']==0 and g['outside_rest']==1
@pytest.mark.parametrize('patch',[{'rush_attempt':None},{'posteam':None},{'rusher_player_id':None},{'lateral_rush':None},{'lateral_rusher_player_id':B},{'pass_attempt':'1'}])
def test_uncertain_rush_never_zero(patch):
 g=group_proof({B},w(A),cell([row(**patch)]),'rush_attempts',{A:'pa',B:'pb'});assert not g['native_group_complete'];assert g['candidate_labels'][0]['count']is None
@pytest.mark.parametrize('patch',[{'qb_kneel':'1','play_type':'qb_kneel','play_type_nfl':'RUSH'},{'qb_scramble':'1','qb_dropback':'1'}])
def test_kneel_scramble_still_one_official_rush(patch):assert cell([row(**patch)])['known_events']==1

def test_missing_opposing_source_not_zero():assert not build_census([row()],S)[0][G,'MIA']['rush_attempts']['native_credit_census_exact']
def test_positive_credit_missing_weekly_not_filled():assert group_proof({A},{},cell([row()]),'rush_attempts',{A:'pa'})['candidate_labels'][0]['count']is None
def test_known_zero_vs_positive_credit_conflict():assert group_proof({A},w(A,0),cell([row()]),'rush_attempts',{A:'pa'})['conflicts']
def test_budget_mismatch_not_fixed():assert not group_proof({A},w(A,2),cell([row()]),'rush_attempts',{A:'pa'})['native_group_complete']
def test_global_collision_closure():
 d=resolve_all_edges([dict(source_key=A,player_master_id='P'),dict(source_key=A,player_master_id='Q'),dict(source_key=B,player_master_id='P')]);assert d=={A:None,B:None}
def test_unmapped_positive_participant_blocks():assert group_proof({A},w(A),cell([row()]),'rush_attempts',{A:'pa'},['unknown'])['unknown_positive_participants']
def test_native_mapped_positive_zero_allowed():assert group_proof({A},w(A),cell([row()]),'rush_attempts',{A:'pa',B:'pb'},['pb'])['canonical_group_complete']
def test_eligible_unknown_receiver_not_zero():
 r=row(play_type='pass',play_type_nfl='PASS',pass_attempt='1',rush_attempt='0',receiver_player_id='',passer_player_id=A,qb_dropback='1');assert not cell([r],'targets')['native_credit_census_exact']
def test_target_and_passer_shared_event_not_two_attempts():
 r=row(play_type='pass',play_type_nfl='PASS',pass_attempt='1',rush_attempt='0',receiver_player_id=B,passer_player_id=A,qb_dropback='1');g,e=build_census([r],S);assert g[G,'BUF']['pass_attempts']['known_events']==g[G,'BUF']['targets']['known_events']==1
@pytest.mark.parametrize('no_play',[True,None])
def test_explicit_no_play_exclusion_or_unknown(no_play):
 c=cell([row(no_play=no_play)]);assert not c['native_credit_census_exact']or no_play is True

def test_duplicate_native_play_rejected():
 with pytest.raises(ValueError):build_census([row(),row()],S)
def test_sack_pass_flag_once_not_attempt():assert pass_eligible(row(play_type='pass',play_type_nfl='SACK',pass_attempt='1',rush_attempt='0',sack='1',qb_dropback='1'))is False

@pytest.mark.parametrize('patch',[{'lateral_rushing_yards':'-1'},{'qb_kneel':'1','rush_attempt':'0'},{'qb_spike':'1'}])
def test_signed_lateral_or_positive_shape_contradiction(patch):assert not cell([row(**patch)])['native_credit_census_exact']

@pytest.mark.parametrize('kind,native',[('run','RUSH'),('pass','PASS'),('qb_kneel','RUSH'),('qb_spike','PASS'),(None,'RUSH'),(None,'PASS')])
def test_physical_native_class_all_zero_flags_masks_all_channels(kind,native):
 r=row(play_type=kind,play_type_nfl=native,pass_attempt='0',rush_attempt='0',sack='0',qb_dropback='0',qb_scramble='0',qb_kneel='0',qb_spike='0')
 gs,_=build_census([r],S)
 for c in CHANNELS:
  assert gs[G,'BUF'][c]['unknown_events']==[1]
  assert not gs[G,'BUF'][c]['native_credit_census_exact']

@pytest.mark.parametrize('patch',[{'no_play':True},{'play_type':'no_play'},{'two_point_attempt':'1'}])
def test_explicit_exclusions_precede_physical_zero_guard(patch):
 r=row(pass_attempt='0',rush_attempt='0',sack='0',qb_dropback='0',qb_scramble='0',qb_kneel='0',qb_spike='0',**patch)
 gs,_=build_census([r],S)
 assert all(not gs[G,'BUF'][c]['unknown_events']for c in CHANNELS)

def test_quarter_flag_does_not_erase_physical_zero_contradiction():
 r=row(rush_attempt='0',quarter_end='1')
 gs,_=build_census([r],S)
 assert gs[G,'BUF']['rush_attempts']['unknown_events']==[1]
