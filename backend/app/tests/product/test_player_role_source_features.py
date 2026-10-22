from datetime import UTC,datetime,timedelta
from pathlib import Path
import pandas as pd
import pytest
from backend.app.services.source_capture import SourceCaptureService,SnapshotIntegrityError
from backend.app.tests.test_source_capture import _session
from backend.app.product_services.player_role_source_features import extract_retained_role_sources
from backend.app.product_services.player_role_features import build_player_role_features

NOW=datetime(2026,10,19,19,tzinfo=UTC);PID='11111111-1111-4111-8111-111111111111';NATIVE='00-0000001'

@pytest.fixture
def sources(tmp_path):
    session=_session();service=SourceCaptureService(session,snapshot_root=tmp_path/'snapshots',clock=lambda:NOW)
    def make(rosters=None,depths=None):
        rs=rosters if rosters is not None else [dict(season=2026,week=6,game_type='REG',team='WAS',position='OC',gsis_id=NATIVE,status='OUT')]
        ds=depths if depths is not None else [dict(dt=NOW.isoformat(),team='WAS',gsis_id=NATIVE,pos_abb='C',pos_rank=1,pos_slot=1)]
        out=[]
        for dataset,rows in [('weekly_rosters',rs),('player_depth_charts',ds)]:
            out.append(service.capture_dataframe(pd.DataFrame(rows),artifact_name=dataset+'.csv',source_system='fixture',dataset=dataset,season=2026,week=6,slate='TEST',source_license='fixture',source_uri='nflreadpy://'+dataset).snapshot)
        return out
    yield make
    session.close()


def extract(snapshots,aliases=None,**kwargs):
    return extract_retained_role_sources(*snapshots,canonical_ids=aliases or {NATIVE:PID},season=2026,week=6,teams=['WAS'],cutoff=kwargs.get('cutoff',NOW+timedelta(minutes=1)))


def test_actual_snapshot_bytes_native_identity_full_provider_universe_depth_rank(sources):
    snapshots=sources();r=extract(snapshots)
    assert len(r['actors'])==1 and len(r['facts'])==3 and not r['identity_review_requests']
    assert r['facts'][1]['depth_position']==1 and r['facts'][2]['role']=='expected_starter'
    assert not r['roster_coverage']['WAS']['complete']
    features=build_player_role_features(r['actors'],r['facts'],season=2026,week=6,cutoff=NOW+timedelta(minutes=1),roster_coverage=r['roster_coverage'])
    assert features['players'][0]['metrics']['G17-M05']['value']==1
    assert features['teams'][0]['metrics']['G18-M03']['value'] is None


@pytest.mark.parametrize('kind',['tamper','future','scope','postseason','duplicate','alias'])
def test_invalid_source_scope_or_identity_does_not_silently_map_or_count(sources,kind):
    rosters=[dict(season=2026,week=6,game_type='REG',team='WAS',position='OC',gsis_id=NATIVE,status='OUT')]
    if kind=='postseason':rosters[0]['game_type']='POST'
    if kind=='duplicate':rosters.append(dict(rosters[0]))
    snapshots=sources(rosters=rosters)
    if kind=='tamper':snapshots[0].content_sha256='0'*64
    if kind=='scope':snapshots[1].week=5
    if kind=='alias':
        r=extract(snapshots,aliases={NATIVE:[PID,'22222222-2222-4222-8222-222222222222']})
        assert not r['actors'] and r['identity_review_requests'][0]['reason']=='ambiguous_native_alias';return
    with pytest.raises((ValueError,SnapshotIntegrityError)):extract(snapshots,cutoff=NOW-timedelta(seconds=1) if kind=='future' else NOW+timedelta(minutes=1))


def test_future_depth_event_and_wrong_position_do_not_create_promotion(sources):
    snapshots=sources(depths=[dict(dt=(NOW+timedelta(days=1)).isoformat(),team='WAS',gsis_id=NATIVE,pos_abb='C',pos_rank=1)])
    assert len(extract(snapshots)['facts'])==1
    snapshots=sources(depths=[dict(dt=NOW.isoformat(),team='WAS',gsis_id=NATIVE,pos_abb='WR',pos_rank=1)])
    r=extract(snapshots);assert len(r['facts'])==1 and r['identity_review_requests'][0]['reason']=='depth_roster_team_or_position_conflict'


@pytest.mark.parametrize('roster_position,depth_position',[('DB','FS'),('DB','LCB'),('LB','LILB'),('LB','RILB'),('LB','RDE'),('RB','FB')])
def test_real_provider_broad_or_hybrid_positions_retain_explicit_depth_unit(sources,roster_position,depth_position):
    snapshots=sources(rosters=[dict(season=2026,week=6,game_type='REG',team='WAS',position=roster_position,gsis_id=NATIVE,status='OUT')],depths=[dict(dt=NOW.isoformat(),team='WAS',gsis_id=NATIVE,pos_abb=depth_position,pos_rank=1)])
    r=extract(snapshots);assert len(r['facts'])==3 and not r['identity_review_requests']
    assert r['facts'][1]['roster_position']==roster_position and r['facts'][1]['source_position']==depth_position


def test_returner_depth_is_separate_from_primary_role_not_an_identity_error(sources):
    snapshots=sources(rosters=[dict(season=2026,week=6,game_type='REG',team='WAS',position='WR',gsis_id=NATIVE,status='OUT')],depths=[dict(dt=NOW.isoformat(),team='WAS',gsis_id=NATIVE,pos_abb='PR',pos_rank=1)])
    r=extract(snapshots);assert len(r['facts'])==1 and not r['identity_review_requests']
    assert r['role_scope_exclusions'][0]['depth_slot']=='PR'
