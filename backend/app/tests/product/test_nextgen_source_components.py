from datetime import datetime,UTC,timedelta
from copy import deepcopy
import polars as pl
import pytest
from backend.app.product_services.nextgen_source_components import normalize_nextgen_rows,capture_nextgen_source,load_nextgen_snapshot
from backend.app.tests.test_source_capture import _session
from backend.app.services.source_capture import SourceCaptureService,SnapshotIntegrityError
NOW=datetime(2026,10,20,3,tzinfo=UTC)
PID='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
def row(**kw):
 r=dict(season=2023,season_type='REG',week=1,player_gsis_id='00-0031234',team_abbr='LA',attempts=20,completion_percentage=65,avg_time_to_throw=2.5);r.update(kw);return r
def norm(rows,**kw):return normalize_nextgen_rows(rows,stat_type='passing',cutoff=NOW,**kw)
def test_native_UUID_and_week0_POST_grains_no_inferred_game():
 rows=norm([row(),row(week=0),row(week=18,season_type='POST')],canonical_ids={'00-0031234':PID})['rows']
 summary=next(r for r in rows if r['week']==0);weekly=next(r for r in rows if r['week']==1);post=next(r for r in rows if r['season_type']=='POST')
 assert summary['grain']=='season_aggregate' and not summary['weekly_feature_eligible']
 assert weekly['team']=='LAR' and weekly['player_master_id']==PID
 assert not post['weekly_feature_eligible'] and 'game_id' not in weekly
def test_unknown_native_and_cohort_absence_not_zero():
 b=norm([row(player_gsis_id=None)])
 assert b['rows'][0]['source_player_id'] is None and b['rows'][0]['values']['pass_yards'] is None
 assert b['identity_review_requests'] and not b['rows'][0]['weekly_feature_eligible']
@pytest.mark.parametrize('change',[{'week':1.5},{'season_type':None},{'season':2027},{'week':-1}])
def test_invalid_native_scope(change):
 with pytest.raises(ValueError):norm([row(**change)])
def test_duplicate_alias_team_integral_period_and_invalid_UUID():
 with pytest.raises(ValueError,match='Duplicate'):norm([row(),row(team_abbr='LAR',week='1.0')])
 with pytest.raises(ValueError,match='UUID'):norm([row()],canonical_ids={'00-0031234':'name'})
def test_numeric_quality_signed_values_and_unknowns():
 r=norm([row(attempts=-1,completion_percentage=101,avg_time_to_throw=-1,completion_percentage_above_expectation=-12,pass_yards=-5)])['rows'][0]
 assert r['values']['attempts'] is None and r['values']['pass_yards']==-5
 assert r['values']['completion_percentage_above_expectation']==-12 and len(r['source_quality'])==3
 assert norm([row(attempts=float('nan'))])['rows'][0]['values']['attempts'] is None
def capture(tmp_path):
 s=_session();service=SourceCaptureService(s,snapshot_root=tmp_path/'source',clock=lambda:NOW)
 class Provider:
  __version__='installed_shape_fixture'
  @staticmethod
  def load_nextgen_stats(seasons,stat_type):
   assert seasons is True and stat_type=='passing'
   return pl.DataFrame([row(),row(week=0,avg_time_to_throw=None)])
 return s,capture_nextgen_source(service,stat_type='passing',season=2026,week=6,slate='offline_ngs',slate_lock_at=NOW-timedelta(hours=3),nfl_module=Provider)
def test_polars_capture_native_null_roundtrip_and_actual_postlock(tmp_path):
 s,c=capture(tmp_path)
 try:
  b=load_nextgen_snapshot(c.snapshot,stat_type='passing',cutoff=NOW)
  assert len(b['rows'])==2 and b['rows'][0]['values']['avg_time_to_throw'] is None
  assert not c.pre_lock and not b['pregame_serving_eligible']
  assert b['source']['field_availability']['attempts']
 finally:s.close()
def test_snapshot_provider_time_bound_and_tamper(tmp_path):
 s,c=capture(tmp_path)
 try:
  with pytest.raises(ValueError,match='available'):load_nextgen_snapshot(c.snapshot,stat_type='passing',cutoff=NOW-timedelta(seconds=1))
  with pytest.raises(ValueError,match='byte bound'):load_nextgen_snapshot(c.snapshot,stat_type='passing',cutoff=NOW,max_bytes=1)
  with pytest.raises(ValueError,match='mismatch'):load_nextgen_snapshot(c.snapshot,stat_type='rushing',cutoff=NOW)
  from pathlib import Path
  p=Path(c.snapshot.artifact_path);p.chmod(0o600);p.write_text('tamper')
  with pytest.raises(SnapshotIntegrityError):load_nextgen_snapshot(c.snapshot,stat_type='passing',cutoff=NOW)
 finally:s.close()
