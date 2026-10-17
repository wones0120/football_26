import json
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app.api.preliminary_report_routes import router
from backend.app.product_services import preliminary_optimizer as service

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(service,'LEDGER',tmp_path)
    app=FastAPI();app.include_router(router)
    value=dict(contract_id=service.CONTRACT,classification='PRELIMINARY_RESEARCH',entry_ready=False,scope=dict(season=2026,week=6,slate='SUNDAY_MAIN',contest_format='classic'),projection_run_id='projection',ownership_run_id='ownership',preparation_job_id='preparation',data_cutoff_at='2026-10-14T00:00:00Z',assumption_manifest=dict(declared_at='2026-10-14T00:00:00Z',exclude_player_ids=['canonical-Q']),assumption_manifest_sha256='assumptions',source_sha256='sources',pool_sha256='pool',normal_readiness=dict(reason_codes=['official_player_status_refresh_failed']),pool=[dict(private_model='not served')])
    saved=service.save_snapshot(value)
    return TestClient(app),saved,tmp_path

def test_scoped_library_and_metadata_preserve_false_readiness_and_do_not_serve_pool(client):
    http,snapshot,_=client
    response=http.get('/api/optimizer/preliminary/snapshots?season=2026&week=6&slate=SUNDAY_MAIN');assert response.status_code==200
    rows=response.json()['rows'];assert len(rows)==1 and rows[0]['snapshot_sha256']==snapshot['sha256']
    assert rows[0]['entry_ready'] is False and 'pool' not in rows[0] and 'normal_readiness' not in rows[0]
    assert rows[0]['assumption_manifest']['exclude_player_ids']==['canonical-Q']
    assert http.get('/api/optimizer/preliminary/snapshots?season=2026&week=5&slate=SUNDAY_MAIN').json()['rows']==[]
    assert http.get('/api/optimizer/preliminary/snapshots/'+snapshot['sha256']).json()==rows[0]

def test_unknown_and_symlink_escaped_snapshot_rejected(client,tmp_path):
    http,snapshot,ledger=client
    assert http.get('/api/optimizer/preliminary/snapshots/not-a-hash').status_code==404
    path=ledger/(snapshot['sha256']+'.json');outside=tmp_path.parent/(tmp_path.name+'-outside.json');outside.write_text(path.read_text());path.unlink();path.symlink_to(outside)
    assert http.get('/api/optimizer/preliminary/snapshots/'+snapshot['sha256']).status_code==404
    listing=http.get('/api/optimizer/preliminary/snapshots?season=2026&week=6&slate=SUNDAY_MAIN').json();assert not listing['rows'] and listing['warnings']

def test_mutated_hash_and_bounded_scan_are_visible(client):
    http,snapshot,ledger=client
    path=ledger/(snapshot['sha256']+'.json');value=json.loads(path.read_text());value['entry_ready']=True;path.write_text(json.dumps(value))
    assert http.get('/api/optimizer/preliminary/snapshots/'+snapshot['sha256']).status_code==404
    for i in range(55):(ledger/(f'unlisted-{i}.txt')).write_text('not an approved snapshot')
    response=http.get('/api/optimizer/preliminary/snapshots?season=2026&week=6&slate=SUNDAY_MAIN');assert response.status_code==200 and any('limited' in w for w in response.json()['warnings'])

def test_per_file_and_aggregate_byte_limits_fail_explicitly(client,monkeypatch):
    from backend.app.api import preliminary_report_routes as routes
    http,snapshot,_=client
    monkeypatch.setattr(routes,'MAX_SCAN_BYTES',1)
    result=http.get('/api/optimizer/preliminary/snapshots?season=2026&week=6&slate=SUNDAY_MAIN').json()
    assert result['rows']==[] and any('byte budget' in w for w in result['warnings'])
    monkeypatch.setattr(routes,'MAX_SNAPSHOT_BYTES',1)
    assert http.get('/api/optimizer/preliminary/snapshots/'+snapshot['sha256']).status_code==404
