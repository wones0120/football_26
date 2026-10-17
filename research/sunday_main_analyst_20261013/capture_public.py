from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request,urlopen
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
p=Path(__file__).resolve().parent/'public';p.mkdir(exist_ok=True)
urls={'NE_NFL':'https://www.nfl.com/teams/new-england-patriots/','PHI_home':'https://www.philadelphiaeagles.com/','nfl_schedule':'https://www.nfl.com/schedules/2026/by-week/week-6','ARI':'https://www.azcardinals.com/news/','LAR':'https://www.therams.com/news/injury-report','BAL':'https://www.baltimoreravens.com/news/transcripts','CLE':'https://www.clevelandbrowns.com/news/all','BUF':'https://www.buffalobills.com/news/','LV':'https://www.raiders.com/news/','CAR':'https://www.panthers.com/news/','PHI':'https://www.philadelphiaeagles.com/news/','CHI':'https://www.chicagobears.com/news/injury-update','ATL':'https://www.atlantafalcons.com/team/injury-report/','LAC':'https://www.chargers.com/media/2026-season/week-6','KC':'https://www.chiefs.com/news/','NO':'https://www.neworleanssaints.com/news/','NYG':'https://www.giants.com/news/','NYJ':'https://www.newyorkjets.com/news/all-news','NE':'https://www.patriots.com/news/','PIT':'https://www.steelers.com/news/','TB':'https://www.buccaneers.com/news/all-content','TEN':'https://www.tennesseetitans.com/news/','IND':'https://www.colts.com/news/'}
def capture(item):
 key,url=item;dest=p/(key+'.html');meta=p/(key+'.json')
 if meta.exists():return key,'existing'
 now=datetime.now(timezone.utc).isoformat()
 try:
  with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=35) as r: data=r.read();final=r.url
  dest.write_bytes(data);rec={'uri':url,'resolved_uri':final,'observed_at':now,'capture_sha256':hashlib.sha256(data).hexdigest(),'coverage':'verified','capture_kind':'raw_http_html','bytes':len(data)}
 except Exception as e:rec={'uri':url,'observed_at':now,'coverage':'unavailable','error':str(e)}
 meta.write_text(json.dumps(rec,indent=2)+'\n');return key,rec['coverage']
with ThreadPoolExecutor(max_workers=5) as ex:
 for x in ex.map(capture,urls.items()):print(*x)
