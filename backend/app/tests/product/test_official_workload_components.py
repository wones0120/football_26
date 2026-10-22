from copy import deepcopy
import pytest
from backend.app.product_services.opportunity_events import build_event_evidence
from backend.app.product_services.official_workload_components import build_official_workload_components
from backend.app.tests.product.test_defense_context_evidence import play,SOURCE,CUTOFF,IDS
from backend.app.tests.product.test_defense_context_extensions import rush,proof,NATIVE,CANONICAL
QN='00-0000002';QP='00000000-0000-0000-0000-000000000003'


def build(rows,proofs=None,source=None):
 rows=deepcopy(rows)
 for row in rows:
  for key in ('passer_player_id','rusher_player_id'):
   if row.get(key)=='q':row[key]=QN
 parent=dict(event_evidence=build_event_evidence(rows,canonical_ids={QN:QP,NATIVE:CANONICAL,'w':IDS['w']},source_receipt=source or SOURCE,cutoff=CUTOFF))
 return build_official_workload_components(parent,before_period=202606,cutoff=CUTOFF,position_evidence=proofs if proofs is not None else [proof(source_player_id=QN,player_master_id=QP),proof(position='RB')])


def actor(result,native):return next(r for r in result['actor_game_rows'] if r['source_player_id']==native)


def test_official_dropback_union_includes_spike_sack_scramble_once_excludes_kneel():
 rows=[play(1),play(2,sack=1),play(3,qb_spike=1,receiver_player_id=None),rush(4,rusher_player_id='q',passer_player_id=None,qb_scramble=1,qb_dropback=1),rush(5,rusher_player_id='q',qb_kneel=1)]
 result=build(rows);q=actor(result,QN)['metrics']
 assert q['G03-M01']['exact_within_log_count']==4
 assert q['G03-M07']['exact_within_log_value']==.25
 assert q['G03-M10']['exact_within_log_value']==1
 assert result['full_team_denominators'][0]['measurements']['dropbacks']['exact_within_log_count']==4


def test_union_is_physical_even_source_qb_dropback_unknown_not_arbitrary_count_sum():
 result=build([play(1,qb_dropback=None),play(2,sack=1,qb_dropback=None)])
 assert actor(result,QN)['metrics']['G03-M01']['exact_within_log_count']==2


def test_official_RB_contexts_include_kneels_and_fullteam_QB_carry_denominator():
 rows=[rush(1,down=1,ydstogo=1,qtr=2,half_seconds_remaining=100,score_differential=3),
  rush(2,down=3,ydstogo=2,qtr=4,half_seconds_remaining=120,score_differential=-1,qb_kneel=1),
  rush(3,down=2,ydstogo=4,qtr=1,half_seconds_remaining=500,score_differential=0),
  rush(4,rusher_player_id='q',qb_kneel=1,qtr=4,score_differential=7)]
 r=actor(build(rows),NATIVE)['metrics'];share=r['G06-M02']
 assert share['numerator']['exact_within_log_count']==3 and share['full_team_denominator']['exact_within_log_count']==4
 assert share['exact_within_log_value']==.75
 assert [r[k]['exact_within_log_count'] for k in ['G06-M03','G06-M04','G06-M05','G06-M06','G06-M07','G06-M08','G06-M09','G06-M10']]==[2,1,2,2,2,1,1,1]


def test_backup_native_unmapped_still_in_team_dropback_budget():
 result=build([play(1),play(2,passer_player_id='unmapped')]);m=actor(result,QN)['metrics']['G03-M10']
 assert m['denominator']['exact_within_log_count']==2 and m['exact_within_log_value']==.5


def test_missing_passer_or_rusher_masks_actor_but_keeps_known_team_budget():
 result=build([play(1),play(2,passer_player_id=None),rush(3),rush(4,rusher_player_id=None)])
 q=actor(result,QN)['metrics'];r=actor(result,NATIVE)['metrics']
 assert q['G03-M01']['counted_lower_bound']==1 and q['G03-M01']['exact_within_log_count'] is None
 assert q['G03-M10']['denominator']['exact_within_log_count']==2
 assert r['G06-M02']['full_team_denominator']['exact_within_log_count']==2
 assert r['G06-M02']['exact_within_log_value'] is None and result['unattributed_events']


