from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.post_fumble_workload import derive_retrospective_post_fumble
from backend.app.product_services.evaluation_record import digest
root=Path('research/post_fumble_workload_20261020/v1');now=datetime.now(UTC);start=time.monotonic()
ref=json.loads(Path('research/player_opportunity_components_20261019/v1/actual_derivation_current_receipt.json').read_text())['parent_artifact_ref']
with Session(engine) as session:
 snapshot=session.get(SourceSnapshot,ref['source_snapshot_id'])
 result=derive_retrospective_post_fumble(ref,snapshot,actual_read_at=now)
result['provenance']['actual_publication_at']=datetime.now(UTC).isoformat()
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=8*1024*1024;sha=hashlib.sha256(raw).hexdigest();path=Path('artifacts/post_fumble_workload')/(sha+'.json');path.parent.mkdir(exist_ok=True)
 if path.exists():assert path.read_bytes()==raw
 else:
  with path.open('xb') as stream:stream.write(raw)
 return dict(path=str(path.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items() if k not in {'rows','unknown_anchor_evidence','provenance','semantic_sha256','identity_review_requests'}};selected['rows']=[r for r in result['rows'] if r['team'] in {'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};slice_ref=save(selected)
receipt=dict(full_ref=full,selected_ref=slice_ref,actor_game_anchors=len(result['rows']),selected_rows=len(selected['rows']),known_share_changes={ch:sum(r['metrics'][ch]['after_minus_before'] is not None for r in result['rows']) for ch in ['pass_attempts','rush_attempts','targets']},unknown_anchor_evidence=len(result['unknown_anchor_evidence']),identity_review_requests=result['identity_review_requests'],identity_requests_persisted=False,source_event_sha256=result['source_event_sha256'],native_order_semantic_sha256=result['native_order_semantic_sha256'],parent_artifact_ref=ref,global_semantic_sha256=result['semantic_sha256'],actual_read_at=now.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,model_fits=0,source_fetches=0,database_writes=0,evidence_use=result['evidence_use'],catalog_completion_claim=False)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
