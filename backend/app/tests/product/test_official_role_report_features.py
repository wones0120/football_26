from datetime import UTC,datetime,timedelta
from pathlib import Path
import json
import pytest
from backend.app.services.source_capture import SourceCaptureService,SnapshotIntegrityError
from backend.app.tests.test_source_capture import _session
from backend.app.tests.product.test_factual_designation import html,URI,KICK
from backend.app.product_services.official_role_report_features import parse_dated_practice_rows,extract_official_role_report
from backend.app.product_services.player_role_features import build_player_role_features

NOW=datetime(2026,10,19,19,tzinfo=UTC);PID='11111111-1111-4111-8111-111111111111'

def parse(body):return parse_dated_practice_rows(body,source_uri=URI,season=2026,week=6,team='WAS',opponent='SF',kickoff_at=KICK,observed_at=NOW)

@pytest.fixture
def snapshot(tmp_path):
    session=_session();service=SourceCaptureService(session,snapshot_root=tmp_path/'snapshots',clock=lambda:NOW)
    def make(body=None):
        body=body or html();parsed,_=parse(body);envelope=dict(source_uri=URI,observed_at=NOW.isoformat(),received_at=NOW.isoformat(),body=body,parsed=parsed)
        path=tmp_path/'source.json';path.write_text(json.dumps(envelope))
        return service.capture_file(path,source_system='nfl_official',dataset='official_final_game_report',season=2026,week=6,slate='TEST',source_license='fixture',source_uri=URI,metadata={k:v for k,v in parsed.items() if k!='rows'},row_count=len(parsed['rows'])).snapshot
    yield make
    session.close()


def test_game_calendar_dates_come_from_authored_day_headers_not_capture():
    _,rows=parse(html())
    assert [p['practice_date'] for p in rows[0]['practices']]==['2026-10-15','2026-10-16','2026-10-17']
    assert [p['practice_status'] for p in rows[0]['practices']]==['LP','DNP','LP']
    _,missing=parse(html().replace('<td>Limited</td>','<td></td>',1))
    assert missing[0]['practices'][0]['practice_status'] is None


def test_real_verified_snapshot_identity_and_practice_feature_reaches_catalog(snapshot):
    s=snapshot();roster=[dict(player_master_id=PID,team='WAS',position='WR',player_name='Terry McLaurin')]
    out=extract_official_role_report(s,roster,[],cutoff=NOW+timedelta(minutes=1))
    assert len(out['facts'])==4 and not out['identity_review_requests']
    features=build_player_role_features(roster,out['facts'],season=2026,week=6,cutoff=NOW+timedelta(minutes=1))
    trend=features['players'][0]['metrics']['G17-M02']['value']
    assert trend['previous']=='DNP' and trend['latest']=='LP' and trend['ordinal_change']==1


def test_name_alone_or_ambiguous_identity_cannot_map_report(snapshot):
    s=snapshot();roster=[dict(player_master_id=PID,team='SF',position='WR',player_name='Terry McLaurin')]
    assert extract_official_role_report(s,roster,[],cutoff=NOW+timedelta(minutes=1))['identity_review_requests']
    roster=[dict(player_master_id=PID,team='WAS',position='WR',player_name='Terry McLaurin'),dict(player_master_id='22222222-2222-4222-8222-222222222222',team='WAS',position='WR',player_name='Terry McLaurin')]
    out=extract_official_role_report(s,roster,[],cutoff=NOW+timedelta(minutes=1));assert not out['facts'] and out['identity_review_requests'][0]['reason']=='ambiguous'


def test_persisted_native_alias_wins_with_scoped_position_and_name_change(snapshot):
    s=snapshot();parsed,_=parse(html());key=parsed['rows'][0]['source_key']
    roster=[dict(player_master_id=PID,team='WAS',position='WR',player_name='Changed Display')]
    aliases=[dict(source_system='nfl_official',source_key=key,player_master_id=PID,alias_name='old')]
    out=extract_official_role_report(s,roster,aliases,cutoff=NOW+timedelta(minutes=1))
    assert out['identity_resolution_actions'][0]['method']=='source_native_id'


def test_offensive_tackle_position_family_keeps_full_roster_identity(snapshot):
    s=snapshot(html().replace('WR Terry McLaurin','T Terry McLaurin'))
    roster=[dict(player_master_id=PID,team='WAS',position='OT',player_name='Terry McLaurin')]
    out=extract_official_role_report(s,roster,[],cutoff=NOW+timedelta(minutes=1))
    assert out['facts'][0]['position']=='OT' and out['facts'][0]['source_position']=='T'


@pytest.mark.parametrize('kind',['future','hash','scope','headers'])
def test_snapshot_and_report_scope_errors_do_not_create_practice_data(snapshot,kind):
    if kind=='headers':
        with pytest.raises(ValueError):parse(html().replace('<th>Friday</th>','<th>Thursday</th>'))
        return
    s=snapshot()
    if kind=='hash':s.content_sha256='0'*64
    if kind=='scope':s.week=5
    with pytest.raises((ValueError,SnapshotIntegrityError)):
        extract_official_role_report(s,[],[],cutoff=NOW-timedelta(minutes=1) if kind=='future' else NOW+timedelta(minutes=1))


def test_official_combined_center_guard_position_uses_same_known_line_family(snapshot):
    s=snapshot(html().replace('WR Terry McLaurin','C/G Terry McLaurin'))
    roster=[dict(player_master_id=PID,team='WAS',position='G',player_name='Terry McLaurin')]
    out=extract_official_role_report(s,roster,[],cutoff=NOW+timedelta(minutes=1))
    assert not out['identity_review_requests'] and out['facts'][0]['position']=='G'
    assert out['facts'][0]['source_position']=='C/G'


def test_identity_actions_use_existing_durable_alias_and_queue_workflow(snapshot,monkeypatch):
    from backend.app.product_services.official_role_report_features import persist_official_role_identities
    observed=[]
    def record(connection,row,pid,reason,**scope):observed.append((row,pid,reason,scope));return pid is not None
    monkeypatch.setattr('backend.app.product_services.official_injuries._record_identity',record)
    s=snapshot();roster=[dict(player_master_id=PID,team='WAS',position='WR',player_name='Terry McLaurin')]
    receipt=extract_official_role_report(s,roster,[],cutoff=NOW+timedelta(minutes=1))
    assert persist_official_role_identities(object(),receipt)['resolved']==1
    assert observed[0][3]==dict(season=2026,week=6,slate='TEST')
    unresolved=extract_official_role_report(s,[],[],cutoff=NOW+timedelta(minutes=1));assert persist_official_role_identities(object(),unresolved)['review']==1
    assert observed[-1][1] is None and observed[-1][0]['source_key'].startswith(URI)
