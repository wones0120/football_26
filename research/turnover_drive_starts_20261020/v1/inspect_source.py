"""Bounded original-drive acquisition field inspection, no feature promotion."""
from pathlib import Path
from datetime import datetime,UTC
from collections import Counter,defaultdict
import csv,json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import verify_snapshot_artifact
from backend.app.product_services.market_snapshots import canonical_team
from backend.app.product_services.original_drive_field_context import _integer
from backend.app.product_services.fumble_event_components import _flag
root=Path('research/turnover_drive_starts_20261020/v1');started=datetime.now(UTC);start=time.monotonic()
ref=json.loads(Path('research/drive_start_context_20261020/v1/actual_receipt.json').read_text())['full_ref'];p=Path(ref['path']);raw=p.read_bytes();assert len(raw)==ref['bytes']and hashlib.sha256(raw).hexdigest()==ref['sha256'];parent=json.loads(raw)
with Session(engine)as session:
 snapshot=session.get(SourceSnapshot,'79230705-26c3-5cbd-af43-b26c9bb4e1bb');verify_snapshot_artifact(snapshot);assert snapshot.byte_count<=64*1024*1024 and snapshot.content_sha256==parent['source']['content_sha256']
 source=dict(snapshot_id=str(snapshot.snapshot_id),sha256=snapshot.content_sha256,bytes=snapshot.byte_count,captured_at=str(snapshot.captured_at),path=snapshot.artifact_path)
physical={(g['game_id'],g['team'],d['original_drive_id']):d for g in parent['game_rows']for d in g['drives']};groups=defaultdict(lambda:defaultdict(set));seen=set();rows=0;fields=[];native_origins=Counter();flags=Counter();orders=[]
with Path(source['path']).open(newline='')as f:
 reader=csv.DictReader(f);fields=list(reader.fieldnames)
 for r in reader:
  if r['season_type']!='REG'or int(float(r['season']))*100+int(float(r['week']))>=parent['before_period']:continue
  key=(r['game_id'],str(_integer(r['play_id'])))
  if key in seen:raise ValueError('Duplicate native source play')
  seen.add(key);rows+=1
  for flag in('interception','fumble','fumble_lost','return_touchdown'):flags[flag+':'+str(_flag(r.get(flag)))]+=1
  team=canonical_team(r['posteam'])if r.get('posteam')else None;did=_integer(r.get('drive'))
  if team is None or did is None:continue
  group=(r['game_id'],team,did)
  for field in('drive_start_transition','drive_end_transition','drive_start_yard_line','drive_play_id_started','drive_play_id_ended'):
   if r.get(field)not in(None,''):groups[group][field].add(r[field])
summary={}
for field in('drive_start_transition','drive_end_transition','drive_start_yard_line','drive_play_id_started','drive_play_id_ended'):
 summary[field]=dict(known_unique=sum(len(groups[k][field])==1 for k in physical),unknown_or_conflicting=sum(len(groups[k][field])!=1 for k in physical))
for key in physical:
 values=groups[key]['drive_start_transition']
 native_origins[next(iter(values))if len(values)==1 else'UNKNOWN_OR_CONFLICT']+=1
r=dict(actual_read_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,source=source,original_drive_parent_ref=ref,before_period=parent['before_period'],prior_native_rows=rows,
 physical_original_drives=len(physical),native_acquisition_transition_counts=dict(native_origins),per_field_physical_drive_coverage=summary,raw_flag_counts=dict(flags),field_availability={k:k in fields for k in('drive_start_transition','drive_end_transition','order_sequence','return_team','fumbled_1_team','fumble_recovery_1_team','fumbled_1_player_id','fumble_recovery_1_player_id')},
 definitions_only='Native source how-offense-got-ball field verified; no after-turnover or normal feature classification yet. Typed handoff/native order/reset/first-link proof still required.',primary_dictionary='https://nflfastr.com/reference/fast_scraper.html',source_fetches=0,parent_inflates=0,database_writes=0,models=0,pregame_serving_eligible=False,evidence_use='postlock_source_inspection_not_feature_approval')
(root/'source_inspection.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
