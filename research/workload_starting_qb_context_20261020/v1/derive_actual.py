from pathlib import Path
from datetime import datetime,UTC
import hashlib,json,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.workload_starting_qb_context import load_starting_qb_context,build_workload_starting_qb_context
from backend.app.product_services import weekly_effectiveness_catalog_features as producer
from backend.app.product_services.evaluation_record import digest
root=Path('research/workload_starting_qb_context_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
r=json.loads(Path('research/weekly_effectiveness_catalog_features_20261020/v1/actual_derivation_receipt.json').read_text());ref=r['full_ref'];p=Path(ref['path']).resolve();raw=p.read_bytes()
assert p.parent==Path('artifacts/weekly_effectiveness_catalog').resolve() and p.name==ref['sha256']+'.json' and len(raw)==ref['bytes'] and len(raw)<=96*1024*1024 and hashlib.sha256(raw).hexdigest()==ref['sha256'];weekly=json.loads(raw)
assert weekly['provenance']['producer_code_sha256']==hashlib.sha256(Path(producer.__file__).read_bytes()).hexdigest()
extract=weekly['provenance']['source_extract_ref'];path=Path(extract['path']).resolve();raw=path.read_bytes();assert path.parent==Path('artifacts/weekly_effectiveness_sources').resolve() and path.name==extract['sha256']+'.json' and len(raw)==extract['bytes'] and hashlib.sha256(raw).hexdigest()==extract['sha256']
with Session(engine) as session:
 snapshot=session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b');schedule,starters=load_starting_qb_context(snapshot,cutoff=now)
targets=sorted({r['game_id'] for r in starters['rows'] if r['season']*100+r['week']==weekly['before_period']})
result=build_workload_starting_qb_context(weekly,schedule,starters,before_period=weekly['before_period'],target_game_ids=targets,cutoff=now)
result['provenance'].update(weekly_input_ref=ref,source_extract_ref=extract,actual_read_at=now.isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/workload_starting_qb_context.py').read_bytes()).hexdigest())
def save(v):
 raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=96*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/workload_starting_qb_context')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items() if k not in {'rows','provenance','semantic_sha256'}};selected['rows']=[row for row in result['rows'] if row['team'] in {'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
receipt=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,weekly_input_ref=ref,source_extract_ref=extract,schedule_provenance=schedule['provenance'],target_game_ids=targets,target_team_contexts=[r for r in starters['rows'] if r['game_id'] in targets],actor_target_context_rows=len(result['rows']),canonical_rows=sum(r['player_master_id'] is not None for r in result['rows']),known_with_target_starter_means={ch:sum(row['metrics'][ch]['with_reported_target_starter']['exact_per_observed_log'] is not None for row in result['rows']) for ch in ['pass_attempts','rush_attempts','targets']},known_with_minus_other={ch:sum(row['metrics'][ch]['with_minus_other'] is not None for row in result['rows']) for ch in ['pass_attempts','rush_attempts','targets']},selected_rows=len(selected['rows']),new_target_identity_requests=[r for r in result['identity_review_requests'] if 'game_id' in r],global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],evidence_use=result['evidence_use'],models=0,source_fetches=0,database_writes=0)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in {'target_team_contexts','schedule_provenance'}}))
