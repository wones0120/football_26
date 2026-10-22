"""Missing-only two authoritative team releases; original capture clock only."""
from pathlib import Path
from datetime import datetime,UTC
import json,time,hashlib
import requests
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import SourceCaptureService,verify_snapshot_artifact
ROOT=Path('research/documented_coordinator_change_20261020/v1');start=datetime.now(UTC);timer=time.monotonic()
urls=[('departure','https://www.neworleanssaints.com/news/new-orleans-saints-part-ways-three-assistant-coaches-carmichael-bicknell-burns'),('appointment','https://www.neworleanssaints.com/news/klint-kubiak-new-orleans-saints-offensive-coordinator-announcement')]
outputs=[]
for kind,url in urls:
 with Session(engine)as session:
  existing=session.scalars(select(SourceSnapshot).where(SourceSnapshot.source_system=='official_team',SourceSnapshot.dataset=='coordinator_announcement',SourceSnapshot.source_uri==url)).all()
  assert len(existing)<=1,'Ambiguous source revision needs explicit selection'
  fetched=False
  if existing:snapshot=existing[0]
  else:
   response=requests.get(url,timeout=(5,15),stream=True,headers={'User-Agent':'football_26 source evidence review'})
   response.raise_for_status();assert response.url==url and 'text/html'in response.headers.get('Content-Type','')
   body=bytearray()
   for block in response.iter_content(65536):
    body.extend(block);assert len(body)<=2*1024*1024,'Bounded source body exceeded'
   raw=bytes(body);assert raw and b'neworleanssaints'in raw.lower();p=ROOT/(kind+'_http_entity.html')
   if p.exists():assert p.read_bytes()==raw
   else:
    with p.open('xb')as f:f.write(raw)
    p.chmod(0o444)
   response_meta=dict(status_code=response.status_code,final_url=response.url,headers=dict(response.headers),actual_HTTP_completed_at=datetime.now(UTC).isoformat(),entity_byte_sha256=hashlib.sha256(raw).hexdigest(),entity_bytes=len(raw),publication_time='Not inferred from HTTP Date or capture; parse explicit article metadata separately')
   result=SourceCaptureService(session).capture_file(p,source_system='official_team',dataset='coordinator_announcement',season=2024,week=None,slate='offline_coordinator_change',source_license='Official team web content; copyright retained; internal immutable source evidence',source_uri=url,effective_at=None,slate_lock_at=None,media_type='text/html',observation_basis='capture_clock',metadata=dict(contract='official_team_coordinator_announcement_source_v1',team_id='NO',document_kind=kind,http=response_meta,historical_publication_not_capture=True))
   snapshot=result.snapshot;session.commit();fetched=True
  verify_snapshot_artifact(snapshot)
  outputs.append(dict(kind=kind,snapshot_id=snapshot.snapshot_id,path=snapshot.artifact_path,manifest_path=snapshot.manifest_path,sha256=snapshot.content_sha256,bytes=snapshot.byte_count,source_uri=snapshot.source_uri,source_system=snapshot.source_system,dataset=snapshot.dataset,captured_at=snapshot.captured_at.isoformat(),observed_at=snapshot.observed_at.isoformat(),effective_at=None,HTTP_fetch=fetched,metadata=snapshot.metadata_json))
out=dict(actual_started_at=start.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,sources=outputs,source_requests=sum(s['HTTP_fetch']for s in outputs),source_only=True,catalog_promotions=0,models=0)
(ROOT/'source_receipt.json').write_text(json.dumps(out,indent=2,default=str)+'\n');print(json.dumps(dict(stage='source_END',requests=out['source_requests'],elapsed_seconds=out['elapsed_seconds'],sources=[{k:s[k]for k in('kind','snapshot_id','bytes','sha256')}for s in outputs])),flush=True)
