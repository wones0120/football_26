"""Missing-only free completed-result capture and explicit retrospective derivation."""
from pathlib import Path
from datetime import datetime,UTC
import hashlib,json,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import SourceCaptureService
from backend.app.product_services.scoreboard_result_features import capture_scoreboard_results,read_indexed_scoreboard,normalize_completed_scores,build_opponent_team_point_distributions,read_score_corroboration
from backend.app.product_services.evaluation_record import digest
root=Path('research/scoreboard_result_features_20261020/v1');start=time.monotonic();observed=datetime.now(UTC);inventory=json.loads((root/'existing_source_inventory.json').read_text())
all_rows=[];used=[];captures=[];errors=[];progress=[]
with Session(engine)as session:
 schedule_source=session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b');pbp=session.get(SourceSnapshot,'79230705-26c3-5cbd-af43-b26c9bb4e1bb')
 schedule,proofs,corroboration_source=read_score_corroboration(schedule_source,pbp,before_period=202606,actual_read_at=observed)
 for week in range(1,6):
  existing=next((r for r in inventory['matching_indexed_snapshots']if r['week']==week),None);old_rows=[]
  if existing:
   try:
    snapshot=session.get(SourceSnapshot,existing['snapshot_id']);loaded=read_indexed_scoreboard(snapshot,actual_read_at=datetime.now(UTC))
    old_rows=normalize_completed_scores(loaded['payload'],schedule,season=2026,week=week,observed_at=loaded['observed_at'],source_ref=loaded['source_ref'])
    all_rows.extend(old_rows);used.append(dict(kind='existing_original_source',**loaded['source_ref']))
   except Exception as exc:errors.append(dict(week=week,stage='existing_source_validation',error_type=type(exc).__name__,error=str(exc)[:500]))
  need=not old_rows or any(not r['completed_score_eligible']for r in old_rows)
  if need:
   try:
    capture=capture_scoreboard_results(SourceCaptureService(session),season=2026,week=week,slate_lock_at=datetime(2026,10,20,0,15,tzinfo=UTC));session.commit()
    snapshot=capture.snapshot;loaded=read_indexed_scoreboard(snapshot,actual_read_at=datetime.now(UTC))
    rows=normalize_completed_scores(loaded['payload'],schedule,season=2026,week=week,observed_at=loaded['observed_at'],source_ref=loaded['source_ref'])
    all_rows.extend(rows);used.append(dict(kind='new_missing_completion_source',**loaded['source_ref']))
    captures.append(dict(week=week,source_ref=loaded['source_ref'],artifact_path=snapshot.artifact_path,
      completed_native_games=sum(r['completed_score_eligible']for r in rows),unknown_native_games=sum(not r['completed_score_eligible']for r in rows),source_pre_lock=capture.pre_lock))
   except Exception as exc:
    session.rollback();errors.append(dict(week=week,stage='missing_completion_capture',error_type=type(exc).__name__,error=str(exc)[:500]))
  progress.append(dict(week=week,existing_source_reused=bool(old_rows),capture_needed=need,elapsed_seconds=time.monotonic()-start))
  (root/'capture_progress.json').write_text(json.dumps(dict(progress=progress,captures=captures,errors=errors),indent=2)+'\n')
  print(json.dumps(progress[-1]),flush=True)
result=build_opponent_team_point_distributions(all_rows,proofs,before_period=202606)
result['provenance']=dict(scoreboard_sources=used,corroboration_source=corroboration_source,
 producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/scoreboard_result_features.py').read_bytes()).hexdigest(),
 actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat())
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/scoreboard_result_features')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb')as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items()if k not in {'game_rows','team_distributions','semantic_sha256','provenance'}}
selected['game_rows']=[r for r in result['game_rows']if {r['home_team'],r['away_team']}&{'SF','WAS'}]
selected['team_distributions']=[r for r in result['team_distributions']if r['team']in {'SF','WAS'}]
selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
receipt=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,
 global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],
 native_games=len(result['game_rows']),exact_completed_games=sum(r['exact_completed_score']is not None for r in result['game_rows']),
 unknown_games=sum(r['exact_completed_score']is None for r in result['game_rows']),team_profiles=len(result['team_distributions']),
 exact_team_distributions=sum(r['mean_opponent_real_points']is not None for r in result['team_distributions']),
 selected_games=len(selected['game_rows']),selected_team_profiles=len(selected['team_distributions']),
 captures=captures,source_reuse=used,errors=errors,parent_inflates=0,models=0,
 evidence_use=result['evidence_use'],pregame_serving_eligible=False)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(dict(status='complete',native_games=receipt['native_games'],exact_completed_games=receipt['exact_completed_games'],captures=len(captures),errors=errors)),flush=True)
