from copy import deepcopy
import pytest
from backend.app.tests.product.test_workload_starting_qb_context import sources,CUTOFF
from backend.app.product_services.active_workload_distributions import build_active_workload_distributions,require_feature_use


def inputs():
    w,s,_=sources();p=dict(version='canonical_offensive_participation_v1',pregame_serving_eligible=False,actual_derived_at='2026-10-20T04:00:00Z',provenance={},rows=[])
    for r in w['rows']:
        p['rows'].append(dict(season=r['season'],week=r['week'],native_game_id=str(r['week']),team=r['team'],player_master_id=r['player_master_id'],offense_snaps=5,source_ref={'native':'PFR'}))
    return w,s,p


def run(w=None,s=None,p=None):
    a,b,c=inputs();return build_active_workload_distributions(w or a,s or b,p or c,before_period=202607,cutoff=CUTOFF)


def test_positive_snap_conditional_variance_and_zero_preserved():
    x=run();m=x['rows'][0]['metrics']
    assert m['X02-M02']['value']==pytest.approx(5/3)
    assert m['X02-M05']['value']==.25
    assert m['X02-M03']['value']==0
    assert x['forecast'] is None and require_feature_use(x,purpose='offline_descriptive') is x
    with pytest.raises(ValueError):require_feature_use(x,purpose='optimizer')


@pytest.mark.parametrize('snaps',[None,0])
def test_missing_or_zero_snap_not_DNP_nor_known_inactive(snaps):
    w,s,p=inputs();p['rows'][0]['offense_snaps']=snaps
    m=run(w,s,p)['rows'][0]['metrics']['X02-M05']
    assert m['value'] is None and m['unknown_participation_logs']==1
    assert m['known_sample_value']==0


def test_no_snap_row_unknown_and_no_count_row_zero_fill():
    w,s,p=inputs();p['rows'].pop()
    assert run(w,s,p)['rows'][0]['metrics']['X02-M02']['value'] is None
    w,s,p=inputs();w['rows'].pop()
    x=run(w,s,p)
    assert len(x['positive_participants_missing_weekly_rows'])==1
    assert x['rows'][0]['metrics']['X02-M02']['value'] is None


def test_count_null_masks_not_complete_case_variance():
    w,s,p=inputs();w['rows'][0]['metrics']['G07-M01']['denominator']=None
    m=run(w,s,p)['rows'][0]['metrics']['X02-M02']
    assert m['value'] is None and m['unknown_count_logs']==1 and m['known_sample_value']==1


def test_role_conditions_not_from_positive_attempts():
    w,s,p=inputs()
    for r in w['rows']:r['source_position']='WR'
    x=run(w,s,p)['rows'][0]['metrics']
    assert x['X02-M03']['value'] is None and not x['X02-M03']['source_role_applicable']
    assert x['X02-M05']['value'] is None and x['X02-M04']['value']==0
    for r in w['rows']:r['source_position']=None
    assert all(m['value'] is None for m in run(w,s,p)['rows'][0]['metrics'].values())


@pytest.mark.parametrize('mutation',['negative','duplicate','future','game','canonical'])
def test_physical_identity_scope_guards(mutation):
    w,s,p=inputs()
    if mutation=='negative':p['rows'][0]['offense_snaps']=-1
    if mutation=='duplicate':p['rows'].append(deepcopy(p['rows'][0]))
    if mutation=='future':p['rows'][0]['week']=7
    if mutation=='game':p['rows'][0]['native_game_id']='other'
    if mutation=='canonical':p['rows'][0]['player_master_id']='display name'
    with pytest.raises(ValueError):run(w,s,p)


def test_single_log_variance_undefined_and_no_team_pooling():
    w,s,p=inputs();w['rows']=w['rows'][:1];p['rows']=p['rows'][:1]
    x=run(w,s,p)['rows'][0]['metrics']
    assert x['X02-M02']['value'] is None and x['X02-M05']['value']==1


def test_authenticated_snap_adapter_preserves_scope_revisions_and_unknown_identity(tmp_path):
    import json
    from datetime import datetime,UTC
    from backend.app.tests.test_source_capture import _session
    from backend.app.services.source_capture import SourceCaptureService,SnapshotIntegrityError
    from backend.app.tests.product.test_recent_snap_features import row,ALIASES
    from backend.app.product_services.active_workload_distributions import load_positive_snap_participation
    now=datetime(2026,10,20,3,tzinfo=UTC);s=_session()
    try:
        rows=[row(1),row(2,offense_snaps=0,offense_pct=.1),row(3,'Unmapped0'),row(6)]
        duplicate=deepcopy(rows[0]);duplicate.update(source_row_id='repeat',ingest_run_id='second-ingest');rows.append(duplicate)
        runs=[dict(ingest_run_id=k,status='completed',started_at='2026-10-19T19:00:00Z',completed_at='2026-10-19T21:00:00Z') for k in ('original-ingest','second-ingest')]
        value=dict(contract='retained_snap_count_revision_v1',season=2026,rows=rows,aliases=ALIASES,identity_blocks=[],original_ingest_runs=runs,actual_extract_started_at='2026-10-20T02:00:00Z',actual_extract_completed_at='2026-10-20T02:01:00Z',original_provider_snapshot_claim=False,source_origin='Retained revision')
        path=tmp_path/'rows.json';path.write_text(json.dumps(value))
        snapshot=SourceCaptureService(s,snapshot_root=tmp_path/'sources',clock=lambda:now).capture_file(path,source_system='retained_db',dataset='snap_counts_revision',season=2026,week=6,slate='features',source_uri='retained-db://public.raw_nfl_snap_count/season=2026',source_license='test',slate_lock_at=datetime(2026,10,20,0,15,tzinfo=UTC),observation_basis='capture_clock',media_type='application/json',row_count=len(rows)).snapshot
        result=load_positive_snap_participation(snapshot,cutoff=now)
        assert len(result['rows'])==3 and len(result['skipped_source_rows'])==1
        first=next(r for r in result['rows'] if r['week']==1)
        assert len(first['source_records'])==2 and first['offense_snaps']==10
        assert next(r for r in result['rows'] if r['week']==2)['offense_snaps'] is None
        assert next(r for r in result['rows'] if r['week']==3)['player_master_id'] is None
        snapshot.content_sha256='0'*64
        with pytest.raises(SnapshotIntegrityError):load_positive_snap_participation(snapshot,cutoff=now)
    finally:s.close()


def test_recapture_positive_snap_magnitude_and_input_order_stable_numerical_semantics():
    w,s,p=inputs();sha=run(w,s,p)['semantic_sha256'];w['rows'].reverse();p['rows'].reverse()
    for r in p['rows']:r['offense_snaps']=10;r['source_ref']={'new':'capture'}
    for r in w['rows']:r['source_ref']['imported_at']='2026-10-20T02:00:00Z'
    assert run(w,s,p)['semantic_sha256']==sha


def test_separate_source_role_cohorts_and_unmapped_participation_retained():
    w,s,p=inputs();w['rows'][0]['source_position']='RB'
    p['identity_review_requests']=[{'source_key':'native_unresolved'}]
    extra=deepcopy(p['rows'][0]);extra['player_master_id']=None;p['rows'].append(extra)
    x=run(w,s,p)
    assert len(x['rows'])==2 and len(x['unresolved_participation_rows'])==1
    assert x['participation_identity_review_requests']==p['identity_review_requests']
    assert next(r for r in x['rows'] if r['source_position']=='RB')['metrics']['X02-M02']['value'] is None
