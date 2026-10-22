from copy import deepcopy
import pytest
from backend.app.product_services.offensive_environment_catalog import build_offensive_environment_catalog

def row(**kw):
    r=dict(game_id='2026_05_WAS_SF',season=2026,week=5,team='WAS',known_offensive_snaps=10,unknown_snap_eligibility=0,
        offensive_play_volume=dict(known_offensive_snaps=10,unknown_snap_eligibility=0,observed_game_logs=1),
        metrics={'G01-M06':dict(observed_outcome_sum=2,eligible_events=10,known_outcome_events=10,unknown_outcome_events=0,unknown_eligibility_events=0)})
    r.update(kw);return r

def context(rows):return dict(version='environment_context_evidence_v1',before_period=202606,forecast=None,semantic_measurements_sha256='reviewed',game_rows=rows)
def build(rows):return build_offensive_environment_catalog(context(rows),before_period=202606)

def test_physical_volume_and_no_huddle_pooled_denominator():
    r2=row(game_id='2026_04_WAS_DAL',week=4,known_offensive_snaps=20,offensive_play_volume=dict(known_offensive_snaps=20,unknown_snap_eligibility=0,observed_game_logs=1),metrics={'G01-M06':dict(observed_outcome_sum=10,eligible_events=20,known_outcome_events=20,unknown_outcome_events=0,unknown_eligibility_events=0)})
    v=build([row(),r2]);w=v['team_windows'][0]
    assert w['metrics']['G01-M01']['value']==15
    assert w['metrics']['G01-M06']['value']==12/30
    assert len(w['observed_game_ids'])==2

def test_unknown_eligibility_not_false_zero_or_exact_known_lower_bound():
    r=row(unknown_snap_eligibility=1);r['offensive_play_volume']['unknown_snap_eligibility']=1;r['metrics']['G01-M06']['unknown_eligibility_events']=1
    v=build([r]);m=v['game_rows'][0]['metrics']
    assert m['G01-M01']['value'] is None and m['G01-M01']['known_lower_bound']==10
    assert m['G01-M06']['value'] is None and v['team_windows'][0]['metrics']['G01-M06']['value'] is None

def test_missing_flag_keeps_physical_count_but_unknown_rate():
    r=row();r['metrics']['G01-M06'].update(known_outcome_events=9,unknown_outcome_events=1)
    m=build([r])['game_rows'][0]['metrics'];assert m['G01-M01']['value']==10 and m['G01-M06']['value'] is None

@pytest.mark.parametrize('change',[dict(week=6),dict(team='DAL'),dict(game_id='2026_04_WAS_SF')])
def test_native_scope_rejects(change):
    with pytest.raises(ValueError):build([row(**change)])

def test_duplicate_and_physical_denominator_guard():
    with pytest.raises(ValueError,match='Duplicate'):build([row(),row()])
    r=row();r['metrics']['G01-M06']['eligible_events']=11
    with pytest.raises(ValueError,match='denominator'):build([r])

def test_source_order_and_capture_provenance_does_not_change_measurements():
    r2=row(game_id='2026_04_WAS_DAL',week=4)
    c=context([row(),r2]);d=deepcopy(c);d['provenance']={'captured_at':'new'};d['game_rows'].reverse()
    assert build_offensive_environment_catalog(c,before_period=202606)['semantic_sha256']==build_offensive_environment_catalog(d,before_period=202606)['semantic_sha256']

def test_prior_season_not_current_season_window():
    r=row(game_id='2025_05_WAS_SF',season=2025)
    v=build([r,row()]);assert len(v['game_rows'])==2 and len(v['team_windows'][0]['observed_game_ids'])==1

