"""Existing immutable weekly defense files, native aliases; no network or models."""
from datetime import UTC,datetime
from pathlib import Path
import json,hashlib
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.pfr_defender_features import build_verified_defender_features,persist_defender_identity_requests

root=Path('research/pfr_defender_features_20261020/v1');root.mkdir(parents=True,exist_ok=True)
manifest_path=Path('research/pfr_source_components_20261020/v1/actual_validated_capture_receipt.json')
raw=manifest_path.read_bytes();manifest=json.loads(raw);cutoff=datetime.now(UTC)
with engine.connect() as c:
    aliases=[dict(r) for r in c.execute(text("SELECT source_system,source_key,player_master_id::text AS player_master_id,created_at FROM public.player_alias WHERE source_system='pfr' AND created_at<=:cutoff"),dict(cutoff=cutoff)).mappings()]
with Session(engine) as s:
    snapshots=[s.get(SourceSnapshot,r['source_snapshot_id']) for r in manifest['reports'] if r['asset_name'].startswith('advstats_week_def_')]
    features=build_verified_defender_features(snapshots,aliases,before_period=202606,cutoff=cutoff)
with engine.begin() as c:queue=persist_defender_identity_requests(c,features)
value=dict(features=features,identity_queue=queue,actual_derived_at=datetime.now(UTC).isoformat(),source_manifest_sha256=hashlib.sha256(raw).hexdigest(),producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/pfr_defender_features.py').read_bytes()).hexdigest(),evidence_use='postlock_descriptive_not_pregame_or_serving',identity_queue_persisted=True)
raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False,default=str).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/pfr_defender_features')/(sha+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==raw
else:p.write_bytes(raw)
r=dict(artifact_ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(raw)),actual_derived_at=value['actual_derived_at'],actor_games=len(features['actor_game_rows']),canonical_actor_games=sum(r['player_master_id'] is not None for r in features['actor_game_rows']),known_missed_tackle_fractions=sum(r['metrics']['G15-M07']['value'] is not None for r in features['actor_game_rows']),identity_requests=len(features['identity_review_requests']),queue_persisted=True,semantic_sha256=features['semantic_sha256'])
(root/'actual_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
