from datetime import datetime,UTC
from types import SimpleNamespace
import polars as pl
import pytest
from backend.app.product_services.schedule_context_features import normalize_schedule_context,capture_schedule_context,load_schedule_context
from backend.app.tests.test_source_capture import _session
from backend.app.services.source_capture import SourceCaptureService,SnapshotIntegrityError
from backend.app.models import SourceSnapshot

NOW=datetime(2026,10,20,3,tzinfo=UTC)
def row(**changes):
    r=dict(game_id='2026_06_WAS_SF',season=2026,week=6,game_type='REG',home_team='SF',away_team='WAS',gameday='2026-10-19',roof='open',surface='grass',temp=72,wind=0,home_rest=10,away_rest=7)
    r.update(changes);return r

def test_literal_roof_temperature_wind_surface_and_team_rest():
    r=normalize_schedule_context([row()],cutoff=NOW)['game_rows'][0]
    home,away=r['team_rows']
    assert home['metrics']['G20-M03']['value']=='open'
    assert home['metrics']['G20-M04']['value']==72 and home['metrics']['G20-M05']['value']==0
    assert home['metrics']['G20-M08']['value']=='grass'
    assert home['metrics']['G20-M09']['value']==10 and away['metrics']['G20-M09']['value']==7

@pytest.mark.parametrize('roof',['dome','outdoors',None,'retractable'])
def test_no_invented_retractable_status(roof):
    assert normalize_schedule_context([row(roof=roof)],cutoff=NOW)['game_rows'][0]['team_rows'][0]['metrics']['G20-M03']['value'] is None

def test_unknown_not_zero_and_signed_temperature():
    metrics=normalize_schedule_context([row(temp=-12,wind=-2,home_rest=None)],cutoff=NOW)['game_rows'][0]['team_rows'][0]['metrics']
    assert metrics['G20-M04']['value']==-12
    assert metrics['G20-M05']['value'] is None and metrics['G20-M09']['value'] is None

@pytest.mark.parametrize('changes',[dict(home_team='DAL'),dict(week=7),dict(game_type=None),dict(season=True)])
def test_scope_and_native_identity(changes):
    with pytest.raises(ValueError):normalize_schedule_context([row(**changes)],cutoff=NOW)

def test_duplicate_native_game_rejects_and_record_order_stable():
    with pytest.raises(ValueError):normalize_schedule_context([row(),row()],cutoff=NOW)
    second=row(game_id='2026_05_SF_DAL',week=5,home_team='DAL',away_team='SF')
    assert normalize_schedule_context([row(),second],cutoff=NOW)['semantic_sha256']==normalize_schedule_context([second,row()],cutoff=NOW)['semantic_sha256']

def test_actual_capture_load_and_byte_clock_verification(tmp_path):
    s=_session()
    try:
        service=SourceCaptureService(s,snapshot_root=tmp_path/'source',clock=lambda:NOW)
        module=SimpleNamespace(load_schedules=lambda seasons:pl.DataFrame([row()]))
        capture=capture_schedule_context(service,season=2026,week=7,slate='FEATURES',slate_lock_at='2026-10-27T00:15:00Z',nfl_module=module)
        snap=s.get(SourceSnapshot,capture.snapshot.snapshot_id)
        loaded=load_schedule_context(snap,cutoff=NOW)
        assert loaded['pregame_serving_eligible'] is False and loaded['provenance']['field_availability']['temp']
        with pytest.raises(ValueError,match='unavailable'):load_schedule_context(snap,cutoff='2026-10-20T02:59:00Z')
        snap.content_sha256='0'*64
        with pytest.raises(SnapshotIntegrityError):load_schedule_context(snap,cutoff=NOW)
    finally:s.close()
