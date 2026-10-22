from copy import deepcopy
from datetime import datetime,UTC,timedelta
from pathlib import Path
from types import SimpleNamespace
import hashlib,io
import polars as pl
import pytest
from backend.app.product_services.participation_source_components import normalize_participation_rows,capture_participation_source,load_participation_snapshot,VERSION,URL
A='00-0000001';B='00-0000002';C='00-0000003'

def row(**kw):
    return dict(nflverse_game_id='2023_01_BUF_MIA',play_id=1,possession_team='BUF',offense_players=A+';'+B,defense_players=[C],offense_positions='QB;WR',defense_positions=['CB'],n_offense=2,n_defense=1,was_pressure=True,time_to_throw=2.1,offense_personnel='1 RB, 1 TE, 3 WR')|kw

def build(rows):return normalize_participation_rows(rows,season=2023)

def test_native_positions_are_typed_and_aligned_not_names_or_guesses():
    r=build([row()]);p=r['rows'][0]['participant_scopes']['offense']
    assert p['position_by_native_id']=={A:'QB',B:'WR'}
    assert r['rows'][0]['native_phase']is None
    assert r['pregame_serving_eligible']is False

def test_unknown_lists_and_mismatched_count_or_positions_remain_unknown():
    for change in (dict(offense_players=None),dict(offense_players=A+';Name Only'),dict(n_offense=11),dict(offense_positions='QB'),dict(offense_players=A+';'+A)):
        p=build([row(**change)])['rows'][0]['participant_scopes']['offense']
        assert p['position_by_native_id']is None
        assert p['original_player_list']==row(**change)['offense_players']

def test_cross_side_native_identity_conflict_cannot_be_role_proof():
    p=build([row(defense_players=[A])])['rows'][0]['participant_scopes']
    assert all(v['position_by_native_id']is None for v in p.values())

@pytest.mark.parametrize('v',[None,2,float('nan'),'not known'])
def test_bad_or_absent_pressure_is_not_false(v):
    assert build([row(was_pressure=v)])['rows'][0]['measurements']['was_pressure']is None

@pytest.mark.parametrize('v',[True,1,1.0,'1','true','TRUE'])
def test_real_pressure_flag_true(v):assert build([row(was_pressure=v)])['rows'][0]['measurements']['was_pressure']is True

def test_signed_air_yards_and_zero_pressure_not_clipped():
    r=build([row(ngs_air_yards=-3,was_pressure=0,time_to_throw=-1,number_of_pass_rushers=12)])['rows'][0]
    assert r['measurements']['ngs_air_yards']==-3 and r['measurements']['was_pressure']is False
    assert r['measurements']['time_to_throw']is None and r['measurements']['number_of_pass_rushers']is None

@pytest.mark.parametrize('change',[dict(nflverse_game_id='2022_01_BUF_MIA'),dict(possession_team='GB'),dict(play_id=1.5),dict(season=2024),dict(week=2)])
def test_native_scope_contradictions_reject(change):
    with pytest.raises(ValueError):build([row(**change)])

def test_alias_teams_native_keys_unique_integral_and_phase_not_inferred():
    r=build([row(nflverse_game_id='2023_20_LA_SF',possession_team='LA')])
    assert r['rows'][0]['possession_team']=='LAR'and r['rows'][0]['native_phase']is None
    with pytest.raises(ValueError):build([row(),row(play_id=1.0)])

def test_row_order_invariance_keeps_original_ordinals_only_in_provenance():
    records=[row(),row(play_id=2)]
    assert build(records)['semantic_sha256']==build(records[::-1])['semantic_sha256']


def parquet_bytes():
    f=pl.DataFrame([row()]);out=io.BytesIO();f.write_parquet(out);return out.getvalue()

