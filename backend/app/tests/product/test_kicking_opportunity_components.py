import pytest
from backend.app.product_services.opportunity_events import build_event_evidence
from backend.app.product_services.kicking_opportunity_components import build_kicking_components
from backend.app.tests.product.test_defense_context_evidence import play,SOURCE,CUTOFF
K='00-0031234';P='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
def kick(n=1,**kw):
 r=play(n,play_type='field_goal',pass_attempt=0,rush_attempt=0,qb_dropback=0,passer_player_id=None,receiver_player_id=None,rusher_player_id=None,field_goal_attempt=1,extra_point_attempt=0,field_goal_result='made',kick_distance=35,kicker_player_id=K,no_play=0);r.update(kw);return r
def build(rows,ids=None,source=None):
 e=build_event_evidence(rows,canonical_ids={},source_receipt=source or SOURCE,cutoff=CUTOFF)
 return build_kicking_components(dict(event_evidence=e),before_period=202606,cutoff=CUTOFF,canonical_ids={K:P} if ids is None else ids)
def metric(x,mid):return x['actor_game_rows'][0]['metrics'][mid]
def test_native_kicker_official_attempts_distance_accuracy_and_XP_separate():
 r=build([kick(),kick(2,kick_distance=55,field_goal_result='missed'),kick(3,play_type='extra_point',field_goal_attempt=0,extra_point_attempt=1,extra_point_result='made')])
 assert metric(r,'G23-M01')['exact_attempts']==2 and metric(r,'G23-M04')['exact_attempts']==1
 assert metric(r,'G23-M03')['distance_buckets']['30-39']['exact_within_log_accuracy']==1
 assert metric(r,'G23-M03')['distance_buckets']['50-59']['exact_within_log_accuracy']==0
 assert r['actor_game_rows'][0]['player_master_id']==P
def test_distance_boundaries_disjoint_and_blocked_failure_not_unknown():
 r=build([kick(i+1,kick_distance=n,field_goal_result='blocked') for i,n in enumerate([19,20,29,30,39,40,49,50,59,60])]);b=metric(r,'G23-M02')['distance_buckets']
 assert [b[k]['attempts'] for k in ('0-19','20-29','30-39','40-49','50-59','60+')]==[1,2,2,2,2,1]
 assert all(v['exact_within_log_accuracy']==0 for k,v in b.items() if k!='unknown')
def test_unknown_distance_keeps_full_attempt_and_masks_knownbucket_exact():
 r=build([kick(),kick(2,kick_distance=None)])
 assert metric(r,'G23-M01')['exact_attempts']==2
 assert metric(r,'G23-M02')['distance_buckets']['30-39']['exact_attempts'] is None
 assert r['team_game_rows'][0]['distance_buckets']['30-39']['exact_attempts'] is None
 assert metric(r,'G23-M02')['distance_buckets']['unknown']['attempts']==1
def test_unknown_result_not_fake_miss_or_accuracy():
 b=metric(build([kick(field_goal_result=None)]),'G23-M03')['distance_buckets']['30-39']
 assert b['unknown_result']==1 and b['exact_within_log_accuracy'] is None and b['known_result_accuracy'] is None
def test_no_play_and_two_point_not_extra_kicks():
 r=build([kick(),kick(2,no_play=1),kick(3,two_point_attempt=1)])
 assert metric(r,'G23-M01')['exact_attempts']==1
def test_missing_native_actor_keeps_team_budget_and_masks_actor_count():
 r=build([kick(),kick(2,kicker_player_id=None)])
 assert r['team_game_rows'][0]['FG']['exact_attempts']==2 and metric(r,'G23-M01')['exact_attempts'] is None
def test_unresolved_native_preserved_queue_and_no_position_guess():
 r=build([kick()],ids={})
 assert r['actor_game_rows'][0]['player_master_id'] is None and r['identity_review_requests']
 assert 'position' not in r['actor_game_rows'][0]
@pytest.mark.parametrize('change',[dict(kick_distance=-1),dict(kick_distance=20.5),dict(kicker_player_id='Kicker Name'),dict(field_goal_attempt=1,extra_point_attempt=1)])
def test_source_contradiction_rejects(change):
 with pytest.raises(ValueError):build([kick(**change)])
