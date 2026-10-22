from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.scoring_zone_decisions import derive_retrospective_scoring_zone_decisions
from backend.app.product_services.evaluation_record import digest
root=Path('research/scoring_zone_decisions_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
ref=json.loads(Path('research/player_opportunity_components_20261019/v1/actual_derivation_current_receipt.json').read_text())['parent_artifact_ref']
with Session(engine) as session:
 snap=session.get(SourceSnapshot,ref['source_snapshot_id']);result=derive_retrospective_scoring_zone_decisions(ref,snap,actual_read_at=now)
result['provenance']['actual_publication_at']=datetime.now(UTC).isoformat()
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=8*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/scoring_zone_decisions')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as stream:stream.write(raw)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items() if k not in {'game_rows','provenance','semantic_sha256'}};selected['game_rows']=[r for r in result['game_rows'] if r['team'] in {'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sl=save(selected)
coverage={mid:dict(observed_cells=sum(len(r['metrics'][mid]['cells']) for r in result['game_rows']),exact_positive_decision_cells=sum(c['pass_fraction'] is not None for r in result['game_rows'] for c in r['metrics'][mid]['cells']),known_pass_calls=sum(c['pass_calls'] for r in result['game_rows'] for c in r['metrics'][mid]['cells']),known_rush_calls=sum(c['rush_calls'] for r in result['game_rows'] for c in r['metrics'][mid]['cells']),unknown_coordinates=sum(r['metrics'][mid]['unknown_coordinate_events'] for r in result['game_rows']),unknown_membership=sum(c['unknown_membership_events'] for r in result['game_rows'] for c in r['metrics'][mid]['cells']),unknown_calls=sum(c['unknown_call_events'] for r in result['game_rows'] for c in r['metrics'][mid]['cells'])) for mid in ['X05-M04','X05-M05']}
r=dict(full_ref=full,selected_ref=sl,parent_artifact_ref=ref,team_games=len(result['game_rows']),selected_team_games=len(selected['game_rows']),coverage=coverage,global_semantic_sha256=result['semantic_sha256'],actual_read_at=now.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,parent_inflates=1,source_fetches=0,model_fits=0,database_writes=0,evidence_use=result['evidence_use'])
(root/'actual_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
