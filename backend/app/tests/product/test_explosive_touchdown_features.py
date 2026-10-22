from backend.app.tests.product.test_opportunity_events import play,build,CUTOFF
from backend.app.product_services.explosive_touchdown_features import build_explosive_touchdown_features

def run(rows):return build_explosive_touchdown_features(build(rows),before_period=202509,cutoff=CUTOFF)['game_rows'][0]
def passing(n=1,**kw):return play(n,**(dict(passing_yards=20,complete_pass=1,pass_touchdown=0,rush_touchdown=0)|kw))
def rush(n=2,**kw):return play(n,**(dict(play_type='run',pass_attempt=0,rush_attempt=1,qb_dropback=0,rushing_yards=10,rush_touchdown=0,pass_touchdown=0,rusher_player_id='q')|kw))

def test_channel_thresholds_union_and_td_once():
 r=run([passing(pass_touchdown=1),rush()]);assert r['channels']['pass']['value']==1 and r['channels']['rush']['value']==0 and r['channels']['physical_union']['value']==.5

def test_source_credit_not_net_or_initial_receiver():
 r=run([passing(passing_yards=5,yards_gained=80,receiving_yards=80)]);assert r['channels']['physical_union']['known_explosive_plays']==0 and r['channels']['physical_union']['value'] is None

def test_unknown_yards_masks_exact():
 r=run([passing(),passing(2,passing_yards=None)]);assert r['channels']['pass']['value'] is None and r['channels']['pass']['known_sample_rate']==0

def test_unknown_td_masks_exact_not_zero():
 r=run([passing(pass_touchdown=None)]);assert r['channels']['pass']['value'] is None and r['channels']['pass']['unknown_explosive_td_outcomes']==1

def test_proven_incompletion_yards_zero_only():
 r=run([passing(complete_pass=0,passing_yards=None)]);assert r['events'][0]['channels'][0]['source_credited_yards']==0

def test_rushing_kneel_counts_official_but_not_explosive():
 r=run([rush(qb_kneel=1,rushing_yards=-1)]);assert r['channels']['rush']['known_explosive_plays']==0

def test_scramble_not_passing_duplicate():
 r=run([rush(qb_scramble=1,rush_touchdown=1)]);assert r['channels']['physical_union']['known_explosive_tds']==1


def test_physical_td_or_same_event_once():
 r=run([passing(pass_touchdown=1,rush_touchdown=1)])
 assert r['channels']['physical_union']['known_explosive_tds']==1

def test_missing_other_td_flag_does_not_certify_physical_zero():
 r=run([passing(rush_touchdown=None)])
 assert r['channels']['pass']['value']==0 and r['channels']['physical_union']['value'] is None

def test_missing_yards_known_no_td_still_unknown_denominator():
 r=run([passing(passing_yards=None,pass_touchdown=0,rush_touchdown=0)])
 assert r['channels']['physical_union']['unknown_explosive_eligibility']==1 and r['channels']['physical_union']['value'] is None

def test_excluded_no_play_two_point_not_explosive():
 r=build_explosive_touchdown_features(build([passing(play_type='no_play'),passing(2,two_point_attempt=1)]),before_period=202509,cutoff=CUTOFF)
 assert not r['game_rows']

def test_incompletion_cannot_override_nonzero_yards():
 import pytest
 with pytest.raises(ValueError):run([passing(complete_pass=0,passing_yards=25)])

def test_descriptive_use_only():
 import pytest
 from backend.app.product_services.explosive_touchdown_features import require_feature_use
 r=build_explosive_touchdown_features(build([passing()]),before_period=202509,cutoff=CUTOFF)
 assert require_feature_use(r,purpose='offline_descriptive') is r
 with pytest.raises(ValueError):require_feature_use(r,purpose='forecast')
