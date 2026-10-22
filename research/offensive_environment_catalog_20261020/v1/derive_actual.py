"""Read reviewed immutable context/source/parent bytes without parent inflation."""
from datetime import datetime,UTC
from pathlib import Path
import hashlib,json
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.offensive_environment_catalog import read_reviewed_environment_catalog
root=Path('research/offensive_environment_catalog_20261020/v1')
r=json.loads(Path('research/environment_context_evidence_20261019/v1/actual_combined_receipt.json').read_text())
with Session(engine) as s:
    snapshot=s.get(SourceSnapshot,r['parent_artifact_ref']['source_snapshot_id'])
    result=read_reviewed_environment_catalog(r['full_context'],snapshot,actual_read_at=datetime.now(UTC))
result['actual_derived_at']=datetime.now(UTC).isoformat();result['producer_code_sha256']=hashlib.sha256(Path('backend/app/product_services/offensive_environment_catalog.py').read_bytes()).hexdigest()
raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/offensive_environment_catalog')/(sha+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==raw
else:p.write_bytes(raw)
receipt=dict(actual_derived_at=result['actual_derived_at'],artifact_ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(raw)),game_rows=len(result['game_rows']),team_windows=len(result['team_windows']),known_game_values={m:sum(r['metrics'][m]['value'] is not None for r in result['game_rows']) for m in ['G01-M01','G01-M06']},known_window_values={m:sum(r['metrics'][m]['value'] is not None for r in result['team_windows']) for m in ['G01-M01','G01-M06']},semantic_sha256=result['semantic_sha256'],original_context_ref=r['full_context'],parent_inflated=False,evidence_use=result['evidence_use'],models_or_optimizer_consumed=False)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
