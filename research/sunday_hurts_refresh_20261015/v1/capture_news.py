from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,httpx
from concurrent.futures import ThreadPoolExecutor
P=Path(__file__).resolve().parent
urls={
'hurts_statement':'https://www.philadelphiaeagles.com/news/statement-from-the-philadelphia-eagles-on-qb-jalen-hurts',
'phi_depth':'https://www.philadelphiaeagles.com/team/depth-chart',
'chi_qb':'https://www.chicagobears.com/news/caleb-williams-takes-another-step-toward-return-from-hamstring-injury',
'phi_injury':'https://www.philadelphiaeagles.com/news/panthers-vs-eagles-injury-report-2026-nfl-week-6-saquon-barkley-devonta-smith',
'car_injury':'https://www.panthers.com/team/injury-report/',
'bal_injury':'https://www.baltimoreravens.com/team/injury-report/',
'chi_injury':'https://www.chicagobears.com/team/injury-report/',
'no_injury':'https://www.neworleanssaints.com/news/injury-report-new-york-giants-vs-new-orleans-saints-2026-nfl-week-6-wednesday'}
def capture(kv):
 k,u=kv;f=P/(k+'.json')
 if f.exists():return k,'preserved'
 r=httpx.get(u,follow_redirects=True,timeout=40,headers={'Cache-Control':'no-cache'});r.raise_for_status();t=datetime.now(UTC).isoformat();v=dict(uri=str(r.url),received_at=t,headers=dict(r.headers),body=r.text,body_sha256=hashlib.sha256(r.content).hexdigest());f.write_text(json.dumps(v,indent=2)+'\n');return k,len(r.content)
with ThreadPoolExecutor(max_workers=6) as x:
 for v in x.map(capture,urls.items()):print(*v,flush=True)