def test_capture_original_bytes_license_scope_and_unsupported_current_year(monkeypatch):
    import nflreadpy.utils_date
    monkeypatch.setattr(nflreadpy.utils_date,'get_current_season',lambda **kw:2026)
    data=parquet_bytes();seen={}
    class Service:
        def capture_file(self,path,**kw):
            seen.update(kw);seen['bytes']=Path(path).read_bytes();return 'captured'
    assert capture_participation_source(Service(),season=2023,slate_lock_at=datetime.now(UTC),fetcher=lambda url:data)=='captured'
    assert seen['bytes']==data and seen['source_uri']==URL.format(season=2023)
    assert seen['metadata']['provider_generation']=='FTN'
    assert seen['metadata']['original_remote_parquet_bytes']is True
    with pytest.raises(ValueError,match='historical'):capture_participation_source(Service(),season=2026,slate_lock_at=datetime.now(UTC),fetcher=lambda url:data)


def test_indexed_parquet_read_authentication_clocks_and_field_coverage(tmp_path,monkeypatch):
    from backend.app.services import source_capture
    now=datetime.now(UTC);data=parquet_bytes();p=tmp_path/'original.parquet';p.write_bytes(data)
    s=SimpleNamespace(season=2023,source_system='nflverse_participation',dataset='play_participation',media_type='application/vnd.apache.parquet',source_uri=URL.format(season=2023),
        metadata_json=dict(contract_id=VERSION,installed_loader='nflreadpy.load_participation',original_remote_parquet_bytes=True,provider_generation='FTN',original_sha256=hashlib.sha256(data).hexdigest()),observed_at=now-timedelta(seconds=2),captured_at=now-timedelta(seconds=1),byte_count=len(data),row_count=1,artifact_path=p,
        content_sha256=hashlib.sha256(data).hexdigest(),snapshot_id='indexed')
    def verify(value):assert hashlib.sha256(Path(value.artifact_path).read_bytes()).hexdigest()==value.content_sha256
    monkeypatch.setattr(source_capture,'verify_snapshot_artifact',verify)
    r=load_participation_snapshot(s,actual_read_at=now)
    assert r['known_measurement_rows']['was_pressure']==1 and r['unknown_measurement_rows']['route']==1
    s.captured_at=now+timedelta(days=1)
    with pytest.raises(ValueError,match='boundary'):load_participation_snapshot(s,actual_read_at=now)
    s.captured_at=now;s.row_count=2
    with pytest.raises(ValueError,match='row count'):load_participation_snapshot(s,actual_read_at=now)


def test_native_pbp_join_retains_unmatched_and_conflicting_scope_not_name_join():
    from backend.app.product_services.participation_source_components import audit_native_participation_join
    b=build([row(),row(play_id=2),row(play_id=3),row(play_id=4)])
    p=[dict(game_id='2023_01_BUF_MIA',play_id=i,season=2023,week=1,season_type='REG',posteam='BUF')for i in (1,2,3)]
    p[1]['posteam']='MIA';p[2]['season_type']=None
    r=audit_native_participation_join(b,p,season=2023)
    assert r['counts']==dict(qualified_native_game_play_matches=1,native_possession_team_conflict=1,PBP_native_phase_unverified=1,missing_native_PBP_game_play=1)
    assert r['qualified_phase_counts']=={'REG':1}
    with pytest.raises(ValueError,match='Duplicate'):audit_native_participation_join(b,p+p[:1],season=2023)


def test_downloaded_schema_failure_still_preserves_raw_immutable_source():
    f=pl.DataFrame({'unexpected':[1]});out=io.BytesIO();f.write_parquet(out);data=out.getvalue();seen={}
    class Service:
        def capture_file(self,path,**kw):seen.update(kw);seen['bytes']=Path(path).read_bytes();return 'captured'
    assert capture_participation_source(Service(),season=2023,slate_lock_at=datetime.now(UTC),fetcher=lambda url:data)=='captured'
    assert seen['bytes']==data and seen['metadata']['initial_validation_error']is not None
    assert seen['week']is None
