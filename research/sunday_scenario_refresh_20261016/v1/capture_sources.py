from pathlib import Path
from datetime import datetime,UTC
from concurrent.futures import ThreadPoolExecutor
import json,hashlib,httpx
from html.parser import HTMLParser
import re,html
P=Path(__file__).resolve().parent
sources={f.stem:json.loads(f.read_text())['uri'] for f in Path('research/sunday_refresh_20261015/v1').glob('official_*.json') if f.stem not in ['official_schedule','official_NFL_delta','official_CLE']}
sources.update(official_NO_friday='https://www.neworleanssaints.com/news/injury-report-new-york-giants-vs-new-orleans-saints-2026-nfl-week-6-friday',official_ATL_final='https://www.atlantafalcons.com/team/injury-report/',official_NFL='https://www.nfl.com/injuries/',official_BUF='https://www.buffalobills.com/news/buffalo-bills-injury-report-vs-raiders-week-6',official_TB='https://www.buccaneers.com/news/buccaneers-steelers-injury-report-oct-16-week-6-2026',official_LAR='https://www.therams.com/news/rams-injury-report-week-6-2026-vs-cardinals-trent-mcduffie-and-kam-curl-questionable',official_CHI_final='https://www.chicagobears.com/news/injury-update-caleb-williams-questionable-for-sunday-s-game-vs-falcons',official_PHI_qb='https://www.philadelphiaeagles.com/news/tanner-mckee-will-be-ready-for-his-moment-2026-nfl-week-6-carolina-panthers',official_BAL_final='https://www.baltimoreravens.com/team/injury-report/',official_CLE='https://www.clevelandbrowns.com/team/injury-report/',official_NO_final='https://www.neworleanssaints.com/team/injury-report/',official_NYG='https://www.giants.com/team/injury-report/')
def one(item):
 sid,url=item
 if (P/(sid+'.json')).exists():return(sid,'existing immutable capture retained')
 try:
  r=httpx.get(url,timeout=45,follow_redirects=True);r.raise_for_status();t=datetime.now(UTC).isoformat();raw=r.content;(P/(sid+'.html')).write_bytes(raw);text=raw.decode('utf-8',errors='replace');pub=re.search(r'<meta[^>]+(?:property|name)=["\']article:published_time["\'][^>]+content=["\']([^"\']+)',text);tables=[]
  class Parser(HTMLParser):
   def __init__(self):super().__init__();self.parts=[];self.skip=0
   def handle_starttag(self,tag,attrs):
    if tag in ['script','style']:self.skip+=1
    if tag in ['p','div','tr','td','h1','h2','h3','br','li']:self.parts.append('\n')
   def handle_endtag(self,tag):
    if tag in ['script','style']:self.skip=max(0,self.skip-1)
   def handle_data(self,data):
    if not self.skip:self.parts.append(data)
  parser=Parser();parser.feed(text);txt='\n'.join(x.strip() for x in ''.join(parser.parts).splitlines() if x.strip());(P/(sid+'.txt')).write_text(txt);out=dict(source_id=sid,uri=str(r.url),observed_at=t,available_at=t,published_at=pub.group(1) if pub else None,coverage='verified',capture_sha256=hashlib.sha256(raw).hexdigest(),tables=tables,text_path=str(P/(sid+'.txt')));(P/(sid+'.json')).write_text(json.dumps(out,indent=2)+'\n');return(sid,len(txt),len(tables),out['published_at'])
 except Exception as e:return(sid,str(e))
print(*ThreadPoolExecutor(6).map(one,sources.items()),sep='\n')
