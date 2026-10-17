import json
from datetime import datetime
from pathlib import Path
from backend.app.db import engine
from backend.app.product_services.pregame_context import PregameContextService
r=Path(__file__).resolve().parent;p=json.loads((r/'charles_context_receipt.json').read_text())['payload']
for f in p['players'][0]['evidence']['source_facts']:
 if f.get('source')=='official_nfl_club_transaction':
  f.pop('published_at',None)
  f['publication_text']='Oct 14, 2026 at 02:03 PM; page timezone unverified'
p['notes']+=' Publication timezone correction: original source HTTP observation/receipt clocks unchanged; no timezone is inferred for the visible publication text.'
p['observed_at']=datetime.fromisoformat(p['observed_at'])
result=PregameContextService(engine=engine).create_run(p)
(r/'charles_publication_clock_clarification.json').write_text(json.dumps(dict(payload=p,result=result,predecessor='charles_context_receipt.json'),indent=2,default=str))
