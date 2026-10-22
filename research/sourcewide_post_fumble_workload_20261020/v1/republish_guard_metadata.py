"""Metadata-only guard revision; original measurements and their producer remain bound."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from backend.app.product_services.evaluation_record import digest
R=Path('research/sourcewide_post_fumble_workload_20261020/v1');start=datetime.now(UTC);tick=time.monotonic()
def sha(b):return hashlib.sha256(b).hexdigest()
archive=R/'prior_24test_revision';e=json.loads((archive/'immutable_pins.json').read_text())
for pin in e['pins']:
 b=(archive/Path(pin['path']).name).read_bytes();assert len(b)==pin['bytes']and sha(b)==pin['sha256']
old_code=(archive/'sourcewide_post_fumble_workload.py').read_text();current_code=Path('backend/app/product_services/sourcewide_post_fumble_workload.py').read_text()
a=old_code.index('                for r in uncertain_by_game[gid]:');z=old_code.index('                exact=exact_anchor',a);block=old_code[a:z]
expected=old_code[:a]+'                if anchor is not None:\n'+''.join('    '+line+'\n'for line in block.rstrip('\n').split('\n'))+old_code[z:];assert current_code==expected
prior=json.loads((archive/'actual_receipt.json').read_text())
def load(ref):
 p=Path(ref['path']);b=p.read_bytes();assert len(b)==ref['bytes']<=64*1024*1024 and sha(b)==ref['sha256'];return json.loads(b)
def save(x):
 b=json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode();p=Path('artifacts/sourcewide_post_fumble_workload')/(sha(b)+'.json')
 if p.exists():assert p.read_bytes()==b
 else:
  with p.open('xb')as f:f.write(b)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha(b),bytes=len(b))
x=load(prior['full_ref']);old=load(prior['full_ref']);assert x['uncertain_official_rows']==[] and x['provenance']['producer_code_sha256']==sha(old_code.encode())
keys=('version','candidate_id','before_period','rows','possible_anchor_evidence','excluded_anchor_evidence','official_channel_event_basis','unknown_order_games','potential_native_fumbler_ids','uncertain_official_rows','identity_qualification','identity_review_requests')
assert digest({k:x[k]for k in keys})==x['semantic_sha256']
x['provenance'].update(original_measurement_full_ref=prior['full_ref'],original_measurement_producer_sha256=sha(old_code.encode()),guard_revision_code_sha256=sha(current_code.encode()),actual_guard_metadata_publication_at=datetime.now(UTC).isoformat(),guard_revision_reason='AnchorNone guard for synthetic uncertain-official-row branch; actual uncertain_official_rows empty, zero numeric/source/identity/queue replay')
full=save(x);s=load(prior['selected_ref']);s['provenance']=x['provenance'];s['selection']['full_ref']=full;selected=save(s)
assert {k:x[k]for k in keys}=={k:old[k]for k in keys}
proof=dict(actual_started_at=start.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-tick,original_full_ref=prior['full_ref'],new_full_ref=full,original_selected_ref=prior['selected_ref'],new_selected_ref=selected,entire_semantic_core_equal=True,rows_metrics_and_identity_equal=x['rows']==old['rows']and x['identity_qualification']==old['identity_qualification'],semantic_sha256=x['semantic_sha256'],actual_guard_branch_iterations=0,original_measurement_producer_preserved=True,queue_replays=0,raw_reads=0,parent_decodes=0,database_reads=0,database_writes=0,numeric_transform_reruns=0)
assert proof['rows_metrics_and_identity_equal']
(R/'guard_metadata_parity.json').write_text(json.dumps(proof,indent=2)+'\n');prior.update(full_ref=full,selected_ref=selected,guard_metadata_refresh=proof);(R/'actual_receipt.json').write_text(json.dumps(prior,indent=2)+'\n');print(json.dumps(proof))
