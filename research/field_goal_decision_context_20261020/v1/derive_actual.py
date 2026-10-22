from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,csv,time
from backend.app.product_services.field_goal_decision_context import build_field_goal_decision_context,load_reviewed_third_failure_context,project_context_source,SOURCE_FIELDS
ROOT=Path('research/field_goal_decision_context_20261020/v1');started=datetime.now(UTC);tick=time.monotonic()
def sha(b):return hashlib.sha256(b).hexdigest()
ref=json.loads(Path('research/third_down_decision_context_20261020/v1/actual_receipt.json').read_text())['full_ref'];parent=load_reviewed_third_failure_context(ref,cutoff=started)
source=parent['provenance']['source_ref'];p=Path(source['path']);raw=p.read_bytes();assert len(raw)==source['bytes']<=64*1024*1024 and sha(raw)==source['sha256'];del raw
assert source['sha256']==parent['provenance']['boundary_provenance']['original_parent_provenance']['parent_ref']['source_sha256']
records=[];total=0
with p.open(newline='') as f:
 reader=csv.DictReader(f);assert set(SOURCE_FIELDS)<=set(reader.fieldnames)
 for r in reader:
  total+=1;assert total<=200000
  if r['season_type']=='REG' and int(r['season'])*100+int(r['week'])<parent['before_period']:records.append(project_context_source(r))
assert total==16212 and len(records)==13842
result=build_field_goal_decision_context(records,parent)
helpers=['third_down_decision_context','late_game_market_response','drive_scoring_range','original_drive_field_context','defense_context_evidence','market_snapshots']
result['provenance']=dict(reviewed_anchor_parent_ref=ref,parent_semantic_sha256=parent['semantic_sha256'],parent_publication_at=parent['provenance']['actual_publication_at'],source_ref=source,source_event_sha256=parent['provenance']['source_event_sha256'],original_source_clocks=parent['provenance'],actual_read_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_sha256=sha(Path('backend/app/product_services/field_goal_decision_context.py').read_bytes()),helper_sha256={name:sha(Path('backend/app/product_services/'+name+'.py').read_bytes()) for name in helpers},source_adapter_replays=0,database_reads=0,database_writes=0,new_captures=0,parent_inflations=0,models=0,original_availability='Revised historical source and postlock derived feature; original publication/full-game completeness unknown')
def save(x):
 b=json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode();p=Path('artifacts/field_goal_decision_context')/(sha(b)+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==b
 else:
  with p.open('xb') as f:f.write(b)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha(b),bytes=len(b))
full=save(result);selected=dict(result,game_rows=[g for g in result['game_rows']if g['team']in{'SF','WAS'}],profiles=[g for g in result['profiles']if g['team']in{'SF','WAS'}],anchor_basis=[g for g in result['anchor_basis']if g['team']in{'SF','WAS'}],selection=dict(teams=['SF','WAS'],full_ref=full));sel=save(selected)
def contrasts(rows):return sum(any(v is not None for v in c['all_anchor_frequency_differences'].values()) for g in rows for c in g['contrasts'])
out=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-tick,full_ref=full,selected_ref=sel,parent_ref=ref,source_ref=source,semantic_sha256=result['semantic_sha256'],native_source_rows=len(records),game_logs=len(result['game_rows']),profiles=len(result['profiles']),known_anchors=sum(b['eligible_anchor']is True for b in result['anchor_basis']),possible_unknown_anchors=sum(b['eligible_anchor']is None for b in result['anchor_basis']),exact_nonempty_game_cells=sum(c['all_anchor_frequencies']is not None for g in result['game_rows'] for c in g['cells']),exact_nonempty_profile_cells=sum(c['all_anchor_frequencies']is not None for g in result['profiles'] for c in g['cells']),exact_game_contrasts=contrasts(result['game_rows']),exact_profile_contrasts=contrasts(result['profiles']),source_adapter_replays=0,database_reads=0,database_writes=0,new_captures=0,parent_inflations=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
