from pathlib import Path
from datetime import datetime,UTC
import json,csv,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import verify_snapshot_artifact
from backend.app.product_services.nws_hourly_precipitation_context import build_nws_hourly_precipitation,point_in_geometry
from backend.app.product_services.scheduled_venue_displacement import venue_for_game,kickoff_utc

ROOT=Path('research/nws_hourly_precipitation_context_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
def sha(b):return hashlib.sha256(b).hexdigest()
def auth(ref,kind):
 p=Path(ref['path']).resolve();assert p.parent==Path('artifacts',kind).resolve() and p.name==ref['sha256']+'.json'
 b=p.read_bytes();assert len(b)==ref['bytes'] and sha(b)==ref['sha256'];return json.loads(b)
def ref(p):
 b=p.read_bytes();return dict(path=str(p.resolve()),sha256=sha(b),bytes=len(b))
def save(obj):
 b=json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode();p=Path('artifacts/nws_hourly_precipitation_context')/(sha(b)+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==b
 else:
  with p.open('xb') as f:f.write(b)
  p.chmod(0o444)
 return ref(p)
parent_ref=json.loads(Path('research/scheduled_venue_displacement_20261020/v1/actual_receipt.json').read_text())['full_ref'];parent=auth(parent_ref,'scheduled_venue_displacement');provenance=parent['provenance']
assert provenance['producer_code_sha256']==sha(Path('backend/app/product_services/scheduled_venue_displacement.py').read_bytes())
registry=auth(provenance['registry_ref'],'scheduled_venue_registry')
schedule_ref=provenance['schedule_csv_ref'];schedule_path=Path(schedule_ref['path']).resolve();raw=schedule_path.read_bytes();assert len(raw)==schedule_ref['bytes'] and sha(raw)==schedule_ref['sha256']
schedule_manifest_ref=provenance['schedule_manifest_ref'];schedule_manifest_path=Path(schedule_manifest_ref['path']);b=schedule_manifest_path.read_bytes();assert len(b)==schedule_manifest_ref['bytes'] and sha(b)==schedule_manifest_ref['sha256'];schedule_manifest=json.loads(b)
assert schedule_manifest['content_sha256']==schedule_ref['sha256'];rows=list(csv.DictReader(raw.decode().splitlines()));assert len(rows)==schedule_manifest['row_count']<=50000
with Session(engine) as session:
 snapshot=session.get(SourceSnapshot,'a7a128ab-8f56-5088-8cde-b4f3412eaca5')
 if snapshot is None:raise ValueError('Original indexed NWS snapshot not found; no substitute capture permitted')
 assert snapshot.byte_count<=1024*1024 and snapshot.media_type=='application/json'
 verify_snapshot_artifact(snapshot)
 manifest_path=Path(snapshot.manifest_path);manifest=json.loads(manifest_path.read_text());payload_path=Path(snapshot.artifact_path);payload=json.loads(payload_path.read_text())
 source_index=dict(snapshot_id=snapshot.snapshot_id,source_system=snapshot.source_system,dataset=snapshot.dataset,source_uri=snapshot.source_uri,
  season=snapshot.season,week=snapshot.week,slate=snapshot.slate,sha256=snapshot.content_sha256,bytes=snapshot.byte_count,
  observed_at=snapshot.observed_at.isoformat(),captured_at=snapshot.captured_at.isoformat(),slate_lock_at=snapshot.slate_lock_at.isoformat())
 assert manifest['pre_lock'] is True and manifest['source_license']=='Official NWS public forecast'
 lock=datetime.fromisoformat(manifest['slate_lock_at'].replace('Z','+00:00'))
 candidates=[]
 for row in rows:
  if row['season']!=str(snapshot.season) or row['week']!=str(snapshot.week) or row['game_type']!='REG':continue
  kickoff=kickoff_utc(row.get('gameday'),row.get('gametime'))
  if kickoff!=lock:continue
  native=dict(row,season=int(row['season']),week=int(row['week']))
  venue,mapping=venue_for_game(native,registry)
  if venue and point_in_geometry(venue['longitude'],venue['latitude'],payload.get('geometry')) is True:
   candidates.append((native,venue,mapping,kickoff))
 assert len(candidates)==1,'Unique native schedule/game-time/venue-to-grid binding required; no city/name selection'
 game,venue,mapping,kickoff=candidates[0]
 game.update(kickoff_at=kickoff.isoformat())
 result=build_nws_hourly_precipitation(payload,source_index,game,venue,actual_cutoff=now)
 result['provenance']=dict(original_nws_source_index=source_index,original_nws_manifest_ref=ref(manifest_path),original_nws_payload_ref=ref(payload_path),
  approved_venue_parent_ref=parent_ref,registry_ref=provenance['registry_ref'],schedule_csv_ref=schedule_ref,schedule_manifest_ref=schedule_manifest_ref,
  native_schedule_row=game,native_venue_record=venue,venue_mapping_method=mapping,source_geometry=payload.get('geometry'),
  primary_probability_definition_uri='https://www.weather.gov/ppg/forecast_terms',
  actual_source_read_at=now.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),
  producer_code_sha256=sha(Path('backend/app/product_services/nws_hourly_precipitation_context.py').read_bytes()),
  source_capture_verifier_code_sha256=sha(Path('backend/app/services/source_capture.py').read_bytes()),
  chronology='NWS original forecast generated/update/capture precede kickoff; native schedule/registry attribution is later revised binding, not all-input original pregametime proof')
 result['team_contexts']=[dict(team=game[role],game_id=game['game_id'],probability_percent=result['probability_percent']) for role in ('home_team','away_team')]
 full=save(result)
 out=dict(actual_started_at=now.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,
  full_ref=full,semantic_sha256=result['semantic_sha256'],native_game_id=game['game_id'],venue_record_id=venue['registry_record_id'],
  probability_percent=result['probability_percent'],probability_fraction=result['probability_fraction'],unknown_reasons=result['unknown_reasons'],
  original_forecast_generated_at=result['original_forecast_generated_at'],original_source_capture_at=source_index['captured_at'],kickoff_at=game['kickoff_at'],
  source_observations=1,team_contexts=2,database_read_queries=1,database_writes=0,new_captures=0,source_fetches=0,parent_adapter_replays=0,parent_inflations=0,models=0)
 (ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
