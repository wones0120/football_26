"""Learned Single Stat bindings preserve scope, missingness and legacy receipts."""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest

from backend.app.product_services import single_stat as stat
from backend.app.product_services import single_stat_learned_yards as learned
from backend.app.product_services.evaluation_record import digest
from backend.app.tests.product.test_single_stat import NOW, package

PID = '00000000-0000-0000-0000-000000000001'
JOB = '00000000-0000-0000-0000-000000000002'


def receipt():
    req = package(); req.prepared_input_job_id = JOB
    forecast = dict(learned_opportunities=True, before_period=202606, model={'training_max_period':202605}, source_cutoff_at=NOW.isoformat(),
        yardage_model=dict(version='role_efficiency_yards_v1', training_max_period=202605),
        players=[dict(player_master_id=PID, team='A', position='WR', projected_yards=dict(rushing_yards=4, receiving_yards=40),
            utility=9999, counts={'targets': 5}, efficiency={})])
    forecast['sha256'] = digest(forecast)
    result = dict(action='prepare', season=2026, week=6, data_cutoff_at=NOW.isoformat(), workload_forecast=forecast,
        source_manifest={'games':[dict(game_id='canonical-game', away_team='A', home_team='B', kickoff_at=req.games[0].scheduled_start_at.isoformat())]})
    job = SimpleNamespace(job_id=JOB, run_id='preparation', status='completed', completed_at=NOW.replace(tzinfo=None), result_json=result)
    return req, job


def test_binding_and_raw_yards_not_points():
    req, job = receipt()
    binding, actors = learned.bind_preparation(req, SimpleNamespace(get=lambda *args: job))
    assert binding['selection_weights'] == dict(rushing_yards=1, receiving_yards=1, passing_yards=0)
    f = learned.actor_forecast(actors[PID], dict(team='A',position='WR'))
    assert f['value'] == 44 and f['counts']['targets'] == 5
    assert f['sample_games'] is None
    with pytest.raises(ValueError, match='team/position'):
        learned.actor_forecast(actors[PID], dict(team='B',position='WR'))
    unknown = learned.actor_forecast(None, dict(team='A',position='WR'))
    assert unknown['value'] is None and len(unknown['missing_components']) == 2


@pytest.mark.parametrize('problem', ['hash','future_completion','future_source','training','game','scope','unfinished','duplicate','count_training','target_period'])
def test_binding_rejects_invalid_receipts(problem):
    req, job = receipt(); r=job.result_json; f=r['workload_forecast']
    if problem == 'hash': f['players'][0]['projected_yards']['rushing_yards']=999
    if problem == 'future_completion': job.completed_at += timedelta(seconds=1)
    if problem == 'future_source': f['source_cutoff_at']=(NOW+timedelta(seconds=1)).isoformat()
    if problem == 'count_training': f['model']['training_max_period']=202606
    if problem == 'target_period': f['before_period']=202607
    if problem == 'training': f['yardage_model']['training_max_period']=202606
    if problem == 'game': r['source_manifest']['games'][0]['away_team']='C'
    if problem == 'scope': r['week']=5
    if problem == 'unfinished': job.status='running'
    if problem == 'duplicate': f['players'].append(deepcopy(f['players'][0]))
    if problem != 'hash': f['sha256']=digest({k:v for k,v in f.items() if k!='sha256'})
    with pytest.raises(ValueError): learned.bind_preparation(req, SimpleNamespace(get=lambda *args: job))


def test_legacy_hash_unchanged_and_learned_import_selection(tmp_path, monkeypatch):
    req = package()
    legacy_payload=req.model_dump(mode='json'); legacy_payload.pop('prepared_input_job_id')
    baseline=lambda *args: dict(method='baseline',components={'rushing_yards':1,'receiving_yards':2},value=3,missing_components=[],sample_games=3)
    old=stat.import_pool(req,None,directory=tmp_path,now=NOW,resolver=lambda x:x,forecaster=baseline)
    assert old['import_request_sha256']==stat.digest(legacy_payload)
    assert 'prepared_input_job_id' not in old['source'] and 'forecast_binding' not in old
    req.prepared_input_job_id=JOB
    actors={str(i):dict(team='A' if i<3 else 'B',position=None,projected_yards={'rushing_yards':i*10,'receiving_yards':i}) for i in range(1,5)}
    actors['1']['projected_yards']['receiving_yards']=None
    monkeypatch.setattr(learned,'bind_preparation',lambda *args:({'method':'learned'},actors))
    monkeypatch.setattr(stat,'historical_baseline',baseline)
    pool=stat.import_pool(req,None,directory=tmp_path,now=NOW,resolver=lambda x:x)
    assert all(p['baseline_comparison']['value']==3 for p in pool['players'])
    with pytest.raises(ValueError,match='coverage_incomplete'):
        stat.optimize(stat.Optimize(pool_sha256=pool['sha256']),directory=tmp_path,now=NOW)
    report=stat.optimize(stat.Optimize(pool_sha256=pool['sha256'],allow_incomplete_pool_research=True),directory=tmp_path,now=NOW)
    assert report['expected_metric']==99 and report['objective_scope']=='measured_eligible_subset_only'
    assert report['excluded_players'][0]['forecast']['value'] is None
    assert stat.load(old['sha256'],tmp_path)==old


def test_public_learned_import_generate_reopen(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.api.single_stat_routes import router
    from backend.app.db import get_db_session
    req, job = receipt()
    f=job.result_json['workload_forecast']
    f['players']=[dict(player_master_id=f'00000000-0000-0000-0000-{i:012d}',team='A' if i<3 else 'B',position=None,
        projected_yards={'rushing_yards':i*10,'receiving_yards':i}) for i in range(1,5)]
    f['sha256']=digest({k:v for k,v in f.items() if k!='sha256'})
    req.player_evidence['4']=stat.NativePlayerEvidence(status='Q',source_reference='fixture provider',observed_at=NOW)
    monkeypatch.setattr(stat,'LEDGER',tmp_path)
    monkeypatch.setattr(stat,'historical_baseline',lambda *args: {'value':999,'components':{},'missing_components':[]})
    original_import=stat.import_pool; original_optimize=stat.optimize
    monkeypatch.setattr(stat,'import_pool',lambda r,s: original_import(r,s,now=NOW,resolver=lambda i:f'00000000-0000-0000-0000-{int(i):012d}'))
    monkeypatch.setattr(stat,'optimize',lambda r:original_optimize(r,now=NOW))
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[get_db_session]=lambda:SimpleNamespace(get=lambda *args:job)
    client=TestClient(app)
    imported=client.post('/api/single-stat/pools',json=req.model_dump(mode='json'))
    assert imported.status_code==200, imported.text
    result=client.post('/api/single-stat/optimize',json={'pool_sha256':imported.json()['sha256'],'exclude_questionable':False})
    assert result.status_code==200, result.text
    report=result.json()
    assert report['classification']=='LEARNED_YARDS_RESEARCH' and report['expected_metric']==99
    assert report['players'][0]['baseline_comparison']['value']==999
    assert any(p.get('status_evidence',{}).get('status')=='Q' for p in report['players'])
    assert client.get('/api/single-stat/records/'+report['sha256']).json()==report
