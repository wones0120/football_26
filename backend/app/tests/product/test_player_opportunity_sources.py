from copy import deepcopy
import json,hashlib
import pytest
from backend.app.product_services.player_opportunity_sources import load_component_sources


def block(year=2025):
    return dict(version='player_opportunity_components_v1',forecast=None,before_period=year*100+19,
        definitions={'targets':'official attributed targets'},semantic_measurements_sha256='semantic',pregame_serving_eligible=False,
        evidence_use='revised_retrospective_training_not_original_pregame',
        provenance={'actual_derived_at':'2026-10-20T01:01:00+00:00','actual_publication_at':'2026-10-20T01:02:00+00:00'},
        actor_game_rows=[dict(game_id=f'{year}_01_WAS_SF',team='SF',source_player_id='00-1234567',player_master_id=None,metrics={})],
        team_denominators=[dict(game_id=f'{year}_01_WAS_SF',team='SF')],identity_review_requests=[{'source_player_id':'00-1234567'}],unattributed_events=[{'source':'unknown'}])


def save(root,b):
    directory=root/'player_opportunity_history';directory.mkdir(exist_ok=True)
    raw=json.dumps(b).encode();sha=hashlib.sha256(raw).hexdigest();path=directory/(sha+'.json');path.write_bytes(raw)
    return dict(path=str(path),sha256=sha,bytes=len(raw),semantic_measurements_sha256=b['semantic_measurements_sha256'])


def test_multiple_original_contexts_retained_unknown_identity_not_dropped(tmp_path):
    refs=[save(tmp_path,block(2024)),save(tmp_path,block(2025))]
    r=load_component_sources(refs,cutoff='2026-10-20T01:03:00+00:00',root=tmp_path)
    assert len(r['actor_game_rows'])==2 and len(r['team_denominators'])==2
    assert len(r['identity_review_requests'])==2 and len(r['unattributed_events'])==2
    assert r['pregame_serving_eligible'] is False
    assert len(r['provenance']['source_contexts'])==2


@pytest.mark.parametrize('kind',['bytes','future_publication','path','overlap','definitions'])
def test_invalid_sources_do_not_silently_revise_history(tmp_path,kind):
    b=block();r=save(tmp_path,b);refs=[r]
    if kind=='bytes':open(r['path'],'a').write('x')
    if kind=='future_publication':
        b['provenance']['actual_publication_at']='2027-01-01T00:00:00+00:00';refs=[save(tmp_path,b)]
    if kind=='path':r['path']=str(tmp_path/'wrong'/r['sha256'])
    if kind=='overlap':
        b['semantic_measurements_sha256']='revision';refs.append(save(tmp_path,b))
    if kind=='definitions':
        b=block(2024);b['definitions']={'targets':'routes'};refs.append(save(tmp_path,b))
    with pytest.raises(ValueError):load_component_sources(refs,cutoff='2026-10-20T01:03:00+00:00',root=tmp_path)


def test_actual_shaped_artifact_publication_clock_is_not_ignored(tmp_path):
    b=block();b['provenance'].pop('actual_publication_at')
    b['provenance']['artifact_publication']={'actual_publication_at':'2026-10-20T01:04:00+00:00'}
    ref=save(tmp_path,b)
    with pytest.raises(ValueError,match='unavailable'):load_component_sources([ref],cutoff='2026-10-20T01:03:00+00:00',root=tmp_path)
    result=load_component_sources([ref],cutoff='2026-10-20T01:05:00+00:00',root=tmp_path)
    assert result['provenance']['source_contexts'][0]['actual_available_at']=='2026-10-20T01:04:00+00:00'


@pytest.mark.parametrize('mutation',[None,'raw_hash','late_receipt','current_season','identity'])
def test_current_history_rechecks_raw_clocks_identity_and_preserves_historical_status(tmp_path,monkeypatch,mutation):
    from backend.app.product_services import player_opportunity_sources as source
    root=tmp_path/'artifacts';root.mkdir();monkeypatch.setattr(source,'ROOT',root)
    raw=tmp_path/'history.parquet';raw.write_bytes(b'verified source bytes')
    b=block(2026 if mutation=='current_season' else 2025)
    b['actor_game_rows'][0]['player_master_id']='canonical'
    manifest=dict(bytes=raw.stat().st_size,sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),received_at='2026-10-19T01:00:00+00:00')
    if mutation=='late_receipt':manifest['received_at']='2027-01-01T00:00:00+00:00'
    b['provenance'].update(original_source_descriptor=dict(path=str(raw),manifest=manifest),source=dict(content_sha256=manifest['sha256']))
    ref=save(root,b)
    if mutation=='raw_hash':raw.write_bytes(b'changed')
    current=block(2026);current['before_period']=202607
    ids={'00-1234567':'different' if mutation=='identity' else 'canonical'}
    if mutation:
        with pytest.raises(ValueError):source.current_history_components([ref],current,cutoff='2026-10-20T01:03:00+00:00',before_period=202607,canonical_ids=ids)
    else:
        out=source.current_history_components([ref],current,cutoff='2026-10-20T01:03:00+00:00',before_period=202607,canonical_ids=ids)
        assert out['pregame_serving_eligible'] is True
        assert out['current_consumer_contract']=='new_model_primary_v1'
        assert out['provenance']['original_historical_pregame_availability_proven'] is False
        assert out['provenance']['current_history_refs']==[ref]
        assert len(out['actor_game_rows'])==2
        assert b['pregame_serving_eligible'] is False
