from pathlib import Path
from datetime import datetime,UTC
from collections import defaultdict
import csv,json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import verify_snapshot_artifact
from backend.app.product_services.original_drive_field_context import _field,_integer
from backend.app.product_services.market_snapshots import canonical_team
from backend.app.product_services.defense_context_evidence import _number
ROOT=Path('research/drive_scoring_range_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
r=json.loads(Path('research/drive_start_context_20261020/v1/actual_receipt.json').read_text());ref=r['full_ref'];b=Path(ref['path']).read_bytes();assert len(b)==ref['bytes'] and hashlib.sha256(b).hexdigest()==ref['sha256'];original=json.loads(b)
fields=['game_id','play_id','season','week','season_type','posteam','drive','order_sequence','game_half','qtr','yardline_100','end_yard_line','drive_end_yard_line','drive_end_transition','play_type','play_type_nfl','kick_distance','field_goal_attempt','field_goal_result','punt_attempt','interception','fumble_lost','touchdown','desc']
with Session(engine) as session:
 s=session.get(SourceSnapshot,'79230705-26c3-5cbd-af43-b26c9bb4e1bb');verify_snapshot_artifact(s)
 assert str(s.snapshot_id)==original['source']['snapshot_id'] and s.content_sha256==original['source']['content_sha256']
 rows=[];count=0
 with Path(s.artifact_path).open(newline='') as f:
  for x in csv.DictReader(f):
   count+=1
   if x['season_type']=='REG' and int(x['season'])*100+int(x['week'])<202606:rows.append({k:x.get(k) for k in fields})
 assert count==s.row_count
 source=dict(snapshot_id=str(s.snapshot_id),sha256=s.content_sha256,bytes=s.byte_count,path=s.artifact_path,observed_at=s.observed_at.isoformat(),captured_at=s.captured_at.isoformat())
idx={};groups=defaultdict(list)
for x in rows:
 key=(x['game_id'],_integer(x['play_id']));assert key not in idx;idx[key]=x
 if x['posteam'] not in ('',None):groups[(x['game_id'],canonical_team(x['posteam']),_integer(x['drive']))].append(x)
proof=[];summary=defaultdict(lambda:dict(drives=0,terminal_verified=0,end_equals_last_preLOS=0,end_equals_last_postfield=0,known_end=0,examples=[]))
for g in original['game_rows']:
 for d in g['drives']:
  gid,team=g['game_id'],g['team'];raw=groups[(gid,team,d['original_drive_id'])];ends=sorted({x['drive_end_yard_line'] for x in raw if x['drive_end_yard_line'] not in ('',None)})
  pair={canonical_team(x) for x in gid.split('_')[2:]};end=_field(ends[0],team,pair) if len(ends)==1 else None
  last=idx.get((gid,d['source_last_play_id']));first=idx.get((gid,d['source_first_play_id']))
  item=dict(native_game_id=gid,team=team,original_drive_id=d['original_drive_id'],source_end_fields=ends,source_end_yardline100=end,raw_end_transitions=d['raw_end_transitions'],terminal_verified=d['terminal_verified'],native_boundary_order_verified=d['native_boundary_order_verified'],first_source_row=first,last_source_row=last)
  proof.append(item);tag='|'.join(d['raw_end_transitions']);v=summary[tag];v['drives']+=1;v['terminal_verified']+=d['terminal_verified'];v['known_end']+=end is not None
  if last and end is not None:
   v['end_equals_last_preLOS']+=end==_number(last['yardline_100']);v['end_equals_last_postfield']+=end==_field(last['end_yard_line'],team,pair)
  if len(v['examples'])<3:v['examples'].append(item)
out=dict(inspected_at=now.isoformat(),elapsed_seconds=time.monotonic()-start,parent_ref=ref,source_ref=source,original_drive_rows=len(proof),raw_REG_rows=len(rows),by_terminal=summary,source_inspection_only=True,catalog_ids_completed=[],models=0,source_fetches=0,parent_inflations=0,database_writes=0)
(ROOT/'source_inspection.json').write_text(json.dumps(out,indent=2)+'\n');(ROOT/'endpoint_proofs.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({k:{q:z for q,z in v.items() if q!='examples'} for k,v in summary.items()}));print('elapsed',time.monotonic()-start)
