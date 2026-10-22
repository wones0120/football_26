from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pandas as pd
import pytest

from backend.app.services.source_capture import SourceCaptureService,SnapshotIntegrityError,verify_snapshot_artifact
from backend.app.product_services.opportunity_source_capture import (
    SourceLimits,capture_opportunity_source,derive_opportunity_event_evidence,
)
from backend.app.tests.test_source_capture import _session

NOW=datetime(2026,9,20,12,tzinfo=timezone.utc)
LOCK=NOW+timedelta(hours=3)
NATIVE='00-0000001';CANONICAL=str(UUID(int=1))


def row(play=1,week=1,**changes):
    value=dict(game_id=f'2026_{week:02d}_BUF_MIA',play_id=play,season=2026,week=week,season_type='REG',
        posteam='BUF',defteam='MIA',play_type='run',pass_attempt=0,rush_attempt=1,sack=0,
        no_play=0,two_point_attempt=0,qb_kneel=0,qb_scramble=0,goal_to_go=0,yardline_100=25,
        rusher_player_id=NATIVE,yards_gained=0)
    value.update(changes);return value


@pytest.fixture
def service(tmp_path):
    session=_session()
    yield SourceCaptureService(session,snapshot_root=tmp_path/'snapshots',clock=lambda:NOW)
    session.close()


def capture(service,events=None,module=None,**kwargs):
    events=events if events is not None else [row()]
    module=module or SimpleNamespace(__version__='synthetic',load_pbp=lambda **kw:pd.DataFrame(events))
    return capture_opportunity_source(service,season=2026,week=3,slate='SUNDAY_MAIN',slate_lock_at=LOCK,nfl_module=module,**kwargs)


def derive(snapshot,**kwargs):
    params=dict(canonical_ids={NATIVE:CANONICAL},before_period=202603,cutoff=NOW+timedelta(minutes=1));params.update(kwargs)
    return derive_opportunity_event_evidence(snapshot,**params)


def test_actual_source_service_capture_verify_prior_selection_and_unknown_finalness(service):
    result=capture(service,[row(),row(2,3),row(3,4),row(4,1,season_type='PRE')])
    verify_snapshot_artifact(result.snapshot)
    receipt=derive(result.snapshot)
    assert receipt['source_rows']==4 and receipt['derived_scoped_event_rows']==1
    assert receipt['excluded_rows']==dict(not_prior_period=2,not_regular_season=1,union_excluded=3)
    assert receipt['event_evidence']['teams'][0]['counts']['rush_attempts']==1
    assert receipt['event_evidence']['events'][0]['raw_flags']['yards_gained']==0
    assert receipt['forecast'] is None and 'unverified' in receipt['game_completion']
    assert 'cache' in receipt['event_evidence']['source']['remote_freshness']
    assert receipt['event_evidence']['source']['game_completion']=='unverified'
    assert receipt['event_evidence']['source']['received_at_basis'].startswith('persisted_snapshot')


def test_installed_provider_polars_shape_without_to_pandas_dependency(service):
    import polars as pl
    frame=pl.DataFrame([row()])
    module=SimpleNamespace(__version__='installed-shaped',load_pbp=lambda **kw:frame)
    result=capture(service,module=module)
    event=derive(result.snapshot)['event_evidence']['events'][0]
    assert event['opportunities'][0]['source_player_id']==NATIVE
    assert event['opportunities'][0]['player_master_id']==CANONICAL
    assert event['raw_flags']['pass_attempt']==0 and event['raw_flags']['goal_to_go']==0


def test_source_bytes_tamper_and_future_cutoff_rejected(service):
    result=capture(service)
    with pytest.raises(ValueError,match='unavailable'):derive(result.snapshot,cutoff=NOW-timedelta(seconds=1))
    path=Path(result.snapshot.artifact_path);original=path.read_bytes();result.snapshot.content_sha256='0'*64
    with pytest.raises(SnapshotIntegrityError):derive(result.snapshot)
    assert path.read_bytes()==original


def test_integral_native_play_alias_cannot_evade_duplicate_detection(service):
    result=capture(service,[row('1'),row('1.0')])
    with pytest.raises(ValueError,match='Duplicate native play'):derive(result.snapshot)


