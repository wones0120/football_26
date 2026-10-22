from pathlib import Path
from datetime import datetime,UTC
import hashlib,json,time
from backend.app.product_services.history_team_coverage import build_history_team_coverage
from backend.app.product_services import weekly_effectiveness_catalog_features as producer
from backend.app.product_services.factual_designation import clock
from backend.app.product_services.evaluation_record import digest
root=Path('research/history_team_coverage_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
r=json.loads(Path('research/weekly_effectiveness_catalog_features_20261020/v1/actual_derivation_receipt.json').read_text());ref=r['full_ref'];p=Path(ref['path']).resolve();raw=p.read_bytes()
assert p.parent==Path('artifacts/weekly_effectiveness_catalog').resolve() and p.name==ref['sha256']+'.json' and len(raw)==ref['bytes'] and len(raw)<=96*1024*1024 and hashlib.sha256(raw).hexdigest()==ref['sha256'];weekly=json.loads(raw)
assert weekly['provenance']['producer_code_sha256']==hashlib.sha256(Path(producer.__file__).read_bytes()).hexdigest() and clock(weekly['provenance']['actual_derived_at'])<=now
extract=weekly['provenance']['source_extract_ref'];p=Path(extract['path']).resolve()
assert p.parent==Path('artifacts/weekly_effectiveness_sources').resolve() and p.name==extract['sha256']+'.json' and p.stat().st_size==extract['bytes']
with p.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==extract['sha256']
result=build_history_team_coverage(weekly,before_period=weekly['before_period']);result['provenance']=dict(original_weekly_provenance=result['provenance'],weekly_input_ref=ref,source_extract_ref=extract,actual_read_at=now.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/history_team_coverage.py').read_bytes()).hexdigest())
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=96*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/history_team_coverage')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as stream:stream.write(raw)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
result['provenance']['actual_publication_at']=datetime.now(UTC).isoformat();full=save(result);selected={k:v for k,v in result.items() if k not in {'rows','provenance','semantic_sha256'}};selected['rows']=[r for r in result['rows'] if r['season']==2026 and r['team'] in {'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};slice_ref=save(selected)
receipt=dict(full_ref=full,selected_ref=slice_ref,weekly_input_ref=ref,source_extract_ref=extract,native_target_logs=len(result['rows']),canonical_target_logs=sum(r['player_master_id'] is not None for r in result['rows']),selected_rows=len(selected['rows']),known_same_team_log_fractions=sum(r['same_team_log_fraction'] is not None for r in result['rows']),known_same_team_exposure_fractions={ch:sum(r['metrics'][ch]['same_team_exposure_fraction'] is not None for r in result['rows']) for ch in ['pass_attempts','rush_attempts','targets']},source_identity_requests=len(result['identity_review_requests']),source_identity_queue='Inherited reviewed389durable weekly sourceissues; no newnativeidentity inferred',global_semantic_sha256=result['semantic_sha256'],actual_read_at=now.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,parent_inflates=0,source_fetches=0,model_fits=0,database_writes=0,evidence_use=result['evidence_use'])
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
