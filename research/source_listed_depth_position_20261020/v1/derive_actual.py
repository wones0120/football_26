from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from backend.app.product_services.source_listed_depth_position import build_source_listed_depth_position,load_reviewed_depth_parent
ROOT=Path('research/source_listed_depth_position_20261020/v1');started=datetime.now(UTC);tick=time.monotonic()
def sha(b):return hashlib.sha256(b).hexdigest()
ref=json.loads(Path('research/observed_depth_changes_20261020/v1/actual_receipt.json').read_text())['artifact_ref'];parent=load_reviewed_depth_parent(ref,cutoff=started);result=build_source_listed_depth_position(parent,cutoff=started)
qpath=Path('research/observed_depth_changes_20261020/v1/identity_receipt.json');qb=qpath.read_bytes();queue=json.loads(qb);qref=dict(path=str(qpath.resolve()),sha256=sha(qb),bytes=len(qb));assert {(q['source_snapshot_id'],q['source_row'])for q in queue['records']}=={(q['source_snapshot_id'],q['source_row'])for q in parent['identity_review_requests']}
result['provenance']=dict(approved_depth_parent_ref=ref,parent_semantic_sha256=parent['semantic_sha256'],original_measurement_derived_at=parent['provenance']['actual_derived_at'],original_source_clocks=parent['provenance']['sources'],frozen_native_identity_attachment=parent['provenance']['identity_attachment'],inherited_identity_incident_receipt_ref=qref,source_adapter_replays=0,database_reads=0,database_writes=0,identity_replays=0,new_captures=0,models=0,actual_parent_read_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_sha256=sha(Path('backend/app/product_services/source_listed_depth_position.py').read_bytes()),original_availability='Source document/observation/capture and current feature publication are distinct; provider effective-season-week/target applicability unknown')
b=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode();p=Path('artifacts/source_listed_depth_position')/(sha(b)+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==b
else:
 with p.open('xb')as f:f.write(b)
 p.chmod(0o444)
full=dict(path=str(p.resolve()),sha256=sha(b),bytes=len(b))
out=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-tick,full_ref=full,parent_ref=ref,semantic_sha256=result['semantic_sha256'],source_capture_scope=result['capture_scope'],frames=result['frames'],native_role_facts=len(result['role_facts']),known_native_ranks=sum(r['source_depth_order']is not None for r in result['role_facts']),canonical_role_facts=sum(r['player_master_id']is not None for r in result['role_facts']),source_native_players=len({r['source_player_id']for r in result['role_facts']}),special_unit_role_facts=sum(r['unit']=='special_teams'for r in result['role_facts']),unkeyed_current_source_rows=len(result['unknown_source_roles']),inherited_identity_incidents=len(queue['records']),new_identity_incidents=0,source_adapter_replays=0,database_reads=0,database_writes=0,new_captures=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
