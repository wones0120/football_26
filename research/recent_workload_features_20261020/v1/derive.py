"""Read-only retained weekly source derivation; no inference/serving writes."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from backend.app.db import engine
from backend.app.product_services.workload_count_forecast import load_history
from backend.app.product_services.recent_workload_features import build_recent_workload_features

ROOT=Path('research/recent_workload_features_20261020/v1')
cutoff='2026-10-19T23:00:39.837202+00:00'
source_receipt=json.loads(Path('research/player_role_features_20261020/v1/actual_retained_feature_receipt.json').read_text())
ref=source_receipt['artifact_ref']; raw=Path(ref['path']).read_bytes()
assert len(raw)==ref['bytes'] and hashlib.sha256(raw).hexdigest()==ref['sha256']
roster=json.loads(raw)['extracted']['actors']
weekly=load_history(engine,season=2026,week=6,cutoff=cutoff)
features=build_recent_workload_features(weekly,roster,before_period=202606,cutoff=cutoff)
result=dict(evidence_use='postlock_descriptive_not_pregame_or_serving',
    actual_derived_at=datetime.now(UTC).isoformat(),original_source_cutoff=cutoff,
    source_roster_ref=ref,features=features,model_consumed=False,optimizer_consumed=False)
output=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
sha=hashlib.sha256(output).hexdigest();dest=Path('artifacts/recent_workload_features')/(sha+'.json')
dest.parent.mkdir(exist_ok=True)
if dest.exists():assert dest.read_bytes()==output
else:dest.write_bytes(output)
coverage={mid:{c:sum(a['metrics'][mid]['channels'][c]['difference'] is not None for a in features['actors'])
    for c in ('pass_attempts','rush_attempts','targets')} for mid in ('G22-M01','G22-M02')}
receipt=dict(status='actual_observed_features_not_forecasts',actual_derived_at=result['actual_derived_at'],
    artifact_ref=dict(path=str(dest.resolve()),sha256=sha,bytes=len(output)),
    source_rows=len(weekly),requested_actors=len(roster),exact_contrast_coverage=coverage,
    model_consumed=False,optimizer_consumed=False,
    limitation='Prior8 unavailable before Week6 within same season; no cross-season fill. Missing participant rows unknown.')
(ROOT/'actual_receipt.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
