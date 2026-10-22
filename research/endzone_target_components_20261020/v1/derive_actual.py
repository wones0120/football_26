from datetime import datetime,UTC
from pathlib import Path
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.endzone_target_components import derive_retrospective_endzone_targets
from backend.app.product_services.evaluation_record import digest
R=Path('research/endzone_target_components_20261020/v1');now=datetime.now(UTC);start=time.monotonic();ref=json.loads(Path('research/player_opportunity_components_20261019/v1/actual_derivation_current_receipt.json').read_text())['parent_artifact_ref']
with Session(engine) as session:
 snapshot=session.get(SourceSnapshot,ref['source_snapshot_id']);result=derive_retrospective_endzone_targets(ref,snapshot,actual_read_at=now)
result['provenance']['actual_publication_at']=datetime.now(UTC).isoformat()
def save(v):
 raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=8*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/endzone_target_components')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items() if k not in {'provenance','semantic_sha256'}}
for field in ('actor_game_rows','team_game_rows','unattributed_events','native_attachment_unknown_rows'):selected[field]=[r for r in result[field] if r['team'] in {'SF','WAS'}]
selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sl=save(selected)
r=dict(full_ref=full,selected_ref=sl,parent_ref=ref,actor_games=len(result['actor_game_rows']),selected_actor_games=len(selected['actor_game_rows']),exact_actor_counts=sum(r['value'] is not None for r in result['actor_game_rows']),team_games=len(result['team_game_rows']),exact_team_counts=sum(r['value'] is not None for r in result['team_game_rows']),known_team_endzone_targets=sum(r['known_endzone_targets'] for r in result['team_game_rows']),unknown_team_endzone_events=sum(r['unknown_endzone_target_events'] for r in result['team_game_rows']),unattributed_events=len(result['unattributed_events']),native_attachment_unknown_rows=result['native_attachment_unknown_rows'],identity_review_requests=result['identity_review_requests'],global_semantic_sha256=result['semantic_sha256'],actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,parent_inflates=1,source_fetches=0,model_fits=0,database_writes=0,evidence_use=result['evidence_use'])
(R/'actual_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
