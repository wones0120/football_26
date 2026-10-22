from datetime import UTC,datetime
import hashlib,json
from pathlib import Path
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.venue_schedule_features import extract_venue_schedule_features
from backend.app.product_services.market_snapshots import utc_time

root=Path('research/venue_schedule_features_20261020/v1')
parent=json.loads(Path('research/market_environment_features_20261020/v1/actual_receipt.json').read_text())['artifact_ref']
raw=Path(parent['path']).read_bytes();assert len(raw)==parent['bytes'] and hashlib.sha256(raw).hexdigest()==parent['sha256']
market=json.loads(raw);selected=max(market['canonical_observations'],key=lambda r:utc_time(r['observed_at']))
game={k:selected[k] for k in ('game_id','source_game_id','season','week','home_team','away_team','kickoff_at')}
with Session(engine) as s:
    snapshot=s.get(SourceSnapshot,selected['source_snapshot_id'])
    features=extract_venue_schedule_features(snapshot,[game],cutoff=market['original_cutoff'])
out=dict(evidence_use='postlock_descriptive_not_pregame_or_serving',actual_derived_at=datetime.now(UTC).isoformat(),
    original_source_parent=parent,features=features,model_consumed=False,optimizer_consumed=False)
raw=json.dumps(out,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest()
p=Path('artifacts/venue_schedule_features')/(sha+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==raw
else:p.write_bytes(raw)
receipt=dict(status='native_venue_features_only',actual_derived_at=out['actual_derived_at'],
    artifact_ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(raw)),source_snapshot_id=selected['source_snapshot_id'],
    known_features={g['team']:{mid:m['value'] for mid,m in g['metrics'].items()} for g in features['games']},
    source_gaps=features['source_gaps'],model_consumed=False,optimizer_consumed=False)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
