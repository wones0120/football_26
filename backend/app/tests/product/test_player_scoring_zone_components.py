from copy import deepcopy
import pytest
from backend.app.product_services.opportunity_events import build_event_evidence
from backend.app.product_services.player_scoring_zone_components import build_player_scoring_zone_components,DEFINITIONS
from backend.app.tests.product.test_defense_context_evidence import play,SOURCE,CUTOFF,IDS
from backend.app.tests.product.test_defense_context_extensions import rush,NATIVE,CANONICAL,proof


def build(rows,ids=None,source=None,proofs=()):
 parent=dict(event_evidence=build_event_evidence(rows,canonical_ids=IDS if ids is None else ids,source_receipt=source or SOURCE,cutoff=CUTOFF))
 return build_player_scoring_zone_components(parent,before_period=202606,cutoff=CUTOFF,position_evidence=proofs)


def actor(result,native):return next(r for r in result['actor_game_rows'] if r['source_player_id']==native)


def count(row,key):return row['metrics'][key]['exact_within_log_count']


def test_all_three_disjoint_preplay_zones_and_native_boundaries():
 result=build([play(n,yardline_100=y,goal_to_go=0) for n,y in enumerate([100,21,20,6,5,0],1)])
 assert len(DEFINITIONS)==10
 q=actor(result,'q');w=actor(result,'w')
 assert [count(q,f'G11-M{i:02}') for i in (7,8,9)]==[2,2,2]
 assert [count(w,f'G11-M{i:02}') for i in (4,5,6)]==[2,2,2]
 assert len(result['full_team_denominators'])==1
 channels=result['full_team_denominators'][0]['channels']
 assert channels['targets']['all_official']['exact_within_log_count']==6
 assert channels['targets']['unknown_zone']['exact_within_log_count']==0
 assert result['definitions']['G11-M10']['catalog_scope'].startswith('Declared channel-specific')


def test_official_rush_includes_kneel_and_official_pass_spike_but_not_sack_or_scramble_pass():
 result=build([rush(1,yardline_100=20,qb_kneel=1),rush(2,yardline_100=5,qb_scramble=1,qb_dropback=1),
  play(3,yardline_100=21,qb_spike=1,receiver_player_id=None),play(4,yardline_100=5,sack=1)])
 r=actor(result,NATIVE);q=actor(result,'q')
 assert count(r,'G11-M02')==1 and count(r,'G11-M03')==1
 assert count(q,'G11-M07')==1 and count(q,'G11-M09')==0
 assert not any('targets' in r['goal_to_go_channel_shares'] for r in result['actor_game_rows'])


def test_full_team_GTG_denominator_keeps_unmapped_other_actor_and_no_cross_channel_sum():
 result=build([play(1,yardline_100=4,goal_to_go=1),play(2,yardline_100=3,goal_to_go=1,receiver_player_id='unmapped')])
 w=actor(result,'w');q=actor(result,'q')
 assert w['goal_to_go_channel_shares']['targets']['exact_within_log_share']==.5
 assert q['goal_to_go_channel_shares']['pass_attempts']['exact_within_log_share']==1
 assert result['identity_review_requests']
 assert actor(result,'unmapped')['player_master_id'] is None
 assert result['forecast'] is None


def test_missing_native_receiver_retains_team_counts_and_masks_exact_actor_count_and_share():
 result=build([play(1,yardline_100=4,goal_to_go=1),play(2,yardline_100=3,goal_to_go=1,receiver_player_id=None)])
 w=actor(result,'w');m=w['metrics']['G11-M06']
 assert m['counted_lower_bound']==1 and m['exact_within_log_count'] is None
 assert m['unknown_eligibility_events']==1
 assert w['goal_to_go_channel_shares']['targets']['full_team_denominator']['counted_lower_bound']==1
 assert w['goal_to_go_channel_shares']['targets']['full_team_denominator']['exact_within_log_count'] is None
 assert w['goal_to_go_channel_shares']['targets']['exact_within_log_share'] is None


def test_unknown_zone_masks_partition_not_channel_GTG_and_unknown_gtg_not_zero():
 result=build([play(1,yardline_100=None,goal_to_go=1),play(2,yardline_100=3,goal_to_go=None)])
 w=actor(result,'w')
 assert all(w['metrics'][f'G11-M{i:02}']['exact_within_log_count'] is None for i in (4,5,6))
 assert w['channel_coverage']['targets']['unknown_zone']['counted_lower_bound']==1
 assert w['channel_coverage']['targets']['all_official']['counted_lower_bound']==2
 share=w['goal_to_go_channel_shares']['targets']
 assert share['exact_within_log_share'] is None
 assert share['full_team_denominator']['counted_lower_bound']==1
 assert share['full_team_denominator']['unknown_eligibility_events']==1