def test_duplicate_canonical_kicker_native_and_order_invariance():
 rows=[kick(),kick(2,field_goal_result='missed')]
 assert build(rows)['semantic_sha256']==build(list(reversed(rows)))['semantic_sha256']
 with pytest.raises(ValueError,match='Canonical kicker'):build([kick(),kick(2,kicker_player_id='00-0031235')],ids={K:P,'00-0031235':P})

def test_postlock_measurement_rejects_current_registration():
 from backend.app.product_services.kicking_opportunity_components import require_feature_use
 x=build([kick()]);assert require_feature_use(x,purpose='offline_descriptive') is x
 with pytest.raises(ValueError,match='cannot'):require_feature_use(x,purpose='current_forecast')

def test_unknown_FG_eligibility_masks_team_known_distance_buckets():
 r=build([kick(),kick(2,play_type=None,field_goal_attempt=None,extra_point_attempt=0,kick_distance=None,pass_attempt=None,rush_attempt=None,sack=None,qb_dropback=None,qb_scramble=None)])
 assert r['team_game_rows'][0]['FG']['unknown_eligibility']==1
 assert r['team_game_rows'][0]['distance_buckets']['30-39']['exact_attempts'] is None

def test_native_XP_good_failed_vocabulary_preserved_as_known_outcomes():
 r=build([kick(play_type='extra_point',field_goal_attempt=0,extra_point_attempt=1,extra_point_result='good'),kick(2,play_type='extra_point',field_goal_attempt=0,extra_point_attempt=1,extra_point_result='failed')])
 x=metric(r,'G23-M04');assert x['exact_attempts']==2 and x['known_made']==1 and x['known_failed']==1 and x['unknown_result']==0

@pytest.mark.parametrize('xp',[False,True])
def test_unknown_no_play_cannot_certify_official_FG_or_XP(xp):
 changes=dict(no_play=None)
 if xp:changes.update(play_type='extra_point',field_goal_attempt=0,extra_point_attempt=1,extra_point_result='good')
 x=build([kick(**changes)])
 metric_id='G23-M04' if xp else 'G23-M01'
 assert metric(x,metric_id)['exact_attempts'] is None and metric(x,metric_id)['unknown_eligibility']==1
 other='G23-M01' if xp else 'G23-M04'
 assert metric(x,other)['exact_attempts']==0

@pytest.mark.parametrize('xp',[False,True])
def test_absent_no_play_known_nflverse_agreeing_native_class_is_independent_proof(xp):
 k=kick(play_type_nfl='FIELD_GOAL')
 if xp:k.update(play_type='extra_point',play_type_nfl='XP_KICK',field_goal_attempt=0,extra_point_attempt=1,extra_point_result='good')
 del k['no_play']
 x=build([k],source={**SOURCE,'source_uri':'nflreadpy://pbp/2026'})
 assert metric(x,'G23-M04' if xp else 'G23-M01')['exact_attempts']==1
 b=x['event_basis'][0];assert b['no_play'] is None and b['no_play_key_present'] is False and b['derived_no_play'] is False
 assert b['nullification_basis']=='verified_source_exclusive_native_kick_classes'
@pytest.mark.parametrize('native',['PENALTY',None,'XP_KICK'])
def test_conflicting_missing_or_unknown_source_native_class_never_certifies(native):
 k=kick(play_type_nfl=native);del k['no_play']
 assert metric(build([k],source={**SOURCE,'source_uri':'nflreadpy://pbp/2026'}),'G23-M01')['exact_attempts'] is None
 k['play_type_nfl']='FIELD_GOAL'
 assert metric(build([k]),'G23-M01')['exact_attempts'] is None

def test_explicit_null_or_exclusion_precedes_known_categorical_source():
 source={**SOURCE,'source_uri':'nflreadpy://pbp/2026'}
 assert metric(build([kick(no_play=None,play_type_nfl='FIELD_GOAL')],source=source),'G23-M01')['exact_attempts'] is None
 x=build([kick(no_play=1,play_type_nfl='FIELD_GOAL')],source=source)
 assert x['actor_game_rows']==[]
