from copy import deepcopy
import pytest
from backend.app.product_services.late_half_possession_context import build_late_half_context,project_late_half_source
from backend.app.product_services.drive_scoring_range import build_drive_scoring_range
from backend.app.tests.product.test_drive_scoring_range import inputs,raw


def fixture():
 x=list(inputs())
 for r in x[0]:r.update(qtr=2,game_half='Half1',half_seconds_remaining=100)
 x[0][0]['half_seconds_remaining']=121
 return x[0],build_drive_scoring_range(*x)


def run(rs=None,b=None):
 if rs is None:rs,b=fixture()
 return build_late_half_context(rs,b)['game_rows'][0]
def drive(x):return x['drives'][0]


def test_live_FG_entry_at115_when_last_physical_offense_was121():
 rs,b=fixture();rs[1]['half_seconds_remaining']=115;r=run(rs,b);d=drive(r)
 assert d['late_window_entry']is True and d['first_late_play_id']==2
 assert d['live_FG_attempt']is True and d['offensive_TD']is False
 assert d['reached20']is False and r['metrics']['exact_late_possession_count']==1
 assert d['starts_before_vs_inside_window']=='before'

@pytest.mark.parametrize('clock,entry',[(0,True),(120,True),(121,False),(-1,None),(None,None),(901,None)])
def test_clock_boundary_and_source_precision(clock,entry):
 rs,b=fixture()
 for r in rs:r['half_seconds_remaining']=clock
 assert drive(run(rs,b))['late_window_entry']is entry

@pytest.mark.parametrize('qtr,half,entry',[(1,'Half1',False),(3,'Half2',False),(5,'Overtime',False),(4,'Half2',True),(2,'UNKNOWN',None)])
def test_only_recognized_end_half_quarters_not_OT_or_end_quarter_substitute(qtr,half,entry):
 rs,b=fixture()
 for r in rs:r.update(qtr=qtr,game_half=half,half_seconds_remaining=100)
 assert drive(run(rs,b))['late_window_entry']is entry


def test_provider_order_firstentry_not_numeric_id_or_minimum_clock():
 rs,b=fixture();rs[0].update(play_id=100,half_seconds_remaining=115,order_sequence=1);rs[1].update(play_id=2,half_seconds_remaining=100,order_sequence=2)
 b['game_rows'][0]['drives'][0]['source_first_play_id']=100
 d=drive(run(rs[::-1],b));assert d['first_late_play_id']==100 and d['starts_before_vs_inside_window']=='inside'


def test_known_reach_needs_observed_preplay_site_but_nonreach_requires_terminal():
 rs,b=fixture();rs[0].update(half_seconds_remaining=100,yardline_100=4)
 b['game_rows'][0]['drives'][0]['verified_terminal_class']=None
 d=drive(run(rs,b));assert d['reached5']is True and d['offensive_TD']is None
 assert d['live_FG_attempt']is True and d['complete_postentry_segment']is False


def test_missing_zone_unknown_outcome_not_false_and_known_success_retained():
 rs,b=fixture();rs[1]['yardline_100']=None;d=drive(run(rs,b))
 assert d['reached20']is None and d['live_FG_attempt']is True


def test_unknown_earlier_entry_clock_does_not_claim_firstknown_is_certified_first():
 rs,b=fixture();rs[0]['half_seconds_remaining']=None;d=drive(run(rs,b))
 assert d['late_window_entry']is True and d['first_known_late_play_id']==2 and d['first_late_play_id']is None
 assert d['reached20']is None


def test_unknown_offense_or_drive_entry_preserves_possible_exposure_not_phantom_drive():
 rs,b=fixture();r=raw(3,posteam=None,drive=None,qtr=2,game_half='Half1',half_seconds_remaining=100,order_sequence=3)
 rs.append(r);x=build_late_half_context(rs,b)
 assert len(x['game_rows'][0]['drives'])==1 and len(x['unassigned_native_incidents'])==1
 assert x['game_rows'][0]['metrics']['exact_late_possession_count']is None

