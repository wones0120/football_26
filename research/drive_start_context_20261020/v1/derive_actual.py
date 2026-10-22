from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.original_drive_field_context import derive_retrospective_original_drives
from backend.app.product_services.evaluation_record import digest
root=Path('research/drive_start_context_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
ref=json.loads(Path('research/player_opportunity_components_20261019/v1/actual_derivation_current_receipt.json').read_text())['parent_artifact_ref']
with Session(engine) as session:
 snap=session.get(SourceSnapshot,ref['source_snapshot_id']);result=derive_retrospective_original_drives(ref,snap,actual_read_at=now)
result['provenance']['actual_publication_at']=datetime.now(UTC).isoformat()
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=8*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/original_drive_field_context')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as stream:stream.write(raw)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items() if k not in {'game_rows','provenance','semantic_sha256'}};selected['game_rows']=[r for r in result['game_rows'] if r['team'] in {'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sl=save(selected)
coverage={'X05-M01':dict(exact_game_distributions=sum(r['metrics']['X05-M01']['exact_histogram'] is not None for r in result['game_rows']),known_start_drives=sum(r['metrics']['X05-M01']['known_start_drives'] for r in result['game_rows'])), 'X05-M02':dict(exact_game_rates=sum(r['metrics']['X05-M02']['value'] is not None for r in result['game_rows']),known_reaches=sum(r['metrics']['X05-M02']['known_reaches'] for r in result['game_rows']),known_outcomes=sum(r['metrics']['X05-M02']['known_reach_outcomes'] for r in result['game_rows']))}
r=dict(full_ref=full,selected_ref=sl,parent_artifact_ref=ref,team_games=len(result['game_rows']),selected_team_games=len(selected['game_rows']),coverage=coverage,global_semantic_sha256=result['semantic_sha256'],actual_read_at=now.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,parent_inflates=1,source_fetches=0,model_fits=0,database_writes=0,evidence_use=result['evidence_use'])
(root/'actual_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
