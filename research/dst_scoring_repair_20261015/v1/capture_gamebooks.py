from pathlib import Path
from datetime import datetime,UTC
from concurrent.futures import ThreadPoolExecutor
import json,httpx,hashlib,re,gzip
from backend.app.product_services.official_injuries import _Document
from Database.dst import normalize_team
P=Path(__file__).resolve().parent/'gamebooks';P.mkdir(exist_ok=True)
slugs=dict(ARI='cardinals',ATL='falcons',BAL='ravens',BUF='bills',CAR='panthers',CHI='bears',CIN='bengals',CLE='browns',DAL='cowboys',DEN='broncos',DET='lions',GB='packers',HOU='texans',IND='colts',JAX='jaguars',KC='chiefs',LV='raiders',LAC='chargers',LAR='rams',MIA='dolphins',MIN='vikings',NE='patriots',NO='saints',NYG='giants',NYJ='jets',PHI='eagles',PIT='steelers',SEA='seahawks',SF='49ers',TB='buccaneers',TEN='titans',WAS='commanders')
scored=json.load(open(P.parent/'scored_games.json'));bygame={r['game_id']:r for r in scored if r['season']==2026 or r['game_id'] in ['2024_04_NO_ATL','2024_04_CLE_LV']};schedule={r['game_id']:r for r in json.load(open('research/opponent_qb_context_20261015/v1/schedule.json'))['rows']}
def capture(item):
 gid,row=item;folder=P/gid;folder.mkdir(exist_ok=True);meta=folder/'capture.json'
 if meta.exists():return json.load(open(meta))
 s=schedule[gid];u=f"https://www.nfl.com/games/{slugs[normalize_team(s['away_team'])]}-at-{slugs[normalize_team(s['home_team'])]}-{s['season']}-reg-{s['week']}?tab=recap"
 try:
  r=httpx.get(u,follow_redirects=True,timeout=45);r.raise_for_status();page_at=datetime.now(UTC).isoformat();(folder/'gamecenter.html.gz').write_bytes(gzip.compress(r.content));root=_Document(r.text).root
  links={a.attrs.get('href') for a in root.find('a') if 'game book' in a.content().lower() and '.pdf' in a.attrs.get('href','')}
  if len(links)!=1:raise ValueError(f'Expected one official gamebook, found {len(links)}')
  pdf=next(iter(links));response=httpx.get(pdf,follow_redirects=True,timeout=45);response.raise_for_status();(folder/'gamebook.pdf').write_bytes(response.content)
  v=dict(game_id=gid,page_uri=u,page_observed_at=page_at,page_sha256=hashlib.sha256(r.content).hexdigest(),pdf_uri=pdf,pdf_observed_at=datetime.now(UTC).isoformat(),pdf_sha256=hashlib.sha256(response.content).hexdigest(),status='captured')
 except Exception as e:v=dict(game_id=gid,page_uri=u,status='unresolved',reason=str(e))
 meta.write_text(json.dumps(v,indent=2)+'\n');return v
with ThreadPoolExecutor(max_workers=8) as pool:
 values=list(pool.map(capture,bygame.items()))
(P.parent/'gamebook_manifest.json').write_text(json.dumps(values,indent=2)+'\n');print('captured',sum(v['status']=='captured' for v in values),'of',len(values));print([v for v in values if v['status']!='captured'])
