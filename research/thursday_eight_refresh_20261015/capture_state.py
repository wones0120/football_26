import json
from pathlib import Path
from dataclasses import asdict
from sqlalchemy import select
from backend.app.db import SessionLocal
from backend.app.models import OperationalJob
from backend.app.product_services.optimizer import OptimizerService
root=Path(__file__).resolve().parent
with SessionLocal() as s:
 j=s.get(OperationalJob,'6b1f206b-3294-40b6-87f2-bb0be3363715')
 print('preparation',j.status,j.stage,j.progress_message,j.run_id)
 if j.result_json:
  (root/'preparation_job.json').write_text(json.dumps(dict(job_id=j.job_id,status=j.status,result=j.result_json),indent=2,default=str))
  print(json.dumps(j.result_json,default=str)[:1200])
