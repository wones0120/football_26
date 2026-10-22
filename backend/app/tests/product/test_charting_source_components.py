from copy import deepcopy
from datetime import datetime,UTC,timedelta
import pandas as pd
import pytest
import polars as pl
from backend.app.product_services.charting_source_components import normalize_charting_rows,capture_charting_source,load_charting_snapshot,PROVIDER_URL
from backend.app.tests.test_source_capture import _session
from backend.app.services.source_capture import SourceCaptureService,SnapshotIntegrityError
NOW=datetime(2026,10,20,2,0,tzinfo=UTC)


def row(**changes):
 return dict(nflverse_game_id='2023_01_BUF_NYJ',nflverse_play_id='1',season=2023,week=1,is_throw_away=False,is_play_action=True,is_screen_pass=False,is_catchable_ball=True,is_contested_ball=False,is_drop=False,n_blitzers=0,n_pass_rushers=4,read_thrown='0',date_pulled='2024-02-20T10:00:00Z',**changes)


def norm(rows,season=2023):return normalize_charting_rows(rows,source_season=season,cutoff=NOW)


def test_native_ID_strings_integral_play_and_false_zero_not_null():
 result=norm([row()])[0]
 assert result['play_id']=='1' and result['flags']['is_throw_away'] is False
 assert result['counts']['n_blitzers']==0 and result['flags']['is_motion'] is None
 assert result['primary_read'] is True
 assert result['date_pulled']['status']=='provider_API_retrieval_not_original_publication'


@pytest.mark.parametrize('change',[{'nflverse_play_id':'1.5'},{'week':2},{'season':2024},{'nflverse_game_id':'rawname'},{'is_drop':'unknown'}])
def test_bad_native_scope_or_measurement_not_silently_coerced(change):
 r=row();r.update(change)
 with pytest.raises(ValueError):norm([r])


def test_duplicate_native_gameplay_cannot_evade_as_1_vs_1point0():
 r=row();other=deepcopy(r);other['nflverse_play_id']='1.0'
 with pytest.raises(ValueError,match='Duplicate'):norm([r,other])


def test_first_read_dictionary_2022_missing_or_zero_never_becomes_known_primary():
 r=row();r.update(season=2022,nflverse_game_id='2022_01_BUF_NYJ')
 result=norm([r],season=2022)[0];assert result['primary_read'] is None
 r['read_thrown']=None;assert norm([r],season=2022)[0]['primary_read'] is None
 for code in ('1','2','CHK','DES','SD'):
  r['read_thrown']=code;assert norm([r],season=2022)[0]['primary_read'] is False


def test_date_pulled_is_not_publication_and_unknown_timezone_retained():
 r=row();r['date_pulled']='2024-02-20 10:00:00'
 assert norm([r])[0]['date_pulled']['status']=='provider_timezone_unknown'
 r['date_pulled']='2026-10-21T00:00:00Z'
 with pytest.raises(ValueError,match='retrieval clock'):norm([r])


def test_POST_native_rows_not_fake_REG_and_drop_conflict_kept_explicit():
 r=row();r.update(week=22,nflverse_game_id='2023_22_KC_SF',is_drop=True,is_catchable_ball=False)
 result=norm([r])[0]
 assert result['week']==22 and 'season_type' not in result and result['drop_catchability_conflict']


def capture(tmp_path,frame=None):
 session=_session();service=SourceCaptureService(session,snapshot_root=tmp_path/'source',clock=lambda:NOW)
 class Provider:
  __version__='fixture_installed_shape'
  @staticmethod
  def load_ftn_charting(seasons):assert seasons==[2023];return frame if frame is not None else pl.DataFrame([row()])
 result=capture_charting_source(service,season=2023,week=6,slate='offline_ftn',slate_lock_at=NOW-timedelta(hours=2),nfl_module=Provider)
 return session,result


def test_real_Polars_nullable_provider_immutable_capture_roundtrip_postlock(tmp_path):
 r=row();r.update(is_motion=None,n_blitzers=None)
 session,result=capture(tmp_path,pl.DataFrame([r]))
 try:
  snapshot=result.snapshot;loaded=load_charting_snapshot(snapshot,cutoff=NOW)
  assert snapshot.source_uri==PROVIDER_URL.format(season=2023)
  assert loaded['rows'][0]['flags']['is_throw_away'] is False
  assert loaded['rows'][0]['counts']['n_blitzers'] is None
  assert loaded['source']['field_availability']['is_motion']
  assert result.pre_lock is False
  assert loaded['source']['revision_status']=='revised_retrospective_provider_capture'
 finally:session.close()


def test_Pandas_provider_also_supported_no_pyarrow_conversion(tmp_path):
 session,result=capture(tmp_path,pd.DataFrame([row()]))
 try:assert len(load_charting_snapshot(result.snapshot,cutoff=NOW)['rows'])==1
 finally:session.close()


def test_artifact_tamper_wrong_provider_future_cutoff_and_bounds_reject(tmp_path):
 session,result=capture(tmp_path)
 try:
  snapshot=result.snapshot
  with pytest.raises(ValueError,match='available'):load_charting_snapshot(snapshot,cutoff=NOW-timedelta(seconds=1))
  with pytest.raises(ValueError,match='byte bound'):load_charting_snapshot(snapshot,cutoff=NOW,max_bytes=1)
  snapshot.source_system='other'
  with pytest.raises(ValueError,match='provider'):load_charting_snapshot(snapshot,cutoff=NOW)
  snapshot.source_system='nflreadpy'
  from pathlib import Path
  Path(snapshot.artifact_path).chmod(0o600)
  Path(snapshot.artifact_path).write_text('tampered')
  with pytest.raises(SnapshotIntegrityError):load_charting_snapshot(snapshot,cutoff=NOW)
 finally:session.close()


def test_missing_required_columns_empty_provider_and_row_bound_fail_explicitly(tmp_path):
 for frame in [pl.DataFrame({'wrong':[1]}),pl.DataFrame(schema={'nflverse_game_id':pl.String})]:
  with pytest.raises(ValueError):capture(tmp_path,frame)
 with pytest.raises(ValueError,match='row bound'):normalize_charting_rows([row(),dict(row(),nflverse_play_id='2')],source_season=2023,cutoff=NOW,max_rows=1)


def test_invalid_provider_defender_sentinels_remain_unknown_with_original_not_clipped():
 r=row();r.update(n_blitzers=-1,n_pass_rushers=12)
 result=norm([r])[0]
 assert result['counts']=={'n_blitzers':None,'n_pass_rushers':None}
 assert result['raw_counts']=={'n_blitzers':-1,'n_pass_rushers':12}
 assert set(result['inconsistent_count_fields'])=={'n_blitzers','n_pass_rushers'}
