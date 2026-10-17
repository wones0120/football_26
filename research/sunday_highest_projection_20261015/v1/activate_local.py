"""Activate this authorized local feature only while the durable job queue is idle."""
from pathlib import Path
import os,signal,subprocess,time,json,urllib.request
from sqlalchemy import text
from backend.app.db import engine
P=Path(__file__).resolve().parent
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 active=[dict(r) for r in c.execute(text("select job_id,job_type,status from operational_job where status in ('queued','running')")).mappings()]
print('active jobs',active,flush=True)
if active:raise SystemExit('Refusing to restart API/worker with active durable jobs')
expected={21965:'-m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000',8057:'-m backend.app.worker'}
for pid,signature in expected.items():
 cmd=subprocess.check_output(['ps','-p',str(pid),'-o','command='],text=True).strip()
 if signature not in cmd:raise SystemExit(f'Process identity mismatch for {pid}')
for pid in expected:os.kill(pid,signal.SIGTERM)
for attempt in range(40):
 try:
  urllib.request.urlopen('http://127.0.0.1:8000/',timeout=.2)
 except Exception:break
 time.sleep(.1)
processes={}
for label,args in [('api',['-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8000']),('worker',['-m','backend.app.worker'])]:
 log=(P/(label+'_activated.log')).open('a')
 child=subprocess.Popen([str(Path.cwd()/'.venv/bin/python'),*args],cwd=Path.cwd(),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 processes[label]=child.pid
for attempt in range(100):
 try:
  with urllib.request.urlopen('http://127.0.0.1:8000/',timeout=.5) as response:body=json.load(response)
  if body.get('service')=='football_26':break
 except Exception:pass
 time.sleep(.1)
else:raise SystemExit('New API did not become healthy; inspect api_activated.log')
(P/'activation.json').write_text(json.dumps(dict(previous=expected,new=processes,active_jobs_before_restart=active,health=body),indent=2)+'\n');print('activated',processes,body,flush=True)
