from copy import deepcopy
import pytest
from backend.app.product_services.recent_snap_features import build_recent_snap_features

PID='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';ALIASES=[dict(source_system='pfr',source_key='Native00',player_master_id=PID,created_at='2026-10-19T00:00:00Z')]
def row(week,native='Native00',**changes):
    r=dict(source_row_id=f'{native}:{week}',ingest_run_id='original-ingest',created_at='2026-10-19T20:00:00Z',raw=dict(season=2026,week=week,game_type='REG',game_id=f'2026_{week:02}_WAS_SF',team='WAS',pfr_player_id=native,offense_snaps=week*10,offense_pct=week/10,defense_snaps=0,defense_pct=0,st_snaps=None,st_pct=None))
    r['raw'].update(changes);return r

def build(rows,aliases=ALIASES,**kw):return build_recent_snap_features(rows,aliases,before_period=202606,cutoff='2026-10-20T03:00:00Z',**kw)

def test_count_and_share_trend_same_observed_team_logs_separate_channels():
    v=build([row(i) for i in [1,2,3,5]])['actor_trends'][0]
    assert v['channels']['offense']['snaps']['latest']==50
    assert v['channels']['offense']['snaps']['prior_mean']==20
    assert v['channels']['offense']['snaps']['delta']==30
    assert v['channels']['defense']['snaps']['delta']==0
    assert v['channels']['st']['snaps']['delta'] is None
    assert v['prior_observed_team_game_ids']==['2026_01_WAS_SF','2026_02_WAS_SF','2026_03_WAS_SF']

def test_missing_latest_actor_not_zero_or_last_positive_fallback():
    rows=[row(i) for i in [1,2,3,4]]+[row(i,'Other00') for i in [1,2,3]]
    v=next(r for r in build(rows)['actor_trends'] if r['pfr_player_id']=='Other00')
    assert v['source_row_present_in_latest'] is False
    assert v['channels']['offense']['snaps']['latest'] is None and v['channels']['offense']['snaps']['delta'] is None
    assert v['channels']['offense']['snaps']['prior_mean']==20

def test_missing_prior_row_or_field_stays_unknown():
    rows=[row(i) for i in [1,2,3,4]]+[row(i,'Other00') for i in [1,3,4]]
    v=next(r for r in build(rows)['actor_trends'] if r['pfr_player_id']=='Other00')
    assert v['channels']['offense']['snaps']['prior_mean'] is None
    rows=[row(i,offense_snaps=None if i==2 else 10) for i in [1,2,3,4]]
    assert build(rows)['actor_trends'][0]['channels']['offense']['snaps']['delta'] is None
    assert build(rows)['actor_trends'][0]['channels']['offense']['share']['delta'] is not None

def test_no_cross_season_or_team_donation():
    rows=[row(i) for i in [1,2,3]]+[row(4,team='SF')]
    v=next(r for r in build(rows)['actor_trends'] if r['team']=='SF')
    assert v['channels']['offense']['snaps']['prior_mean'] is None
    r=row(1,season=2025,game_id='2025_01_WAS_SF')
    assert not build([r])['actor_trends']

def test_native_alias_future_and_identity_collision_quarantine_whole_batch():
    a=ALIASES+[{**ALIASES[0],'source_key':'Other00'}]
    v=build([row(1),row(2),row(1,'Other00')],a)
    assert all(r['player_master_id'] is None for r in v['actor_trends'])
    assert len(v['canonical_identity_collisions'])==1
    a=deepcopy(ALIASES);a[0]['created_at']='2026-10-21T00:00:00Z'
    assert build([row(1)],a)['actor_trends'][0]['player_master_id'] is None

def test_persisted_collision_proof_blocks_alias_even_without_current_cooccurrence():
    b=dict(source_system='pfr',status='open',reason_code='canonical_native_game_collision',source_player_key='Native00',first_seen_at='2026-10-20T02:00:00Z')
    assert build([row(1)],identity_blocks=[b])['actor_trends'][0]['player_master_id'] is None
    b['first_seen_at']='2026-10-21T00:00:00Z'
    with pytest.raises(ValueError,match='proof'):build([row(1)],identity_blocks=[b])

def test_source_clock_and_duplicate_guard():
    r=row(1);r['created_at']='2026-10-21T00:00:00Z'
    with pytest.raises(ValueError,match='cutoff'):build([r])
    with pytest.raises(ValueError,match='Duplicate'):build([row(1),row(1)])

def test_zero_count_positive_fraction_contradiction_not_fake_known_trend():
    v=build([row(i,offense_snaps=0,offense_pct=.1) for i in [1,2,3,4]])['actor_trends'][0]
    assert v['channels']['offense']['snaps']['delta'] is None
    assert v['channels']['offense']['share']['delta'] is None

def test_unknown_phase_can_hide_latest_game_so_masks_team_trend():
    rows=[row(i) for i in [1,2,3,4]]+[row(5,game_type=None)]
    v=build(rows)['actor_trends'][0]
    assert v['team_game_scope_unknown'] and v['channels']['offense']['snaps']['delta'] is None

def test_malformed_native_retains_team_log_and_queue_without_name_join():
    v=build([row(1,pfr_player_id=None)])
    assert v['team_observed_game_ids']['WAS']==['2026_01_WAS_SF'] and v['identity_review_requests']
    assert not v['actor_trends']

