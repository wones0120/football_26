"""Verified native aliases and PFR weekly source; no annual fill or models."""
from datetime import UTC,datetime
import hashlib,json
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.pfr_advanced_features import build_pfr_advanced_features,persist_feature_identity_requests

root=Path('research/pfr_advanced_features_20261020/v1');root.mkdir(exist_ok=True,parents=True)
source=Path('research/pfr_source_components_20261020/v1/actual_validated_capture_receipt.json')
source_raw=source.read_bytes();manifest=json.loads(source_raw);cutoff=datetime.now(UTC)
with engine.connect() as c:
    aliases=[dict(r) for r in c.execute(text("SELECT source_system,source_key,player_master_id::text AS player_master_id,created_at FROM public.player_alias WHERE source_system='pfr' AND created_at<=:cutoff"),dict(cutoff=cutoff)).mappings()]
with Session(engine) as s:
    snapshots=[s.get(SourceSnapshot,r['source_snapshot_id']) for r in manifest['reports']]
    features=build_pfr_advanced_features(snapshots,aliases,before_period=202606,cutoff=cutoff)
with engine.begin() as c:queue=persist_feature_identity_requests(c,features)
out=dict(evidence_use='postlock_descriptive_not_pregame_or_serving',actual_derived_at=datetime.now(UTC).isoformat(),
    source_manifest_sha256=hashlib.sha256(source_raw).hexdigest(),features=features,identity_queue=queue,
    producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/pfr_advanced_features.py').read_bytes()).hexdigest(),
    model_consumed=False,optimizer_consumed=False)
raw=json.dumps(out,sort_keys=True,separators=(',',':'),allow_nan=False,default=str).encode();sha=hashlib.sha256(raw).hexdigest()
p=Path('artifacts/pfr_advanced_features')/(sha+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==raw
else:p.write_bytes(raw)
coverage={mid:sum(a['metrics'].get(mid,{}).get('value') is not None for a in features['actor_game_rows']) for mid in ('G07-M07','G07-M08','G07-M09','G13-M03')}
receipt=dict(status='actual_pfr_weekly_native_alias_features_only',actual_derived_at=out['actual_derived_at'],
    artifact_ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(raw)),actor_games=len(features['actor_game_rows']),
    canonical_actor_games=sum(a['player_master_id'] is not None for a in features['actor_game_rows']),
    defense_games=len(features['defense_game_rows']),identity_review_requests=len(features['identity_review_requests']),
    identity_queue_persisted=queue['requests'],known_actor_metrics=coverage,
    observed_defense_metrics={mid:sum(d['metrics'][mid]['observed_source_sum'] is not None for d in features['defense_game_rows']) for mid in ('G15-M05','G15-M06')},
    excluded_sources=len(features['provenance']['excluded_sources']),model_consumed=False,optimizer_consumed=False)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
