from datetime import UTC,datetime
from io import BytesIO
import polars as pl
import pytest
from backend.app.product_services.pfr_source_components import asset_scope,validate_pfr_frame,capture_pfr_asset,select_prior_weekly_pfr,BASE
from backend.app.tests.test_source_capture import _session
from backend.app.services.source_capture import SourceCaptureService,verify_snapshot_artifact
from backend.app.models import SourceSnapshot

NOW=datetime(2026,10,20,3,tzinfo=UTC)


def weekly():
    return pl.DataFrame(dict(season=[2026,2026],week=[5,6],game_id=['2026_05_WAS_DAL','2026_06_WAS_SF'],
        pfr_game_id=['202610110dal','202610190sfo'],game_type=['REG','REG'],team=['WAS','WAS'],pfr_player_id=['DaniJa00','DaniJa00'],pfr_player_name=['Display','Changed'],times_pressured=[0,None]))


def test_asset_scope_exact_week_vs_season_and_url_name():
    assert asset_scope('advstats_week_def_2026.parquet')==dict(stat_type='def',summary_level='week',season=2026)
    assert asset_scope('advstats_season_rush.parquet')['season'] is None
    with pytest.raises(ValueError):asset_scope('../../secret')


def test_native_weekly_grain_known_zero_unknown_and_no_display_name_join():
    result=validate_pfr_frame(weekly(),stat_type='pass',summary_level='week',season=2026)
    assert result['native_grain_valid'] and result['season_rows']=={2026:2}
    assert result['native_player_id_field']=='pfr_player_id'
    assert weekly()['times_pressured'].to_list()==[0,None]
    assert result['forecast'] is None and not result['current_serving_eligible']


def test_missing_native_id_and_conflicting_fields_are_explicit_not_name_resolved():
    frame=weekly().with_columns(pl.lit(None,dtype=pl.String).alias('pfr_player_id'))
    result=validate_pfr_frame(frame,stat_type='pass',summary_level='week')
    assert len(result['identity_requests'])==2 and not result['native_grain_valid']
    frame=weekly().with_columns(pl.lit('Other00').alias('pfr_id'))
    assert 'conflicting_native' in validate_pfr_frame(frame,stat_type='pass',summary_level='week')['identity_requests'][0]['reason']


def test_duplicate_native_player_game_remains_review_not_silent_dedupe():
    frame=pl.concat([weekly(),weekly().head(1)])
    result=validate_pfr_frame(frame,stat_type='pass',summary_level='week')
    assert len(result['duplicate_native_rows'])==1 and result['row_count']==3


def test_season_aggregate_never_joined_as_weekly_or_team_normalized():
    frame=pl.DataFrame(dict(season=[2025,2026],pfr_id=['Some00','Some00'],team=['2TM','WAS'],yards_after_contact=[12,0]))
    result=validate_pfr_frame(frame,stat_type='rush',summary_level='season')
    assert not result['weekly_feature_use_allowed'] and result['time_grain']=='player_season_aggregate'
    assert frame['team'].to_list()==['2TM','WAS']
    with pytest.raises(ValueError,match='grain fields'):select_prior_weekly_pfr(frame,stat_type='rush',before_period=202606)
    teams=pl.DataFrame(dict(season=[2025,2025],pfr_id=['Some00','Some00'],tm=['2TM','WAS']))
    result=validate_pfr_frame(teams,stat_type='rush',summary_level='season')
    assert result['native_grain_valid'] and result['native_team_field']=='tm'


def test_period_and_native_game_scope_rejected():
    frame=weekly().with_columns(pl.lit(2025).alias('season'))
    with pytest.raises(ValueError,match='asset scope'):validate_pfr_frame(frame,stat_type='pass',summary_level='week',season=2026)
    with pytest.raises(ValueError,match='game identity'):validate_pfr_frame(frame,stat_type='pass',summary_level='week')
    annual=pl.DataFrame(dict(season=[2027],pfr_id=['Some00'],tm=['WAS']))
    with pytest.raises(ValueError,match='asset scope'):validate_pfr_frame(annual,stat_type='pass',summary_level='season',max_season=2026)