def test_native_identity_missingness_is_review_pending_not_false_zero(service):
    result=capture(service,[row(rusher_player_id=None,rush_attempt=1),row(2,rush_attempt=None)])
    receipt=derive(result.snapshot)
    assert receipt['status']=='identity_review_pending' and receipt['identity_review_requests']
    team=receipt['event_evidence']['teams'][0]
    assert team['counts']['rush_attempts'] is None and team['counted_lower_bound']['rush_attempts']==1
    with pytest.raises(ValueError,match='native GSIS'):derive(result.snapshot,canonical_ids={'Example Name':CANONICAL})


def test_unscoped_nonoffense_preserved_without_fake_team_and_offensive_scope_rejected(service):
    result=capture(service,[row(1,posteam=None,play_type='kickoff',rush_attempt=0),row(2)])
    receipt=derive(result.snapshot)
    assert receipt['derived_scoped_event_rows']==1 and len(receipt['unscoped_nonoffensive_rows'])==1
    assert receipt['unscoped_nonoffensive_rows'][0]['posteam'] is None
    result=capture(service,[row(posteam=None)])
    with pytest.raises(ValueError,match='lacks team'):derive(result.snapshot)


def test_source_bounds_and_wrong_scope_fail_before_consumption(service):
    with pytest.raises(ValueError,match='row bound'):capture(service,[row(),row(2)],limits=SourceLimits(max_rows=1))
    with pytest.raises(ValueError,match='byte bound'):capture(service,limits=SourceLimits(max_bytes=2))
    result=capture(service)
    with pytest.raises(ValueError,match='scope differs'):derive(result.snapshot,before_period=202604)
    with pytest.raises(ValueError,match='precede.*lock'):derive(result.snapshot,cutoff=LOCK)


def test_conflicting_regular_season_scope_and_future_reconciliation_not_claimed(service):
    result=capture(service,[row(week=19)])
    with pytest.raises(ValueError,match='invalid week'):derive(result.snapshot)
    result=capture(service)
    with pytest.raises(ValueError,match='reconciliation'):derive(result.snapshot,official_components=[dict(source_id='official',imported_at=LOCK.isoformat())])


def test_native_game_period_conflict_cannot_pass_source_column_checks(service):
    result=capture(service,[row(game_id='2025_01_BUF_MIA')])
    with pytest.raises(ValueError,match='native game identity conflicts'):derive(result.snapshot)


def test_polars_nullable_boolean_flags_preserve_false_and_unknown(service):
    import polars as pl
    frame=pl.DataFrame([row(pass_attempt=False,rush_attempt=True),row(2,pass_attempt=False,rush_attempt=None)])
    result=capture(service,module=SimpleNamespace(__version__='synthetic',load_pbp=lambda **kw:frame))
    receipt=derive(result.snapshot)
    events=receipt['event_evidence']['events']
    assert events[0]['raw_flags']['pass_attempt'] is False
    assert events[1]['raw_flags']['rush_attempt'] is None
    assert receipt['event_evidence']['teams'][0]['counts']['rush_attempts'] is None


@pytest.mark.parametrize('field',['posteam','defteam'])
def test_contradictory_native_game_team_rejected(service,field):
    result=capture(service,[row(**{field:'GB'})])
    with pytest.raises(ValueError,match='contradicts native game'):derive(result.snapshot)


def test_legitimate_team_alias_preserves_native_fields_and_reconciliation(service):
    result=capture(service,[row(game_id='2026_01_LA_SF',posteam='LA',defteam='SF')])
    receipt=derive(result.snapshot,official_components=[dict(game_id='2026_01_LA_SF',season_type='REG',team='LA',source_player_id=NATIVE,
        rush_attempts=1,source_id='independent_official',imported_at=NOW.isoformat())])
    event=receipt['event_evidence']['events'][0]
    assert event['team']=='LAR' and event['raw_flags']['posteam']=='LAR'
    assert event['raw_flags']['source_native_team_fields']==dict(posteam='LA',defteam='SF')
    assert receipt['event_evidence']['source']['team_transform']['native_to_canonical']['LA']=='LAR'
    assert receipt['event_evidence']['official_reconciliation'][0]['status']=='matched'
    assert 'LA' in Path(result.snapshot.artifact_path).read_text()


def test_capture_advertised_minimum_aligns_existing_service(service):
    with pytest.raises(ValueError,match='scope'):capture_opportunity_source(service,season=1999,week=3,slate='x',slate_lock_at=LOCK)



