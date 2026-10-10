"""Read-only API checks against the local saved Week5 run; creates no decisions."""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app.api.product_routes import router
from backend.app.product_dependencies import get_optimizer_service
from backend.app.product_services.optimizer import OptimizerService
from backend.app.config import get_settings

RUN='3a41af88-a28c-41b1-888c-462ddcd7d74d'


def main():
    service=OptimizerService(get_settings().sqlalchemy_database_uri)
    if service.engine.url.host not in {'localhost','127.0.0.1','::1'}:
        raise ValueError('Only the local development database is supported by this verifier')
    app=FastAPI();app.include_router(router);app.dependency_overrides[get_optimizer_service]=lambda:service
    client=TestClient(app);base=f'/api/optimizer/results/{RUN}/selection-review'
    resp=client.get(base);assert resp.status_code==200,resp.text[:300]
    value=resp.json()
    assert value['review']['counts']=={'quality_eligible':75,'finalists':20,'ceiling_outsiders':10}
    assert value['selection_status']=='AI_SELECTION_UNKNOWN' and not value['can_record_prelock']
    comparison=client.post(base+'/compare',json={'review_hash':value['review_hash'],'candidate_ids':[RUN+':beb41d478b13c469',RUN+':8e2120be4073304e']})
    assert comparison.status_code==200,comparison.text[:300]
    assert comparison.json()['proposed_pair']['shared_player_count']==5
    download=client.get(base+'/download');assert download.status_code==200
    assert set(download.json())=={'review','review_hash'}
    summary=client.get('/api/learning/research/showdown-selection-review');assert summary.status_code==200,summary.text[:300]
    assert client.get('/api/learning/research/showdown-selection-review?season=2026').status_code==200
    (ROOT/'artifacts/showdown_ai_selection_review/database_api_verification.json').write_text(json.dumps({
        'passed':True,'run_id':RUN,'counts':value['review']['counts'],'selection_status':value['selection_status'],
        'can_record_prelock':False,'observed_pair_overlap':5,'decision_records_created':0,'research_summary':summary.json()},indent=2)+'\n')
    print('PASS: Real local saved-run API / comparison / safe export / research summary; zero historical decisions created.')


if __name__=='__main__':main()
