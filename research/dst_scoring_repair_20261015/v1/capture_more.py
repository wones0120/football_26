from pathlib import Path
from datetime import datetime,UTC
import httpx,json,hashlib
from concurrent.futures import ThreadPoolExecutor
P=Path(__file__).resolve().parent
urls={'play_by_play_2024.parquet':'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2024.parquet','play_by_play_2025.parquet':'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2025.parquet','draftkings_rules.html':'https://www.draftkings.com/help/rules/1/1','draftkings_scoring_explanation.html':'https://dknetwork.draftkings.com/2022/09/19/how-reignmakers-football-scoring-works/','phi_jax_gamebook.pdf':'https://static.www.nfl.com/image/upload/v1791805919/gamecenter/aa6b5c2b-4feb-11f1-abca-2c54536568a9.pdf'}
def capture(kv):
 name,u=kv;path=P/name
 if path.exists():return name,'preserved'
 r=httpx.get(u,follow_redirects=True,timeout=120);r.raise_for_status();path.write_bytes(r.content);(P/(name+'.capture.json')).write_text(json.dumps(dict(uri=u,captured_at=datetime.now(UTC).isoformat(),headers=dict(r.headers),sha256=hashlib.sha256(r.content).hexdigest(),bytes=len(r.content)),indent=2)+'\n');return name,len(r.content)
with ThreadPoolExecutor(max_workers=4) as pool:
 for v in pool.map(capture,urls.items()):print(*v,flush=True)