def test_actual_provider_game_header_and_quarter_boundary_preserved_without_fake_team(service):
    headers=[row(1,posteam=None,play_type=None,desc='GAME',quarter_end=0,pass_attempt=None,rush_attempt=None,sack=None),
        row(2,posteam=None,play_type=None,desc='END QUARTER 2',quarter_end=1,pass_attempt=None,rush_attempt=None,sack=None)]
    receipt=derive(capture(service,headers+[row(3)]).snapshot)
    assert len(receipt['unscoped_nonoffensive_rows'])==2 and receipt['derived_scoped_event_rows']==1
    assert receipt['unscoped_nonoffensive_rows'][0]['posteam'] is None
    assert receipt['unscoped_nonoffensive_rows'][0]['rush_attempt'] is None
    assert receipt['event_evidence']['teams'][0]['counts']['rush_attempts']==1


@pytest.mark.parametrize('changes',[dict(desc='unknown',quarter_end=0),dict(desc='GAME',quarter_end=0,pass_attempt=1)])
def test_unknown_or_conflicting_typeless_missing_team_not_hidden(service,changes):
    fields=dict(posteam=None,play_type=None,pass_attempt=None,rush_attempt=None,sack=None);fields.update(changes)
    event=row(**fields)
    with pytest.raises(ValueError,match='lacks team'):derive(capture(service,[event]).snapshot)


@pytest.mark.parametrize('indicator',['qb_dropback','qb_scramble','qb_spike','qb_kneel','two_point_attempt'])
def test_positive_offense_indicator_cannot_hide_in_typeless_quarter_control(service,indicator):
    fields=dict(posteam=None,play_type=None,desc='END QUARTER 2',quarter_end=1,
        pass_attempt=None,rush_attempt=None,sack=None)
    fields[indicator]=1
    with pytest.raises(ValueError,match='lacks team'):derive(capture(service,[row(**fields)]).snapshot)



def test_scoped_quarter_and_end_game_are_controls_not_unknown_opportunities(service):
    controls=[row(1,play_type=None,desc='END QUARTER 1',quarter_end=1,pass_attempt=None,rush_attempt=None,sack=None),
        row(2,play_type=None,desc='END GAME',quarter_end=0,pass_attempt=None,rush_attempt=None,sack=None)]
    receipt=derive(capture(service,controls+[row(3)]).snapshot)
    assert len(receipt['scoped_administrative_rows'])==2 and receipt['derived_scoped_event_rows']==1
    assert receipt['event_evidence']['coverage']['unknown']==0
    assert receipt['event_evidence']['source']['scope_exclusions']['scoped_administrative_controls']==2
    assert receipt['event_evidence']['teams'][0]['counts']['rush_attempts']==1
    assert 'unverified' in receipt['game_completion']


def test_scoped_control_positive_flag_and_unmatched_prose_remain_unknown(service):
    controls=[row(1,play_type=None,desc='END GAME',quarter_end=0,pass_attempt=None,rush_attempt=None,sack=None,qb_dropback=1),
        row(2,play_type=None,desc='The game has resumed.',quarter_end=0,pass_attempt=None,rush_attempt=None,sack=None)]
    receipt=derive(capture(service,controls+[row(3)]).snapshot)
    assert receipt['scoped_administrative_rows']==[]
    assert receipt['event_evidence']['coverage']['unknown']==2
    assert receipt['event_evidence']['teams'][0]['counts']['rush_attempts'] is None


def test_duplicate_control_id_not_exempt_from_native_integrity(service):
    controls=[row('1.0',play_type=None,desc='END GAME',quarter_end=0,pass_attempt=None,rush_attempt=None,sack=None)]
    with pytest.raises(ValueError,match='Duplicate native play'):derive(capture(service,controls+[row('1')]).snapshot)


def test_compact_artifact_immutable_roundtrip_ref_and_raw_snapshot_checks(service,tmp_path):
    from backend.app.product_services.opportunity_source_capture import freeze_event_artifact,load_event_artifact
    result=capture(service);evidence=derive(result.snapshot);directory=tmp_path/'derived'
    ref=freeze_event_artifact(evidence,result.snapshot,directory=directory)
    original=Path(ref['path']).read_bytes()
    assert freeze_event_artifact(evidence,result.snapshot,directory=directory)==ref
    assert Path(ref['path']).read_bytes()==original
    assert load_event_artifact(ref,result.snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=2),directory=directory)==evidence
    altered=dict(ref,source_sha256='0'*64)
    with pytest.raises(ValueError,match='reference differs'):load_event_artifact(altered,result.snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=2),directory=directory)
    result.snapshot.content_sha256='0'*64
    with pytest.raises(SnapshotIntegrityError):load_event_artifact(ref,result.snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=2),directory=directory)


