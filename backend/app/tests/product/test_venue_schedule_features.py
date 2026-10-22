from copy import deepcopy
import csv,json
import pytest
from backend.app.tests.product.test_espn_markets import payload,GAME,NOW
from backend.app.tests.test_source_capture import _session
from backend.app.services.source_capture import SourceCaptureService,SnapshotIntegrityError
from backend.app.product_services.espn_markets import scoreboard_url
from backend.app.product_services.venue_schedule_features import extract_venue_schedule_features

G={**GAME,'season':2026,'week':5,'source_game_id':'espn-1'}


@pytest.fixture
def source(tmp_path):
    session=_session();service=SourceCaptureService(session,snapshot_root=tmp_path/'snapshots',clock=lambda:NOW)
    def make(change=None):
        p=payload();c=p['events'][0]['competitions'][0];c['venue']={'id':'native-venue','fullName':'Venue','indoor':False};c.pop('odds')
        if change:change(p)
        path=tmp_path/'native.csv'
        with path.open('w') as f:
            w=csv.DictWriter(f,fieldnames=['response_json','capture_observed_at']);w.writeheader();w.writerow(dict(response_json=json.dumps(p),capture_observed_at=NOW.isoformat()))
        return service.capture_file(path,source_system='espn',dataset='schedule_market_snapshot',season=2026,week=5,slate='test',source_uri=scoreboard_url(2026,5),source_license='fixture').snapshot
    yield make
    session.close()


def test_native_venue_and_homeaway_independent_of_odds_weather(source):
    result=extract_venue_schedule_features(source(),[G],cutoff=NOW)
    games={g['team']:g for g in result['games']}
    assert games['GB']['metrics']['G20-M01']['value']=='home'
    assert games['CHI']['metrics']['G20-M01']['value']=='away'
    assert games['GB']['metrics']['G20-M02']['value']=='outdoor'
    assert 'G20-M03' in result['source_gaps'] and result['forecast'] is None


@pytest.mark.parametrize('value',[None,'false',0])
def test_missing_or_untyped_indoor_is_unknown_not_false(source,value):
    s=source(lambda p:p['events'][0]['competitions'][0]['venue'].update(indoor=value))
    assert extract_venue_schedule_features(s,[G],cutoff=NOW)['games'][0]['metrics']['G20-M02']['value'] is None


@pytest.mark.parametrize('field,value',[('source_game_id','wrong'),('away_team','DAL'),('week',6),('kickoff_at','2026-10-11T20:00:00Z')])
def test_native_scope_mismatch_never_name_only_fallback(source,field,value):
    game={**G,field:value}
    with pytest.raises(ValueError):extract_venue_schedule_features(source(),[game],cutoff=NOW)


def test_duplicate_native_events_and_live_status_rejected(source):
    s=source(lambda p:p['events'].append(deepcopy(p['events'][0])))
    with pytest.raises(ValueError,match='ambiguous'):extract_venue_schedule_features(s,[G],cutoff=NOW)
    s=source(lambda p:p['events'][0]['competitions'][0]['status']['type'].update(state='in'))
    with pytest.raises(ValueError,match='pregame'):extract_venue_schedule_features(s,[G],cutoff=NOW)


def test_actual_byte_integrity_and_cutoff_guard(source):
    s=source();original=s.content_sha256;s.content_sha256='0'*64
    with pytest.raises(SnapshotIntegrityError):extract_venue_schedule_features(s,[G],cutoff=NOW)
    s.content_sha256=original
    with pytest.raises(ValueError,match='unavailable'):extract_venue_schedule_features(s,[G],cutoff='2026-10-10T19:59:00Z')
