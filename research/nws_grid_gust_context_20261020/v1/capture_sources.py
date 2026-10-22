"""At most two original NWS requests for one upcoming native game; no fallback search."""
from pathlib import Path
from datetime import datetime,UTC,timedelta
import csv,json,hashlib,time
import requests
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import SourceCaptureService,verify_snapshot_artifact
from backend.app.product_services.scheduled_venue_displacement import venue_for_game,kickoff_utc
from backend.app.product_services.nws_hourly_precipitation_context import _time
ROOT=Path('research/nws_grid_gust_context_20261020/v1');started=datetime.now(UTC);timer=time.monotonic()
def read(r):
 b=Path(r['path']).read_bytes();assert len(b)==r['bytes']and hashlib.sha256(b).hexdigest()==r['sha256'];return b
parent_ref=json.loads(Path('research/scheduled_venue_displacement_20261020/v1/actual_receipt.json').read_text())['full_ref'];parent=json.loads(read(parent_ref));pr=parent['provenance'];registry=json.loads(read(pr['registry_ref']));rows=list(csv.DictReader(read(pr['schedule_csv_ref']).decode().splitlines()));candidates=[]
for row in rows:
 if row['game_type']!='REG':continue
 kickoff=kickoff_utc(row.get('gameday'),row.get('gametime'))
 if kickoff is None or not started+timedelta(hours=1)<kickoff<started+timedelta(days=7):continue
 native=dict(row,season=int(row['season']),week=int(row['week']));venue,method=venue_for_game(native,registry)
 if venue and venue['coordinate_source_uri']and -125<venue['longitude']<-66 and 24<venue['latitude']<50:candidates.append((kickoff,native,venue,method))
assert candidates,'No supported upcoming native game/venue; do not fetch arbitrary location'
candidates.sort(key=lambda x:(x[0],x[1]['game_id']));kickoff,game,venue,mapping=candidates[0];game['kickoff_at']=kickoff.isoformat()
# No outcome-dependent location search. The first eligible scheduled kickoff is fixed before querying forecasts.
urls=[('point','https://api.weather.gov/points/'+f"{venue['latitude']:.4f},{venue['longitude']:.4f}",'grid_point_mapping')];sources=[];payloads={}
for kind,url,dataset in urls:
 with Session(engine)as session:
  existing=session.scalars(select(SourceSnapshot).where(SourceSnapshot.source_system=='nws',SourceSnapshot.dataset==dataset,SourceSnapshot.source_uri==url,SourceSnapshot.season==game['season'],SourceSnapshot.week==game['week'])).all();assert len(existing)<=1,'Ambiguous current source revision'
  fetched=False
  if existing:snapshot=existing[0]
  else:
   response=requests.get(url,timeout=(5,15),stream=True,headers={'User-Agent':'football_26 feature source research','Accept':'application/geo+json'});response.raise_for_status();assert response.url==url
   b=bytearray()
   for block in response.iter_content(65536):b.extend(block);assert len(b)<=1024*1024,'Bounded JSON exceeded'
   raw=bytes(b);payload=json.loads(raw);assert isinstance(payload,dict);path=ROOT/(kind+'_http_entity.json')
   if path.exists():assert path.read_bytes()==raw
   else:
    with path.open('xb')as f:f.write(raw)
    path.chmod(0o444)
   updated=_time(payload.get('properties',{}).get('updateTime'))if kind=='grid'else None
   result=SourceCaptureService(session).capture_file(path,source_system='nws',dataset=dataset,season=game['season'],week=game['week'],slate='offline_grid_gust',source_license='Official NWS open forecast',source_uri=url,effective_at=updated,slate_lock_at=kickoff,media_type='application/json',observation_basis='capture_clock',metadata=dict(contract='nws_grid_gust_source_v1',kind=kind,native_game_id=game['game_id'],venue_record_id=venue['registry_record_id'],http=dict(status=response.status_code,headers=dict(response.headers),final_url=response.url,actual_HTTP_completed_at=datetime.now(UTC).isoformat()),original_issuance_at=None))
   snapshot=result.snapshot;session.commit();fetched=True
  verify_snapshot_artifact(snapshot);raw=Path(snapshot.artifact_path).read_bytes();payloads[kind]=json.loads(raw)
  sources.append(dict(kind=kind,snapshot_id=snapshot.snapshot_id,path=snapshot.artifact_path,manifest_path=snapshot.manifest_path,sha256=snapshot.content_sha256,bytes=snapshot.byte_count,source_uri=snapshot.source_uri,source_system=snapshot.source_system,dataset=snapshot.dataset,season=snapshot.season,week=snapshot.week,observed_at=snapshot.observed_at.isoformat(),captured_at=snapshot.captured_at.isoformat(),snapshot_effective_at=snapshot.effective_at.isoformat(),slate_lock_at=snapshot.slate_lock_at.isoformat(),HTTP_fetch=fetched))
 if kind=='point':
  grid_url=payloads[kind].get('properties',{}).get('forecastGridData');import re
  assert isinstance(grid_url,str)and re.fullmatch(r'https://api\.weather\.gov/gridpoints/[A-Z]{3}/\d+,\d+',grid_url),'Native grid href missing; no invented office/location'
  urls.append(('grid',grid_url,'grid_gust_forecast'))
out=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,sources=sources,native_game=game,native_venue=venue,mapping_method=mapping,approved_schedule_parent_ref=parent_ref,schedule_ref=pr['schedule_csv_ref'],registry_ref=pr['registry_ref'],source_requests=sum(s['HTTP_fetch']for s in sources),source_only=True,models=0)
(ROOT/'source_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(dict(stage='source_END',elapsed_seconds=out['elapsed_seconds'],requests=out['source_requests'],game_id=game['game_id'],sources=sources)))
