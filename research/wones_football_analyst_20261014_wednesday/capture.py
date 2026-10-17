"""Fresh read-only evidence; immutable destinations, no ingest or production writes."""
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor
import json, hashlib
from backend.app.db import engine
from sqlalchemy import text
P=Path(__file__).resolve().parent/'v1'
def save(n,r):
 p=P/n
 if p.exists(): raise RuntimeError('Refusing overwrite '+str(p))
 p.write_text(json.dumps(r,default=str,indent=2)+'\n')
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 queries={
 'salary':"select * from curated_salary where season=2026 and week=6 order by slate,game_info,team,player_master_id",
 'schedule':"select * from raw_nfl_schedule where season=2026 and week=6",
 'projection_runs':"select * from target.projection_run where season=2026 and week=6 order by created_at desc",
 'injury_counts':"select slate,count(*) from curated_injury where season=2026 and week=6 group by slate",
 'aliases':"select * from player_alias where player_master_id in (select player_master_id from curated_salary where season=2026 and week=6)"}
 for n,q in queries.items():
  rows=[dict(x) for x in c.execute(text(q)).mappings()]
  save(n+'_capture.json',{'observed_at':datetime.now(timezone.utc).isoformat(),'access':'read-only transaction','query':q,'rows':rows});print(n,len(rows))
 c.rollback()
urls={
 'SEA_tuesday':'https://www.seahawks.com/news/week-6-injury-report-seahawks-at-broncos',
 'DEN_tuesday':'https://www.denverbroncos.com/news/injury-report-cb-riley-moss-remains-limited-practice-participant-ahead-of-week-6-game-vs-seahawks',
 'NE_roundup':'https://www.nfl.com/news/nfl-news-roundup-latest-league-updates-from-tuesday-oct-13',
 'LAR_suspension':'https://www.nfl.com/news/rams-lt-alaric-jackson-suspended-two-games-for-striking-bradley-chubb-following-monday-night-s-game',
 'GB_preview':'https://www.packers.com/news/packers-host-the-cowboys-in-primetime-week-6-2026',
 'SF_preview':'https://www.49ers.com/news/morning-reports/morning-report-locker-room-reactions-brock-purdy-50-career-starts',
 'GB_schedule':'https://www.packers.com/schedule/',
 'SF_schedule':'https://www.49ers.com/schedule/',
 'DEN_schedule':'https://www.denverbroncos.com/schedule/'}
def capture(pair):
 n,u=pair;now=datetime.now(timezone.utc).isoformat()
 try:
  with urlopen(Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=30) as r: data=r.read();resolved=r.url
  target=P/(n+'.html')
  if target.exists():raise RuntimeError('immutable capture exists')
  target.write_bytes(data)
  save(n+'.json',{'source_id':n,'uri':u,'resolved_uri':resolved,'coverage':'verified','observed_at':now,'available_at':now,'published_at':None,'publication_clock_note':'Displayed publication date only; timezone not inferred','capture_sha256':hashlib.sha256(data).hexdigest(),'capture_kind':'raw_http_html'})
  return (n,len(data))
 except Exception as e:
  save(n+'.json',{'source_id':n,'uri':u,'coverage':'unavailable','observed_at':now,'reason':type(e).__name__});return(n,'unavailable')
with ThreadPoolExecutor(max_workers=5) as pool:
 for result in pool.map(capture,urls.items()):print(*result)