def test_unknown_channel_eligibility_inherited_by_all_potential_actors():
 result=build([play(1,yardline_100=4),play(2,yardline_100=4,pass_attempt=None,qb_dropback=None,sack=None,qb_spike=None)])
 w=actor(result,'w');q=actor(result,'q')
 assert count(q,'G11-M09') is None and count(w,'G11-M06') is None
 assert count(w,'G11-M04')==0 # known inside5 cannot be outside20 despite unknown channel


def test_zero_GTG_denominator_is_unknown_share_not_zero_and_excluded_plays_do_not_count():
 result=build([play(1,goal_to_go=0),play(2,no_play=1,goal_to_go=1),play(3,two_point_attempt=1,goal_to_go=1)])
 w=actor(result,'w');s=w['goal_to_go_channel_shares']['targets']
 assert s['zero_denominator'] and s['exact_within_log_share'] is None
 assert sum(count(w,f'G11-M{i:02}') for i in (4,5,6))==1
 assert build([])['actor_game_rows']==[]


def test_order_recapture_invariant_material_zone_and_quality_change_hash():
 rows=[play(1,yardline_100=4),rush(2,yardline_100=20)]
 first=build(rows);source=deepcopy(SOURCE);source['captured_at']=source['received_at']='2026-10-19T19:30:00Z'
 assert first['semantic_measurements_sha256']==build(rows[::-1],source=source)['semantic_measurements_sha256']
 rows[0]['yardline_100']=21
 assert first['semantic_measurements_sha256']!=build(rows)['semantic_measurements_sha256']
 source['full_game_coverage']='independently_verified'
 assert build(rows)['semantic_measurements_sha256']!=build(rows,source=source)['semantic_measurements_sha256']


def test_canonical_scope_and_prior_only_clocks_use_existing_verified_guards():
 known=build([rush(1,yardline_100=4)],ids={NATIVE:CANONICAL},proofs=[proof(player_master_id=None)])
 assert actor(known,NATIVE)['player_master_id']==CANONICAL
 with pytest.raises(ValueError):build([play(1,game_id='2026_06_BUF_MIA',week=6)])
 with pytest.raises(ValueError):build([rush(1)],proofs=[proof(available_at='2026-10-20T01:00:00Z')])


def test_known_official_rush_missing_rusher_remains_fullteam_not_donated():
 result=build([rush(1,yardline_100=4,goal_to_go=1),rush(2,yardline_100=3,goal_to_go=1,rusher_player_id=None)])
 r=actor(result,NATIVE);m=r['metrics']['G11-M03']
 assert m['counted_lower_bound']==1 and m['exact_within_log_count'] is None
 assert m['inherited_unattributed_eligible_events']==1
 assert r['goal_to_go_channel_shares']['rush_attempts']['full_team_denominator']['exact_within_log_count']==2
 assert r['goal_to_go_channel_shares']['rush_attempts']['exact_within_log_share'] is None


def test_retrospective_actual_clocks_and_current_use_rejection(tmp_path):
 from datetime import timedelta
 from backend.app.tests.product.test_opportunity_source_capture import capture,derive,NOW,LOCK
 from backend.app.tests.test_source_capture import _session
 from backend.app.services.source_capture import SourceCaptureService
 from backend.app.product_services.opportunity_source_capture import freeze_event_artifact
 from backend.app.product_services.player_opportunity_components import require_component_use
 from backend.app.product_services.player_scoring_zone_components import derive_retrospective_player_scoring_zones
 session=_session()
 try:
  service=SourceCaptureService(session,snapshot_root=tmp_path/'raw',clock=lambda:NOW)
  snapshot=capture(service).snapshot;ref=freeze_event_artifact(derive(snapshot),snapshot,directory=tmp_path/'parents')
  actual=LOCK+timedelta(minutes=1)
  result=derive_retrospective_player_scoring_zones(ref,snapshot,actual_read_at=actual,directory=tmp_path/'parents')
  assert result['provenance']['retrospective_read']['actual_read_at']==actual.isoformat()
  assert result['provenance']['retrospective_read']['original_evidence_boundary_at']==ref['decision_cutoff_at']
  with pytest.raises(ValueError,match='cannot be registered'):require_component_use(result,purpose='current_forecast')
  with pytest.raises(ValueError,match='postlock'):derive_retrospective_player_scoring_zones(ref,snapshot,actual_read_at=NOW,directory=tmp_path/'parents')
 finally:session.close()
