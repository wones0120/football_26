"""API contracts use an isolated packet ledger, never the local football DB."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.main import app
from backend.app.product_schemas import OptimizerRunRequest
from backend.app.product_services import analyst_packets

PACKET_PATH = Path(__file__).resolve().parents[4] / 'research/pregame_ai_packet_20261013/packet.json'

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(analyst_packets, 'LEDGER', tmp_path)
    return TestClient(app)

def test_import_retry_read_and_no_filesystem_paths(client):
    packet = json.loads(PACKET_PATH.read_text())
    first = client.post('/api/optimizer/analyst-packets', json={'packet':packet})
    assert first.status_code == 200, first.text
    second = client.post('/api/optimizer/analyst-packets', json={'packet':packet})
    assert second.json() == first.json()
    result = first.json()
    assert 'path' not in result
    assert 'sources' not in result
    assert result['analyst_name'] == 'Wones Football Analyst'
    read = client.get('/api/optimizer/analyst-packets/' + result['analyst_packet_sha256'])
    assert read.status_code == 200
    assert read.json() == result

def test_bad_packet_and_unknown_hash(client):
    packet = json.loads(PACKET_PATH.read_text())
    packet['players'][0]['player_master_id'] = 'name-only'
    response = client.post('/api/optimizer/analyst-packets', json={'packet':packet})
    assert response.status_code == 422
    assert 'canonical' in response.json()['detail']
    assert client.get('/api/optimizer/analyst-packets/' + '0'*64).status_code == 422
    assert client.get('/api/optimizer/analyst-packets/not-a-hash').status_code == 422

@pytest.mark.parametrize('format,strategy', [('classic','classic_small_field_gpp'),('showdown','showdown_small_field_gpp')])
def test_packet_hash_carries_through_worker_params_only(format, strategy):
    request = OptimizerRunRequest(season=2026,week=6,slate='THURSDAY_NIGHT' if format == 'showdown' else 'SUNDAY_MAIN',strategy=strategy,contest_format=format,objective='gpp',analyst_packet_sha256='a'*64)
    serialized = request.model_dump()
    assert serialized['params']['analyst_packet_sha256'] == 'a'*64
    assert serialized['params']['analyst_candidates_per_thesis'] == 2
    assert 'analyst_packet_sha256' not in serialized # run_job receives existing public kwargs
    assert 'analyst_candidates_per_thesis' not in serialized
    baseline = OptimizerRunRequest(season=2026,week=6,slate='SUNDAY_MAIN',strategy=strategy,contest_format=format,objective='gpp')
    assert not any(key.startswith('analyst_') for key in baseline.params)

@pytest.mark.parametrize('params', [{'analyst_packet_sha256':'bad'}, {'analyst_packet_sha256':'A'*64}, {'analyst_candidates_per_thesis':2}, {'analyst_packet_sha256':'a'*64,'analyst_candidates_per_thesis':True}, {'analyst_packet_sha256':'a'*64,'analyst_candidates_per_thesis':11}])
def test_invalid_analyst_request_rejected(params):
    with pytest.raises(ValidationError):
        OptimizerRunRequest(season=2026,week=6,slate='SUNDAY_MAIN',strategy='classic_small_field_gpp',params=params)

@pytest.mark.parametrize('format,strategy', [('classic','classic_small_field_gpp'),('showdown','showdown_small_field_gpp')])
def test_queued_optimizer_preserves_analyst_params(client, monkeypatch, format, strategy):
    from datetime import datetime, UTC
    from backend.app.api import product_routes
    from backend.app.db import get_db_session
    from backend.app.product_services import slate_preparation
    captured = {}
    def enqueue(session, **kwargs):
        captured.update(kwargs)
        return object(), True
    monkeypatch.setattr(product_routes, 'enqueue_job', enqueue)
    monkeypatch.setattr(slate_preparation, 'validate_prepared_optimizer', lambda *args, **kwargs: {})
    now = datetime.now(UTC)
    monkeypatch.setattr(product_routes, 'job_response', lambda job: {
        'job_id':'queue-test','job_type':'optimizer','idempotency_key':'optimizer:test',
        'status':'queued','stage':'queued','progress_current':0,'progress_total':1,
        'progress_percent':0,'attempt_count':0,'max_attempts':1,'created_at':now,'updated_at':now})
    app.dependency_overrides[get_db_session] = lambda: object()
    try:
        response = client.post('/api/optimizer/jobs', json={'season':2026,'week':6,
            'slate':'THURSDAY_NIGHT' if format == 'showdown' else 'SUNDAY_MAIN',
            'strategy':strategy,'contest_format':format,'objective':'gpp',
            'analyst_packet_sha256':'a'*64,'analyst_candidates_per_thesis':3})
        assert response.status_code == 202, response.text
        payload = captured['request_payload']
        assert payload['params']['analyst_packet_sha256'] == 'a'*64
        assert payload['params']['analyst_candidates_per_thesis'] == 3
        assert 'analyst_packet_sha256' not in payload
    finally:
        app.dependency_overrides.pop(get_db_session, None)

def test_saved_results_expose_analyst_generation_diagnostics(client, monkeypatch):
    from types import SimpleNamespace
    from backend.app.product_dependencies import get_optimizer_service
    from backend.app.product_services import classic_game_environment
    report = {'status':'generated','packet_sha256':'a'*64,'generated_count':2,'selected_count':1,
        'captain_analysis':{'contract_id':'captain_analysis_v1','assessments':[{'player_master_id':'canonical','opponent_capability':'unknown','scenario_ids':['branch']}],'forced_bringback':False}}
    job = SimpleNamespace(job_id='saved',status='completed',strategy='showdown_small_field_gpp',
        params={'strategy_runtime':{'football_analyst':report}},contest_format='showdown',objective='gpp',
        results=[],projection_run_id=None,rule_run_id=None,data_cutoff_at=None,lineage_persisted=True,
        message=None,created_at=None,updated_at=None)
    monkeypatch.setattr(classic_game_environment, 'review_job', lambda job: None)
    app.dependency_overrides[get_optimizer_service] = lambda: SimpleNamespace(get_job=lambda key: job)
    try:
        response = client.get('/api/optimizer/results/saved')
        assert response.status_code == 200, response.text
        assert response.json()['football_analyst'] == report
    finally:
        app.dependency_overrides.pop(get_optimizer_service, None)


def test_missing_import_metadata_never_creates_artifact(client, tmp_path):
    packet = json.loads(PACKET_PATH.read_text())
    del packet['packet_id']
    response = client.post('/api/optimizer/analyst-packets', json={'packet':packet})
    assert response.status_code == 422
    assert not list(tmp_path.glob('*.json'))


def test_merged_scenario_packet_metadata_and_request_roundtrip(client):
    from scripts.run_merged_analyst_fixture import scenario_fixture
    packet,_=scenario_fixture('CLASSIC')
    response=client.post('/api/optimizer/analyst-packets',json={'packet':packet})
    assert response.status_code==200 and response.json()['scenario_count']==2
    request=OptimizerRunRequest(season=2099,week=1,slate='SYNTHETIC_SUNDAY_MAIN',strategy='classic_large_gpp_v1',contest_format='classic',objective='gpp',analyst_packet_sha256=response.json()['analyst_packet_sha256'],analyst_strategy='MERGED_SCENARIOS')
    assert request.model_dump()['params']['analyst_strategy']=='MERGED_SCENARIOS'
    assert 'analyst_strategy' not in request.model_dump()
    with pytest.raises(ValueError):OptimizerRunRequest(season=2099,week=1,slate='SYNTHETIC_SUNDAY_MAIN',strategy='classic_large_gpp_v1',analyst_strategy='MERGED_SCENARIOS')


def test_captain_contract_import_and_read(client):
    from scripts.run_merged_analyst_fixture import scenario_fixture
    packet,_=scenario_fixture('SHOWDOWN')
    packet['captain_analysis']={'contract_id':'captain_analysis_v1','opponents':[],'captains':[]}
    response=client.post('/api/optimizer/analyst-packets',json={'packet':packet})
    assert response.status_code==200, response.text
    metadata=response.json()
    assert metadata['captain_analysis_contract']=='captain_analysis_v1'
    assert client.get('/api/optimizer/analyst-packets/'+metadata['analyst_packet_sha256']).json()==metadata
    packet['captain_analysis']['contract_id']='unversioned'
    assert client.post('/api/optimizer/analyst-packets',json={'packet':packet}).status_code==422


def test_discovery_packet_import_is_idempotent_and_exposes_bounded_contract(client):
    from backend.app.tests.product.test_analyst_discovery import investigated_fixture
    packet,_,_,_=investigated_fixture()
    first=client.post('/api/optimizer/analyst-packets',json={'packet':packet})
    assert first.status_code==200,first.text
    assert first.json()['discovery_contract']=='analyst_discovery_v1'
    assert first.json()['discovery_finding_count']==1
    assert client.post('/api/optimizer/analyst-packets',json={'packet':packet}).json()==first.json()
    assert client.get('/api/optimizer/analyst-packets/'+first.json()['analyst_packet_sha256']).json()==first.json()


@pytest.mark.parametrize('params',[{'analyst_discovery_enabled':'true'},{'analyst_discovery_controls':{'max_reserved_slots':4}},{'analyst_discovery_controls':{'maximum_opportunity_transfer':.2}}])
def test_unbounded_or_untyped_discovery_controls_rejected(params):
    with pytest.raises(ValidationError):OptimizerRunRequest(season=2026,week=6,slate='SUNDAY_MAIN',strategy='classic_large_gpp_v1',params=params)


@pytest.mark.parametrize('contest_format,analyst_strategy,portfolio_mode',[('showdown','MERGED_SCENARIOS','SCENARIO_FIRST'),('classic','CONSTRUCTION','SCENARIO_FIRST'),('classic','MERGED_SCENARIOS','CONDITIONAL_COVERAGE')])
def test_challenger_scope_rejected_instead_of_silently_ignored(contest_format,analyst_strategy,portfolio_mode):
    with pytest.raises(ValidationError,match='Classic scenario-first'):
        OptimizerRunRequest(season=2026,week=6,slate='SUNDAY_MAIN',strategy='classic_large_gpp_v1',contest_format=contest_format,params={'analyst_packet_sha256':'a'*64,'analyst_strategy':analyst_strategy,'analyst_challenger_enabled':True,'analyst_portfolio_mode':portfolio_mode})


def test_scoped_imported_packet_catalog_has_no_pool_or_filesystem_paths(client):
    from backend.app.tests.product.test_analyst_discovery import investigated_fixture
    packet,_,_,_=investigated_fixture()
    for game in packet['games']:game.update(season=2099,week=1)
    metadata=client.post('/api/optimizer/analyst-packets',json={'packet':packet}).json();game=packet['games'][0]
    result=client.get('/api/optimizer/analyst-packets',params={'season':game['season'],'week':game['week'],'format':'classic'})
    assert result.status_code==200 and result.json()['rows'][0]==metadata
    assert metadata['discovery_snapshot_sha256']=='a'*64
    assert 'pool' not in result.text and 'sources' not in result.text and 'path' not in result.text


@pytest.mark.parametrize('params',[{'analyst_teammate_enabled':'true'},{'analyst_teammate_controls':{'max_solver_calls':9}},{'analyst_teammate_point_checks':{'name':[15]}},{'analyst_teammate_point_checks':{'00000000-0000-0000-0000-000000000001':[float('inf')]}},{'analyst_teammate_choice':{'source_optimizer_run_id':'bad','pair_id':'name','branch':'cheaper'}}])
def test_untyped_unbounded_teammate_controls_and_choices_rejected(params):
    with pytest.raises(ValidationError):OptimizerRunRequest(season=2026,week=6,slate='SUNDAY_MAIN',strategy='classic_large_gpp_v1',params=params)


def test_selected_only_focus_has_typed_bounded_ids_and_no_unselected_branch_tools():
    base=dict(season=2099,week=1,slate='SYNTHETIC',strategy='classic_large_gpp_v1',contest_format='classic',objective='gpp',params=dict(analyst_strategy='MERGED_SCENARIOS',analyst_packet_sha256='a'*64,analyst_scenario_focus_mode='SELECTED_ONLY',analyst_scenario_focus_ids=['declared']))
    assert OptimizerRunRequest(**base).params['analyst_scenario_focus_ids']==['declared']
    for update in [dict(analyst_scenario_focus_ids=[]),dict(analyst_scenario_focus_ids=['same','same']),dict(analyst_challenger_enabled=True),dict(analyst_teammate_enabled=True),dict(analyst_strategy='CONSTRUCTION'),dict(analyst_scenario_focus_mode='unknown')]:
        with pytest.raises(ValidationError):OptimizerRunRequest(**{**base,'params':{**base['params'],**update}})
