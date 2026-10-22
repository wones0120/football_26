"""Public research API contract, isolated services; no production DB mutations."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.app.api.product_routes import router
from backend.app.db import get_db_session
from backend.app.product_services import scenario_breadth_replay as service


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db_session] = lambda: object()
    return TestClient(app)


def test_public_build_reopen_and_list_use_research_service(client, monkeypatch):
    result = {'replay_id':'a'*64, 'research_only':True, 'entry_clearance':False}
    monkeypatch.setattr(service, 'build_replay', lambda session, run_id: result)
    monkeypatch.setattr(service, 'read_replay', lambda replay_id: result)
    monkeypatch.setattr(service, 'list_replays', lambda: {'rows':[result]})
    assert client.post('/api/learning/research/scenario-breadth/source').json() == result
    assert client.get('/api/learning/research/scenario-breadth/saved/'+'a'*64).json() == result
    assert client.get('/api/learning/research/scenario-breadth').json() == {'rows':[result]}


@pytest.mark.parametrize('error,status', [(ValueError('invalid source/hash'),422),(LookupError('missing source'),404)])
def test_public_build_preserves_actionable_errors(client, monkeypatch, error, status):
    def fail(*args):raise error
    monkeypatch.setattr(service, 'build_replay', fail)
    response = client.post('/api/learning/research/scenario-breadth/source')
    assert response.status_code == status and response.json()['detail'] == str(error)


def test_full_game_research_public_build_reopen_without_optimizer_mutation(client,monkeypatch):
    from backend.app.product_services import full_game_breadth_replay as full
    result={'replay_id':'b'*64,'research_only':True,'entry_clearance':False,'outcomes_used':False}
    monkeypatch.setattr(full,'build',lambda session,run_id:result)
    monkeypatch.setattr(full,'read',lambda replay_id:result)
    monkeypatch.setattr(full,'list_replays',lambda:{'rows':[result]})
    assert client.post('/api/learning/research/full-game-breadth/source').json()==result
    assert client.get('/api/learning/research/full-game-breadth/saved/'+'b'*64).json()==result
    assert client.get('/api/learning/research/full-game-breadth').json()=={'rows':[result]}


def test_joint_portfolio_public_build_and_reopen_are_research_only(client,monkeypatch):
    from backend.app.product_services import joint_portfolio_replay as joint
    result={'replay_id':'c'*64,'research_only':True,'entry_clearance':False,'outcomes_used':False}
    monkeypatch.setattr(joint,'build',lambda session,parent_id:result)
    monkeypatch.setattr(joint,'read',lambda replay_id:result)
    monkeypatch.setattr(joint,'list_replays',lambda:{'rows':[result]})
    assert client.post('/api/learning/research/joint-coverage/source').json()==result
    assert client.get('/api/learning/research/joint-coverage/saved/'+'c'*64).json()==result
    assert client.get('/api/learning/research/joint-coverage').json()=={'rows':[result]}


def test_ablation_public_build_reopen_uses_frozen_research_service(client,monkeypatch):
    from backend.app.product_services import lineup_ablation_replay as ablation
    result={'replay_id':'d'*64,'research_only':True,'entry_clearance':False,'outcomes_used':False}
    monkeypatch.setattr(ablation,'build',lambda session,parent_id:result)
    monkeypatch.setattr(ablation,'read',lambda replay_id:result)
    monkeypatch.setattr(ablation,'list_replays',lambda:{'rows':[result]})
    assert client.post('/api/learning/research/lineup-ablations/source').json()==result
    assert client.get('/api/learning/research/lineup-ablations/saved/'+'d'*64).json()==result
    assert client.get('/api/learning/research/lineup-ablations').json()=={'rows':[result]}
