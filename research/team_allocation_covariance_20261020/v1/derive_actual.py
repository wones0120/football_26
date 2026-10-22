from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.opportunity_source_coverage import load_reviewed_player_component
from backend.app.product_services.team_allocation_covariance import build_team_allocation_covariance
from backend.app.product_services.evaluation_record import digest
root=Path('research/team_allocation_covariance_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
r=json.loads(Path('research/player_opportunity_components_20261019/v1/actual_derivation_current_receipt.json').read_text());ref=r['full_ref']
with Session(engine) as session:
 snap=session.get(SourceSnapshot,r['source_snapshot_id']);source=load_reviewed_player_component(ref,snap,cutoff=now)
result=build_team_allocation_covariance(source,before_period=source['before_period']);result['provenance']=dict(original_component_provenance=result['provenance'],input_component_ref=ref,actual_read_at=now.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/team_allocation_covariance.py').read_bytes()).hexdigest(),reader_code_sha256=hashlib.sha256(Path('backend/app/product_services/opportunity_source_coverage.py').read_bytes()).hexdigest())
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=8*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/team_allocation_covariance')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as stream:stream.write(raw)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
result['provenance']['actual_publication_at']=datetime.now(UTC).isoformat();full=save(result);selected={k:v for k,v in result.items() if k not in {'team_windows','provenance','semantic_sha256'}};selected['team_windows']=[r for r in result['team_windows'] if r['team'] in {'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};slice_ref=save(selected)
summary={mid:dict(exact_complete_window_covariances=sum(r['metrics'][mid]['covariance'] is not None for r in result['team_windows']),known_complete_sample_covariances=sum(r['metrics'][mid]['known_complete_sample_covariance'] is not None for r in result['team_windows']),complete_allocation_logs=sum(r['metrics'][mid]['known_complete_allocation_logs'] for r in result['team_windows']),unknown_or_zero_budget_logs=sum(r['metrics'][mid]['unknown_or_zero_budget_logs'] for r in result['team_windows'])) for mid in ['X02-M09','X02-M10']}
receipt=dict(full_ref=full,selected_ref=slice_ref,input_component_ref=ref,team_windows=len(result['team_windows']),selected_team_windows=len(selected['team_windows']),coverage=summary,global_semantic_sha256=result['semantic_sha256'],actual_read_at=now.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,parent_inflates=0,source_fetches=0,model_fits=0,database_writes=0,evidence_use=result['evidence_use'])
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
