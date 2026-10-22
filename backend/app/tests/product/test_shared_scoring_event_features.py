from copy import deepcopy
import pytest
from backend.app.product_services.shared_scoring_event_features import build_shared_scoring_events
Q='00-0000001';R='00-0000002';L='00-0000003'
P='00000000-0000-0000-0000-000000000001';W='00000000-0000-0000-0000-000000000002';X='00000000-0000-0000-0000-000000000003'
G='2026_01_BUF_MIA'

def inputs():
    provenance=dict(source=dict(snapshot_id='raw',content_sha256='sha'),event_receipt_sha256='events')
    common=dict(before_period=202606,evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,provenance=provenance)
    actors=[dict(game_id=G,team='BUF',source_player_id=n,player_master_id=p)for n,p in ((Q,P),(R,W),(L,X))]
    scoring=dict(**common,version='scoring_share_components_v1',semantic_sha256='s',actor_game_rows=actors,event_basis=[dict(game_id=G,team='BUF',play_id='1',passing_and_receiving_same_TD=True,receiver=R,original_receiver=R)])
    effect=dict(**common,version='player_effectiveness_components_v1',semantic_measurements_sha256='e',actor_game_rows=[dict(**r,position='QB'if r['source_player_id']==Q else 'WR',position_status='scoped_source_proven')for r in actors])
    return scoring,effect,[dict(game_id=G,team='BUF',play_id='1',passer_player_id=Q)]

def build(s,e,p):return build_shared_scoring_events(s,e,p,before_period=202606)

def test_one_physical_touchdown_has_two_linked_credits_not_two_team_tds():
    r=build(*inputs());g=r['team_game_rows'][0];event=r['event_rows'][0]
    assert g['known_physical_passing_TDs']==g['known_shared_QB_receiver_TDs']==1
    assert event['physical_team_TD_count']==event['shared_QB_passing_and_receiver_TD_credit']==1
    assert r['pair_game_rows'][0]['exact_within_log_shared_TDs']==1
    assert r['forecast']is None and r['pregame_serving_eligible']is False

def test_lateral_scorer_not_initial_recipient_and_self_catch_legal():
    s,e,p=inputs();s['event_basis'][0]['receiver']=L
    event=build(s,e,p)['event_rows'][0]
    assert event['source_TD_scorer_id']==L and event['source_initial_receiver_id']==R
    assert event['lateral_TD_scorer_differs_from_initial_receiver']is True
    s['event_basis'][0]['receiver']=Q
    assert build(s,e,p)['event_rows'][0]['same_actor_event']is True

def test_known_nonqb_trick_pass_kept_structural_not_in_qb_pair():
    s,e,p=inputs();e['actor_game_rows'][0]['position']='WR'
    r=build(s,e,p)
    assert len(r['event_rows'])==1 and not r['pair_game_rows']
    assert r['team_game_rows'][0]['known_nonQB_passing_TDs']==1
    assert r['team_game_rows'][0]['exact_within_log_shared_QB_receiver_TDs']==0

@pytest.mark.parametrize('field',['passer','scorer','position','TD_status'])
def test_unknown_pair_membership_masks_known_pair_exact_total(field):
    s,e,p=inputs();s['event_basis'].append({**s['event_basis'][0],'play_id':'2'});p.append({**p[0],'play_id':'2'})
    if field=='passer':p[1]['passer_player_id']=None
    if field=='scorer':s['event_basis'][1]['receiver']=None
    if field=='position':e['actor_game_rows'][0]['position_status']='unknown'
    if field=='TD_status':s['event_basis'][1]['passing_and_receiving_same_TD']=None
    r=build(s,e,p)
    assert r['team_game_rows'][0]['exact_within_log_shared_QB_receiver_TDs']is None
    if r['pair_game_rows']:assert r['pair_game_rows'][0]['exact_within_log_shared_TDs']is None

def test_missing_canonical_attachment_preserves_native_pair_and_review_request():
    s,e,p=inputs();s['actor_game_rows'][1]['player_master_id']=None;e['actor_game_rows'][1]['player_master_id']=None
    r=build(s,e,p)
    assert r['pair_game_rows'][0]['source_TD_scorer_id']==R
    assert r['pair_game_rows'][0]['TD_scorer_player_master_id']is None
    assert len(r['identity_review_requests'])==1

@pytest.mark.parametrize('change',['future','source','canonical','duplicate','name','missing_passer'])
def test_native_source_scope_or_identity_contradictions_reject(change):
    s,e,p=inputs()
    if change=='future':s['event_basis'][0]['game_id']='2026_06_BUF_MIA'
    if change=='source':e['provenance']=deepcopy(e['provenance']);e['provenance']['source']['content_sha256']='different'
    if change=='canonical':e['actor_game_rows'][0]['player_master_id']=W
    if change=='duplicate':p.append(deepcopy(p[0]))
    if change=='name':p[0]['passer_player_id']='Quarter Back'
    if change=='missing_passer':p.clear()
    with pytest.raises(ValueError):build(s,e,p)

def test_source_order_does_not_change_commutative_event_semantics():
    s,e,p=inputs();s['event_basis'].append({**s['event_basis'][0],'play_id':'2'});p.append({**p[0],'play_id':'2'})
    expected=build(s,e,p)['semantic_sha256'];s['event_basis'].reverse();p.reverse()
    assert build(s,e,p)['semantic_sha256']==expected
