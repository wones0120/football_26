"""Feature-only authenticated small context composition; no parent inflation."""
from datetime import datetime,UTC
from pathlib import Path
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.drive_volume_catalog import read_drive_volume_catalog
from backend.app.product_services.evaluation_record import digest
root=Path('research/drive_volume_catalog_20261020/v1');start=time.monotonic()
original=json.loads(Path('research/environment_context_evidence_20261019/v1/actual_combined_receipt.json').read_text())
with Session(engine) as s:
 snapshot=s.get(SourceSnapshot,original['parent_artifact_ref']['source_snapshot_id'])
 result=read_drive_volume_catalog(original['full_context'],snapshot,actual_read_at=datetime.now(UTC))
result['provenance']['actual_publication_at']=datetime.now(UTC).isoformat()
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/drive_volume_catalog')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items() if k not in {'game_rows','team_windows','provenance','semantic_sha256'}}
selected['game_rows']=[r for r in result['game_rows'] if r['team'] in {'SF','WAS'}];selected['team_windows']=[r for r in result['team_windows'] if r['team'] in {'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};ref=save(selected)
receipt=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=ref,global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],game_rows=len(result['game_rows']),selected_game_rows=len(selected['game_rows']),team_windows=len(result['team_windows']),coverage={mid:dict(exact=sum(r['metrics'][mid]['value'] is not None for r in result['game_rows']),unknown_or_zero=sum(r['metrics'][mid]['value'] is None for r in result['game_rows'])) for mid in ('G01-M02','G01-M03')},original_context_ref=original['full_context'],parent_inflated=False,evidence_use=result['evidence_use'],consumer_status=result['consumer_status'])
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
