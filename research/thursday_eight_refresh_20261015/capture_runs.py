import json
from dataclasses import asdict
from pathlib import Path
from sqlalchemy import select
from backend.app.db import SessionLocal
from backend.app.models import OperationalJob
from backend.app.product_services.optimizer import OptimizerService
r=Path(__file__).resolve().parent;srv=OptimizerService()
with SessionLocal() as s:
 jobs=list(s.scalars(select(OperationalJob).where(OperationalJob.job_type=='optimizer_run').order_by(OperationalJob.created_at.desc()).limit(2)))
 for op in jobs:
  print(op.job_id,op.status,op.run_id)
  if op.status=='completed':
   j=srv.get_job(op.run_id);intent=j.params.get('analyst_optimization_intent');print('saved',j.job_id,intent,len(j.results or []))
   (r/((intent or 'unknown').lower()+'_job.json')).write_text(json.dumps(asdict(j),indent=2,default=str))