@pytest.mark.parametrize('field',['logical_sha256','expanded_bytes','decision_cutoff_at','source_captured_at','source_snapshot_id','event_receipt_sha256'])
def test_artifact_ref_fields_must_match_frozen_contents(service,tmp_path,field):
    from backend.app.product_services.opportunity_source_capture import freeze_event_artifact,load_event_artifact
    snapshot=capture(service).snapshot;ref=freeze_event_artifact(derive(snapshot),snapshot,directory=tmp_path)
    changed=dict(ref);changed[field]=1 if field=='expanded_bytes' else 'changed'
    with pytest.raises(ValueError,match='reference differs'):load_event_artifact(changed,snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=2),directory=tmp_path)


def test_artifact_size_decompression_and_managed_path_bounds(service,tmp_path):
    from backend.app.product_services.opportunity_source_capture import ArtifactLimits,freeze_event_artifact,load_event_artifact
    snapshot=capture(service).snapshot;evidence=derive(snapshot)
    with pytest.raises(ValueError,match='expanded'):freeze_event_artifact(evidence,snapshot,directory=tmp_path,limits=ArtifactLimits(max_expanded_bytes=1))
    ref=freeze_event_artifact(evidence,snapshot,directory=tmp_path)
    for limits,match in [(ArtifactLimits(max_compressed_bytes=1),'compressed'),(ArtifactLimits(max_expanded_bytes=1),'expanded')]:
        with pytest.raises(ValueError,match=match):load_event_artifact(ref,snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=2),directory=tmp_path,limits=limits)
    with pytest.raises(ValueError,match='managed root'):load_event_artifact(dict(ref,path='/private/tmp/unrelated'),snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=2),directory=tmp_path)
    with pytest.raises(ValueError,match='Artifact bounds'):load_event_artifact(ref,snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=2),directory=tmp_path,limits=ArtifactLimits(max_expanded_bytes=-1))


def test_changed_content_clock_and_raw_source_pair_cannot_pass_self_hash(service,tmp_path):
    from copy import deepcopy
    import hashlib,json
    from backend.app.product_services.opportunity_source_capture import freeze_event_artifact,load_event_artifact
    snapshot=capture(service).snapshot;evidence=derive(snapshot);changed=deepcopy(evidence)
    inner=changed['event_evidence'];inner['source']['captured_at']=(NOW+timedelta(seconds=1)).isoformat();inner['source']['received_at']=inner['source']['captured_at']
    inner.pop('sha256');inner['sha256']=hashlib.sha256(json.dumps(inner,sort_keys=True,allow_nan=False).encode()).hexdigest()
    with pytest.raises(ValueError,match='actual raw source'):freeze_event_artifact(changed,snapshot,directory=tmp_path)
    other=capture(service,[row(yards_gained=4)]).snapshot
    with pytest.raises(ValueError,match='actual raw source'):freeze_event_artifact(evidence,other,directory=tmp_path)
    ref=freeze_event_artifact(evidence,snapshot,directory=tmp_path)
    with pytest.raises(ValueError,match='after forecast cutoff'):load_event_artifact(ref,snapshot,before_period=202603,cutoff=NOW,directory=tmp_path)


def test_scalar_actor_filter_preserves_semantic_hash_team_denominator_and_unallocated_residual(service):
    from backend.app.product_services.opportunity_source_capture import semantic_event_view
    second=str(UUID(int=2));unobserved=str(UUID(int=3))
    evidence=derive(capture(service,[row(1),row(2,rusher_player_id='00-0000002')]).snapshot,
        canonical_ids={NATIVE:CANONICAL,'00-0000002':second})
    full=semantic_event_view(evidence,teams=['BUF']);view=semantic_event_view(evidence,teams=['BUF'],actor_ids=[CANONICAL,unobserved])
    assert view['semantic_measurements_sha256']==full['semantic_measurements_sha256']
    assert view['team_rows']==full['team_rows'] and view['team_rows'][0]['counts']['rush_attempts']==2
    assert len(view['actor_rows'])==1
    assert view['actor_attachment_residuals'][0]['unallocated_counted_lower_bound']['rush_attempts']==1
    assert view['unobserved_requested_actor_ids']==[unobserved] and view['forecast'] is None
    def has_raw_rows(value):
        if isinstance(value,dict):return 'raw_flags' in value or any(has_raw_rows(v) for v in value.values())
        if isinstance(value,list):return any(has_raw_rows(v) for v in value)
        return False
    assert not has_raw_rows(view)


