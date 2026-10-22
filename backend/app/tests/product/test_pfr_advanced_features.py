from datetime import UTC,datetime
from io import BytesIO
from copy import deepcopy
import polars as pl
import pytest
from backend.app.product_services.pfr_advanced_features import _derive,build_pfr_advanced_features
from backend.app.product_services.pfr_source_components import capture_pfr_asset,BASE
from backend.app.tests.test_source_capture import _session
from backend.app.services.source_capture import SourceCaptureService,SnapshotIntegrityError
from backend.app.models import SourceSnapshot

NOW=datetime(2026,10,20,3,tzinfo=UTC);PID='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'


def aliases():return [dict(source_system='pfr',source_key='Native00',player_master_id=PID,created_at='2026-10-19T19:00:00Z')]


def record(**changes):
    result=dict(game_id='2026_05_WAS_DAL',season=2026,week=5,game_type='REG',team='WAS',opponent='DAL',pfr_player_id='Native00',
        carries=2,rushing_yards_before_contact=-2,rushing_yards_after_contact=8,rushing_broken_tackles=1,
        _stat_type='rush',_source_snapshot_id='snapshot',_native_row=0)
    result.update(changes);return result


def derive(rows,a=None):return _derive(rows,aliases() if a is None else a,before_period=202606,cutoff=NOW)


def test_matched_source_yards_signed_unknown_zero_and_broken_not_missed():
    row=derive([record()])['actor_game_rows'][0]
    assert row['metrics']['G07-M07']['value']==-2
    assert row['metrics']['G07-M07']['per_carry']==-1
    assert row['metrics']['G07-M08']['per_carry']==4
    assert 'not_all_missed' in row['metrics']['G07-M09']['variant']
    assert derive([record(rushing_yards_after_contact=None)])['actor_game_rows'][0]['metrics']['G07-M08']['value'] is None
    assert derive([record(rushing_yards_after_contact=0)])['actor_game_rows'][0]['metrics']['G07-M08']['value']==0


def test_unmapped_source_actors_remain_in_defense_measurements_no_donation():
    rows=[record(),record(pfr_player_id='Unknown00',_native_row=1)]
    result=derive(rows);defense=result['defense_game_rows'][0]['metrics']['G15-M06']
    assert defense['observed_source_sum']==16 and defense['unmapped_actors']==1
    assert len(result['identity_review_requests'])==1
    assert derive(rows,[])['defense_game_rows']==[dict(result['defense_game_rows'][0],metrics={mid:{**m,'unmapped_actors':2} for mid,m in result['defense_game_rows'][0]['metrics'].items()})]


def test_native_alias_only_future_or_ambiguous_never_name_fallback():
    assert derive([record()],[])['actor_game_rows'][0]['player_master_id'] is None
    a=aliases();a[0]['created_at']='2026-10-21T00:00:00Z'
    assert derive([record()],a)['alias_quality']
    a=aliases()+[{**aliases()[0],'player_master_id':'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'}]
    assert derive([record()],a)['identity_review_requests'][0]['reason']=='conflicting_native_alias'


def test_canonical_native_duplicate_game_collision_rejected():
    a=aliases()+[{**aliases()[0],'source_key':'Other00'}]
    with pytest.raises(ValueError,match='collision'):derive([record(),record(pfr_player_id='Other00')],a)


def test_pressure_fraction_not_divided_by100_or_inverted_to_denominator():
    value=derive([record(_stat_type='pass',times_pressured=5,times_pressured_pct=.208)])['actor_game_rows'][0]['metrics']['G13-M03']
    assert value['value']==.208 and value['pressure_count']==5
    assert 'not reverse' in value['denominator']
    assert derive([record(_stat_type='pass',times_pressured_pct=20.8)])['actor_game_rows'][0]['metrics']['G13-M03']['value'] is None


def test_zero_exposure_and_nonfinite_source_not_fake_numeric():
    result=derive([record(carries=0,rushing_yards_after_contact=8)])
    assert result['actor_game_rows'][0]['metrics']['G07-M08']['value'] is None
    assert derive([record(rushing_yards_before_contact=float('nan'))])['actor_game_rows'][0]['metrics']['G07-M07']['value'] is None


def test_actual_verified_snapshot_weekly_source_gate(tmp_path):
    frame=pl.DataFrame([{k:v for k,v in record().items() if not k.startswith('_')}]).with_columns(pl.lit('202610110dal').alias('pfr_game_id'))
    buffer=BytesIO();frame.write_parquet(buffer);raw=buffer.getvalue();name='advstats_week_rush_2026.parquet'
    session=_session()
    try:
        service=SourceCaptureService(session,snapshot_root=tmp_path/'snapshots',clock=lambda:NOW)
        report=capture_pfr_asset(service,dict(name=name,url=BASE+name),capture_season=2026,fetch=lambda a:(raw,{}),clock=lambda:NOW)
        snapshot=session.get(SourceSnapshot,report['source_snapshot_id'])
        result=build_pfr_advanced_features([snapshot],aliases(),before_period=202606,cutoff=NOW)
        assert len(result['actor_game_rows'])==1 and not result['model_consumed']
        assert result['provenance']['alias_receipts'][0]['source_key']=='Native00'
        with pytest.raises(ValueError,match='unavailable'):build_pfr_advanced_features([snapshot],aliases(),before_period=202606,cutoff='2026-10-20T02:59:59Z')
        with pytest.raises(ValueError,match='single revision'):build_pfr_advanced_features([snapshot,snapshot],aliases(),before_period=202606,cutoff=NOW)
        snapshot.content_sha256='0'*64
        with pytest.raises(SnapshotIntegrityError):build_pfr_advanced_features([snapshot],aliases(),before_period=202606,cutoff=NOW)
    finally:session.close()


def test_unresolved_native_alias_queue_is_idempotent_person_key_not_name():
    from backend.app.product_services.pfr_advanced_features import persist_feature_identity_requests
    features=derive([record(pfr_player_name='Display'),record(game_id='2026_04_WAS_SF',week=4,opponent='SF',pfr_player_name='Changed')],[])
    calls=[]
    class Connection:
        def execute(self,sql,params):calls.append((str(sql),params))
    result=persist_feature_identity_requests(Connection(),features)
    assert result['requests']==1 and calls[0][1]['native']=='Native00'
    assert calls[0][1]['key']=='pfr-player:Native00'
    assert 'DO NOTHING' in calls[0][0] and 'UPDATE' not in calls[0][0]
