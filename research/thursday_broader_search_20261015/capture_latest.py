import argparse,json
from pathlib import Path
from dataclasses import asdict
from sqlalchemy import select
from backend.app.db import SessionLocal
from backend.app.models import OperationalJob
from backend.app.product_services.optimizer import OptimizerService
r=Path(__file__).resolve().parent;parser=argparse.ArgumentParser();parser.add_argument('label');a=parser.parse_args()
with SessionLocal() as s:
 j=s.scalars(select(OperationalJob).where(OperationalJob.job_type=='optimizer_run').order_by(OperationalJob.created_at.desc()).limit(1)).first()
 print(j.job_id,j.status,j.stage,j.progress_message,j.run_id)
 if j.status=='completed':
  run=OptimizerService().get_job(j.run_id);path=r/(a.label+'_job.json');assert not path.exists() or json.loads(path.read_text())['job_id']==run.job_id
  path.write_text(json.dumps(asdict(run),indent=2,default=str))
  print('saved',run.job_id,run.params.get('analyst_optimization_intent'),len(run.results or []),run.params.get('captain_max_exposure'))
