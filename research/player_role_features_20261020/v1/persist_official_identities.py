"""Persist only reviewed identity actions; original feature/source bytes stay fixed."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import verify_snapshot_artifact
from backend.app.product_services.official_role_report_features import persist_official_role_identities

root=Path('research/player_role_features_20261020/v1')
feature_receipt=json.loads((root/'actual_official_practice_receipt.json').read_text())
ref=feature_receipt['artifact_ref'];raw=Path(ref['path']).read_bytes()
assert len(raw)==ref['bytes'] and hashlib.sha256(raw).hexdigest()==ref['sha256']
features=json.loads(raw);outputs=features['source_outputs']
with Session(engine) as session:
    for result in outputs:
        snapshot=session.get(SourceSnapshot,result['provenance']['original_snapshot_id'])
        verify_snapshot_artifact(snapshot)
        assert snapshot.content_sha256==result['provenance']['source_sha256']
with engine.begin() as connection:
    keys=[a['source_key'] for result in outputs for a in result['identity_resolution_actions']]
    query=text("SELECT source_key,player_master_id::text AS player_master_id FROM public.player_alias WHERE source_system='nfl_official' AND source_key=ANY(:keys) ORDER BY source_key")
    before=[dict(r) for r in connection.execute(query,dict(keys=keys)).mappings()]
    actions=[persist_official_role_identities(connection,result) for result in outputs]
    after=[dict(r) for r in connection.execute(query,dict(keys=keys)).mappings()]
receipt=dict(actual_persisted_at=datetime.now(UTC).isoformat(),status='identity_actions_persisted_not_feature_republication',
    original_feature_ref=ref,actions=actions,before=before,after=after,
    source_context_projection_model_settings_changed=False,
    historical_identity_availability='New alias persistence time is actual current time, not original report availability')
(root/'actual_official_identity_persistence_receipt.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(dict(status=receipt['status'],actions=actions,before_aliases=len(before),after_aliases=len(after))))
