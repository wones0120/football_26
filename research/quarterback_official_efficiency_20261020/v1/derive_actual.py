"""Immutable High-reviewed weekly component composition; no DB/source fetch."""
from pathlib import Path
from datetime import datetime,UTC
import hashlib,json,time
from backend.app.product_services.quarterback_official_efficiency import build_quarterback_official_efficiency
from backend.app.product_services import weekly_effectiveness_catalog_features as producer
root=Path('research/quarterback_official_efficiency_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
r=json.loads(Path('research/weekly_effectiveness_catalog_features_20261020/v1/actual_derivation_receipt.json').read_text());ref=r['full_ref'];p=Path(ref['path']).resolve();raw=p.read_bytes()
assert p.parent==Path('artifacts/weekly_effectiveness_catalog').resolve() and p.name==ref['sha256']+'.json' and len(raw)==ref['bytes'] and len(raw)<=96*1024*1024 and hashlib.sha256(raw).hexdigest()==ref['sha256']
source=json.loads(raw);assert source['provenance']['producer_code_sha256']==hashlib.sha256(Path(producer.__file__).read_bytes()).hexdigest()
extract=source['provenance']['source_extract_ref'];path=Path(extract['path']).resolve();assert path.parent==Path('artifacts/weekly_effectiveness_sources').resolve() and path.name==extract['sha256']+'.json' and path.stat().st_size==extract['bytes'];h=hashlib.sha256()
with path.open('rb') as f:
 for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
assert h.hexdigest()==extract['sha256']
result=build_quarterback_official_efficiency(source,before_period=source['before_period']);result['provenance'].update(immutable_input_ref=ref,actual_composition_read_at=now.isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),catalog_producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/quarterback_official_efficiency.py').read_bytes()).hexdigest())
def save(v):
 raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/quarterback_official_efficiency')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items() if k not in {'rows','provenance','semantic_sha256'}};selected['rows']=[r for r in result['rows'] if r['season']==2026 and r['team'] in {'SF','WAS'}]
from backend.app.product_services.evaluation_record import digest
selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
receipt=dict(actual_read_at=now.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,input_ref=ref,source_extract_ref=extract,QB_rows=len(result['rows']),known_ratios=sum(r['metrics']['G05-M05']['value'] is not None for r in result['rows']),selected_rows=len(selected['rows']),global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],source_fetches=0,models=0,database_writes=0,evidence_use=result['evidence_use'])
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
