"""New normal Classic service run preserving the saved request and prior run."""
from dataclasses import asdict
import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

from backend.app.config import get_settings
from backend.app.db import engine
from backend.app.product_services.optimizer import OptimizerService, _json_safe
from backend.app.product_services.classic_data_readiness import ClassicDataNotReady
from backend.app.product_services.slate_preparation import digest


def main():
    out = Path('artifacts/classic_gpp_overblocking_repair')
    request = json.loads(Path('artifacts/classic_live_pipeline_integrity/completion/rerun_request.json').read_text())
    prior = request['optimizer_run_id']
    def saved_prior():
        with engine.connect() as c:
            return dict(c.execute(text('SELECT * FROM target.optimizer_run WHERE optimizer_run_id=:id'), {'id':prior}).mappings().one())
    before = saved_prior()
    new_id = str(uuid4())
    request['optimizer_run_id'] = new_id
    (out/'rerun_request.json').write_text(json.dumps(request,indent=2))
    print('New optimizer run:',new_id,flush=True)
    service = OptimizerService(get_settings().sqlalchemy_database_uri)
    def progress(stage,current,total,message,**kwargs):
        print(stage, current, total, message,flush=True)
    try:
        job = service.run_job(**request,progress=progress)
    except ClassicDataNotReady as exc:
        print(str(exc),flush=True)
        job = service.get_job(new_id)
    if job is None:
        raise ValueError('Normal run did not persist an auditable optimizer result')
    result = _json_safe(asdict(job))
    (out/'rerun_optimizer.json').write_text(json.dumps(result,indent=2,default=str))
    readiness = result['params']['data_readiness']
    (out/'rerun_readiness.json').write_text(json.dumps(readiness,indent=2,default=str))
    preservation = dict(prior_run_id=prior,new_run_id=new_id,prior_unchanged=digest(before)==digest(saved_prior()),
        controls_unchanged=all(result['params'].get(k)==v for k,v in request['params'].items()),
        readiness=readiness['status'],solver_called=readiness['solver_called'],lineup_count=len(result.get('results') or []))
    (out/'preservation_check.json').write_text(json.dumps(preservation,indent=2))
    print(preservation,flush=True)


if __name__ == '__main__':
    main()
