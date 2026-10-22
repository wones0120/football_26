"""Single free schedule source revision, descriptive feature-only; no model jobs."""
from datetime import datetime,UTC
from pathlib import Path
from collections import Counter
import hashlib,json,time
from sqlalchemy.orm import Session
from nflreadpy.config import update_config
from backend.app.db import engine
from backend.app.services.source_capture import SourceCaptureService
from backend.app.product_services.schedule_context_features import capture_schedule_context,load_schedule_context

root=Path('research/schedule_context_features_20261020/v1');root.mkdir(parents=True,exist_ok=True)
start=datetime.now(UTC);timer=time.monotonic();update_config(cache_mode='off',timeout=30)
with Session(engine) as s:
    cap=capture_schedule_context(SourceCaptureService(s),season=start.year,week=7,slate='offline_schedule_feature_inventory',slate_lock_at=datetime(2026,10,20,0,15,tzinfo=UTC));s.commit()
    snapshot=cap.snapshot
    value=load_schedule_context(snapshot,cutoff=datetime.now(UTC))
    value['producer_code_sha256']=hashlib.sha256(Path('backend/app/product_services/schedule_context_features.py').read_bytes()).hexdigest()
    value['actual_derived_at']=datetime.now(UTC).isoformat()
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/schedule_context_features')/(sha+'.json');p.parent.mkdir(exist_ok=True)
    if p.exists():assert p.read_bytes()==raw
    else:p.write_bytes(raw)
    mids=['G20-M03','G20-M04','G20-M05','G20-M08','G20-M09']
    coverage={mid:sum(t['metrics'][mid]['value'] is not None for r in value['game_rows'] for t in r['team_rows']) for mid in mids}
    receipt=dict(actual_started_at=start.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,source_snapshot_id=str(snapshot.snapshot_id),source_sha256=snapshot.content_sha256,source_bytes=snapshot.byte_count,source_rows=snapshot.row_count,source_pre_lock=cap.pre_lock,source_artifact_path=snapshot.artifact_path,artifact_ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(raw)),seasons=dict(sorted(Counter(r['season'] for r in value['game_rows']).items())),known_team_game_values=coverage,semantic_sha256=value['semantic_sha256'],evidence_use=value['evidence_use'],models_or_optimizer_consumed=False)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
