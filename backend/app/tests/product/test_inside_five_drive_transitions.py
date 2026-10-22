from backend.app.tests.product.test_game_clock_pace_catalog import _parent
from backend.app.tests.product.test_environment_context_evidence import event
from backend.app.tests.product.test_defense_context_evidence import CUTOFF
from backend.app.product_services.inside_five_drive_transitions import build_inside_five_drive_transitions

def run(rows):return build_inside_five_drive_transitions(_parent(rows),before_period=202606,cutoff=CUTOFF)['game_rows'][0]
def play(pid,yard,order,**kw):return event(pid,order_sequence=order,yardline_100=yard,fixed_drive=1,defteam='MIA',**kw)
def td(pid=3,yard=3,order=3):return play(pid,yard,order,pass_touchdown=1)

def test_reach_and_td_once():
 r=run([play(10,19,1),play(1,5,2),td()]);assert r['metrics']['X05-M03']['value']==r['metrics']['G12-M07']['value']==1

def test_right_censored_nonreach_unknown():
 r=run([play(1,19,1),play(2,8,2)]);assert r['metrics']['X05-M03']['value'] is None and not r['metrics']['G12-M07']['observed_entered_drives']

def test_observed_reach_requires_no_terminal_for_reach_only():
 r=run([play(1,19,1),play(2,4,2)]);assert r['metrics']['X05-M03']['value']==1 and r['metrics']['G12-M07']['value'] is None

def test_terminal_certifies_nonreach():
 terminal=play(2,8,2,play_type='field_goal',pass_attempt=0,qb_dropback=0,field_goal_attempt=1,field_goal_result='made',fixed_drive_result='Field goal',drive_end_transition='FIELD_GOAL')
 r=run([play(1,19,1),terminal]);assert r['metrics']['X05-M03']['value']==0

def test_unknown_yard_masks_nonreach():
 terminal=play(3,8,3,play_type='field_goal',pass_attempt=0,qb_dropback=0,field_goal_attempt=1,field_goal_result='made',fixed_drive_result='Field goal',drive_end_transition='FIELD_GOAL')
 r=run([play(1,19,1),play(2,None,2),terminal]);assert r['metrics']['X05-M03']['value'] is None

def test_native_order_not_numeric_ids():
 r=run([play(30,19,1),play(20,4,2),td(10,3,3)]);assert r['metrics']['G12-M07']['value']==1

def test_terminal_before_inside5_is_not_success():
 r=run([play(1,19,1),td(2,10,2),play(3,4,3)]);assert r['metrics']['G12-M07']['value'] is None

def test_missing_order_masks_all_transitions():
 r=run([play(1,19,None),td()]);assert r['metrics']['X05-M03']['value'] is None

def test_unknown_native_drive_membership_masks_game():
 r=run([play(1,19,1),td(),event(4,order_sequence=4,yardline_100=3,fixed_drive=None)])
 assert r['metrics']['X05-M03']['value'] is None and r['metrics']['X05-M03']['known_sample_value']==1

def test_no_entry_population_is_not_zero_rate():
 r=run([play(1,40,1)]);assert r['metrics']['X05-M03']['value'] is None and r['metrics']['X05-M03']['observed_entered_drives']==0

def test_retrospective_use_guard():
 import pytest
 from backend.app.product_services.inside_five_drive_transitions import build_inside_five_drive_transitions,require_feature_use
 r=build_inside_five_drive_transitions(_parent([play(1,19,1),td()]),before_period=202606,cutoff=CUTOFF)
 assert require_feature_use(r,purpose='offline_descriptive') is r
 with pytest.raises(ValueError):require_feature_use(r,purpose='forecast')
