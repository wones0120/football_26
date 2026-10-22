from backend.app.tests.product.test_opportunity_events import play,build,CUTOFF
from backend.app.product_services.endzone_target_components import build_endzone_target_components

def run(rows):return build_endzone_target_components(build(rows),before_period=202509,cutoff=CUTOFF)
def event(n=1,**kw):return play(n,air_yards=15,yardline_100=10,**kw)

def test_known_target_endpoint_and_boundaries():
 r=run([event(),play(2,air_yards=10,yardline_100=10),play(3,air_yards=20,yardline_100=10)])
 assert r['actor_game_rows'][0]['value']==3 and r['team_game_rows'][0]['value']==3

def test_known_beyond_backline_and_short_is_zero():
 r=run([play(1,air_yards=21,yardline_100=10),play(2,air_yards=9,yardline_100=10)])
 assert r['actor_game_rows'][0]['value']==0

def test_missing_depth_unknown_not_zero():
 r=run([event(),play(2,air_yards=None,yardline_100=10)])
 assert r['actor_game_rows'][0]['value'] is None and r['actor_game_rows'][0]['known_endzone_targets']==1

def test_no_play_excluded():
 assert not run([event(play_type='no_play')])['actor_game_rows']

def test_unknown_native_masks_actor_and_retains_team():
 r=run([event(),play(2,receiver_player_id=None,air_yards=15,yardline_100=10)])
 assert r['actor_game_rows'][0]['value'] is None and len(r['unattributed_events'])==1

def test_unknown_actor_outside_band_does_not_donate_or_mask_endzone():
 r=run([event(),play(2,receiver_player_id=None,air_yards=2,yardline_100=40)])
 assert r['actor_game_rows'][0]['value']==1 and not r['unattributed_events']

def test_two_point_not_official_target():
 assert not run([event(two_point_attempt=1)])['actor_game_rows']

def test_missing_field_coordinate_unknown():
 assert run([play(1,air_yards=20,yardline_100=None)])['actor_game_rows'][0]['value'] is None


def test_use_guard():
 import pytest
 from backend.app.product_services.endzone_target_components import require_feature_use
 r=run([event()]);assert require_feature_use(r,purpose='offline_descriptive') is r
 with pytest.raises(ValueError):require_feature_use(r,purpose='forecast')
