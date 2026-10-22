from copy import deepcopy
import pytest
from backend.app.product_services.workload_kickoff_groups import normalize_kickoff_context,build_workload_kickoff_groups
from backend.app.tests.product.test_workload_market_contexts import fixture as source_fixture


def fixture():
    w,s,raw=source_fixture()
    for r in raw:r['gametime']='19:00' if r['week']%2 else '18:59'
    return w,s,raw


def run(w=None,s=None,raw=None):
    a,b,c=fixture();w=w or a;s=s or b
    ctx=normalize_kickoff_context(c if raw is None else raw,s,before_period=202607)
    return build_workload_kickoff_groups(w,s,ctx,before_period=202607)


def test_declared_Eastern_boundary_and_observed_workload_difference():
    r=run()['rows'][0]['metrics']['G21-M06'];ch=r['channels']['rush_attempts']
    assert ch['at_or_after_19_eastern']['observed_logs']==2 and ch['before_19_eastern']['observed_logs']==2
    assert ch['night_minus_earlier']==-1 and r['unknown_kickoff_logs']==0
    assert run()['pregame_serving_eligible'] is False

@pytest.mark.parametrize('value',['7pm','24:00','19:60','19:00:60',None,1900])
def test_missing_or_ambiguous_clock_not_inferred(value):
    w,s,raw=fixture();raw[0]['gametime']=value
    m=run(w,s,raw)['rows'][0]['metrics']['G21-M06']
    assert m['unknown_kickoff_logs']==1 and m['channels']['rush_attempts']['night_minus_earlier'] is None


def test_native_seconds_boundary_and_no_venue_timezone_conversion():
    w,s,raw=fixture();raw[0]['gametime']='18:59:59';raw[1]['gametime']='19:00:00'
    ctx=normalize_kickoff_context(raw,s,before_period=202607)
    assert ctx['source_clock_timezone']=='Eastern' and ctx['rows'][0]['at_or_after_19_eastern'] is False
    assert ctx['rows'][1]['at_or_after_19_eastern'] is True


def test_missing_official_exposure_and_single_group_remain_undefined():
    w,s,raw=fixture();w['rows'][0]['metrics']['G07-M01']['denominator']=None
    assert run(w,s,raw)['rows'][0]['metrics']['G21-M06']['channels']['rush_attempts']['night_minus_earlier'] is None
    for r in raw:r['gametime']='20:00'
    assert run(raw=raw)['rows'][0]['metrics']['G21-M06']['channels']['targets']['night_minus_earlier'] is None

@pytest.mark.parametrize('kind',['duplicate','orientation','future_weekly','source','group'])
def test_scope_source_and_group_contradictions_reject(kind):
    w,s,raw=fixture()
    if kind=='duplicate':raw.append(deepcopy(raw[0]))
    elif kind=='orientation':raw[0]['away_team']='GB'
    elif kind=='future_weekly':w['rows'][0]['season']=2027
    if kind in {'duplicate','orientation','future_weekly'}:
        with pytest.raises(ValueError):run(w,s,raw)
    else:
        ctx=normalize_kickoff_context(raw,s,before_period=202607)
        if kind=='source':ctx['provenance']['snapshot_id']='different-source'
        else:ctx['rows'][0]['at_or_after_19_eastern']=False
        with pytest.raises(ValueError):build_workload_kickoff_groups(w,s,ctx,before_period=202607)


def test_native_source_order_and_recapture_do_not_add_measurement_votes():
    w,s,raw=fixture();a=run(w,s,raw)['semantic_sha256'];raw.reverse();w['rows'].reverse()
    for row in w['rows']:row['source_ref']['imported_at']='2026-10-20T04:00:00Z'
    assert run(w,s,raw)['semantic_sha256']==a


def test_indexed_native_clock_loader_checks_actual_source_clock_and_bytes(tmp_path):
    from types import SimpleNamespace
    from datetime import datetime,UTC
    import polars as pl
    from backend.app.tests.test_source_capture import _session
    from backend.app.services.source_capture import SourceCaptureService,SnapshotIntegrityError
    from backend.app.models import SourceSnapshot
    from backend.app.product_services.schedule_context_features import capture_schedule_context
    from backend.app.product_services.workload_kickoff_groups import load_kickoff_context
    from backend.app.tests.product.test_schedule_context_features import row
    now=datetime(2026,10,20,3,tzinfo=UTC);session=_session()
    try:
        service=SourceCaptureService(session,snapshot_root=tmp_path/'source',clock=lambda:now)
        provider=SimpleNamespace(load_schedules=lambda seasons:pl.DataFrame([row(gametime='21:15')]))
        capture=capture_schedule_context(service,season=2026,week=7,slate='FEATURES',slate_lock_at='2026-10-27T00:15:00Z',nfl_module=provider)
        snapshot=session.get(SourceSnapshot,capture.snapshot.snapshot_id)
        _,ctx=load_kickoff_context(snapshot,before_period=202607,cutoff=now)
        assert ctx['rows'][0]['native_eastern_kickoff_seconds']==76500 and ctx['provenance']['source_gametime_field_present']
        with pytest.raises(ValueError,match='unavailable'):load_kickoff_context(snapshot,before_period=202607,cutoff='2026-10-20T02:59:59Z')
        snapshot.content_sha256='0'*64
        with pytest.raises(SnapshotIntegrityError):load_kickoff_context(snapshot,before_period=202607,cutoff=now)
    finally:session.close()
