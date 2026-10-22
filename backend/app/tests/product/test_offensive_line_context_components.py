from copy import deepcopy
import pytest
from backend.app.product_services.opportunity_events import build_event_evidence
from backend.app.product_services.offensive_line_context_components import build_offensive_line_context_components
from backend.app.tests.product.test_defense_context_evidence import play,SOURCE,CUTOFF,IDS
from backend.app.tests.product.test_defense_context_extensions import rush


def build(rows,source=None,last=8):
 parent=dict(event_evidence=build_event_evidence(rows,canonical_ids=IDS,source_receipt=source or SOURCE,cutoff=CUTOFF))
 return build_offensive_line_context_components(parent,before_period=202606,cutoff=CUTOFF,last_n_games=last)


def metric(result,key):return result['team_windows'][0]['metrics'][key]


def test_sack_denominator_official_pass_attempt_plus_sack_not_scramble_or_double_count():
 result=build([play(1),play(2,sack=1),play(3,qb_spike=1,receiver_player_id=None),rush(4,qb_dropback=1,qb_scramble=1)])
 m=metric(result,'G13-M04')
 assert m['eligible_events']==3 and m['observed_outcome_sum']==1
 assert m['all_eligible_mean']==pytest.approx(1/3)
 assert result['forecast'] is None


def test_shortyard_includes_scramble_and_TD_conversion_not_kneel_or_long_yardage():
 result=build([rush(1,ydstogo=1,first_down_rush=1,rush_touchdown=0),rush(2,ydstogo=2,first_down_rush=0,rush_touchdown=1,qb_scramble=1,qb_dropback=1),rush(3,ydstogo=2,first_down_rush=0,rush_touchdown=0),rush(4,ydstogo=3,first_down_rush=1),rush(5,ydstogo=1,qb_kneel=1)])
 m=metric(result,'G13-M08');assert m['eligible_events']==3 and m['all_eligible_mean']==pytest.approx(2/3)


def test_behindLOS_strict_negative_separate_from_zero_stuff_rate():
 result=build([rush(1,yards_gained=-1),rush(2,yards_gained=0),rush(3,yards_gained=2),rush(4,qb_kneel=1,yards_gained=-1)])
 m=metric(result,'G13-M09');assert m['eligible_events']==3 and m['all_eligible_mean']==pytest.approx(1/3)


def test_directions_exactnative_labels_and_unknown_residual_masks_complete_rates():
 result=build([rush(1,run_location='left',epa=.5),rush(2,run_location='right',epa=-1),rush(3,run_location=None,epa=.1),rush(4,run_location='middle',epa=0)])
 d=result['team_windows'][0]['direction_success']
 assert d['left']['observed_known_mean']==1 and d['right']['observed_known_mean']==0 and d['middle']['observed_known_mean']==0
 assert d['unknown']['eligible_events']==1 and d['unknown']['observed_known_mean']==1
 assert all(d[k]['all_eligible_mean'] is None for k in ['left','middle','right'])
 assert all(d[k]['unknown_eligibility_events']==1 for k in ['left','middle','right'])


def test_missing_fields_and_unknown_eligibility_never_zero():
 result=build([rush(1,ydstogo=None,first_down_rush=None,rush_touchdown=0,yards_gained=None,epa=None,run_location='left')])
 assert metric(result,'G13-M08')['unknown_eligibility_events']==1
 assert metric(result,'G13-M09')['unknown_outcome_events']==1
 assert result['team_windows'][0]['direction_success']['left']['unknown_outcome_events']==1
 assert metric(result,'G13-M09')['all_eligible_mean'] is None
 result=build([rush(1,ydstogo=20,pass_attempt=None,rush_attempt=None)])
 assert metric(result,'G13-M08')['unknown_eligibility_events']==0 # known outside subset


def test_known_sample_rates_pool_exposures_not_unweighted_game_means_and_prior_window():
 first=[rush(1,yards_gained=-1)];second=[rush(n,game_id='2026_02_BUF_MIA',week=2,yards_gained=1) for n in range(2,5)]
 result=build(first+second);assert metric(result,'G13-M09')['observed_known_mean']==.25
 last=build(first+second,last=1);assert metric(last,'G13-M09')['all_eligible_mean']==0
 assert last['team_windows'][0]['source_periods']==[202602]


def test_excluded_source_events_not_offensive_counts_and_empty_not_zero_rate():
 result=build([play(1,no_play=1,sack=1),rush(2,two_point_attempt=1)])
 assert metric(result,'G13-M04')['eligible_events']==0 and metric(result,'G13-M04')['all_eligible_mean'] is None
 assert build([])['team_windows']==[]


def test_source_recapture_order_invariance_true_direction_and_sourcequality_change():
 rows=[rush(1,run_location='left'),play(2)];first=build(rows);source=deepcopy(SOURCE);source['captured_at']=source['received_at']='2026-10-19T19:30:00Z'
 assert first['semantic_measurements_sha256']==build(rows[::-1],source=source)['semantic_measurements_sha256']
 rows[0]['run_location']='right'
 assert first['semantic_measurements_sha256']!=build(rows)['semantic_measurements_sha256']
 source['full_game_coverage']='independently_verified'
 assert build(rows)['semantic_measurements_sha256']!=build(rows,source=source)['semantic_measurements_sha256']


def test_native_period_and_window_guards():
 with pytest.raises(ValueError):build([play(1,game_id='2026_06_BUF_MIA',week=6)])
 for last in [0,True,33,1.5]:
  with pytest.raises(ValueError):build([],last=last)


def test_retrospective_actual_time_and_current_use_rejection(tmp_path):
 from datetime import timedelta
 from backend.app.tests.product.test_opportunity_source_capture import capture,derive,NOW,LOCK
 from backend.app.tests.test_source_capture import _session
 from backend.app.services.source_capture import SourceCaptureService
 from backend.app.product_services.opportunity_source_capture import freeze_event_artifact
 from backend.app.product_services.player_opportunity_components import require_component_use
 from backend.app.product_services.offensive_line_context_components import derive_retrospective_offensive_line_context
 session=_session()
 try:
  service=SourceCaptureService(session,snapshot_root=tmp_path/'raw',clock=lambda:NOW);snapshot=capture(service).snapshot
  ref=freeze_event_artifact(derive(snapshot),snapshot,directory=tmp_path/'parents');actual=LOCK+timedelta(minutes=1)
  result=derive_retrospective_offensive_line_context(ref,snapshot,actual_read_at=actual,directory=tmp_path/'parents')
  assert result['provenance']['retrospective_read']['actual_read_at']==actual.isoformat()
  with pytest.raises(ValueError,match='cannot be registered'):require_component_use(result,purpose='forecast')
  with pytest.raises(ValueError,match='postlock'):derive_retrospective_offensive_line_context(ref,snapshot,actual_read_at=NOW,directory=tmp_path/'parents')
 finally:session.close()
