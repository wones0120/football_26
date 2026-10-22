from copy import deepcopy
from datetime import datetime,UTC
from pathlib import Path
import pytest
from backend.app.services.source_capture import SnapshotIntegrityError
from backend.app.product_services.gamebook_weather import parse_gamebook_temperature,bind_gamebook_temperature,capture_gamebook_weather,official_uri
TEXT='''National Football League Game Summary Date: Sunday, 9/21/2025
Denver Broncos at Los Angeles Chargers Start Time: 1:05 PM PDT at SoFi Stadium, Inglewood, CA
Game Weather: Cloudy Temp: 76° F (24.4° C) Humidity:70%, Wind:SE8mph
VISITOR: Denver Broncos 0 7 10 3 20 HOME: Los Angeles Chargers 3 7 3 10 23'''


def schedule():return dict(game_rows=[dict(game_id='2025_03_DEN_LAC',season=2025,week=3,game_type='REG',game_date='2025-09-21',home_team='LAC',away_team='DEN')])


def test_explicit_units_and_native_game_binding_not_schedule_unit_inference():
    p=parse_gamebook_temperature(TEXT);r=bind_gamebook_temperature(p,schedule(),before_period=202607)
    assert p['temperature_f']==76 and p['displayed_temperature_c']==24.4 and r['game_id']=='2025_03_DEN_LAC'
    assert all(t['value']==76 and t['unit']=='degrees_Fahrenheit' for t in r['team_rows'])
    assert p['reported_venue']=='SoFi Stadium'


def test_missing_unit_not_guessed_fahrenheit():
    p=parse_gamebook_temperature(TEXT.replace('76° F (24.4° C)','76'))
    assert p['temperature_f'] is None and p['measurement_issue']


def test_conflicting_dual_units_not_selected():
    p=parse_gamebook_temperature(TEXT.replace('24.4° C','0.0° C'))
    assert p['temperature_f'] is None and p['displayed_temperature_c']==0


def test_known_zero_fahrenheit_is_valid_not_missing():
    p=parse_gamebook_temperature(TEXT.replace('76° F (24.4° C)','0° F (-17.8° C)'))
    assert p['temperature_f']==0


def test_multiple_temperature_reports_unknown_not_newest():
    p=parse_gamebook_temperature(TEXT+' Outdoor Temp: 70° F (21.1° C)')
    assert p['temperature_f'] is None


@pytest.mark.parametrize('kind',['date','teams','phase','duplicate','future'])
def test_native_schedule_scope_rejects(kind):
    s=schedule()
    if kind=='date':s['game_rows'][0]['game_date']='2025-09-22'
    if kind=='teams':s['game_rows'][0]['home_team']='DEN'
    if kind=='phase':s['game_rows'][0]['game_type']='WC'
    if kind=='duplicate':s['game_rows']*=2
    with pytest.raises(ValueError):bind_gamebook_temperature(parse_gamebook_temperature(TEXT),s,before_period=202503 if kind=='future' else 202607)


def test_bad_header_and_unknown_team_not_bound_by_names_guess():
    with pytest.raises(ValueError):parse_gamebook_temperature(TEXT.replace('National Football League Game Summary','Unofficial weather'))
    with pytest.raises(ValueError):parse_gamebook_temperature(TEXT.replace('VISITOR: Denver Broncos','VISITOR: Mystery Club'))


def test_capture_original_bytes_records_validation_error_instead_of_losing_raw(monkeypatch):
    from backend.app.product_services import gamebook_weather as module
    seen={}
    class Service:
        def capture_file(self,path,**kw):seen.update(kw);seen['raw']=Path(path).read_bytes();return 'captured'
    uri='https://static.clubs.nfl.com/image/upload/club/book';data=b'%PDF-original'
    monkeypatch.setattr(module,'first_page_text',lambda payload:(TEXT,19))
    assert capture_gamebook_weather(Service(),uri=uri,season=2025,week=3,slate_lock_at=datetime(2025,9,21,tzinfo=UTC),fetcher=lambda u:data)=='captured'
    assert seen['raw']==data and seen['media_type']=='application/pdf' and seen['metadata']['initial_validation_error'] is None
    assert seen['metadata']['original_publication_at'] is None
    capture_gamebook_weather(Service(),uri=uri,season=2024,week=3,slate_lock_at=datetime(2024,9,21,tzinfo=UTC),fetcher=lambda u:data)
    assert seen['metadata']['initial_validation_error'] and seen['row_count'] is None


