"""One native-game request chain; preserve bytes and reject changed revisions."""
from pathlib import Path
from datetime import datetime,UTC
from urllib.parse import urlsplit,urlunsplit
import json,signal,time
import requests
from research.game_progression_pilot_20261020.v1.prepare_integrated import ref,load
from research.game_progression_pilot_20261020.raw_source_feasibility.bounds import bounded_chunks,verify

D=Path(__file__).resolve().parent

def clean_url(url):
    p=urlsplit(url);return urlunsplit((p.scheme,p.netloc,p.path,'',''))

def main():
    start=time.monotonic();stamp=datetime.now(UTC).isoformat()
    candidate=load(ref(D.parent/'clock_gap_investigation/SOURCE_REVIEW.json'))['one_game_candidate']
    frozen=dict(game_id=candidate['game_id'],url='https://github.com/nflverse/nflverse-pbp/releases/download/raw_pbp_2023/'+candidate['asset_name'],
        expected_sha256=candidate['displayed_sha256'],listed_updated_at=candidate['displayed_updated_at'],
        compressed_cap_bytes=1024*1024,decoded_cap_bytes=8*1024*1024,acquisition_cap_seconds=30,
        recipe_ref=ref(D/'RECIPE.md'),runner_ref=ref(__file__),bounds_ref=ref(D/'bounds.py'))
    with (D/'ACQUISITION_STARTED.json').open('x')as s:json.dump(dict(started_at=stamp,**frozen),s,indent=2)
    def cap(*_):raise TimeoutError('30-second acquisition cap; no retry')
    old=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,30)
    receipt=dict(started_at=stamp,**frozen)
    try:
        session=requests.Session();session.max_redirects=5
        with session.get(frozen['url'],stream=True,timeout=(10,10))as response:
            receipt.update(http_status=response.status_code,redirects=[dict(url=clean_url(r.url),status=r.status_code)for r in response.history],
                final_url=clean_url(response.url),http_last_modified=response.headers.get('Last-Modified'),etag=response.headers.get('ETag'))
            response.raise_for_status();raw=bounded_chunks(response.iter_content(65536),frozen['compressed_cap_bytes'])
        destination=D/candidate['asset_name']
        with destination.open('xb')as s:s.write(raw)
        receipt['source_ref']=ref(destination);verify(raw,frozen['expected_sha256'])
        receipt.update(status='ACQUIRED_HASH_MATCHED',retrieved_at=datetime.now(UTC).isoformat())
    except Exception as exc:
        receipt.update(status='FAILED_NO_RETRY',error=type(exc).__name__+': '+str(exc));raise
    finally:
        receipt['elapsed_seconds']=time.monotonic()-start
        with (D/'ACQUISITION.json').open('x')as s:json.dump(receipt,s,indent=2);s.write('\n')
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
        print(json.dumps({k:receipt[k]for k in ('status','elapsed_seconds','source_ref')if k in receipt}))

if __name__=='__main__':main()