def test_native_missing_outside_subset_does_not_pollute_known_false_subset():
 result=build([rush(1,down=1),rush(2,down=3,rusher_player_id=None)])
 r=actor(result,NATIVE)['metrics']
 assert r['G06-M03']['exact_within_log_count']==1
 assert r['G06-M04']['exact_within_log_count'] is None


def test_unknown_context_not_zero_and_zero_denominator_not_zero_share():
 result=build([rush(1,down=None,ydstogo=None,qtr=None,half_seconds_remaining=None,score_differential=None)])
 r=actor(result,NATIVE)['metrics']
 assert all(r[k]['exact_within_log_count'] is None for k in ['G06-M03','G06-M05','G06-M06','G06-M07','G06-M08','G06-M09','G06-M10'])
 result=build([rush(1,rusher_player_id='q',qb_kneel=1)])
 assert actor(result,QN)['metrics']['G03-M07']['exact_within_log_value'] is None


def test_no_position_guess_and_excluded_no_play_two_point_never_official():
 assert build([play(1),rush(2)],proofs=[])['actor_game_rows']==[]
 result=build([play(1,no_play=1),rush(2,two_point_attempt=1)])
 assert all(t['measurements']['dropbacks']['exact_within_log_count']==0 for t in result['full_team_denominators'])
 assert build([])['actor_game_rows']==[]


def test_source_flags_unknown_mask_official_union_not_zero():
 result=build([play(1),play(2,pass_attempt=None,rush_attempt=None,qb_dropback=None)])
 assert actor(result,QN)['metrics']['G03-M01']['exact_within_log_count'] is None
 assert result['full_team_denominators'][0]['measurements']['dropbacks']['unknown_eligibility_events']==1


def test_canonical_scope_future_clock_and_material_semantics():
 with pytest.raises(ValueError):build([rush(1)],proofs=[proof(player_master_id=QP)])
 with pytest.raises(ValueError):build([play(1,game_id='2026_06_BUF_MIA',week=6)])
 with pytest.raises(ValueError):build([rush(1)],proofs=[proof(available_at='2026-10-20T01:00:00Z')])
 rows=[play(1),rush(2)];a=build(rows);source=deepcopy(SOURCE);source['captured_at']=source['received_at']='2026-10-19T19:30:00Z'
 assert a['semantic_measurements_sha256']==build(rows[::-1],source=source)['semantic_measurements_sha256']
 rows[1]['qb_kneel']=1 # Official-inclusive counts unchanged, but parent source ancestry remains material.
 assert a['semantic_measurements_sha256']!=build(rows)['semantic_measurements_sha256']


def test_retrospective_reader_actual_time_and_current_use_rejection(tmp_path):
 from datetime import timedelta
 from backend.app.tests.product.test_opportunity_source_capture import capture,derive,NOW,LOCK
 from backend.app.tests.test_source_capture import _session
 from backend.app.services.source_capture import SourceCaptureService
 from backend.app.product_services.opportunity_source_capture import freeze_event_artifact
 from backend.app.product_services.player_opportunity_components import require_component_use
 from backend.app.product_services.official_workload_components import derive_retrospective_official_workload
 session=_session()
 try:
  service=SourceCaptureService(session,snapshot_root=tmp_path/'raw',clock=lambda:NOW);snapshot=capture(service).snapshot
  ref=freeze_event_artifact(derive(snapshot),snapshot,directory=tmp_path/'parents');actual=LOCK+timedelta(minutes=1)
  result=derive_retrospective_official_workload(ref,snapshot,actual_read_at=actual,directory=tmp_path/'parents')
  assert result['provenance']['retrospective_read']['actual_read_at']==actual.isoformat()
  with pytest.raises(ValueError,match='cannot be registered'):require_component_use(result,purpose='forecast')
  with pytest.raises(ValueError,match='postlock'):derive_retrospective_official_workload(ref,snapshot,actual_read_at=NOW,directory=tmp_path/'parents')
 finally:session.close()


def test_same_scramble_cannot_be_different_native_passer_and_rusher():
 with pytest.raises(ValueError,match='contradictory native passer/rusher'):
  build([rush(1,passer_player_id='q',rusher_player_id=NATIVE,qb_scramble=1,qb_dropback=1)])
