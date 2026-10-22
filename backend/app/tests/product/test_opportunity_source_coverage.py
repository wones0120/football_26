from copy import deepcopy
import pytest
from backend.app.tests.product.test_opportunity_events import play,build,CUTOFF
from backend.app.product_services.player_opportunity_components import build_player_opportunity_components
from backend.app.product_services.opportunity_source_coverage import build_opportunity_source_coverage


def source():
    events=[play(1,game_id='2025_08_SF_WAS',posteam='SF'),play(2,game_id='2025_08_SF_WAS',posteam='SF',play_type='run',pass_attempt=0,rush_attempt=1,rusher_player_id='r')]
    result=build_player_opportunity_components({'event_evidence':build(events)},before_period=202509,cutoff=CUTOFF)
    result.update(pregame_serving_eligible=False,evidence_use='postlock_descriptive_not_pregame_or_serving');return result


def run(s=None):return build_opportunity_source_coverage(s or source(),before_period=202509)


def test_conserved_known_counts_and_full_actor_coverage():
    x=run();m=x['game_rows'][0]['metrics']
    for ch in ('pass_attempts','rush_attempts','targets'):
        assert m[ch]['X08_M01']['exact_full_source_native_actor_count']==1
        assert m[ch]['X08_M01']['exact_canonical_actor_fraction']==1
        assert m[ch]['X08_M02']['exact_unattributed_opportunities']==0
        assert m[ch]['X08_M02']['known_canonical_attached_opportunities']==1
    assert x['forecast'] is None


def test_unmapped_native_counts_retained_and_canonical_mass_not_donated():
    s=source()
    for r in s['actor_game_rows']:r['player_master_id']=None
    m=run(s)['game_rows'][0]['metrics']['targets']
    assert m['X08_M01']['exact_canonical_actor_fraction']==0
    assert m['X08_M02']['known_unattached_canonical_opportunity_lower_bound']==1
    assert m['X08_M02']['exact_unattributed_opportunities']==0 and not m['X08_M02']['residual_is_allocated']


def test_unknown_native_mass_masks_actor_denominator_not_filled():
    s=source();s['actor_game_rows']=[r for r in s['actor_game_rows'] if r['source_player_id']!='r']
    m=run(s)['game_rows'][0]['metrics']['rush_attempts']
    assert m['X08_M01']['exact_full_source_native_actor_count'] is None
    assert m['X08_M01']['exact_canonical_actor_fraction'] is None
    assert m['X08_M02']['exact_unattributed_opportunities']==1


def test_unknown_eligibility_and_empty_channel_denominators_not_zero_fractions():
    s=source();team=s['team_denominators'][0]['official'];team['unknown_eligibility_events']['targets']=1;team['counts']['targets']=None
    m=run(s)['game_rows'][0]['metrics']['targets']
    assert m['X08_M01']['exact_canonical_attached_opportunity_fraction'] is None
    assert m['X08_M02']['exact_unattributed_opportunities'] is None
    assert m['X08_M02']['unknown_extra_opportunity_quantity'] is None
    s=source();s['actor_game_rows']=[r for r in s['actor_game_rows'] if r['source_player_id']!='r'];team=s['team_denominators'][0]['official'];team['counts']['rush_attempts']=team['counted_lower_bound']['rush_attempts']=0
    assert run(s)['game_rows'][0]['metrics']['rush_attempts']['X08_M01']['exact_canonical_actor_fraction'] is None


@pytest.mark.parametrize('kind',['duplicate','exceeds','canonical','partition','future'])
def test_native_budget_identity_and_count_guards(kind):
    s=source()
    if kind=='duplicate':s['actor_game_rows'].append(deepcopy(s['actor_game_rows'][0]))
    if kind=='exceeds':
        r=next(r for r in s['actor_game_rows'] if 'targets' in r['metrics']);m=r['metrics']['targets'];m.update(observed_outcome_sum=2,known_outcome_events=2,eligible_events=2)
    if kind=='canonical':s['actor_game_rows'][0]['player_master_id']='name'
    if kind=='partition':s['team_denominators'][0]['official']['counts']['targets']=0
    if kind=='future':s['team_denominators'][0]['game_id']='2025_09_SF_WAS'
    with pytest.raises(ValueError):run(s)


def test_source_clocks_not_numerical_semantics_and_row_order_stable():
    s=source();sha=run(s)['semantic_sha256'];s['actor_game_rows'].reverse();s['provenance']['actual_read_at']='later'
    assert run(s)['semantic_sha256']==sha


def test_reviewed_component_reader_preserves_original_vs_actual_clocks(tmp_path,monkeypatch):
    import hashlib,json
    from datetime import datetime,UTC
    from backend.app.tests.test_source_capture import _session
    from backend.app.services.source_capture import SourceCaptureService
    from backend.app.product_services.opportunity_source_coverage import load_reviewed_player_component,require_feature_use
    monkeypatch.chdir(tmp_path);db=_session()
    try:
        original=datetime(2026,10,19,19,tzinfo=UTC);lock=datetime(2026,10,20,0,15,tzinfo=UTC)
        raw=tmp_path/'raw.csv';raw.write_text('game_id,play_id\n2025_08_SF_WAS,1\n')
        snap=SourceCaptureService(db,snapshot_root=tmp_path/'sources',clock=lambda:original).capture_file(raw,source_system='nflreadpy',dataset='play_by_play',season=2026,week=6,slate='test',source_uri='https://example.test/pbp',source_license='test',slate_lock_at=lock,observation_basis='capture_clock',media_type='text/csv',row_count=1).snapshot
        parentraw=b'frozen-compressed-parent';psha=hashlib.sha256(parentraw).hexdigest();parent=tmp_path/'artifacts/opportunity_events'/(psha+'.json.gz');parent.parent.mkdir(parents=True);parent.write_bytes(parentraw)
        v=source();v['provenance']=dict(source=dict(snapshot_id=str(snap.snapshot_id),content_sha256=snap.content_sha256),event_receipt_sha256='event',retrospective_read=dict(original_evidence_boundary_at='2026-10-19T20:00:00Z',source_lock_at=lock.isoformat(),actual_read_at='2026-10-20T01:00:00Z',actual_derived_at='2026-10-20T01:01:00Z',parent_artifact_ref=dict(path=str(parent),artifact_sha256=psha,compressed_bytes=len(parentraw),source_snapshot_id=str(snap.snapshot_id),source_sha256=snap.content_sha256,event_receipt_sha256='event')))
        def save(v):
            b=json.dumps(v).encode();sha=hashlib.sha256(b).hexdigest();p=tmp_path/'artifacts/player_opportunity_components'/(sha+'.json');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b);return dict(path=str(p),sha256=sha,bytes=len(b))
        ref=save(v);assert load_reviewed_player_component(ref,snap,cutoff='2026-10-20T02:00:00Z')==v
        with pytest.raises(ValueError,match='clocks'):load_reviewed_player_component(ref,snap,cutoff='2026-10-20T01:00:00Z')
        v['provenance']['source']['snapshot_id']='wrong'
        with pytest.raises(ValueError,match='pairing'):load_reviewed_player_component(save(v),snap,cutoff='2026-10-20T02:00:00Z')
        assert require_feature_use(run(),purpose='offline_descriptive')['forecast'] is None
        with pytest.raises(ValueError):require_feature_use(run(),purpose='model')
    finally:db.close()


def test_invalid_boundary_and_current_source_not_implicitly_serving():
    s=source()
    with pytest.raises(ValueError):build_opportunity_source_coverage(s,before_period=True)
    s['pregame_serving_eligible']=True
    with pytest.raises(ValueError):run(s)
