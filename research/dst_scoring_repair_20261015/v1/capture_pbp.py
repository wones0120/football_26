from pathlib import Path
from datetime import datetime,UTC
import httpx,json,hashlib
P=Path(__file__).resolve().parent;url='https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2026.parquet';path=P/'play_by_play_2026.parquet'
if not path.exists():
 r=httpx.get(url,follow_redirects=True,timeout=120);r.raise_for_status();path.write_bytes(r.content);(P/'pbp_capture.json').write_text(json.dumps(dict(uri=url,final_uri=str(r.url),captured_at=datetime.now(UTC).isoformat(),headers=dict(r.headers),sha256=hashlib.sha256(r.content).hexdigest(),bytes=len(r.content)),indent=2)+'\n')
import pandas as pd
f=pd.read_parquet(path);print('rows',len(f),'weeks',f.week.value_counts().to_dict());print('columns',list(f.columns));print(f[f.week.eq(5)][['game_id','home_team','away_team']].drop_duplicates().to_string(index=False))
