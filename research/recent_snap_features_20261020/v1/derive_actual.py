"""Freeze current retained rows before feature derivation; no provider redownload."""
from datetime import datetime,UTC
from pathlib import Path
import json,hashlib
from tempfile import TemporaryDirectory
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.services.source_capture import SourceCaptureService,DEFAULT_NFLREADPY_LICENSE
from backend.app.product_services.factual_designation import clock
from backend.app.product_services.recent_snap_features import load_frozen_snap_revision
root=Path('research/recent_snap_features_20261020/v1');root.mkdir(parents=True,exist_ok=True)
fields=['season','week','game_type','game_id','pfr_game_id','pfr_player_id','team','opponent','position','offense_snaps','offense_pct','defense_snaps','defense_pct','st_snaps','st_pct']
start=datetime.now(UTC)
with engine.connect().execution_options(isolation_level='REPEATABLE READ') as c:
    with c.begin():
        rows=[]
        for r in c.execute(text('SELECT raw_nfl_snap_count_id,ingest_run_id,created_at,(SELECT jsonb_object_agg(x.key,x.value) FROM jsonb_each(raw_row_json::jsonb) AS x WHERE x.key=ANY(CAST(:fields AS text[]))) AS raw_row_json FROM raw_nfl_snap_count WHERE season=:season ORDER BY raw_nfl_snap_count_id'),dict(season=2026,fields=fields)).mappings():
            rows.append(dict(source_row_id=r['raw_nfl_snap_count_id'],ingest_run_id=r['ingest_run_id'],created_at=clock(r['created_at']).isoformat(),raw=r['raw_row_json']))
        aliases=[dict(source_system=r['source_system'],source_key=r['source_key'],player_master_id=str(r['player_master_id']),created_at=clock(r['created_at']).isoformat() if r['created_at'] else None) for r in c.execute(text("SELECT source_system,source_key,player_master_id,created_at FROM player_alias WHERE source_system='pfr' ORDER BY source_key,player_master_id")).mappings()]
        runs=[dict(ingest_run_id=r['ingest_run_id'],status=r['status'],started_at=clock(r['started_at']).isoformat() if r['started_at'] else None,completed_at=clock(r['completed_at']).isoformat() if r['completed_at'] else None) for r in c.execute(text('SELECT ingest_run_id,status,started_at,completed_at FROM ingest_run WHERE ingest_run_id IN (SELECT DISTINCT ingest_run_id FROM raw_nfl_snap_count WHERE season=2026)')).mappings()]
        blocks=[{**dict(r),'first_seen_at':clock(r['first_seen_at']).isoformat()} for r in c.execute(text("SELECT identity_quarantine_id,source_system,source_player_key,reason_code,status,first_seen_at FROM target.identity_quarantine WHERE source_system='pfr' AND reason_code='canonical_native_game_collision' AND status='open' ORDER BY identity_quarantine_id")).mappings()]
end=datetime.now(UTC)
payload=dict(contract='retained_snap_count_revision_v1',season=2026,rows=rows,aliases=aliases,identity_blocks=blocks,original_ingest_runs=runs,
    actual_extract_started_at=start.isoformat(),actual_extract_completed_at=end.isoformat(),original_provider_snapshot_claim=False,
    source_origin='Current retained public.raw_nfl_snap_count revision; legacy ingestion can replace rows; actual freeze is not original HTTP/provider availability',transaction_isolation='REPEATABLE READ',raw_projection_fields=fields,raw_projection_contract='Exact original native field presence/null/value retained; unrelated raw JSON fields excluded before extraction')
raw=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
if len(raw)>32*1024*1024:raise ValueError('Snap extract byte bound exceeded before capture')
with TemporaryDirectory(prefix='football_snap_revision_') as tmp,Session(engine) as s:
    p=Path(tmp)/'snap_count_revision_2026.json';p.write_bytes(raw)
    cap=SourceCaptureService(s).capture_file(p,source_system='retained_db',dataset='snap_counts_revision',season=2026,week=6,slate='offline_feature_inventory',source_uri='retained-db://public.raw_nfl_snap_count/season=2026',source_license=DEFAULT_NFLREADPY_LICENSE,slate_lock_at=datetime(2026,10,20,0,15,tzinfo=UTC),observation_basis='capture_clock',media_type='application/json',row_count=len(rows),metadata=dict(contract='retained_snap_count_revision_v1',original_provider_snapshot_claim=False,source_origin=payload['source_origin'],actual_extract_completed_at=end.isoformat()));s.commit()
    source_ref=dict(snapshot_id=str(cap.snapshot.snapshot_id),sha256=cap.snapshot.content_sha256,bytes=cap.snapshot.byte_count,path=cap.snapshot.artifact_path)
    (root/'capture_checkpoint.json').write_text(json.dumps(dict(source_ref=source_ref,rows=len(rows),actual_extract_completed_at=end.isoformat(),original_provider_snapshot_claim=False),indent=2)+'\n')
    value=load_frozen_snap_revision(cap.snapshot,cutoff=datetime.now(UTC))
value['actual_derived_at']=datetime.now(UTC).isoformat();value['producer_code_sha256']=hashlib.sha256(Path('backend/app/product_services/recent_snap_features.py').read_bytes()).hexdigest()
raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/recent_snap_features')/(sha+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==raw
else:p.write_bytes(raw)
receipt=dict(source_ref=source_ref,artifact_ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(raw)),actual_derived_at=value['actual_derived_at'],native_actor_team_rows=len(value['actor_trends']),canonical_actor_team_rows=sum(r['player_master_id'] is not None for r in value['actor_trends']),known_count_deltas={ch:sum(r['channels'][ch]['snaps']['delta'] is not None for r in value['actor_trends']) for ch in ['offense','defense','st']},known_share_deltas={ch:sum(r['channels'][ch]['share']['delta'] is not None for r in value['actor_trends']) for ch in ['offense','defense','st']},identity_requests=len(value['identity_review_requests']),identity_queue_persisted=False,semantic_sha256=value['semantic_sha256'],evidence_use=value['evidence_use'],models_or_optimizer_consumed=False)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
