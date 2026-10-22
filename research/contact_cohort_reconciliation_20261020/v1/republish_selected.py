"""Metadata-only slice repair, source/full feature/queue evidence unchanged."""
from pathlib import Path
from datetime import datetime,UTC
import hashlib,json,time
from research.contact_cohort_reconciliation_20261020.v1.selection import select_contact_scope
root=Path('research/contact_cohort_reconciliation_20261020/v1');r=json.loads((root/'actual_receipt.json').read_text());ref=r['full_ref'];start=time.monotonic();at=datetime.now(UTC).isoformat()
p=Path(ref['path']);raw=p.read_bytes();assert len(raw)==ref['bytes']and hashlib.sha256(raw).hexdigest()==ref['sha256'];full=json.loads(raw)
selected=select_contact_scope(full,{'SF','WAS'});selected['provenance']={**full['provenance'],'full_ref':ref,'actual_selected_at':at,'selection_producer_sha256':hashlib.sha256((root/'selection.py').read_bytes()).hexdigest()}
raw=json.dumps(selected,sort_keys=True,separators=(',',':'),allow_nan=False,default=str).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/contact_cohort_reconciliation')/(sha+'.json')
if p.exists():assert p.read_bytes()==raw
else:
 with p.open('xb')as f:f.write(raw)
 p.chmod(0o444)
prior=r['selected_ref'];r.update(selected_ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(raw)),selected_semantic_sha256=selected['selected_semantic_sha256'],
 selected_scope_revision=dict(actual_republished_at=at,elapsed_seconds=time.monotonic()-start,prior_selected_ref=prior,full_source_and_feature_unchanged=True,identity_requests='All batch-global cases retained; defense metric scope SF/WAS',database_writes=0,source_reads=0))
(root/'actual_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r['selected_scope_revision']),flush=True)