@pytest.mark.parametrize('field,value',[('order_sequence',None),('game_half','Half2'),('drive',2),('posteam',None)])
def test_unknown_boundary_or_intervening_membership_prevents_certified_negative(field,value):
 rs,b=fixture();rs[0]['half_seconds_remaining']=100;rs[1][field]=value;d=drive(run(rs,b))
 assert d['complete_postentry_segment']is False and d['offensive_TD']is None


def test_missing_source_timeline_never_known_zero_possessions():
 rs,b=fixture();rs=[];d=drive(run(rs,b));assert d['late_window_entry']is None


def test_offensive_TD_path_once_no_pass_receiver_doublecredit():
 rs,b=fixture();rs[0].update(half_seconds_remaining=100,pass_touchdown=1,rush_touchdown=0,touchdown=1)
 d=drive(run(rs,b));assert d['offensive_TD']is True
 assert run(rs,b)['metrics']['views']['offensive_TD']['known_successes']==1


def test_return_TD_does_not_become_original_offense_TD():
 rs,b=fixture();rs[0].update(half_seconds_remaining=100,pass_touchdown=0,rush_touchdown=0,touchdown=1,return_touchdown=1)
 assert drive(run(rs,b))['offensive_TD']is False

@pytest.mark.parametrize('flag',['qb_scramble','first_down_pass','pass_touchdown','third_down_failed'])
def test_material_positive_on_nominal_control_is_uncertain_not_quiet_skip(flag):
 rs,b=fixture();rs[0]['half_seconds_remaining']=100;r=raw(3,qtr=2,half_seconds_remaining=105,order_sequence=1.5,play_type='no_play',play_type_nfl='TIMEOUT',pass_attempt=0,qb_dropback=0,**{flag:1})
 rs.append(project_late_half_source(r));d=drive(run(rs,b));assert d['complete_postentry_segment']is False


def test_incomplete_endpoint_censored_not_no_attempt():
 rs,b=fixture();b['game_rows'][0]['drives'][0]['verified_terminal_class']=None;rs.pop()
 d=drive(run(rs,b));assert d['late_window_entry']is None

@pytest.mark.parametrize('bad',['duplicate','period','version'])
def test_native_key_and_source_scope_reject(bad):
 rs,b=fixture()
 if bad=='duplicate':rs.append(deepcopy(rs[0]))
 if bad=='period':rs[0]['week']=2
 if bad=='version':b['version']='other'
 with pytest.raises(ValueError):run(rs,b)


def test_missing_offense_source_cohort_is_unknown_not_zero_possessions():
 rs,b=fixture();b['game_rows'][0]['drives']=[]
 x=run([],b);assert x['metrics']['exact_late_possession_count']is None


def test_unproven_original_boundaries_cannot_certify_no_late_possession():
 rs,b=fixture()
 for r in rs:r['half_seconds_remaining']=121
 b['game_rows'][0]['drives'][0]['native_boundary_and_cohort_verified']=False
 assert drive(run(rs,b))['late_window_entry']is None

@pytest.mark.parametrize('kind',['field_goal','punt'])
def test_known_live_kick_class_with_false_attempt_flag_is_conflict_not_no_possession(kind):
 rs,b=fixture();rs[1].update(play_type=kind,play_type_nfl='FIELD_GOAL'if kind=='field_goal'else'PUNT',field_goal_attempt=0,punt_attempt=0)
 assert drive(run(rs,b))['late_window_entry']is None


def test_positive_TD_with_explicit_false_genericTD_is_unknown_outcome():
 rs,b=fixture();rs[0].update(half_seconds_remaining=100,pass_touchdown=1,rush_touchdown=0,touchdown=0)
 assert drive(run(rs,b))['offensive_TD']is None


def test_positive_FGflag_on_physical_pass_is_unknown_FG_path_not_false():
 rs,b=fixture();rs[0].update(half_seconds_remaining=100,field_goal_attempt=1);rs.pop();b['game_rows'][0]['drives'][0]['source_last_play_id']=1
 assert drive(run(rs,b))['live_FG_attempt']is None
