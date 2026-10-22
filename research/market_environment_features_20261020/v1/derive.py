"""Retained market-source validation only; no fetch/ingest/model writes."""
from datetime import UTC,datetime
import hashlib,json
from pathlib import Path
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.market_snapshots import load_current_markets
from backend.app.product_services.market_environment_features import build_market_environment_features,extract_espn_market_details

root=Path('research/market_environment_features_20261020/v1')
cutoff='2026-10-19T23:00:39.837202+00:00'
with engine.connect() as c:
    observations=[r for r in load_current_markets(c,season=2026,week=6,cutoff=cutoff) if {r['home_team'],r['away_team']}=={'SF','WAS'}]
assert observations
game={k:observations[-1][k] for k in ('game_id','season','week','home_team','away_team','kickoff_at')}
proofs={}
with Session(engine) as s:
    for row in observations:
        sid=row['source_snapshot_id']
        if sid not in proofs:
            snapshot=s.get(SourceSnapshot,sid)
            assert snapshot.season==game['season'] and snapshot.week==game['week']
            proofs[sid]=extract_espn_market_details(snapshot,[game],cutoff=cutoff)
        detail=proofs[sid]['details'][game['game_id']]
        assert (detail['game_total'],detail['home_spread'],detail['source_game_id'])==(row['game_total'],row['home_spread'],row['source_game_id'])
        for field in ('opening_total','opening_home_spread','home_moneyline','away_moneyline','bookmaker'):
            row[field]=detail[field]
        row['detail_source_snapshot_id']=sid
features=build_market_environment_features([game],observations,cutoff=cutoff)
out=dict(evidence_use='postlock_descriptive_not_pregame_or_serving',actual_derived_at=datetime.now(UTC).isoformat(),
    original_cutoff=cutoff,features=features,source_proofs=proofs,canonical_observations=observations,
    model_consumed=False,optimizer_consumed=False)
raw=json.dumps(out,sort_keys=True,separators=(',',':'),default=str,allow_nan=False).encode()
sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/market_environment_features')/(sha+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==raw
else:p.write_bytes(raw)
receipt=dict(status='actual_retained_market_features_not_models',actual_derived_at=out['actual_derived_at'],
    artifact_ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(raw)),verified_source_snapshots=len(proofs),canonical_observations=len(observations),
    features_by_team={g['team']:{mid:m['value'] for mid,m in g['metrics'].items()} for g in features['games']},
    opening_publication_time='unknown; known opening quote only at actual source observation',
    source_gaps=features['missing_source_contracts'],model_consumed=False,optimizer_consumed=False)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
