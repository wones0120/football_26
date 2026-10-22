from copy import deepcopy
import pytest
from backend.app.product_services.opportunity_events import build_event_evidence
from backend.app.product_services.charting_source_components import normalize_charting_rows,PROVIDER_URL
from backend.app.product_services.charted_football_features import build_charted_features
from backend.app.tests.product.test_defense_context_evidence import play,SOURCE,CUTOFF,IDS
from backend.app.tests.product.test_defense_context_extensions import proof
Q='00-0000002'
def chart(n=1,**kw):
 r=dict(nflverse_game_id='2026_01_BUF_MIA',nflverse_play_id=n,season=2026,week=1,is_play_action=True,is_throw_away=False,is_screen_pass=False,is_catchable_ball=True,is_contested_ball=False,is_drop=False,n_blitzers=1,n_pass_rushers=4,read_thrown='0',date_pulled='2026-10-19T19:00:00Z');r.update(kw);return r
def build(plays=None,charts=None,proofs=True):
 rows=deepcopy(plays or [play()])
 for p in rows:
  if p.get('passer_player_id')=='q':p['passer_player_id']=Q
 parent=dict(event_evidence=build_event_evidence(rows,canonical_ids={Q:IDS['q'],'w':IDS['w']},source_receipt=SOURCE,cutoff=CUTOFF))
 b=dict(rows=normalize_charting_rows(charts if charts is not None else [chart()],source_season=2026,cutoff=CUTOFF),source=dict(snapshot_id='ftn',content_sha256='b'*64,source_uri=PROVIDER_URL.format(season=2026),captured_at=CUTOFF,observed_at=CUTOFF))
 return build_charted_features(parent,b,before_period=202606,cutoff=CUTOFF,position_evidence=[proof(source_player_id=Q,player_master_id=IDS['q'])] if proofs else [])
def actor(x,native):return next(r for r in x['actor_game_rows'] if r['source_player_id']==native)['metrics']
def test_charted_QB_and_receiving_metrics_exact_denoms_not_pressure_proxy():
 r=build();q=actor(r,Q);w=actor(r,'w')
 assert q['G03-M05']['exact_within_log_sum']==0 and q['G03-M09']['exact_within_log_value']==1
 assert w['G08-M06']['exact_within_log_value']==1 and w['G08-M10']['exact_within_log_value']==1
 assert w['G09-M09']['exact_within_log_value']==0 and w['G10-M06']['exact_within_log_value']==0
 assert r['defense_game_rows'][0]['metrics']['G14-M02']['exact_within_log_mean']==1
def test_first_read_share_is_fullteam_primary_targets_not_own_alltargets():
 r=build([play(1),play(2,receiver_player_id='other'),play(3)], [chart(1),chart(2),chart(3,read_thrown='1')])
 assert actor(r,'w')['G08-M06']['exact_within_log_value']==.5
 assert r['team_game_denominators'][0]['measurements']['targets']['exact_within_log_sum']==3
def test_missing_chart_is_unknown_not_false_even_on_spike():
 r=build([play(1),play(2,qb_spike=1,receiver_player_id=None)],[chart(1)])
 assert actor(r,Q)['G03-M09']['exact_within_log_value'] is None
 assert r['coverage']['unmatched_relevant_PBP']
def test_drop_uncatchable_conflict_masks_both_rates_no_forced_zero():
 r=build(charts=[chart(is_drop=True,is_catchable_ball=False)])
 assert actor(r,'w')['G08-M10']['exact_within_log_value'] is None
 assert actor(r,'w')['G09-M09']['exact_within_log_value'] is None
def test_drop_catchable_known_rate_and_screen_contest():
 r=build(charts=[chart(is_drop=True,is_screen_pass=True,is_contested_ball=True)])
 assert [actor(r,'w')[k]['exact_within_log_value'] for k in ('G09-M09','G10-M06','G10-M10')]==[1,1,1]
def test_QBproof_absent_never_guesses_role():
 r=build(proofs=False)
 assert not any('G03-M05' in a['metrics'] for a in r['actor_game_rows'])
def test_unattributed_target_keeps_team_primary_denom_and_masks_player_exact():
 r=build([play(1),play(2,receiver_player_id=None)],[chart(1),chart(2)])
 assert actor(r,'w')['G08-M06']['exact_within_log_value'] is None
 m=r['team_game_denominators'][0]['measurements']['targets'];assert m['eligible']==1 and m['unknown_eligibility']==1 and m['exact_within_log_sum'] is None
def test_invalid_blitz_count_stays_unknown_and_no_five_rusher_proxy():
 r=build(charts=[chart(n_blitzers=None,n_pass_rushers=5)])
 assert r['defense_game_rows'][0]['metrics']['G14-M02']['exact_within_log_mean'] is None
def test_source_duplicate_chart_rows_rejected_before_join():
 with pytest.raises(ValueError,match='Duplicate'):build(charts=[chart(),chart()])
def test_scramble_same_physical_actor_conflict_rejected():
 r=play(1,play_type='run',pass_attempt=0,rush_attempt=1,qb_scramble=1,rusher_player_id='other')
 with pytest.raises(ValueError,match='scramble'):build([r])
def test_chart_order_invariant_original_clocks_and_nonserving():
 p=[play(1),play(2)];c=[chart(1),chart(2)]
 x=build(p,c);y=build(list(reversed(p)),list(reversed(c)))
 assert x['semantic_sha256']==y['semantic_sha256'] and not x['pregame_serving_eligible']

def test_postlock_feature_is_not_registered_as_pregame():
 from backend.app.product_services.charted_football_features import require_feature_use
 x=build();assert require_feature_use(x,purpose='offline_descriptive') is x
 with pytest.raises(ValueError,match='cannot'):require_feature_use(x,purpose='forecast')
