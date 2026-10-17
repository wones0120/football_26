from pathlib import Path
import json,httpx
from backend.app.product_services.optimizer import OptimizerService,_json_safe
from sqlalchemy import create_engine
P=Path(__file__).resolve().parent
svc=OptimizerService();svc.engine=create_engine(svc.connection_string,connect_args={'options':'-c default_transaction_read_only=on'})
for arm in ['old_scenarios_friday_eligibility','refreshed_scenarios']:
 q=json.loads((P/(arm+'_queued.json')).read_text());j=httpx.get('http://127.0.0.1:8000/api/jobs/'+q['job']['job_id'],timeout=30).json();(P/(arm+'_status.json')).write_text(json.dumps(j,indent=2)+'\n');print(arm,j['status'],j.get('stage'),flush=True)
 if j['status']=='completed':
  rid=json.loads((P/(arm+'_request.json')).read_text())['optimizer']['optimizer_run_id'];r=httpx.get('http://127.0.0.1:8000/api/optimizer/results/'+rid,timeout=60);r.raise_for_status();(P/(arm+'_saved_api.json')).write_text(r.text+'\n');job=svc.get_job(rid);assert job and job.status=='completed';(P/(arm+'_saved_run.json')).write_text(json.dumps(_json_safe(vars(job)),indent=2)+'\n')
  print('saved',rid,len(job.results or []),flush=True)
