import json
from pathlib import Path
from datetime import UTC,datetime
import httpx
from sqlalchemy import select
from backend.app.db import SessionLocal
from backend.app.models import OperationalJob
from backend.app.services.source_capture import SourceCaptureService
from backend.app.product_services.official_injuries import observation_clock
root=Path(__file__).resolve().parent
uris=['https://www.seahawks.com/news/jaxon-smith-njigba-good-to-go-drake-thomas-ruled-out-for-seahawks-week-6-game-at-denver','https://www.seahawks.com/team/injury-report/']
out=[]
with SessionLocal() as session:
 active=list(session.scalars(select(OperationalJob).where(OperationalJob.status.in_(['queued','running']))))
 assert not active,[(j.job_type,j.status) for j in active]
 for i,uri in enumerate(uris):
  response=httpx.get(uri,timeout=30,follow_redirects=True,headers={'Cache-Control':'no-cache'});response.raise_for_status();received=datetime.now(UTC)
  path=root/f'official_source_{i+1}.html';path.write_text(response.text)
  capture=SourceCaptureService(session).capture_file(path,source_system='seahawks_official',dataset='injury_status_research',season=2026,week=6,slate='THURSDAY_NIGHT',source_uri=uri,slate_lock_at=datetime(2026,10,16,0,15,tzinfo=UTC),source_license='Official Seattle Seahawks public injury reporting; source audit',effective_at=observation_clock(dict(response.headers),received),observation_basis='http_response_clock',media_type='text/html',metadata={'received_at':received.isoformat(),'headers':dict(response.headers),'interpretation':'Team final report explicitly clears JSN; salary-native Q retained separately. Research exception does not fabricate source status.'})
  out.append({'source_uri':uri,'received_at':received.isoformat(),'observed_at':observation_clock(dict(response.headers),received).isoformat(),'snapshot_id':str(capture.snapshot.snapshot_id)})
(root/'primary_source_captures.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
