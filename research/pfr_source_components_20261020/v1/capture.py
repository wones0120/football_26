"""Single bounded sequential public release capture; no models or normalized facts."""
from datetime import UTC,datetime
import hashlib,json,time
from pathlib import Path
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.services.source_capture import SourceCaptureService
from backend.app.product_services.pfr_source_components import capture_pfr_asset,asset_scope

root=Path('research/pfr_source_components_20261020/v1');manifest=json.loads((root/'release_asset_inventory.json').read_text())
original=Path(manifest['raw_metadata_path']).read_bytes();assert hashlib.sha256(original).hexdigest()==manifest['raw_metadata_sha256']
assets=manifest['assets'];assert len(assets)<=40 and sum(a['bytes'] for a in assets)<=8*1024*1024
started=datetime.now(UTC);timer=time.monotonic();reports=[]
code=Path('backend/app/product_services/pfr_source_components.py').read_bytes()
for asset in sorted(assets,key=lambda a:(asset_scope(a['name'])['summary_level']!='week',-(asset_scope(a['name'])['season'] or 0),a['name'])):
    if time.monotonic()-timer>180:
        reports.append(dict(asset_name=asset['name'],status='not_attempted_job_time_cap'));continue
    try:
        with Session(engine) as session:
            report=capture_pfr_asset(SourceCaptureService(session),asset,capture_season=2026)
    except Exception as exc:
        report=dict(asset_name=asset['name'],status='capture_failed',exception=type(exc).__name__,reason=str(exc)[:400])
    reports.append(report)
    progress=dict(status='capturing',started_at=started.isoformat(),actual_updated_at=datetime.now(UTC).isoformat(),reports=reports)
    (root/'actual_capture_progress.json').write_text(json.dumps(progress,indent=2,default=str))
    print(json.dumps(dict(asset=asset['name'],status=report['status'],rows=(report.get('validation') or {}).get('row_count'),error=report.get('validation_error') or report.get('reason'))),flush=True)
out=dict(status='source_capture_complete_not_feature_or_model_activation',started_at=started.isoformat(),actual_finished_at=datetime.now(UTC).isoformat(),
    elapsed_seconds=time.monotonic()-timer,source_manifest_sha256=manifest['raw_metadata_sha256'],producer_code_sha256=hashlib.sha256(code).hexdigest(),
    requested_assets=len(assets),reports=reports,model_consumed=False,optimizer_consumed=False,
    chronology='Actual 2026 download/capture; revised data not original historical pregame evidence')
(root/'actual_capture_receipt.json').write_text(json.dumps(out,indent=2,default=str))
print(json.dumps(dict(status=out['status'],elapsed_seconds=out['elapsed_seconds'],reports=len(reports),captured=sum('source_snapshot_id' in r for r in reports),validated=sum(r['status']=='captured_validated' for r in reports))),flush=True)
