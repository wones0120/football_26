from pathlib import Path
import json,uuid,sys,httpx
P=Path(__file__).resolve().parent
preliminary='--preliminary' in sys.argv;label='preliminary' if preliminary else 'normal'
payload=dict(season=2026,week=6,slate='SUNDAY_MAIN',action='prepare',contest_format='classic',ownership_required=True,preliminary_research=preliminary,analyst_mode='AUTO')
key='accepted-dst-'+label+'-'+str(uuid.uuid4());request=P/(label+'_prepare_request.json');assert not request.exists(),'Preserve original request; use separately versioned research folder for another attempt';request.write_text(json.dumps(dict(idempotency_key=key,payload=payload),indent=2)+'\n')
r=httpx.post('http://127.0.0.1:8000/api/slate/preparation/jobs',json=payload,headers={'Idempotency-Key':key},timeout=60);r.raise_for_status();v=r.json();(P/(label+'_prepare_queued.json')).write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v,indent=2))