def test_scalar_envelope_recapture_and_source_current_period_revision_are_not_new_facts(service):
    from copy import deepcopy
    import hashlib,json
    from backend.app.product_services.opportunity_source_capture import semantic_event_view
    snapshot=capture(service,[row(1,epa=0),row(2,3,epa=1)]).snapshot
    first=derive(snapshot);later=derive(snapshot,cutoff=NOW+timedelta(minutes=2))
    assert semantic_event_view(first)['semantic_measurements_sha256']==semantic_event_view(later)['semantic_measurements_sha256']
    changed=deepcopy(first);inner=changed['event_evidence'];inner['source']['snapshot_id']=str(UUID(int=20));inner['source']['content_sha256']='f'*64
    inner['source']['captured_at']=(NOW+timedelta(seconds=1)).isoformat();inner['source']['received_at']=inner['source']['captured_at']
    inner.pop('sha256');inner['sha256']=hashlib.sha256(json.dumps(inner,sort_keys=True,allow_nan=False).encode()).hexdigest()
    assert semantic_event_view(first)['semantic_measurements_sha256']==semantic_event_view(changed)['semantic_measurements_sha256']
    changed_snapshot=capture(service,[row(1,epa=0),row(2,3,epa=99)]).snapshot
    assert snapshot.content_sha256!=changed_snapshot.content_sha256
    assert semantic_event_view(first)['semantic_measurements_sha256']==semantic_event_view(derive(changed_snapshot))['semantic_measurements_sha256']


@pytest.mark.parametrize('revision',['prior_epa','count','coverage','reconciliation'])
def test_scalar_material_prior_revision_count_coverage_or_reconciliation_changes_hash(service,revision):
    from backend.app.product_services.opportunity_source_capture import semantic_event_view
    first=derive(capture(service,[row(1,epa=0)]).snapshot)
    changes={'prior_epa':dict(epa=1),'count':dict(epa=0,rush_attempt=0),'coverage':dict(epa=0,rush_attempt=None)}
    if revision=='reconciliation':
        second=derive(capture(service,[row(1,epa=0)]).snapshot,official_components=[dict(game_id='2026_01_BUF_MIA',season_type='REG',team='BUF',source_player_id=NATIVE,rush_attempts=2,source_id='official',imported_at=NOW.isoformat())])
    else:second=derive(capture(service,[row(1,**changes[revision])]).snapshot)
    assert semantic_event_view(first)['semantic_measurements_sha256']!=semantic_event_view(second)['semantic_measurements_sha256']


def test_scalar_team_scope_ignores_unrelated_game_revision_and_source_row_order(service):
    from backend.app.product_services.opportunity_source_capture import semantic_event_view
    before=[row(1,epa=0),row(1,game_id='2026_01_SF_WAS',posteam='SF',defteam='WAS',epa=1)]
    after=[row(1,game_id='2026_01_SF_WAS',posteam='SF',defteam='WAS',epa=9),row(1,epa=0)]
    a=semantic_event_view(derive(capture(service,before).snapshot),teams=['BUF'])
    b=semantic_event_view(derive(capture(service,after).snapshot),teams=['BUF'])
    assert a['semantic_measurements_sha256']==b['semantic_measurements_sha256']



def test_artifact_actual_verified_wrong_dataset_still_rejected(service,tmp_path):
    from backend.app.product_services.opportunity_source_capture import freeze_event_artifact,VERSION
    evidence=derive(capture(service).snapshot)
    wrong=service.capture_dataframe(pd.DataFrame([row()]),artifact_name='wrong.csv',source_system='nflreadpy',dataset='weekly_stats',
        season=2026,week=3,slate='SUNDAY_MAIN',source_license='synthetic',source_uri='nflreadpy://pbp/2026',slate_lock_at=LOCK,
        metadata=dict(contract_id=VERSION,loader='load_pbp')).snapshot
    with pytest.raises(ValueError,match='provider contract'):freeze_event_artifact(evidence,wrong,directory=tmp_path)


