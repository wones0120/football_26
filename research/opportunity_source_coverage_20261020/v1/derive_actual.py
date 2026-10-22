from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.opportunity_source_coverage import load_reviewed_player_component,build_opportunity_source_coverage
from backend.app.product_services.evaluation_record import digest
root=Path('research/opportunity_source_coverage_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
receipt=json.loads(Path('research/player_opportunity_components_20261019/v1/actual_derivation_current_receipt.json').read_text());ref=receipt['full_ref']
with Session(engine) as session:
 snap=session.get(SourceSnapshot,receipt['source_snapshot_id']);source=load_reviewed_player_component(ref,snap,cutoff=now)
result=build_opportunity_source_coverage(source,before_period=source['before_period']);result['provenance']=dict(original_component_provenance=result['provenance'],input_component_ref=ref,actual_read_at=now.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/opportunity_source_coverage.py').read_bytes()).hexdigest(),authentication='Indexed immutable raw source and managed component/compressed parent byte hashes verified; no parent inflate')
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=8*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/opportunity_source_coverage')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as stream:stream.write(raw)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
result['provenance']['actual_publication_at']=datetime.now(UTC).isoformat();full=save(result);selected={k:v for k,v in result.items() if k not in {'game_rows','provenance','semantic_sha256'}};selected['game_rows']=[r for r in result['game_rows'] if r['team'] in {'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};slice_ref=save(selected)
summary={ch:{field:sum(r['metrics'][ch]['X08_M02'][field] for r in result['game_rows']) for field in ('known_team_opportunity_lower_bound','known_native_attributed_opportunities','known_canonical_attached_opportunities','known_unattributed_opportunity_lower_bound','unknown_eligibility_events')} for ch in ['pass_attempts','rush_attempts','targets']}
r=dict(full_ref=full,selected_ref=slice_ref,input_component_ref=ref,team_games=len(result['game_rows']),selected_team_games=len(selected['game_rows']),known_full_actor_denominators={ch:sum(r['metrics'][ch]['X08_M01']['exact_full_source_native_actor_count'] is not None for r in result['game_rows']) for ch in summary},channel_coverage=summary,source_identity_requests=len(result['identity_review_requests']),global_semantic_sha256=result['semantic_sha256'],actual_read_at=now.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,parent_inflates=0,source_fetches=0,model_fits=0,database_writes=0,evidence_use=result['evidence_use'])
(root/'actual_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
