from datetime import UTC,datetime
import json
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.pfr_source_components import persist_pfr_native_requests

root=Path('research/pfr_source_components_20261020/v1')
source=json.loads((root/'actual_validated_capture_receipt.json').read_text())
reports=[r for r in source['reports'] if r['status']=='native_identity_review_required']
outputs=[]
with Session(engine) as session:
    snapshots=[session.get(SourceSnapshot,r['source_snapshot_id']) for r in reports]
    with engine.begin() as connection:
        for snapshot in snapshots:outputs.append(persist_pfr_native_requests(connection,snapshot))
        keys=[r['source_record_key'] for o in outputs for r in o['records']]
        persisted=[dict(r) for r in connection.execute(text("SELECT identity_quarantine_id,source_record_key,status,reason_code FROM target.identity_quarantine WHERE source_schema='public' AND source_table='source_snapshot' AND source_record_key=ANY(:keys) ORDER BY source_record_key"),dict(keys=keys)).mappings()]
        assert len(persisted)==len(keys)
out=dict(actual_persisted_at=datetime.now(UTC).isoformat(),status='native_missing_id_review_requests_durable',
    outputs=outputs,records=persisted,requested=len(keys),persisted=len(persisted),
    aliases_or_canonical_names_joined=False,raw_sources_models_projections_changed=False)
(root/'actual_identity_queue_receipt.json').write_text(json.dumps(out,indent=2))
print(json.dumps({k:out[k] for k in ('status','requested','persisted')}))
