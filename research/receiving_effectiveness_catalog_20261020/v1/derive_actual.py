from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.offensive_environment_catalog import load_reviewed_environment_context
from backend.app.product_services.receiving_effectiveness_catalog import build_receiving_effectiveness_catalog,DEFINITIONS
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services import player_effectiveness_components as producer
root=Path('research/receiving_effectiveness_catalog_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
env=json.loads(Path('research/environment_context_evidence_20261019/v1/actual_combined_receipt.json').read_text())
with Session(engine) as session:
 snapshot=session.get(SourceSnapshot,env['parent_artifact_ref']['source_snapshot_id']);verified=load_reviewed_environment_context(env['full_context'],snapshot,actual_read_at=now)
ref=json.loads(Path('research/player_effectiveness_components_20261020/v1/actual_derivation_receipt.json').read_text())['full_ref'];path=Path(ref['path']).resolve();raw=path.read_bytes()
assert path.parent==Path('artifacts/player_effectiveness_components').resolve() and path.name==ref['sha256']+'.json' and len(raw)==ref['bytes'] and len(raw)<=16*1024*1024 and hashlib.sha256(raw).hexdigest()==ref['sha256']
source=json.loads(raw);proof=source['provenance'];assert proof['source']['snapshot_id']==str(snapshot.snapshot_id) and proof['source']['content_sha256']==snapshot.content_sha256 and proof['event_receipt_sha256']==env['parent_artifact_ref']['event_receipt_sha256'] and proof['producer_code_sha256']==hashlib.sha256(Path(producer.__file__).read_bytes()).hexdigest()
result=build_receiving_effectiveness_catalog(source,before_period=202606);result['provenance'].update(actual_composition_read_at=now.isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),immutable_input_ref=ref,authenticated_source_intake=verified['provenance'],catalog_producer_sha256=hashlib.sha256(Path('backend/app/product_services/receiving_effectiveness_catalog.py').read_bytes()).hexdigest())
def save(v):
 raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/receiving_effectiveness_catalog')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items() if k not in {'actor_game_rows','team_denominators','unattributed_events','provenance','semantic_sha256','identity_review_requests'}}
for field in ('actor_game_rows','team_denominators','unattributed_events','identity_review_requests'):selected[field]=[r for r in result[field] if r.get('team') in {'SF','WAS'}]
selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};selected_ref=save(selected)
receipt=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=selected_ref,input_ref=ref,actor_game_rows=len(result['actor_game_rows']),selected_actor_game_rows=len(selected['actor_game_rows']),global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],coverage={m:dict(known_exact=sum(r['metrics'].get(m,{}).get('value') is not None for r in result['actor_game_rows']),with_measurement=sum(m in r['metrics'] for r in result['actor_game_rows'])) for m in DEFINITIONS},evidence_use=result['evidence_use'],models=0,source_fetches=0,parent_inflates=0)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
