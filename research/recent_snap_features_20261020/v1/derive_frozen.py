"""Derive the already frozen snap revision; never re-read mutable source tables."""
from datetime import datetime,UTC
from pathlib import Path
import hashlib,json
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.recent_snap_features import load_frozen_snap_revision,persist_snap_identity_requests
root=Path('research/recent_snap_features_20261020/v1');checkpoint=json.loads((root/'capture_checkpoint.json').read_text());source_ref=checkpoint['source_ref']
with Session(engine) as s:
    snapshot=s.get(SourceSnapshot,source_ref['snapshot_id'])
    if snapshot.content_sha256!=source_ref['sha256']:raise ValueError('Frozen source reference differs')
    value=load_frozen_snap_revision(snapshot,cutoff=datetime.now(UTC))
with engine.begin() as c:
    queue=persist_snap_identity_requests(c,value)
    ids=[r['identity_quarantine_id'] for r in queue['records']];keys=[r['source_record_key'] for r in queue['records'] if r.get('source_record_key')]
    saved=[dict(r) for r in c.execute(text("SELECT identity_quarantine_id,source_record_key,source_player_key,status,reason_code FROM target.identity_quarantine WHERE identity_quarantine_id=ANY(CAST(:ids AS text[])) OR (source_schema='public' AND source_record_key=ANY(CAST(:keys AS text[])))"),dict(ids=ids,keys=keys)).mappings()]
    if any(not any(row['identity_quarantine_id']==r['identity_quarantine_id'] or r.get('source_record_key')==row['source_record_key'] for row in saved) for r in queue['records']):raise ValueError('Identity persistence readback incomplete')
value['identity_queue']=dict(**queue,readback=saved);value['identity_queue_persisted']=True
value['actual_derived_at']=datetime.now(UTC).isoformat();value['producer_code_sha256']=hashlib.sha256(Path('backend/app/product_services/recent_snap_features.py').read_bytes()).hexdigest()
raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/recent_snap_features')/(sha+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==raw
else:p.write_bytes(raw)
receipt=dict(source_ref=source_ref,artifact_ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(raw)),actual_derived_at=value['actual_derived_at'],native_actor_team_rows=len(value['actor_trends']),canonical_actor_team_rows=sum(r['player_master_id'] is not None for r in value['actor_trends']),known_count_deltas={ch:sum(r['channels'][ch]['snaps']['delta'] is not None for r in value['actor_trends']) for ch in ['offense','defense','st']},known_share_deltas={ch:sum(r['channels'][ch]['share']['delta'] is not None for r in value['actor_trends']) for ch in ['offense','defense','st']},identity_requests=len(value['identity_review_requests']),identity_queue_persisted=True,equivalent_revision_groups=len(value['provenance']['equivalent_revision_groups']),semantic_sha256=value['semantic_sha256'],evidence_use=value['evidence_use'],models_or_optimizer_consumed=False)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
