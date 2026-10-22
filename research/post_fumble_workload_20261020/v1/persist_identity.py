from pathlib import Path
import json,hashlib
from datetime import datetime,UTC
from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.post_fumble_identity import persist_identity_requests
root=Path('research/post_fumble_workload_20261020/v1');receipt=json.loads((root/'actual_receipt.json').read_text());ref=receipt['full_ref'];features=json.loads(Path(ref['path']).read_text())
with engine.begin() as conn:
 result=persist_identity_requests(conn,features,artifact_ref=ref)
 rows=conn.execute(text("SELECT source_record_key,source_player_key,reason_code,status FROM target.identity_quarantine WHERE source_schema='public' AND source_table='source_snapshot' AND source_record_key=ANY(:keys)"),dict(keys=[r['source_record_key'] for r in result['records']])).mappings().all()
 assert len(rows)==result['requests']
 result['durable_readback']=[dict(r) for r in rows]
result.update(actual_persisted_at=datetime.now(UTC).isoformat(),helper_code_sha256=hashlib.sha256(Path('backend/app/product_services/post_fumble_identity.py').read_bytes()).hexdigest(),original_feature_artifact_ref=ref,scope='Evidence-specific frozen parent attachment incident; not a current alias-missing assertion or alias repair')
(root/'identity_receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(requests=result['requests'],durable_readback=len(rows),aliases_changed=result['aliases_changed'])))