def test_actual_source_parent_context_verification_and_clocks(tmp_path):
    from datetime import datetime,UTC
    from pathlib import Path
    import json,hashlib
    from backend.app.tests.test_source_capture import _session
    from backend.app.services.source_capture import SourceCaptureService,SnapshotIntegrityError
    from backend.app.product_services.offensive_environment_catalog import read_reviewed_environment_catalog
    from backend.app.product_services import environment_context_evidence as producer,defense_context_evidence as helper
    original=datetime(2026,10,19,19,tzinfo=UTC);now=datetime(2026,10,20,3,tzinfo=UTC);s=_session()
    source=tmp_path/'source.csv';source.write_text('game_id,play_id\n2026_05_WAS_SF,1\n')
    try:
        cap=SourceCaptureService(s,snapshot_root=tmp_path/'snapshots',clock=lambda:original).capture_file(source,source_system='nflreadpy',dataset='play_by_play',season=2026,week=6,slate='features',source_license='test',source_uri='nflreadpy://pbp/2026',slate_lock_at=datetime(2026,10,20,0,15,tzinfo=UTC),observation_basis='capture_clock',media_type='text/csv',row_count=1)
        snapshot=cap.snapshot;directory=tmp_path/'contexts';directory.mkdir();parent_directory=tmp_path/'parents';parent_directory.mkdir()
        raw=b'original frozen compressed evidence';sha=hashlib.sha256(raw).hexdigest();p=parent_directory/(sha+'.json.gz');p.write_bytes(raw)
        parent=dict(contract_id='opportunity_event_artifact_v1',path=str(p.resolve()),artifact_sha256=sha,compressed_bytes=len(raw),before_period=202606,source_snapshot_id=str(snapshot.snapshot_id),source_sha256=snapshot.content_sha256,event_receipt_sha256='event',decision_cutoff_at='2026-10-19T19:30:00Z')
        v=context([row()]);v['provenance']=dict(source=dict(snapshot_id=str(snapshot.snapshot_id),content_sha256=snapshot.content_sha256),event_receipt_sha256='event',decision_cutoff_at='2026-10-19T20:00:00Z',artifact_publication=dict(parent_artifact_ref=parent,decision_cutoff_at='2026-10-19T20:00:00Z',published_at='2026-10-19T20:01:00Z'),producer_code_sha256=hashlib.sha256(Path(producer.__file__).read_bytes()).hexdigest(),numerical_helper_code_sha256=hashlib.sha256(Path(helper.__file__).read_bytes()).hexdigest(),metric_lineage={m:dict(before_period=202606,source_snapshot_id=str(snapshot.snapshot_id),event_receipt_sha256='event') for m in ['G01-M01','G01-M06']})
        def save(value):
            raw=json.dumps(value,sort_keys=True).encode();sha=hashlib.sha256(raw).hexdigest();p=directory/(sha+'.json');p.write_bytes(raw);return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
        ref=save(v);kwargs=dict(snapshot=snapshot,actual_read_at=now,context_directory=directory,parent_directory=parent_directory)
        result=read_reviewed_environment_catalog(ref,**kwargs)
        assert result['game_rows'][0]['metrics']['G01-M01']['value']==10 and not result['pregame_serving_eligible']
        assert result['provenance']['parent_inflated'] is False
        bad=deepcopy(v);bad['provenance']['artifact_publication']['published_at']='2026-10-21T00:00:00Z'
        with pytest.raises(ValueError,match='clock'):read_reviewed_environment_catalog(save(bad),**kwargs)
        for field in ('producer_code_sha256','numerical_helper_code_sha256'):
            bad=deepcopy(v);bad['provenance'][field]='0'*64
            with pytest.raises(ValueError,match='producer'):read_reviewed_environment_catalog(save(bad),**kwargs)
        bad=deepcopy(v);bad['provenance']['metric_lineage']['G01-M06']['before_period']=202605
        with pytest.raises(ValueError,match='lineage'):read_reviewed_environment_catalog(save(bad),**kwargs)
        bad=deepcopy(v);bad['provenance']['artifact_publication']['parent_artifact_ref']['artifact_sha256']='../elsewhere'
        with pytest.raises(ValueError,match='identity'):read_reviewed_environment_catalog(save(bad),**kwargs)
        p=parent_directory/(parent['artifact_sha256']+'.json.gz');p.write_bytes(b'bad')
        with pytest.raises(ValueError,match='Parent'):read_reviewed_environment_catalog(ref,**kwargs)
        p.write_bytes(raw);snapshot.content_sha256='0'*64
        with pytest.raises(SnapshotIntegrityError):read_reviewed_environment_catalog(ref,**kwargs)
    finally:s.close()

def test_zero_denominator_empty_helper_sample_retains_undefined_rate():
    r=row(known_offensive_snaps=0,offensive_play_volume=dict(known_offensive_snaps=0,unknown_snap_eligibility=0,observed_game_logs=1),metrics={'G01-M06':dict(observed_outcome_sum=None,eligible_events=0,known_outcome_events=0,unknown_outcome_events=0,unknown_eligibility_events=0)})
    v=build([r]);m=v['game_rows'][0]['metrics']
    assert m['G01-M01']['value']==0 and m['G01-M06']['value'] is None
    assert m['G01-M06']['numerator'] is None and m['G01-M06']['known_numerator_lower_bound']==0
    assert v['team_windows'][0]['metrics']['G01-M06']['numerator'] is None

def test_all_missing_flags_do_not_invent_certified_zero_numerator():
    r=row();r['metrics']['G01-M06'].update(observed_outcome_sum=None,known_outcome_events=0,unknown_outcome_events=10)
    v=build([r]);m=v['game_rows'][0]['metrics']['G01-M06']
    assert m['value'] is None and m['numerator'] is None and m['numerator_basis']=='empty_known_sample_lower_bound_only'
    assert v['team_windows'][0]['metrics']['G01-M06']['value'] is None

def test_mixed_known_and_empty_pooled_samples_preserve_unknown_flags():
    r=row(game_id='2026_04_WAS_DAL',week=4);r['metrics']['G01-M06'].update(observed_outcome_sum=None,known_outcome_events=0,unknown_outcome_events=10)
    m=build([row(),r])['team_windows'][0]['metrics']['G01-M06']
    assert m['value'] is None and m['numerator']==2 and m['known_denominator']==20 and m['unknown_outcome']==10