@pytest.mark.parametrize('uri',['http://static.clubs.nfl.com/book','https://example.com/nfl/book','https://static.clubs.nfl.com.evil.test/book'])
def test_only_official_https_primary_source(uri):assert not official_uri(uri)


def indexed_source(tmp_path,monkeypatch):
    from backend.app.product_services import gamebook_weather as module
    from backend.app.services.source_capture import SourceCaptureService
    class Session:
        def __init__(self):self.data={}
        def get(self,model,key):return self.data.get(key)
        def add(self,value):self.data[value.snapshot_id]=value
        def commit(self):pass
        def refresh(self,value):pass
    now=datetime(2025,9,22,tzinfo=UTC)
    service=SourceCaptureService(Session(),snapshot_root=tmp_path/'sources',clock=lambda:now)
    monkeypatch.setattr(module,'first_page_text',lambda payload:(TEXT,19))
    result=capture_gamebook_weather(service,uri='https://static.clubs.nfl.com/image/upload/club/book',season=2025,week=3,slate_lock_at=datetime(2025,9,21,20,5,tzinfo=UTC),fetcher=lambda uri:b'%PDF-test-original')
    s=schedule();s.update(version='native_schedule_context_features_v1',pregame_serving_eligible=False,evidence_use='postlock_descriptive_not_pregame_or_serving',provenance=dict(captured_at=now.isoformat(),snapshot_id='schedule',sha256='schedulehash'))
    return result.snapshot,s


def test_indexed_reader_verifies_original_bytes_clocks_native_scope_and_use(tmp_path,monkeypatch):
    from backend.app.product_services.gamebook_weather import load_gamebook_temperature,require_feature_use
    snap,s=indexed_source(tmp_path,monkeypatch)
    value=load_gamebook_temperature(snap,s,before_period=202607,actual_read_at='2025-09-23T00:00:00+00:00')
    assert value['reported_weather']['temperature_f']==76
    assert value['provenance']['original_weather_observation_at'] is None
    with pytest.raises(ValueError):require_feature_use(value,purpose='forecast')
    with pytest.raises(ValueError):load_gamebook_temperature(snap,s,before_period=202607,actual_read_at='2025-09-21T00:00:00+00:00')
    tampered=tmp_path/'tampered.pdf';tampered.write_bytes(b'changed');snap.artifact_path=str(tampered)
    with pytest.raises(SnapshotIntegrityError):load_gamebook_temperature(snap,s,before_period=202607,actual_read_at='2025-09-23T00:00:00+00:00')


@pytest.mark.parametrize('kind',['week','producer_contract','scheduleclock','unverifiedschedule'])
def test_indexed_scope_rejects_unknown_or_mismatched_context(tmp_path,monkeypatch,kind):
    from backend.app.product_services.gamebook_weather import load_gamebook_temperature
    snap,s=indexed_source(tmp_path,monkeypatch)
    if kind=='week':snap.week=4
    if kind=='producer_contract':snap.metadata_json={**snap.metadata_json,'contract':'other'}
    if kind=='scheduleclock':s['provenance']['captured_at']='2025-09-24T00:00:00+00:00'
    if kind=='unverifiedschedule':s['pregame_serving_eligible']=True
    with pytest.raises(SnapshotIntegrityError if kind=='week' else ValueError):load_gamebook_temperature(snap,s,before_period=202607,actual_read_at='2025-09-23T00:00:00+00:00')
