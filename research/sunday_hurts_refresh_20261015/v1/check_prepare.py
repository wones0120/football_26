from pathlib import Path
import httpx,json
P=Path(__file__).resolve().parent;j=json.loads((P/'preparation_queued.json').read_text())['job']['job_id'];v=httpx.get('http://127.0.0.1:8000/api/jobs/'+j,timeout=30).json();(P/'preparation_status.json').write_text(json.dumps(v,indent=2)+'\n');print({k:v.get(k) for k in ['job_id','status','stage','progress_message','error_message']});print('result keys',list((v.get('result') or {}).keys()))
