"""Reuse authenticated native attempt basis plus already captured FTN screens."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time,gc
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.charting_source_components import load_charting_snapshot
from backend.app.product_services.coverage_receiver_performance import VERSION as PARENT_VERSION
from backend.app.product_services.screen_matchup_response import build_screen_matchup_response
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.factual_designation import clock
root=Path('research/screen_matchup_response_20261020/v1');started=datetime.now(UTC);start=time.monotonic();outputs=[]
parents=json.loads(Path('research/coverage_receiver_performance_20261020/v1/actual_receipt.json').read_text())['outputs']
charts={r['season']:r for r in json.loads(Path('research/charting_source_components_20261020/v1/actual_validated_capture_receipt.json').read_text())['seasons']if r.get('capture_status')=='captured_immutable_existing_source_service'}
producer_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in [Path('backend/app/product_services/'+name+'.py')for name in('screen_matchup_response','charting_source_components','coverage_receiver_performance')]}

def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/screen_matchup_response')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb')as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
with Session(engine)as session:
 for entry in parents:
  year=entry['season'];read=datetime.now(UTC);ref=entry['native_ref'];p=Path(ref['path']);assert p.resolve().parent==Path('artifacts/coverage_receiver_performance').resolve()
  raw=p.read_bytes();assert len(raw)==ref['bytes']and hashlib.sha256(raw).hexdigest()==ref['sha256'];parent=json.loads(raw);del raw
  assert parent['version']==PARENT_VERSION and parent['pregame_serving_eligible']is False and parent['season']==year
  assert digest({k:v for k,v in parent.items()if k not in('semantic_sha256','provenance','evidence_use','pregame_serving_eligible','forecast')})==parent['semantic_sha256']
  assert parent['provenance']['producer_code_hashes']['backend/app/product_services/coverage_receiver_performance.py']==producer_hashes['backend/app/product_services/coverage_receiver_performance.py']
  assert clock(parent['provenance']['actual_read_at'])<=read and clock(parent['provenance']['actual_derived_at'])<=read
  snapshot=session.get(SourceSnapshot,charts[year]['snapshot_id']);chart=load_charting_snapshot(snapshot,cutoff=read)
  assert str(snapshot.content_sha256)==charts[year]['sha256']
  result=build_screen_matchup_response(parent,chart)
  result['provenance'].update(parent_ref=ref,parent_provenance=parent['provenance'],actual_read_at=read.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_hashes=producer_hashes,
   original_availability='Revised later source captures, original historical pregame availability unknown; no reconstruction claim')
  full=save(result);selected={k:v for k,v in result.items()if k not in('game_rows','profiles','event_basis','semantic_sha256','provenance')}
  for key in('game_rows','profiles'):selected[key]=[r for r in result[key]if r['team']in{'SF','WAS'}]
  gids={r['game_id']for r in selected['game_rows']};selected['event_basis']=[e for e in result['event_basis']if e['game_id']in gids]
  selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
  out=dict(season=year,parent_ref=ref,FTN_snapshot_id=str(snapshot.snapshot_id),FTN_sha256=snapshot.content_sha256,full_ref=full,selected_ref=sel,global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],
   source_teams=len(result['profiles']),team_games=len(result['game_rows']),reference_known_defenses=result['reference']['known_defenses'],reference_strong_upper=result['reference']['strong_upper_EPA_tercile'],reference_weak_lower=result['reference']['weak_lower_EPA_tercile'],
   known_offensive_screen_attempts=sum(r['offense']['known_screen_attempts']for r in result['game_rows']),unknown_screen_memberships=sum(r['offense']['unknown_screen_membership']for r in result['game_rows']),
   defined_EPA_contrasts=sum(r['strong_minus_weak_screen_EPA']is not None for r in result['profiles']),defined_completion_contrasts=sum(r['strong_minus_weak_screen_completion']is not None for r in result['profiles']),
   unknown_opponent_condition_logs=sum(len(r['unknown_opponent_condition_game_ids'])for r in result['profiles']))
  outputs.append(out);print(json.dumps(out),flush=True);del parent,chart,result,selected;gc.collect()
r=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,outputs=outputs,source_fetches=0,PBP_reads=0,parent_inflates=0,models=0,database_writes=0,
 evidence_use='historical_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False)
(root/'actual_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(stage='END',elapsed_seconds=r['elapsed_seconds'])),flush=True)
