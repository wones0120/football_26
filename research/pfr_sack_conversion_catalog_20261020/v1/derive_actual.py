from datetime import datetime,UTC
from pathlib import Path
import hashlib,json,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.pfr_sack_conversion_catalog import derive_pfr_sack_conversion
from backend.app.product_services.evaluation_record import digest
root=Path('research/pfr_sack_conversion_catalog_20261020/v1');now=datetime.now(UTC);start=time.monotonic()
source_path=Path('research/pfr_source_components_20261020/v1/actual_validated_capture_receipt.json');manifest=json.loads(source_path.read_text());refs=[r for r in manifest['reports'] if r['scope']['summary_level']=='week' and r['scope']['stat_type']=='pass']
canonical=json.loads(Path('research/pfr_advanced_features_20261020/v1/actual_receipt.json').read_text())['artifact_ref']
with Session(engine) as session:
 snapshots=[session.get(SourceSnapshot,r['source_snapshot_id']) for r in refs]
 assert all(str(s.snapshot_id)==r['source_snapshot_id'] and s.content_sha256==r['source_sha256'] and s.byte_count==r['bytes'] for s,r in zip(snapshots,refs))
 schedule=session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b')
 result=derive_pfr_sack_conversion(snapshots,canonical,schedule,before_period=202606,cutoff=now)
result['provenance'].update(source_manifest_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),actual_publication_at=datetime.now(UTC).isoformat())
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/pfr_sack_conversion_catalog')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items() if k not in {'game_rows','semantic_sha256','provenance'}};selected['game_rows']=[r for r in result['game_rows'] if r['season']==2026 and r['defense_team'] in {'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
metrics=[r['metrics']['G14-M03'] for r in result['game_rows']]
r=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,canonical_input_ref=canonical,source_assets=len(refs),before_period=result['before_period'],covered_source_seasons=result['covered_source_seasons'],expected_schedule_game_sides=len(result['game_rows']),observed_source_game_sides=sum(m['source_passer_rows']>0 for m in metrics),missing_passer_game_sides=sum(m['source_passer_rows']==0 for m in metrics),known_exact_rates=sum(m['value']is not None for m in metrics),known_sack_sum=sum(m['known_sack_lower_bound'] for m in metrics),known_pressure_sum=sum(m['known_pressure_lower_bound'] for m in metrics),native_passer_rows=sum(m['source_passer_rows'] for m in metrics),canonical_unknown_passer_rows=sum(g['canonical_unknown_passers'] for g in result['game_rows']),selected_rows=len(selected['game_rows']),global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],G14_M01_source_gap=result['G14_M01_source_gap'],source_fetches=0,database_writes=0,models=0,parent_inflates=0,evidence_use=result['evidence_use'])
(root/'actual_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
