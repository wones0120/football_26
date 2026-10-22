from datetime import UTC,datetime
import hashlib,json
from pathlib import Path
from backend.app.db import engine
from backend.app.product_services.workload_count_forecast import load_history
from backend.app.product_services.unavailable_production_features import build_unavailable_production_features

root=Path('research/unavailable_production_features_20261020/v1')
original=json.loads(Path('research/player_role_features_20261020/v1/actual_official_practice_receipt.json').read_text())
ref=original['artifact_ref'];raw=Path(ref['path']).read_bytes()
assert len(raw)==ref['bytes'] and hashlib.sha256(raw).hexdigest()==ref['sha256']
roles=json.loads(raw)['features'];cutoff=roles['provenance']['decision_cutoff_at']
weekly=load_history(engine,season=2026,week=6,cutoff=cutoff)
features=build_unavailable_production_features(weekly,roles,before_period=202606,cutoff=cutoff)
out=dict(evidence_use='postlock_descriptive_not_pregame_or_serving',actual_derived_at=datetime.now(UTC).isoformat(),
    original_role_ref=ref,features=features,model_consumed=False,optimizer_consumed=False)
data=json.dumps(out,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(data).hexdigest()
p=Path('artifacts/unavailable_production_features')/(sha+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==data
else:p.write_bytes(data)
unavailable=[a for a in features['actors'] if a['availability_state']=='UNAVAILABLE']
receipt=dict(status='historical_unavailable_reference_not_vacancy_forecast',actual_derived_at=out['actual_derived_at'],
    artifact_ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(data)),source_rows=len(weekly),
    actors=len(features['actors']),unavailable_actors=len(unavailable),
    complete_reference_channels={c:sum(a['unavailable_reference'][c] is not None for a in unavailable)
        for c in ('pass_attempts','rush_attempts','targets','receptions','passing_yards','rushing_yards','receiving_yards')},
    exact_team_metrics=sum(v['exact_unavailable_reference_mean'] is not None for t in features['teams'] for m in t['metrics'].values() for v in m['channels'].values()),
    limitation='No full-team completeness proof; unknown status/windows/routes/TD remain unknown. No transfer/donation.',model_consumed=False,optimizer_consumed=False)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
