from pathlib import Path
import subprocess,time,json,urllib.request
P=Path(__file__).resolve().parent
python=str(Path.cwd()/'.venv/bin/python')  # Preserve venv path; resolving symlink loses its environment.
processes={}
for label,args in [('api',['-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8000']),('worker',['-m','backend.app.worker'])]:
 handle=(P/(label+'_restored.log')).open('a')
 child=subprocess.Popen([python,*args],cwd=Path.cwd(),stdin=subprocess.DEVNULL,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
 processes[label]=child.pid
for attempt in range(100):
 try:
  with urllib.request.urlopen('http://127.0.0.1:8000/openapi.json',timeout=1) as r:body=json.load(r)
  if 'highest_projection' in body['components']['schemas']['OptimizerStatusResponse']['properties']:break
 except Exception:pass
 time.sleep(.1)
else:raise SystemExit('New API schema unavailable; inspect restore logs')
(P/'restoration.json').write_text(json.dumps(dict(new=processes,python=python,highest_projection_schema=True),indent=2)+'\n');print('restored',processes,flush=True)