def test_weekly_prior_scope_and_postseason_separate():
    postseason=weekly().head(1).with_columns(pl.lit(19,dtype=pl.Int64).alias('week'),pl.lit('WC').alias('game_type'),pl.lit('2026_19_WAS_DAL').alias('game_id'),pl.lit('202701100dal').alias('pfr_game_id'))
    result=select_prior_weekly_pfr(pl.concat([weekly(),postseason]),stat_type='pass',before_period=202606)
    assert result['week'].to_list()==[5]


def test_actual_parquet_bytes_capture_and_validation_separate_from_ingest(tmp_path):
    buffer=BytesIO();weekly().write_parquet(buffer);raw=buffer.getvalue()
    name='advstats_week_pass_2026.parquet';asset=dict(name=name,url=BASE+name,bytes=len(raw),updated_at='2026-10-19T18:00:00Z')
    session=_session()
    try:
        service=SourceCaptureService(session,snapshot_root=tmp_path/'snapshots',clock=lambda:NOW)
        report=capture_pfr_asset(service,asset,capture_season=2026,fetch=lambda a:(raw,{'Date':NOW.isoformat()}),clock=lambda:NOW)
        snapshot=session.get(SourceSnapshot,report['source_snapshot_id']);verify_snapshot_artifact(snapshot)
        assert report['source_sha256']==report['raw_remote_sha256']
        assert report['status']=='captured_validated'
        assert snapshot.metadata_json['source_publication_at'] is None
        assert snapshot.metadata_json['raw_remote_format']=='parquet_original_bytes'
        assert not report['model_consumed']
    finally:session.close()


def test_malformed_provider_bytes_are_still_immutable_evidence(tmp_path):
    name='advstats_season_pass.parquet';asset=dict(name=name,url=BASE+name)
    session=_session()
    try:
        service=SourceCaptureService(session,snapshot_root=tmp_path/'snapshots',clock=lambda:NOW)
        report=capture_pfr_asset(service,asset,capture_season=2026,fetch=lambda a:(b'bad parquet',{}),clock=lambda:NOW)
        assert report['status']=='captured_requires_review' and report['validation_error']
        verify_snapshot_artifact(session.get(SourceSnapshot,report['source_snapshot_id']))
    finally:session.close()


def test_native_missing_id_uses_existing_quarantine_with_content_key(tmp_path):
    from backend.app.product_services.pfr_source_components import persist_pfr_native_requests
    frame=pl.DataFrame(dict(season=[2025],pfr_id=[None],tm=['WAS'],player=['Unresolved display'],pos=['LB']),schema_overrides={'pfr_id':pl.String})
    data=BytesIO();frame.write_parquet(data);raw=data.getvalue();name='advstats_season_def.parquet'
    session=_session();calls=[]
    class Connection:
        def execute(self,sql,params):calls.append((str(sql),params))
    try:
        service=SourceCaptureService(session,snapshot_root=tmp_path/'snapshots',clock=lambda:NOW)
        report=capture_pfr_asset(service,dict(name=name,url=BASE+name),capture_season=2026,fetch=lambda a:(raw,{}),clock=lambda:NOW)
        snapshot=session.get(SourceSnapshot,report['source_snapshot_id'])
        request=persist_pfr_native_requests(Connection(),snapshot)
        assert request['requests']==1
        assert calls[0][1]['key']==f'pfr-row:{snapshot.content_sha256}:0'
        assert calls[0][1]['name']=='Unresolved display'
        assert 'DO NOTHING' in calls[0][0] and 'UPDATE' not in calls[0][0]
        assert request['records'][0]['source_snapshot_id']==str(snapshot.snapshot_id)
    finally:session.close()


def test_download_url_size_and_remote_byte_bounds(monkeypatch):
    from backend.app.product_services import pfr_source_components as module
    name='advstats_week_pass_2026.parquet'
    with pytest.raises(ValueError,match='provider URL'):
        module.download_pfr_asset(dict(name=name,url='http://127.0.0.1/private'))
    class Response:
        headers={}
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return b'12345'[:n]
    monkeypatch.setattr(module,'urlopen',lambda *a,**k:Response())
    with pytest.raises(ValueError,match='byte bound'):
        module.download_pfr_asset(dict(name=name,url=BASE+name),max_bytes=3)
    with pytest.raises(ValueError,match='release size changed'):
        module.download_pfr_asset(dict(name=name,url=BASE+name,bytes=4))