def test_recapture_and_input_order_do_not_change_numeric_semantics():
    rows=[row(i) for i in [1,2,3,4]];other=deepcopy(rows)
    for r in other:r['created_at']='2026-10-19T21:00:00Z';r['ingest_run_id']='new-capture';r['source_row_id']='new:'+r['source_row_id']
    assert build(rows)['semantic_sha256']==build(list(reversed(other)))['semantic_sha256']

def test_frozen_actual_revision_origin_and_byte_clock_contract(tmp_path):
    import json
    from datetime import datetime,UTC
    from backend.app.tests.test_source_capture import _session
    from backend.app.services.source_capture import SourceCaptureService,SnapshotIntegrityError
    from backend.app.product_services.recent_snap_features import load_frozen_snap_revision
    now=datetime(2026,10,20,3,tzinfo=UTC);s=_session()
    try:
        value=dict(contract='retained_snap_count_revision_v1',season=2026,rows=[row(i) for i in [1,2,3,4]],aliases=ALIASES,identity_blocks=[],original_ingest_runs=[dict(ingest_run_id='original-ingest',status='completed',started_at='2026-10-19T19:00:00Z',completed_at='2026-10-19T21:00:00Z')],actual_extract_started_at='2026-10-20T02:00:00Z',actual_extract_completed_at='2026-10-20T02:01:00Z',original_provider_snapshot_claim=False,source_origin='Current retained DB revision, not original provider snapshot')
        path=tmp_path/'rows.json';path.write_text(json.dumps(value));snapshot=SourceCaptureService(s,snapshot_root=tmp_path/'sources',clock=lambda:now).capture_file(path,source_system='retained_db',dataset='snap_counts_revision',season=2026,week=6,slate='features',source_uri='retained-db://public.raw_nfl_snap_count/season=2026',source_license='test',slate_lock_at=datetime(2026,10,20,0,15,tzinfo=UTC),observation_basis='capture_clock',media_type='application/json',row_count=4).snapshot
        result=load_frozen_snap_revision(snapshot,cutoff=now)
        assert result['provenance']['source_revision_not_original_snapshot'] and result['pregame_serving_eligible'] is False
        assert result['actor_trends'][0]['channels']['offense']['snaps']['delta']==20
        with pytest.raises(ValueError,match='unavailable'):load_frozen_snap_revision(snapshot,cutoff='2026-10-20T02:59:00Z')
        snapshot.content_sha256='0'*64
        with pytest.raises(SnapshotIntegrityError):load_frozen_snap_revision(snapshot,cutoff=now)
    finally:s.close()

def test_native_cannot_participate_for_both_teams_in_same_game():
    with pytest.raises(ValueError,match='Duplicate native'):build([row(1),row(1,team='SF')])

def test_identical_distinct_ingest_revisions_collapse_only_values_keep_all_receipts():
    rows=[row(i) for i in [1,2,3,4]]
    equivalent=deepcopy(rows[0]);equivalent.update(source_row_id='later-row',ingest_run_id='later-ingest',created_at='2026-10-19T21:00:00Z')
    v=build(rows+[equivalent])
    assert v['semantic_sha256']==build(rows)['semantic_sha256']
    proofs=v['provenance']['equivalent_revision_groups']
    assert len(proofs)==1 and len(proofs[0]['source_records'])==2
    bad=deepcopy(equivalent);bad['raw']['offense_snaps']=11
    with pytest.raises(ValueError,match='Duplicate native'):build(rows+[bad])
    bad=deepcopy(equivalent);bad['ingest_run_id']='original-ingest'
    with pytest.raises(ValueError,match='Duplicate native'):build(rows+[bad])

def test_identity_requests_use_native_or_frozen_row_keys_without_overwriting_decisions():
    from backend.app.product_services.recent_snap_features import persist_snap_identity_requests
    v=build([row(1,pfr_player_id=None),row(2,'Unmapped00')]);v['provenance'].update(source_snapshot_id='snapshot',source_sha256='a'*64)
    calls=[]
    class C:
        def execute(self,sql,params):calls.append((str(sql),params))
    q=persist_snap_identity_requests(C(),v)
    assert q['requests']==2 and not q['aliases_changed'] and not q['resolved_records_reopened']
    assert {p['key'].split(':')[0] for _,p in calls}=={'pfr-player','snap-row'}
    assert all('DO NOTHING' in sql and 'UPDATE' not in sql for sql,_ in calls)

def test_existing_durable_identity_block_referenced_not_reopened():
    from backend.app.product_services.recent_snap_features import persist_snap_identity_requests
    b=dict(identity_quarantine_id='already-open',source_system='pfr',status='open',reason_code='canonical_native_game_collision',source_player_key='Native00',first_seen_at='2026-10-20T02:00:00Z')
    v=build([row(1)],identity_blocks=[b]);v['provenance'].update(source_snapshot_id='snapshot',source_sha256='a'*64)
    class C:
        def execute(self,sql,params):raise AssertionError('No repeated conflict write needed')
    q=persist_snap_identity_requests(C(),v)
    assert q['records']==[dict(identity_quarantine_id='already-open',source_player_key='Native00',existing_frozen_conflict=True)]

def test_target_season_must_match_real_snap_source_era():
    with pytest.raises(ValueError,match='REG target'):build_recent_snap_features([],ALIASES,before_period=101,cutoff='2026-10-20T03:00:00Z')
