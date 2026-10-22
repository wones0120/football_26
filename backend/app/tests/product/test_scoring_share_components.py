from copy import deepcopy
import pytest
from backend.app.product_services.opportunity_events import build_event_evidence
from backend.app.product_services.scoring_share_components import build_scoring_shares
from backend.app.tests.product.test_defense_context_evidence import play as native_play,SOURCE,CUTOFF,IDS
def play(n=1,**kw):
 r=native_play(n,**kw);r.setdefault('lateral_reception',0);r.setdefault('lateral_rush',0);return r

def rush(n=1,**kw):
 r=play(n,play_type='run',pass_attempt=0,rush_attempt=1,qb_dropback=0,rusher_player_id='q',passer_player_id=None,receiver_player_id=None,rush_touchdown=1,pass_touchdown=0);r.update(kw);return r
def build(rows,ids=None):
 e=build_event_evidence(rows,canonical_ids=ids or IDS,source_receipt=SOURCE,cutoff=CUTOFF)
 return build_scoring_shares(dict(event_evidence=e),before_period=202606,cutoff=CUTOFF)
def actor(x,native,game=None):return next(r for r in x['actor_game_rows'] if r['source_player_id']==native and (game is None or r['game_id']==game))
def test_fullteam_TDshares_physical_pass_and_receiver_TD_count_once():
 r=build([play(1,pass_touchdown=1),play(2,pass_touchdown=0),rush(3),rush(4,rusher_player_id='other')])
 assert actor(r,'q')['metrics']['G12-M04']['exact_within_log_value']==.5
 assert actor(r,'w')['metrics']['G12-M05']['exact_within_log_value']==1
 t=r['team_game_rows'][0]
 assert t['counts']['passing_TD']['known_count']==1 and t['metrics']['G12-M03']['exact_within_log_value']==.5
 assert t['metrics']['G12-M02']['exact_within_log_value']==1
def test_missing_receiver_on_known_TD_masks_actor_share_keeps_team_event():
 r=build([play(1,pass_touchdown=1),play(2,pass_touchdown=1,receiver_player_id=None)])
 m=actor(r,'w')['metrics']['G12-M05'];assert m['exact_within_log_value'] is None
 assert m['full_team_denominator']['known_count']==2 and m['numerator']['exact_within_log_count'] is None
def test_missing_receiver_with_known_noTD_does_not_invent_TD_exposure():
 r=build([play(1,pass_touchdown=1),play(2,pass_touchdown=0,receiver_player_id=None)])
 assert actor(r,'w')['metrics']['G12-M05']['exact_within_log_value']==1
def test_unknown_TDflag_not_false_and_zero_TD_denominator_undefined():
 r=build([play(1,pass_touchdown=None),rush(2,rush_touchdown=0)])
 assert actor(r,'w')['metrics']['G12-M05']['exact_within_log_value'] is None
 assert actor(r,'q')['metrics']['G12-M04']['exact_within_log_value'] is None
def test_official_spike_kneel_denominators_retained_two_point_excluded():
 r=build([play(1,pass_touchdown=1),play(2,qb_spike=1,receiver_player_id=None,pass_touchdown=0),rush(3),rush(4,qb_kneel=1,rush_touchdown=0),rush(5,two_point_attempt=1)])
 t=r['team_game_rows'][0]['metrics'];assert t['G12-M02']['exact_within_log_value']==.5 and t['G12-M03']['exact_within_log_value']==.5
def test_actor_window_denominator_samegames_not_unobserved_team_games():
 a=play(1,pass_touchdown=1);b=play(1,game_id='2026_02_BUF_MIA',week=2,pass_touchdown=1,receiver_player_id='other');c=play(1,game_id='2026_03_BUF_MIA',week=3,pass_touchdown=1)
 x=build([a,b,c]);w=next(r for r in x['actor_windows'] if r['source_player_id']=='w' and r['requested_observed_games']==3)
 assert w['observed_games']==['2026_01_BUF_MIA','2026_03_BUF_MIA'] and w['metrics']['G12-M05']['full_team_denominator']['known_count']==2
 assert w['metrics']['G12-M05']['exact_within_log_value']==1
def test_scope_order_and_prior_guard():
 rows=[play(1,pass_touchdown=1),rush(2)]
 assert build(rows)['semantic_sha256']==build(list(reversed(rows)))['semantic_sha256']
 with pytest.raises(ValueError):build([play(1,game_id='2026_06_BUF_MIA',week=6)])

def test_retrospective_measured_shares_are_not_pregame_registration():
 from backend.app.product_services.scoring_share_components import require_feature_use
 x=build([play(1,pass_touchdown=1)]);assert require_feature_use(x,purpose='offline_descriptive') is x
 with pytest.raises(ValueError,match='cannot'):require_feature_use(x,purpose='forecast')

def test_canonical_UUID_window_combines_verified_native_aliases_preserving_keys():
 rows=[play(1,pass_touchdown=1),play(1,game_id='2026_02_BUF_MIA',week=2,receiver_player_id='alternate',pass_touchdown=1)]
 x=build(rows,ids={**IDS,'alternate':IDS['w']})
 w=[r for r in x['actor_windows'] if r['player_master_id']==IDS['w'] and r['requested_observed_games']==3]
 assert len(w)==1 and w[0]['observed_games_count']==2 and w[0]['source_player_ids']==['alternate','w']

def test_authoritative_lateral_TD_scorer_receives_credit_not_initial_recipient():
 r=build([play(1,pass_touchdown=1,receiver_player_id='w',td_player_id='q',lateral_reception=1)])
 assert actor(r,'q')['metrics']['G12-M05']['exact_within_log_value']==1
 assert actor(r,'w')['metrics']['G12-M05']['exact_within_log_value']==0
 assert r['team_game_rows'][0]['counts']['passing_TD']['known_count']==1

def test_lateral_TD_missing_scorer_unattributed_not_donated_to_first_actor():
 r=build([play(1,pass_touchdown=1,receiver_player_id='w',td_player_id=None,lateral_reception=1)])
 assert actor(r,'w')['metrics']['G12-M05']['exact_within_log_value'] is None
 assert r['team_game_rows'][0]['counts']['passing_TD']['unattributed_known_events']==1

def test_native_scorer_missing_parent_identity_retained_with_review_request():
 r=build([play(1,pass_touchdown=1,td_player_id='native-scoring-actor',lateral_reception=1)])
 a=actor(r,'native-scoring-actor');assert a['player_master_id'] is None and a['metrics']['G12-M05']['exact_within_log_value']==1
 assert any(x['source_player_id']=='native-scoring-actor' for x in r['identity_review_requests'])

def test_rushing_lateral_credits_actual_native_scorer_once():
 r=build([rush(1,rusher_player_id='q',td_player_id='w',lateral_rush=1)])
 assert actor(r,'q')['metrics']['G12-M04']['exact_within_log_value']==0
 assert actor(r,'w')['metrics']['G12-M04']['exact_within_log_value']==1
 assert r['team_game_rows'][0]['counts']['rushing_TD']['known_count']==1

def test_offensive_TD_team_contradiction_rejected():
 with pytest.raises(ValueError,match='TD team'):build([play(1,pass_touchdown=1,td_team='MIA',td_player_id='w')])
