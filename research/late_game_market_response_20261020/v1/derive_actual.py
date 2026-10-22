from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time,csv
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import verify_snapshot_artifact
from backend.app.product_services.third_down_decision_context import load_reviewed_decision_boundary
from backend.app.product_services.late_game_market_response import build_late_game_market_response,SOURCE_FIELDS,project_late_market_source
from backend.app.product_services.workload_market_contexts import load_archived_market_context
from backend.app.product_services.drive_scoring_range import LIVE
from backend.app.product_services.factual_designation import clock
ROOT=Path('research/late_game_market_response_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
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
  reader=csv.DictReader(stream);names=set(reader.fieldnames or []);assert {'order_sequence','game_half','half_seconds_remaining','qtr','score_differential','posteam_score','defteam_score'}<=names
  for row in reader:
   total+=1
   if total>200000:raise ValueError('Bounded source rows required')
   if row.get('season_type')=='REG' and int(row['season'])*100+int(row['week'])<ranges['before_period']:records.append(project_late_market_source(row))
 assert total==snap.row_count
 schedule,market=load_archived_market_context(session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b'),before_period=ranges['before_period'],cutoff=now)
result=build_late_game_market_response(records,ranges,market)
result['provenance']=dict(market_source=market['provenance'],market_semantic_sha256=market['semantic_sha256'],market_definition=dict(version=market['version'],sign_transform=market['sign_transform'],original_quote_at=market['original_quote_at'],original_decision_availability=market['original_decision_availability']),boundary_ref=ref,boundary_semantic_sha256=ranges['semantic_sha256'],boundary_provenance=ranges['provenance'],source_ref=source,source_event_sha256=ranges['provenance']['source_event_sha256'],actual_read_at=now.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/late_game_market_response.py').read_bytes()).hexdigest(),original_availability='Unknown; revised existing historical source and postlock feature, never original pregame proof')
def save(x):
 raw=json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/late_game_market_response')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected=dict(result,game_rows=[g for g in result['game_rows']if g['team']in{'SF','WAS'}],profiles=[p for p in result['profiles']if p['team']in{'SF','WAS'}],selection=dict(teams=['SF','WAS'],global_native_event_drive_and_unassigned_evidence_retained=True,full_ref=full));sel=save(selected)
def contrast_count(field,drive=False):
 return sum(c['values'][field]is not None for p in result['profiles']for c in p['drive_contrasts'if drive else'play_contrasts'])
out=dict(actual_started_at=now.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,boundary_ref=ref,source_ref=source,market_source=market['provenance'],semantic_sha256=result['semantic_sha256'],native_source_rows=len(records),game_logs=len(result['game_rows']),selected_game_logs=len(selected['game_rows']),native_late_physical_events=len(result['event_basis']),known_late_physical_events=sum(e['late_physical_membership']is True for e in result['event_basis']),unknown_late_physical_events=sum(e['late_physical_membership']is None for e in result['event_basis']),known_late_original_possessions=sum(d['late_entry']is True for d in result['drive_basis']),unknown_late_original_possessions=sum(d['late_entry']is None for d in result['drive_basis']),unassigned_drive_incidents=len(result['unassigned_drive_incidents']),exact_profile_play_contrasts={f:contrast_count(f)for f in('dropbacks_fraction','rushes_fraction','kneel_fraction')},exact_profile_drive_contrasts={f:contrast_count(f,True)for f in('TD_fraction','FG_fraction')},source_fetches=0,database_writes=0,parent_inflations=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
