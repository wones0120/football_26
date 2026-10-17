from pathlib import Path
import json,uuid,httpx
P=Path(__file__).resolve().parent
payload=dict(season=2026,week=6,slate='SUNDAY_MAIN',action='prepare',contest_format='classic',ownership_required=True,preliminary_research=True,analyst_mode='BASELINE')
r=httpx.post('http://127.0.0.1:8000/api/slate/preparation/jobs',json=payload,headers={'Idempotency-Key':'hurts-refresh-'+str(uuid.uuid4())},timeout=60);r.raise_for_status();v=r.json();(P/'preparation_queued.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v,indent=2))
