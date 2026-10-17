from pathlib import Path
from datetime import datetime,UTC
import httpx,json,hashlib
from concurrent.futures import ThreadPoolExecutor
out=Path(__file__).resolve().parent/'v1'
urls={
'ARI_LAR':'https://www.azcardinals.com/news/injury-report-week-6-vs-rams',
'BUF_LV':'https://www.raiders.com/news/las-vegas-raiders-buffalo-bills-week-6-injury-report-2026',
'CAR_PHI':'https://www.philadelphiaeagles.com/news/panthers-vs-eagles-injury-report-2026-nfl-week-6-saquon-barkley-devonta-smith',
'NYJ_NE':'https://www.patriots.com/news/week-6-injury-report-patriots-vs-jets',
'CHI':'https://www.chicagobears.com/news/caleb-williams-takes-another-step-toward-return-from-hamstring-injury',
'ATL':'https://www.atlantafalcons.com/news/falcons-injury-report-michael-penix-jr-chicago-bears',
'KC':'https://www.chiefs.com/news/week-6-injury-report-chargers-vs-chiefs-2026',
'LAC':'https://www.chargers.com/news/chiefs-injury-report-ladd-mcconkey-week-6',
'NO_NYG':'https://www.neworleanssaints.com/news/injury-report-new-york-giants-vs-new-orleans-saints-2026-nfl-week-6-wednesday',
'PIT_TB':'https://www.steelers.com/news/week-6-injury-report-buccaneers-x2319',
'TEN':'https://www.tennesseetitans.com/news/week-6-injury-report-titans-at-colts',
'IND':'https://www.colts.com/news/colts-release-unofficial-depth-chart-for-week-6-vs-titans',
'BAL':'https://www.baltimoreravens.com/game-day/2026/reg-week6/ravens-at-browns/media',
'CLE':'https://www.clevelandbrowns.com/news/all',
'NFL_delta':'https://www.nfl.com/news/nfl-news-roundup-latest-league-updates-from-wednesday-oct-14',
'schedule':'https://www.nfl.com/schedules/2026/reg6/' }
def capture(item):
 k,url=item;path=out/('official_'+k+'.json')
 if path.exists():return k,'preserved'
 try:
  r=httpx.get(url,follow_redirects=True,timeout=30,headers={'Cache-Control':'no-cache'});r.raise_for_status();now=datetime.now(UTC).isoformat();body=r.text
  path.write_text(json.dumps(dict(source_id='official_'+k,uri=url,coverage='verified',observed_at=now,available_at=now,published_at=None,capture_kind='http_response',headers=dict(r.headers),body_sha256=hashlib.sha256(body.encode()).hexdigest(),body=body),indent=2)+'\n');return k,len(body)
 except Exception as e:return k,str(e)
with ThreadPoolExecutor(max_workers=6) as p:
 for x in p.map(capture,urls.items()):print(*x)
