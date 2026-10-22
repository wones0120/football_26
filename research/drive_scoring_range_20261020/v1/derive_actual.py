from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time,csv
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import verify_snapshot_artifact
from backend.app.product_services.drive_scoring_range import load_reviewed_range_component,build_drive_scoring_range,LIVE
from backend.app.product_services.scoreboard_result_features import read_indexed_scoreboard
from backend.app.product_services.factual_designation import clock
ROOT=Path('research/drive_scoring_range_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
folders={'original_drive_field_context':'drive_start_context','explosive_touchdown_features':'explosive_touchdown_features','fumble_event_components':'fumble_event_components','scoreboard_result_features':'scoreboard_result_features'}
refs={};inputs={}
for module,folder in folders.items():
 ref=json.loads((Path('research')/(folder+'_20261020')/'v1'/'actual_receipt.json').read_text())['full_ref'];refs[module]=ref;inputs[module]=load_reviewed_range_component(ref,module,cutoff=now)
o=inputs['original_drive_field_context'];s=inputs['explosive_touchdown_features'];f=inputs['fumble_event_components'];scores=inputs['scoreboard_result_features'];ancestor=o['provenance']['parent_ref']
assert s['provenance']['parent_ref']==ancestor
p=Path(ancestor['path']).resolve();assert p.parent==Path('artifacts/opportunity_events').resolve() and p.name==ancestor['artifact_sha256']+'.json.gz' and ancestor['compressed_bytes']<=16*1024*1024
b=p.read_bytes();assert len(b)==ancestor['compressed_bytes'] and hashlib.sha256(b).hexdigest()==ancestor['artifact_sha256']
fields=set(LIVE)|{'game_id','play_id','season','week','season_type','posteam','defteam','drive','order_sequence','game_half','qtr','half_seconds_remaining','game_seconds_remaining','yardline_100','drive_end_yard_line','drive_end_transition','play_type','play_type_nfl','no_play','quarter_end','field_goal_result','punt_blocked','fourth_down_failed','down','desc'}
score_refs=[]
with Session(engine) as session:
 snap=session.get(SourceSnapshot,ancestor['source_snapshot_id']);verify_snapshot_artifact(snap)
 assert snap.byte_count<=64*1024*1024 and snap.content_sha256==ancestor['source_sha256']
 assert snap.source_system=='nflreadpy' and snap.dataset=='play_by_play' and snap.source_uri==f'nflreadpy://pbp/{snap.season}' and (snap.metadata_json or {}).get('contract_id')=='operational_opportunity_source_v1'
 assert clock(snap.observed_at)<=clock(snap.captured_at)<=clock(ancestor['decision_cutoff_at'])<clock(snap.slate_lock_at)<=now
 for source in (o['source'],s['source'],f['provenance']['source']):assert (source['snapshot_id'],source['content_sha256'])==(str(snap.snapshot_id),snap.content_sha256)
 c=scores['provenance']['corroboration_source'];assert (c['pbp_snapshot_id'],c['pbp_sha256'])==(str(snap.snapshot_id),snap.content_sha256)
 for r in scores['provenance']['scoreboard_sources']:
  observed=read_indexed_scoreboard(session.get(SourceSnapshot,r['snapshot_id']),actual_read_at=now);assert observed['source_ref']['sha256']==r['sha256'];score_refs.append(observed['source_ref'])
 records=[];total=0
 with Path(snap.artifact_path).open(newline='') as stream:
  reader=csv.DictReader(stream);names=set(reader.fieldnames or []);assert {'drive_end_yard_line','game_half','half_seconds_remaining','game_seconds_remaining','order_sequence'}<=names
  for row in reader:
   total+=1
   if total>200000:raise ValueError('Bounded source row cardinality required')
   if row.get('season_type')=='REG' and int(row['season'])*100+int(row['week'])<o['before_period']:records.append({k:row[k] if row[k]!='' else None for k in fields&names})
 assert total==snap.row_count
 source_ref=dict(snapshot_id=str(snap.snapshot_id),sha256=snap.content_sha256,bytes=snap.byte_count,source_uri=snap.source_uri,path=snap.artifact_path,observed_at=snap.observed_at.isoformat(),captured_at=snap.captured_at.isoformat())
result=build_drive_scoring_range(records,o,s,f,scores,range_yards=35)
result['provenance']=dict(input_refs=refs,source_ref=source_ref,source_event_sha256=o['source_event_sha256'],score_source_refs=score_refs,
 original_parent_provenance=o['provenance'],actual_read_at=now.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),
 producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/drive_scoring_range.py').read_bytes()).hexdigest(),
 native_physical_helper_sha256=hashlib.sha256(Path('backend/app/product_services/turnover_drive_start_context.py').read_bytes()).hexdigest(),
 original_availability='Unknown; existing revised evidence and new postlock nominal-site feature, not original pregame intake')
raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();path=Path('artifacts/drive_scoring_range')/(sha+'.json');path.parent.mkdir(exist_ok=True)
if path.exists():assert path.read_bytes()==raw
else:
 with path.open('xb') as stream:stream.write(raw)
 path.chmod(0o444)
ref=dict(path=str(path.resolve()),sha256=sha,bytes=len(raw));drives=[d for g in result['game_rows'] for d in g['drives']]
out=dict(completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=ref,input_refs=refs,source_ref=source_ref,native_game_sides=len(result['game_rows']),original_drives=len(drives),
 known_in_range_decisions=sum(d['nominal_range_terminal_decision'] is True for d in drives),unknown_drive_decisions=sum(d['nominal_range_terminal_decision'] is None for d in drives),
 exact_game_counts=sum(g['metrics']['exact_observed_game_count'] is not None for g in result['game_rows']),verified_terminal_classes={t:sum(d['verified_terminal_class']==t for d in drives) for t in sorted({d['verified_terminal_class'] for d in drives if d['verified_terminal_class']})},
 semantic_sha256=result['semantic_sha256'],source_fetches=0,database_writes=0,parent_inflations=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
