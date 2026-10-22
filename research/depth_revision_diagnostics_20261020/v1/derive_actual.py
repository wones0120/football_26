from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from backend.app.product_services.depth_revision_diagnostics import build_depth_revision_diagnostics
import backend.app.product_services.depth_revision_diagnostics as producer
import backend.app.product_services.observed_depth_changes as parent_producer
R=Path('research/depth_revision_diagnostics_20261020/v1');now=datetime.now(UTC);start=time.monotonic()
ref=json.loads(Path('research/observed_depth_changes_20261020/v1/actual_receipt.json').read_text())['artifact_ref'];p=Path(ref['path']).resolve();raw=p.read_bytes();assert p.parent==Path('artifacts/observed_depth_changes').resolve() and p.name==ref['sha256']+'.json' and len(raw)==ref['bytes'] and hashlib.sha256(raw).hexdigest()==ref['sha256'];parent=json.loads(raw)
assert parent['provenance']['producer_sha256']==hashlib.sha256(Path(parent_producer.__file__).read_bytes()).hexdigest()
result=build_depth_revision_diagnostics(parent,cutoff=now);result['provenance']=dict(parent_ref=ref,actual_read_at=now.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),producer_sha256=hashlib.sha256(Path(producer.__file__).read_bytes()).hexdigest(),parent_original_and_actual_provenance=parent['provenance'])
raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/depth_revision_diagnostics')/(sha+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==raw
else:
 with p.open('xb') as f:f.write(raw)
r=dict(artifact_ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(raw)),parent_ref=ref,pairs=len(result['rows']),known_matched_roles=sum(r['units']['all_literal_roles']['known_delta_roles'] for r in result['rows']),rank_revision_count=sum(r['units']['all_literal_roles']['known_rank_revision_count'] for r in result['rows']),absolute_rank_delta_sum=sum(r['units']['all_literal_roles']['known_absolute_rank_delta_sum'] or 0 for r in result['rows']),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,evidence_use=result['evidence_use'],source_fetches=0,parent_inflates=0,database_writes=0,model_fits=0)
(R/'actual_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