def test_invalid_compressed_artifact_is_explicitly_rejected(service,tmp_path):
    import hashlib
    from backend.app.product_services.opportunity_source_capture import load_event_artifact,ARTIFACT_CONTRACT
    snapshot=capture(service).snapshot;payload=b'invalid gzip';sha=hashlib.sha256(payload).hexdigest()
    path=tmp_path/(sha+'.json.gz');path.write_bytes(payload)
    with pytest.raises(ValueError,match='encoding'):load_event_artifact(dict(contract_id=ARTIFACT_CONTRACT,artifact_sha256=sha,path=str(path)),snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=2),directory=tmp_path)



def test_multiple_matching_prior_events_controls_unknown_teams_and_identity_requests_reorder_stable(service):
    from backend.app.product_services.opportunity_source_capture import semantic_event_view
    quiet=dict(play_type=None,pass_attempt=None,rush_attempt=None,sack=None)
    events=[row(1),row(2,rusher_player_id='00-0000002'),row(3,desc='unknown scoped marker',**quiet),
        row(4,desc='END QUARTER 1',quarter_end=1,**quiet),row(5,posteam=None,desc='GAME',quarter_end=0,**quiet),
        row(6,week=2,posteam='MIA',defteam='BUF',desc='unknown only team2',**quiet),
        row(7,posteam='MIA',defteam='BUF',desc='unknown only team1',**quiet)]
    before=derive(capture(service,events).snapshot);after=derive(capture(service,list(reversed(events))).snapshot)
    assert before['event_evidence']['event_rows_sha256']!=after['event_evidence']['event_rows_sha256']
    a=semantic_event_view(before,teams=['BUF','MIA']);b=semantic_event_view(after,teams=['MIA','BUF'])
    assert a['semantic_measurements_sha256']==b['semantic_measurements_sha256']
    assert a['team_rows']==b['team_rows'] and a['actor_rows']==b['actor_rows']
    assert a['quality']['identity_review_requests']==b['quality']['identity_review_requests']


def scalar_fixture(service,tmp_path):
    from backend.app.product_services.opportunity_source_capture import freeze_event_artifact,freeze_scalar_artifact
    snapshot=capture(service).snapshot;parent=freeze_event_artifact(derive(snapshot),snapshot,directory=tmp_path/'parents')
    ref=freeze_scalar_artifact(parent,snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=1),teams=['BUF'],actor_ids=[CANONICAL],
        directory=tmp_path/'views',parent_directory=tmp_path/'parents',producer_clock=lambda:NOW+timedelta(minutes=2))
    return snapshot,parent,ref


def test_scalar_serving_real_source_and_parent_byte_checks_without_full_inflation(service,tmp_path,monkeypatch):
    import gzip
    from backend.app.product_services.opportunity_source_capture import load_scalar_artifact
    snapshot,parent,ref=scalar_fixture(service,tmp_path)
    def no_inflate(*args,**kwargs):raise AssertionError('Serving must not inflate full parent')
    monkeypatch.setattr(gzip,'GzipFile',no_inflate)
    view=load_scalar_artifact(ref,snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=3),directory=tmp_path/'views',parent_directory=tmp_path/'parents')
    assert view['team_rows'][0]['counts']['rush_attempts']==1
    assert ref['selected_semantic_measurements_sha256']==view['semantic_measurements_sha256']
    assert ref['parent_global_semantic_measurements_sha256']==parent['semantic_measurements_sha256']
    assert ref['selected_semantic_measurements_sha256']!=ref['parent_global_semantic_measurements_sha256']


def test_scalar_publication_is_immutable_and_clock_bound_not_backdated(service,tmp_path):
    from backend.app.product_services.opportunity_source_capture import freeze_scalar_artifact,load_scalar_artifact
    snapshot,parent,ref=scalar_fixture(service,tmp_path)
    repeated=freeze_scalar_artifact(parent,snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=1),teams=['BUF'],actor_ids=[CANONICAL],
        directory=tmp_path/'views',parent_directory=tmp_path/'parents',producer_clock=lambda:NOW+timedelta(minutes=2))
    assert repeated==ref
    with pytest.raises(ValueError,match='unavailable'):load_scalar_artifact(ref,snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=1),directory=tmp_path/'views',parent_directory=tmp_path/'parents')
    with pytest.raises(ValueError,match='cannot precede'):freeze_scalar_artifact(parent,snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=1),
        directory=tmp_path/'views',parent_directory=tmp_path/'parents',producer_clock=lambda:NOW)


