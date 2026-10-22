"""Authenticate immutable reviewed small inputs; no event-parent inflation."""
from datetime import datetime, UTC
from pathlib import Path
import hashlib,json,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.offensive_environment_catalog import load_reviewed_environment_context
from backend.app.product_services.offensive_scoring_drive_catalog import build_offensive_scoring_drive_catalog
from backend.app.product_services import scoring_share_components,drive_volume_catalog,offensive_redzone_stalls
from backend.app.product_services.evaluation_record import digest
root=Path('research/offensive_scoring_drive_catalog_20261020/v1');now=datetime.now(UTC);start=time.monotonic()
references=[json.loads(Path(p).read_text())['full_ref'] for p in ('research/scoring_share_components_20261020/v1/actual_derivation_receipt.json','research/drive_volume_catalog_20261020/v1/actual_receipt.json','research/offensive_redzone_stalls_20261020/v1/actual_receipt.json')]
blocks=[]
for ref,folder,module,hashkey in zip(references,('scoring_share_components','drive_volume_catalog','offensive_redzone_stalls'),(scoring_share_components,drive_volume_catalog,offensive_redzone_stalls),('producer_code_sha256','producer_code_sha256','catalog_producer_sha256')):
 p=Path(ref['path']).resolve();assert p.parent==Path('artifacts',folder).resolve() and p.name==ref['sha256']+'.json' and 0<p.stat().st_size==ref['bytes']<=32*1024*1024
 raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()==ref['sha256'];block=json.loads(raw)
 assert block['provenance'][hashkey]==hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest();blocks.append(block)
original=json.loads(Path('research/environment_context_evidence_20261019/v1/actual_combined_receipt.json').read_text())
with Session(engine) as session:
 snapshot=session.get(SourceSnapshot,original['parent_artifact_ref']['source_snapshot_id']);intake=load_reviewed_environment_context(original['full_context'],snapshot,actual_read_at=now)
result=build_offensive_scoring_drive_catalog(*blocks,before_period=blocks[0]['before_period'])
lineage=result['provenance']['source_lineage'];assert lineage['snapshot_id']==str(snapshot.snapshot_id) and lineage['source_sha256']==snapshot.content_sha256 and lineage['event_receipt_sha256']==original['parent_artifact_ref']['event_receipt_sha256']
result['provenance'].update(immutable_input_refs=references,authenticated_intake=intake['provenance'],actual_read_at=now.isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/offensive_scoring_drive_catalog.py').read_bytes()).hexdigest())
def save(v):
 raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/offensive_scoring_drive_catalog')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items() if k not in {'game_rows','semantic_sha256','provenance'}};selected['game_rows']=[r for r in result['game_rows'] if r['team'] in {'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
r=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,input_refs=references,game_rows=len(result['game_rows']),selected_rows=len(selected['game_rows']),known_exact={mid:sum(row['metrics'][mid]['value'] is not None for row in result['game_rows']) for mid in ('G12-M01','G12-M02','G12-M03','G12-M06')},known_physical_offensive_TDs=sum(row['metrics']['G12-M01']['numerator']['known_physical_TDs'] or 0 for row in result['game_rows']),global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],evidence_use=result['evidence_use'],source_fetches=0,models=0,database_writes=0,parent_inflates=0)
(root/'actual_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
