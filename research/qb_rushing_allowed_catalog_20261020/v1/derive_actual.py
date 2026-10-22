from pathlib import Path
from datetime import datetime,UTC
import hashlib,json,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.schedule_context_features import load_schedule_context
from backend.app.product_services.qb_rushing_allowed_catalog import build_qb_rushing_allowed
from backend.app.product_services import weekly_effectiveness_catalog_features as producer
from backend.app.product_services.evaluation_record import digest
root=Path('research/qb_rushing_allowed_catalog_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
r=json.loads(Path('research/weekly_effectiveness_catalog_features_20261020/v1/actual_derivation_receipt.json').read_text());ref=r['full_ref'];p=Path(ref['path']).resolve();raw=p.read_bytes()
assert p.parent==Path('artifacts/weekly_effectiveness_catalog').resolve() and p.name==ref['sha256']+'.json' and len(raw)==ref['bytes'] and len(raw)<=96*1024*1024 and hashlib.sha256(raw).hexdigest()==ref['sha256'];weekly=json.loads(raw)
assert weekly['provenance']['producer_code_sha256']==hashlib.sha256(Path(producer.__file__).read_bytes()).hexdigest()
extract=weekly['provenance']['source_extract_ref'];path=Path(extract['path']).resolve();raw=path.read_bytes();assert path.parent==Path('artifacts/weekly_effectiveness_sources').resolve() and path.name==extract['sha256']+'.json' and len(raw)==extract['bytes'] and hashlib.sha256(raw).hexdigest()==extract['sha256'];frozen=json.loads(raw)
excluded_ids={x['source_id'] for x in weekly['identity_review_requests'] if 'source_id' in x};excluded=[row for row in frozen['rows'] if row['source_id'] in excluded_ids]
with Session(engine) as session:
 snapshot=session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b');schedule=load_schedule_context(snapshot,cutoff=now)
result=build_qb_rushing_allowed(weekly,schedule,before_period=weekly['before_period'],excluded_source_rows=excluded);result['provenance'].update(weekly_input_ref=ref,source_extract_ref=extract,actual_read_at=now.isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/qb_rushing_allowed_catalog.py').read_bytes()).hexdigest())
def save(v):
 raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/qb_rushing_allowed_catalog')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items() if k not in {'game_rows','provenance','semantic_sha256'}};selected['game_rows']=[row for row in result['game_rows'] if row['season']==2026 and row['defense_team'] in {'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
receipt=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,weekly_input_ref=ref,source_extract_ref=extract,schedule_provenance=schedule['provenance'],defense_game_rows=len(result['game_rows']),known_total_yards=sum(row['metrics']['G15-M10']['value'] is not None for row in result['game_rows']),known_carries=sum(row['metrics']['G15-M10']['exact_official_carries'] is not None for row in result['game_rows']),selected_rows=len(selected['game_rows']),unbound_rows=len(result['unbound_rows']),excluded_native_source_rows=len(excluded),global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],evidence_use=result['evidence_use'],models=0,source_fetches=0,database_writes=0)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
