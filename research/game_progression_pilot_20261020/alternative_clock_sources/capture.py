"""Three public entity captures, exclusive destinations and one 45s job cap."""
from pathlib import Path
from datetime import datetime,UTC
from urllib.parse import urlsplit,urlunsplit
import json,signal,time
import requests
from research.game_progression_pilot_20261020.v1.prepare_integrated import ref
from research.game_progression_pilot_20261020.raw_source_feasibility.bounds import bounded_chunks

D=Path(__file__).resolve().parent
SOURCES=[('espn_summary.json','https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event=401547477',2*1024*1024),
    ('official_gamebook.pdf','https://static.clubs.nfl.com/image/upload/saints/gtzghxres7u0a4bosnue.pdf',2*1024*1024),
    ('gsis_clock_protocol.pdf','https://www.nflgsis.com/gsis/Documentation/Partners/Real-time%20Game%20Information.pdf',1024*1024)]

def without_query(url):
    p=urlsplit(url);return urlunsplit((p.scheme,p.netloc,p.path,'',''))

def main():
    start=time.monotonic()
    with (D/'CAPTURE_STARTED.json').open('x')as s:json.dump(dict(started_at=datetime.now(UTC).isoformat(),cap_seconds=45,sources=SOURCES,recipe_ref=ref(D/'RECIPE.md'),runner_ref=ref(__file__)),s,indent=2)
    def cap(*_):raise TimeoutError('45-second acquisition cap; no retry')
    old=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,45);receipts=[]
    try:
        for name,url,limit in SOURCES:
            receipt=dict(name=name,requested_url=url,max_entity_bytes=limit,started_at=datetime.now(UTC).isoformat())
            receipts.append(receipt);session=requests.Session();session.max_redirects=5
            try:
                t=time.monotonic()
                with session.get(url,stream=True,timeout=(10,10))as response:
                    receipt.update(http_status=response.status_code,content_type=response.headers.get('Content-Type'),
                        http_last_modified=response.headers.get('Last-Modified'),etag=response.headers.get('ETag'),
                        redirects=[dict(url=without_query(r.url),status=r.status_code)for r in response.history])
                    response.raise_for_status();raw=bounded_chunks(response.iter_content(65536),limit)
                with (D/name).open('xb')as sink:sink.write(raw)
                receipt.update(status='CAPTURED',source_ref=ref(D/name),retrieved_at=datetime.now(UTC).isoformat(),seconds=time.monotonic()-t)
            except (requests.RequestException,ValueError)as exc:
                receipt.update(status='FAILED_NO_RETRY',error=type(exc).__name__+': '+str(exc))
        print(json.dumps(receipts))
    finally:
        report=dict(elapsed_seconds=time.monotonic()-start,whole_job_cap_seconds=45,receipts=receipts,runner_ref=ref(__file__),new_game_scope_count=1,paid_access=False)
        with (D/'CAPTURE.json').open('x')as sink:json.dump(report,sink,indent=2);sink.write('\n')
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)

if __name__=='__main__':main()
