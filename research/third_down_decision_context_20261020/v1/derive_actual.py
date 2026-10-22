from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time,csv
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import verify_snapshot_artifact
from backend.app.product_services.third_down_decision_context import load_reviewed_decision_boundary,build_third_down_decisions,SOURCE_FIELDS,project_decision_source
from backend.app.product_services.drive_scoring_range import LIVE
from backend.app.product_services.factual_designation import clock
ROOT=Path('research/third_down_decision_context_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
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
  reader=csv.DictReader(stream);names=set(reader.fieldnames or []);assert {'third_down_failed','third_down_converted','order_sequence','game_half','first_down_penalty'}<=names
  for row in reader:
   total+=1
   if total>200000:raise ValueError('Bounded source rows required')
   if row.get('season_type')=='REG' and int(row['season'])*100+int(row['week'])<ranges['before_period']:records.append(project_decision_source(row))
 assert total==snap.row_count
result=build_third_down_decisions(records,ranges)
result['provenance']=dict(boundary_ref=ref,boundary_semantic_sha256=ranges['semantic_sha256'],boundary_provenance=ranges['provenance'],source_ref=source,source_event_sha256=ranges['provenance']['source_event_sha256'],actual_read_at=now.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/third_down_decision_context.py').read_bytes()).hexdigest(),original_availability='Unknown; revised existing historical source and postlock feature, never original pregame proof')
def save(x):
 raw=json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/third_down_decision_context')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected=dict(result,game_rows=[g for g in result['game_rows'] if g['team'] in {'SF','WAS'}],team_profiles=[p for p in result['team_profiles'] if p['team'] in {'SF','WAS'}],selection=dict(teams=['SF','WAS'],global_unknown_native_anchor_incidents_retained=True,full_ref=full));sel=save(selected)
from collections import Counter
anchors=[a for g in result['game_rows'] for a in g['third_failure_anchors']]
out=dict(completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,boundary_ref=ref,source_ref=source,semantic_sha256=result['semantic_sha256'],native_source_rows=len(records),game_logs=len(result['game_rows']),selected_game_logs=len(selected['game_rows']),known_anchors=len(anchors),unknown_possible_anchor_rows=len(result['unknown_native_anchor_incidents']),known_categories=dict(Counter(a['outcome_category'] for a in anchors if a['outcome_category'])),unknown_outcomes=sum(a['outcome_category'] is None for a in anchors),exact_game_categorical_frequencies=sum(g['metrics']['all_anchor_categorical_frequencies'] is not None for g in result['game_rows']),exact_pooled_profiles=sum(p['metrics']['all_anchor_categorical_frequencies'] is not None for p in result['team_profiles']),unbound_native_offense_sides=result['unbound_native_offense_sides'],source_fetches=0,database_writes=0,parent_inflations=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
