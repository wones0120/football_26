"""Isolated synthetic API downloads; no production DB, entries or real player data."""
import csv,io,json,hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app.api.product_routes import router
from backend.app.product_dependencies import get_optimizer_service
from backend.app.tests.product.test_gpp_recommendation import lineup,job
root=Path(__file__).resolve().parent/'synthetic_downloads';root.mkdir(exist_ok=True)
verification=[]
for fmt in ['classic','showdown']:
 candidates=[lineup(0,10,showdown=fmt=='showdown'),lineup(20,11,showdown=fmt=='showdown')]
 run=job(candidates,fmt);run.params['entry_readiness']={'entry_ready':True}
 assert run.params['gpp_recommendation']['recommended']['lineup_number']==2
 app=FastAPI();app.include_router(router)
 app.dependency_overrides[get_optimizer_service]=lambda:SimpleNamespace(get_job=lambda id:run if id=='run' else None,engine=MagicMock())
 client=TestClient(app)
 for mode in ['all','recommended']:
  with patch('backend.app.product_services.evaluation_record.record_export') as record:
   response=client.get('/api/optimizer/results/run/draftkings/download',params={'recommended_only':mode=='recommended'})
  assert response.status_code==200,response.text
  rows=list(csv.reader(io.StringIO(response.content.decode())))
  expected=['CPT']+['FLEX']*5 if fmt=='showdown' else ['QB','RB','RB','WR','WR','WR','TE','FLEX','DST']
  assert rows[0]==expected and len(rows)==(3 if mode=='all' else 2)
  assert all(cell.isdigit() for row in rows[1:] for cell in row)
  if mode=='recommended':
   expected_ids={p['dk_captain_id'] if fmt=='showdown' and p['roster_position']=='CPT' else p['dk_player_id'] for p in candidates[1]}
   assert set(rows[1])==expected_ids
  if fmt=='showdown':assert rows[1][0]==candidates[1 if mode=='recommended' else 0][0]['dk_captain_id']
  assert record.call_args.args[1]=='run' and record.call_args.args[3]==response.content
  assert record.call_args.args[4]==([candidates[1]] if mode=='recommended' else candidates)
  path=root/f'SYNTHETIC_{fmt}_{mode}.csv';path.write_bytes(response.content)
  verification.append(dict(format=fmt,mode=mode,header=rows[0],rows=len(rows)-1,sha256=hashlib.sha256(response.content).hexdigest(),file=path.name,recommended_saved_number=2 if mode=='recommended' else None))
(root/'VERIFICATION.json').write_text(json.dumps(verification,indent=2)+'\n')
(root/'README.txt').write_text('SYNTHETIC TEST DATA ONLY. These files verify route/CSV structure and native ID slot rules. Do not upload them to a real contest. No production export receipt or entry was created.\n')
print(json.dumps(verification,indent=2))
