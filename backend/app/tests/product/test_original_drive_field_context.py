from backend.app.tests.product.test_game_clock_pace_catalog import _parent
from backend.app.tests.product.test_environment_context_evidence import event
from backend.app.tests.product.test_defense_context_evidence import CUTOFF
from backend.app.product_services.original_drive_field_context import build_original_drive_field_context,_field

def p(pid=1,**changes):return event(pid,**(dict(drive=1,fixed_drive=2,order_sequence=pid,drive_start_yard_line='BUF 30',drive_play_id_started=1,drive_play_id_ended=2,drive_inside20=0,drive_end_transition='PUNT',yardline_100=60)|changes))
def end(**changes):return p(2,**(dict(play_type='punt',pass_attempt=0,rush_attempt=0,qb_dropback=0,punt_attempt=1,punt_blocked=0)|changes))
def run(rows):return build_original_drive_field_context(_parent(rows),before_period=202606,cutoff=CUTOFF)['game_rows'][0]

def test_source_start_and_nonreach_terminal_separate():
 r=run([p(),end()]);d=r['drives'][0]
 assert d['start_yardline100']==70 and d['first_observed_physical_snap_yardline100']==60
 assert r['metrics']['X05-M01']['value']==70 and r['metrics']['X05-M02']['value']==0

def test_right_censor_flag_zero_not_failed_transition():
 r=run([p()]);assert r['metrics']['X05-M01']['value']==70 and r['metrics']['X05-M02']['value'] is None

def test_provider_reach_does_not_need_terminal():
 assert run([p(drive_inside20=1)])['metrics']['X05-M02']['value']==1

def test_provider_observed_reach_conflict_unknown():
 r=run([p(yardline_100=19),end()]);assert r['drives'][0]['source_contradiction'] and r['metrics']['X05-M02']['value'] is None

def test_observed_reach_with_unknown_flag_known():
 assert run([p(drive_inside20=None,yardline_100=19)])['metrics']['X05-M02']['value']==1

def test_startinside20_counts_reached_state():
 r=run([p(drive_start_yard_line='MIA 15',drive_inside20=1)])
 assert r['metrics']['X05-M01']['value']==15 and r['metrics']['X05-M02']['value']==1

def test_field_side_and_midfield_unknown():
 pair={'BUF','MIA'}
 assert _field('50','BUF',pair)==50 and _field('MIA 0','BUF',pair)==0 and _field('BUF 0','BUF',pair)==100
 assert _field('LA 30','BUF',pair) is None and _field('garbage','BUF',pair) is None

def test_unknown_start_masks_all_cohort_not_sample():
 r=run([p(),end(),p(3,drive=2,drive_start_yard_line='',drive_play_id_started=3,drive_play_id_ended=3)])
 assert r['metrics']['X05-M01']['value'] is None and r['metrics']['X05-M01']['known_sample_mean']==70

def test_missing_native_first_play_not_reconstructed_from_first_snap():
 r=run([p(drive_play_id_started=9)]);assert r['drives'][0]['reported_start_yardline100']==70 and r['metrics']['X05-M01']['value'] is None

def test_first_native_link_cannot_follow_physical_snap():
 r=run([p(drive_play_id_started=2),p(2,drive_play_id_started=2)]);assert r['metrics']['X05-M01']['value'] is None

def test_native_id_order_not_sorted_numeric():
 r=run([p(20,order_sequence=1,drive_play_id_started=20,drive_play_id_ended=1),p(1,order_sequence=2,drive_play_id_started=20,drive_play_id_ended=1)])
 assert r['metrics']['X05-M01']['value']==70

def test_original_and_fixed_drive_not_equated():
 r=run([p(),end(fixed_drive=9)]);assert len(r['drives'])==1 and r['drives'][0]['source_fixed_drive_ids']==['2','9']

def test_source_flag_conflict_preserved():
 r=run([p(drive_inside20=1),end(drive_inside20=0)]);assert r['metrics']['X05-M02']['value'] is None

def test_descriptive_only_use_guard():
 import pytest
 from backend.app.product_services.original_drive_field_context import require_feature_use
 r=build_original_drive_field_context(_parent([p(),end()]),before_period=202606,cutoff=CUTOFF)
 assert require_feature_use(r,purpose='offline_descriptive') is r
 with pytest.raises(ValueError):require_feature_use(r,purpose='forecast')
