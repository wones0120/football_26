"""Browser's pinned synthetic result -> actual construction-review API."""
import json
import sys
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app.api.product_routes import router
from backend.app.product_dependencies import get_optimizer_service

if __name__ == '__main__':
    payload=json.load(sys.stdin)
    report=json.loads(payload['raw_fixture_json'])[0]['report']
    assert report['effective_strategy_contract']['metadata']['projection_run_id']=='synthetic-projection'
    job=SimpleNamespace(strategy=report['strategy'],status=report['status'],results=report['results'],
        params={'effective_strategy_contract':report['effective_strategy_contract']})
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[get_optimizer_service]=lambda:SimpleNamespace(get_job=lambda _:job)
    response=TestClient(app).post('/api/optimizer/results/'+report['job_id']+'/construction-review?entry='+str(payload['entry'])+'&enforce_single_te='+str(payload['enforce_single_te']).lower())
    assert response.status_code==200,response.text
    print(response.text)
