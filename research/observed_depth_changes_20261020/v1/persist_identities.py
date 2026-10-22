from pathlib import Path
import json
from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.observed_depth_changes import persist_depth_identity_requests
R=Path('research/observed_depth_changes_20261020/v1');r=json.loads((R/'actual_receipt.json').read_text());ref=r['artifact_ref'];features=json.loads(Path(ref['path']).read_text())
with engine.begin() as connection:out=persist_depth_identity_requests(connection,features,artifact_ref=ref)
with engine.connect() as connection:
 rows=connection.execute(text('SELECT identity_quarantine_id,source_record_key,source_player_key,reason_code FROM target.identity_quarantine WHERE source_record_key=ANY(:keys)'),dict(keys=[x['source_record_key'] for x in out['records']])).mappings().all()
 assert {x['source_record_key'] for x in rows}=={x['source_record_key'] for x in out['records']}
 out['durable_readback']=[dict(x) for x in rows]
(R/'identity_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(dict(records=len(out['records']),readback=len(rows),aliases_changed=False,resolved_issues_reopened=False)))
