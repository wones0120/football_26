"""Immutable read-only prior-week statistics and primary-source captures."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

from backend.app.db import engine
from sqlalchemy import text

OUT=Path(__file__).resolve().parent/'v1'

def save(name,data):
    with (OUT/name).open('x') as f: f.write(json.dumps(data,default=str,indent=2)+'\n')

with engine.connect() as c:
    c.execute(text('SET TRANSACTION READ ONLY'))
    for name,q in {
        'stats':'select * from public.curated_weekly_stats where season=2026 and week in (4,5) order by week,game_id,player_master_id',
        'raw':'select * from public.raw_nfl_weekly_stat where season=2026 and week=5 order by raw_nfl_weekly_stat_id',
        'participation':'select * from public.curated_player_game_participation where season=2026 and week in (4,5) order by week,game_id,player_master_id',
        'schedule':'select * from public.raw_nfl_schedule where season=2026 and week in (5,6) order by week,game_id',
        'aliases':"select * from public.player_alias where source_system='nflreadpy' and player_master_id in (select player_master_id from public.curated_salary where season=2026 and week=6)",
    }.items():
        rows=[dict(r) for r in c.execute(text(q)).mappings()]
        save(name+'_capture.json',dict(observed_at=datetime.now(timezone.utc).isoformat(),access='SET TRANSACTION READ ONLY; rollback',query=q,rows=rows))
        print(name,len(rows))
    c.rollback()

for name,url in {
    'BUF_coach':'https://www.buffalobills.com/video/joe-brady-talks-clock-management-ball-security-staying-out-west-and-more',
    'BUF_recap':'https://www.buffalobills.com/news/top-3-things-we-learned-from-bills-vs-rams-week-5',
    'LAR_recap':'https://www.therams.com/news/game-recap-rams-fall-to-bills-37-34-in-overtime-on-monday-night-football',
    'Cook_stats':'https://www.nfl.com/players/james-cook/stats/',
    'BUF_warning':'https://www.nfl.com/news/joe-brady-bills-could-decrease-james-cook-s-carries-if-ball-security-doesn-t-improve',
    'BUF_inactive':'https://www.buffalobills.com/news/dj-moore-among-bills-inactives-vs-rams',
}.items():
    now=datetime.now(timezone.utc).isoformat()
    try:
        with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=30) as r: raw=r.read(); resolved=r.url
        with (OUT/(name+'.html')).open('xb') as f:f.write(raw)
        save(name+'.json',dict(source_id='weekly_'+name,uri=url,resolved_uri=resolved,coverage='verified',observed_at=now,available_at=now,capture_sha256=hashlib.sha256(raw).hexdigest(),fact_assertions={},publication_clock_note='Displayed publication clock preserved in raw page; no inferred timezone'))
        print(name,len(raw))
    except Exception as e:
        save(name+'.json',dict(source_id='weekly_'+name,uri=url,coverage='unavailable',observed_at=now,reason=type(e).__name__)); print(name,type(e).__name__)
