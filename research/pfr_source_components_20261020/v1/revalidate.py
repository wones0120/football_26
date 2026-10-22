"""Authenticate and revalidate existing original bytes; never redownload."""
from datetime import UTC,datetime
import hashlib,json
from pathlib import Path
import polars as pl
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import verify_snapshot_artifact
from backend.app.product_services.pfr_source_components import validate_pfr_frame

root=Path('research/pfr_source_components_20261020/v1');source=root/'actual_capture_receipt.json';raw=source.read_bytes();original=json.loads(raw);results=[]
with Session(engine) as session:
    for captured in original['reports']:
        if not captured.get('source_snapshot_id'):
            results.append(captured);continue
        snapshot=session.get(SourceSnapshot,captured['source_snapshot_id']);verify_snapshot_artifact(snapshot)
        assert snapshot.content_sha256==captured['raw_remote_sha256']==captured['source_sha256']
        scope=captured['scope'];frame=pl.read_parquet(snapshot.artifact_path)
        result=dict(asset_name=captured['asset_name'],source_snapshot_id=captured['source_snapshot_id'],
            source_sha256=snapshot.content_sha256,bytes=snapshot.byte_count,source_uri=snapshot.source_uri,
            actual_captured_at=str(snapshot.captured_at),scope=scope)
        try:
            validation=validate_pfr_frame(frame,**scope,max_season=2026)
            result.update(validation=validation,status='validated' if validation['native_grain_valid'] else 'native_identity_review_required')
        except (ValueError,TypeError,KeyError) as exc:result.update(status='requires_schema_review',error=str(exc))
        results.append(result)
out=dict(status='original_bytes_revalidated_no_refetch',actual_validated_at=datetime.now(UTC).isoformat(),
    original_capture_receipt_sha256=hashlib.sha256(raw).hexdigest(),original_capture_receipt_path=str(source),
    producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/pfr_source_components.py').read_bytes()).hexdigest(),
    reports=results,assets=len(results),validated=sum(r['status']=='validated' for r in results),
    schema_review=sum(r['status']=='requires_schema_review' for r in results),
    identity_review=sum(r['status']=='native_identity_review_required' for r in results),
    source_quality='Native identity/period validation is not proof of complete final game statistics or original historical availability',
    model_consumed=False,optimizer_consumed=False)
(root/'actual_validated_capture_receipt.json').write_text(json.dumps(out,indent=2,default=str))
print(json.dumps({k:out[k] for k in ('status','assets','validated','schema_review','identity_review')}))