@pytest.mark.parametrize('field',['teams','actor_ids','parent_global_semantic_measurements_sha256','selected_semantic_measurements_sha256','parent_artifact_sha256','published_at'])
def test_scalar_serving_ref_fields_cannot_change_contents(service,tmp_path,field):
    from backend.app.product_services.opportunity_source_capture import load_scalar_artifact
    snapshot,parent,ref=scalar_fixture(service,tmp_path)
    changed=dict(ref);changed[field]=[] if field in {'teams','actor_ids'} else 'changed'
    with pytest.raises(ValueError,match='reference differs'):load_scalar_artifact(changed,snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=3),directory=tmp_path/'views',parent_directory=tmp_path/'parents')


def test_scalar_serving_tamper_source_and_parent_fail_without_inflation(service,tmp_path):
    from backend.app.product_services.opportunity_source_capture import load_scalar_artifact
    snapshot,parent,ref=scalar_fixture(service,tmp_path)
    parent_path=Path(parent['path']);original=parent_path.read_bytes()
    # Deliberate corruption of a newly-created isolated test artifact only.
    parent_path.chmod(0o600);parent_path.write_bytes(original[:-1]+bytes([original[-1]^1]))
    with pytest.raises(ValueError,match='parent compressed byte hash'):load_scalar_artifact(ref,snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=3),directory=tmp_path/'views',parent_directory=tmp_path/'parents')
    snapshot.content_sha256='0'*64
    with pytest.raises(SnapshotIntegrityError):load_scalar_artifact(ref,snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=3),directory=tmp_path/'views',parent_directory=tmp_path/'parents')


def test_scalar_serving_size_and_path_bounds(service,tmp_path):
    from backend.app.product_services.opportunity_source_capture import freeze_scalar_artifact,load_scalar_artifact
    snapshot,parent,ref=scalar_fixture(service,tmp_path)
    with pytest.raises(ValueError,match='byte bound'):load_scalar_artifact(ref,snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=3),directory=tmp_path/'views',parent_directory=tmp_path/'parents',max_view_bytes=1)
    with pytest.raises(ValueError,match='managed root'):load_scalar_artifact(dict(ref,path='/private/tmp/other'),snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=3),directory=tmp_path/'views',parent_directory=tmp_path/'parents')
    with pytest.raises(ValueError,match='byte bound'):freeze_scalar_artifact(parent,snapshot,before_period=202603,cutoff=NOW+timedelta(minutes=1),directory=tmp_path/'views',parent_directory=tmp_path/'parents',max_view_bytes=1,producer_clock=lambda:NOW+timedelta(minutes=2))


@pytest.mark.parametrize('changes',[dict(game_id='malformed'),dict(game_id='2026_03_BUF_MIA'),dict(game_id='2026_04_BUF_MIA'),
    dict(game_id='2027_01_BUF_MIA'),dict(season=2025),dict(week=2),dict(team='GB')])
def test_optional_official_reconciliation_cannot_include_wrong_or_future_native_period(service,changes):
    component=dict(game_id='2026_01_BUF_MIA',season_type='REG',team='BUF',source_player_id=NATIVE,rush_attempts=1,source_id='official',imported_at=NOW.isoformat())
    component.update(changes)
    with pytest.raises(ValueError,match='Official reconciliation'):derive(capture(service).snapshot,official_components=[component])


def test_optional_valid_prior_unmatched_component_remains_unverified_not_zero(service):
    component=dict(game_id='2026_02_SF_WAS',season_type='REG',team='SF',source_player_id=NATIVE,rush_attempts=0,source_id='official',imported_at=NOW.isoformat())
    receipt=derive(capture(service).snapshot,official_components=[component])
    check=receipt['event_evidence']['official_reconciliation'][0]
    assert check['derived'] is None and check['status']=='unverified_or_mismatch'


def test_optional_official_reconciliation_requires_explicit_regular_season(service):
    component=dict(game_id='2026_01_BUF_MIA',team='BUF',source_player_id=NATIVE,rush_attempts=1,source_id='official',imported_at=NOW.isoformat())
    with pytest.raises(ValueError,match='prior regular-season scope'):
        derive(capture(service).snapshot,official_components=[component])
