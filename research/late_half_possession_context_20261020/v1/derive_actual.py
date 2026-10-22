from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time,csv
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import verify_snapshot_artifact
from backend.app.product_services.late_half_possession_context import load_reviewed_decision_boundary,build_late_half_context,SOURCE_FIELDS,project_late_half_source
from backend.app.product_services.drive_scoring_range import LIVE
from backend.app.product_services.factual_designation import clock
ROOT=Path('research/late_half_possession_context_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
ref=json.loads(Path('research/drive_scoring_range_20261020/v1/actual_receipt.json').read_text())['full_ref'];ranges=load_reviewed_decision_boundary(ref,cutoff=now)
source=ranges['provenance']['source_ref'];ancestor=ranges['provenance']['original_parent_provenance']['parent_ref']
p=Path(ancestor['path']).resolve();assert p.parent==Path('artifacts/opportunity_events').resolve() and p.name==ancestor['artifact_sha256']+'.json.gz'
b=p.read_bytes();assert len(b)==ancestor['compressed_bytes'] and hashlib.sha256(b).hexdigest()==ancestor['artifact_sha256']
fields=SOURCE_FIELDS
records=[];total=0
with Session(engine) as session:
 snap=session.get(SourceSnapshot,source['snapshot_id']);verify_snapshot_artifact(snap)
 assert snap.content_sha256==source['sha256']==ancestor['source_sha256'] and snap.byte_count==source['bytes']<=64*1024*1024
 assert snap.source_system=='nflreadpy' and snap.dataset=='play_by_play' and snap.source_uri==f'nflreadpy://pbp/{snap.season}' and (snap.metadata_json or {}).get('contract_id')=='operational_opportunity_source_v1'
 assert clock(snap.observed_at)<=clock(snap.captured_at)<=clock(ancestor['decision_cutoff_at'])<clock(snap.slate_lock_at)<=now
 with Path(snap.artifact_path).open(newline='') as stream:
  reader=csv.DictReader(stream);names=set(reader.fieldnames or []);assert {'order_sequence','game_half','half_seconds_remaining','qtr','yardline_100'}<=names
  for row in reader:
   total+=1
   if total>200000:raise ValueError('Bounded source rows required')
   if row.get('season_type')=='REG' and int(row['season'])*100+int(row['week'])<ranges['before_period']:records.append(project_late_half_source(row))
 assert total==snap.row_count
result=build_late_half_context(records,ranges)
result['provenance']=dict(boundary_ref=ref,boundary_semantic_sha256=ranges['semantic_sha256'],boundary_provenance=ranges['provenance'],source_ref=source,source_event_sha256=ranges['provenance']['source_event_sha256'],actual_read_at=now.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/late_half_possession_context.py').read_bytes()).hexdigest(),original_availability='Unknown; revised existing historical source and postlock feature, never original pregame proof')
def save(x):
 raw=json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/late_half_possession_context')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected=dict(result,game_rows=[g for g in result['game_rows']if g['team']in{'SF','WAS'}],profiles=[p for p in result['profiles']if p['team']in{'SF','WAS'}],selection=dict(teams=['SF','WAS'],all_global_unknown_native_incidents_retained=True,full_ref=full));sel=save(selected)
drives=[d for g in result['game_rows']for d in g['drives']]
views={field:dict(known_successes=sum(d[field]is True for d in drives if d['late_window_entry']is True),unknown_outcomes=sum(d[field]is None for d in drives if d['late_window_entry']is True),exact_game_rates=sum(g['metrics']['views'][field]['exact_per_possession_fraction']is not None for g in result['game_rows']))for field in('reached20','reached5','offensive_TD','live_FG_attempt')}
out=dict(actual_started_at=now.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,boundary_ref=ref,source_ref=source,semantic_sha256=result['semantic_sha256'],native_source_rows=len(records),game_logs=len(result['game_rows']),selected_game_logs=len(selected['game_rows']),original_drives=len(drives),known_observed_late_possessions=sum(d['late_window_entry']is True for d in drives),unknown_possible_drive_entries=sum(d['late_window_entry']is None for d in drives),unassigned_native_incidents=len(result['unassigned_native_incidents']),exact_game_possession_counts=sum(g['metrics']['exact_late_possession_count']is not None for g in result['game_rows']),views=views,source_fetches=0,database_writes=0,parent_inflations=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
