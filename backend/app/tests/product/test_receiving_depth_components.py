from copy import deepcopy
import pytest
from backend.app.product_services.opportunity_events import build_event_evidence
from backend.app.product_services.receiving_depth_components import build_receiving_depth_components
from backend.app.tests.product.test_defense_context_evidence import play,SOURCE,CUTOFF,IDS


def build(rows,ids=None,source=None):
 return build_receiving_depth_components(dict(event_evidence=build_event_evidence(rows,canonical_ids=IDS if ids is None else ids,source_receipt=source or SOURCE,cutoff=CUTOFF)),before_period=202606,cutoff=CUTOFF)


def actor(result,native='w'):return next(r for r in result['actor_game_rows'] if r['source_player_id']==native)


def test_signed_depth_boundaries_and_all_target_denominator_preserve_behind_LOS():
 result=build([play(n,air_yards=d) for n,d in enumerate([-2,0,9.9,10,19.9,20,50],1)])
 row=actor(result);b=row['observed_partition']['buckets']
 assert b==dict(behind_LOS=1,short=2,intermediate=2,deep=2,unknown_depth=0)
 assert row['exact_within_log_target_count']==7
 for metric in ('G10-M07','G10-M08','G10-M09'):assert row['metrics'][metric]['exact_within_log_share']==pytest.approx(2/7)
 assert sum(b.values())==7
 assert result['forecast'] is None and 'screen' in result['limitations'][0]


def test_unknown_depth_masks_exact_but_retains_explicit_known_depth_sample():
 result=build([play(1,air_yards=25),play(2,air_yards=None)])
 row=actor(result);m=row['metrics']['G10-M09']
 assert m['known_attributed_bucket_count']==1 and m['exact_within_log_bucket_count'] is None
 assert m['full_player_target_denominator']==2 and m['exact_within_log_share'] is None
 assert m['known_depth_attributed_sample_share']==1 and m['unknown_depth_targets']==1


def test_missing_receiver_unknown_target_does_not_become_zero_or_exact_share():
 row=actor(build([play(1,air_yards=5),play(2,receiver_player_id=None,air_yards=20)]))
 assert row['exact_within_log_target_count'] is None
 assert row['inherited_team_unknown_target_eligibility']==1
 assert row['metrics']['G10-M07']['exact_within_log_share'] is None
 assert row['metrics']['G10-M07']['known_depth_attributed_sample_share']==1


def test_unknown_eligibility_with_native_receiver_not_a_known_target():
 row=actor(build([play(1,air_yards=5),play(2,air_yards=30,pass_attempt=None,qb_dropback=None,sack=None)]))
 assert row['observed_partition']['known_targets']==1
 assert row['observed_partition']['unknown_target_eligibility']==1
 assert row['metrics']['G10-M09']['exact_within_log_share'] is None


def test_unmapped_receiver_kept_in_fullteam_not_donated_to_known_actor():
 result=build([play(1,air_yards=5),play(2,receiver_player_id='unmapped',air_yards=30)])
 row=actor(result);unknown=actor(result,'unmapped');team=result['full_team_denominators'][0]
 assert row['metrics']['G10-M07']['exact_within_log_share']==1
 assert unknown['player_master_id'] is None and unknown['metrics']['G10-M09']['exact_within_log_share']==1
 assert team['known_targets']==2 and team['buckets']['deep']==1
 assert result['identity_review_requests']


def test_source_flags_exclude_spikes_sacks_no_plays_and_two_points():
 rows=[play(1,air_yards=5),play(2,air_yards=30,qb_spike=1,receiver_player_id=None),play(3,air_yards=40,sack=1),play(4,no_play=1),play(5,two_point_attempt=1)]
 row=actor(build(rows));assert row['exact_within_log_target_count']==1
 assert row['metrics']['G10-M07']['exact_within_log_share']==1
 assert build([])['actor_game_rows']==[]


def test_order_and_recapture_invariance_material_source_changes_invalidate():
 rows=[play(1,air_yards=5),play(2,air_yards=30)];first=build(rows);source=deepcopy(SOURCE);source['captured_at']=source['received_at']='2026-10-19T19:30:00Z'
 assert first['semantic_measurements_sha256']==build(rows[::-1],source=source)['semantic_measurements_sha256']
 rows[0]['air_yards']=12
 assert first['semantic_measurements_sha256']!=build(rows)['semantic_measurements_sha256']
 source['full_game_coverage']='independently_verified'
 assert build(rows)['semantic_measurements_sha256']!=build(rows,source=source)['semantic_measurements_sha256']


def test_prior_period_and_source_clock_guards_retained():
 with pytest.raises(ValueError):build([play(1,game_id='2026_06_BUF_MIA',week=6)])
 source=deepcopy(SOURCE);source['received_at']='2026-10-20T01:00:00Z'
 with pytest.raises(ValueError):build([play(1)],source=source)


def test_postlock_reader_keeps_actual_time_and_current_use_rejected(tmp_path):
 from datetime import timedelta
 from backend.app.tests.product.test_opportunity_source_capture import capture,derive,NOW,LOCK
 from backend.app.tests.test_source_capture import _session
 from backend.app.services.source_capture import SourceCaptureService
 from backend.app.product_services.opportunity_source_capture import freeze_event_artifact
 from backend.app.product_services.player_opportunity_components import require_component_use
 from backend.app.product_services.receiving_depth_components import derive_retrospective_receiving_depth
 session=_session()
 try:
  service=SourceCaptureService(session,snapshot_root=tmp_path/'raw',clock=lambda:NOW)
  snapshot=capture(service).snapshot;ref=freeze_event_artifact(derive(snapshot),snapshot,directory=tmp_path/'parents');actual=LOCK+timedelta(minutes=1)
  result=derive_retrospective_receiving_depth(ref,snapshot,actual_read_at=actual,directory=tmp_path/'parents')
  assert result['provenance']['retrospective_read']['actual_read_at']==actual.isoformat()
  assert result['pregame_serving_eligible'] is False
  with pytest.raises(ValueError,match='cannot be registered'):require_component_use(result,purpose='forecast')
  with pytest.raises(ValueError,match='postlock'):derive_retrospective_receiving_depth(ref,snapshot,actual_read_at=NOW,directory=tmp_path/'parents')
 finally:session.close()
