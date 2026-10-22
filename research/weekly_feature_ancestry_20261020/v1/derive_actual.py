from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from backend.app.product_services.weekly_passing_air_efficiency import load_reviewed_weekly_input
from backend.app.product_services.weekly_feature_ancestry import build_weekly_feature_ancestry
from backend.app.product_services.evaluation_record import digest
ROOT=Path('research/weekly_feature_ancestry_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
receipt=json.loads(Path('research/weekly_effectiveness_catalog_features_20261020/v1/actual_derivation_receipt.json').read_text());ref=receipt['full_ref'];weekly=load_reviewed_weekly_input(ref,cutoff=now)
source_ref=weekly['provenance']['source_extract_ref'];p=Path(source_ref['path']).resolve();assert p.parent==Path('artifacts/weekly_effectiveness_sources').resolve() and p.name==source_ref['sha256']+'.json' and source_ref['bytes']<=64*1024*1024
raw=p.read_bytes();assert len(raw)==source_ref['bytes'] and hashlib.sha256(raw).hexdigest()==source_ref['sha256'];source=json.loads(raw)
result=build_weekly_feature_ancestry(source,weekly)
result['provenance'].update(weekly_input_ref=ref,source_extract_ref=source_ref,actual_read_at=now.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),
 actual_publication_at=datetime.now(UTC).isoformat(),diagnostic_producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/weekly_feature_ancestry.py').read_bytes()).hexdigest())
def save(x):
 data=json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(data)<=96*1024*1024
 sha=hashlib.sha256(data).hexdigest();p=Path('artifacts/weekly_feature_ancestry')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==data
 else:
  with p.open('xb') as f:f.write(data)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(data))
full=save(result);selected={k:v for k,v in result.items() if k not in {'rows','semantic_sha256','provenance'}}
selected['rows']=[r for r in result['rows'] if r['team'] in {'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};small=save(selected)
out=dict(completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=small,weekly_input_ref=ref,source_extract_ref=source_ref,
 source_rows=len(source['rows']),diagnostic_rows=len(result['rows']),feature_rows=len(weekly['rows']),quarantined_rows=sum(r['quarantined'] for r in result['rows']),
 selected_rows=len(selected['rows']),field_state_counts=result['field_state_counts'],metric_branch_counts=result['metric_branch_counts'],
 semantic_sha256=result['semantic_sha256'],imputation_ancestry=result['imputation_ancestry'],source_fetches=0,database_writes=0,parent_inflations=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
