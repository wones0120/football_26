from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from backend.app.product_services.weekly_passing_air_efficiency import load_reviewed_weekly_input
from backend.app.product_services.absence_return_opportunity import load_reviewed_absence_input
from backend.app.product_services.availability_history_catalog import load_reviewed_return_input,build_availability_history
ROOT=Path('research/availability_history_catalog_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
a=json.loads(Path('research/official_absence_path_20261020/v1/actual_receipt.json').read_text());r=json.loads(Path('research/absence_return_opportunity_20261020/v1/actual_receipt.json').read_text())
absence=load_reviewed_absence_input(a['artifact_ref'],cutoff=now);returns=load_reviewed_return_input(r['full_ref'],cutoff=now)
assert returns['provenance']['absence_input_ref']==a['artifact_ref'] and returns['provenance']['weekly_input_ref']==a['weekly_input_ref']
weekly=load_reviewed_weekly_input(a['weekly_input_ref'],cutoff=now)
result=build_availability_history(absence,returns,weekly,cutoff=now)
result['provenance'].update(absence_input_ref=a['artifact_ref'],return_input_ref=r['full_ref'],weekly_input_ref=a['weekly_input_ref'],
 actual_read_at=now.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),
 producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/availability_history_catalog.py').read_bytes()).hexdigest())
raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/availability_history_catalog')/(sha+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==raw
else:
 with p.open('xb') as f:f.write(raw)
 p.chmod(0o444)
ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
out=dict(completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=ref,absence_input_ref=a['artifact_ref'],return_input_ref=r['full_ref'],weekly_input_ref=a['weekly_input_ref'],
 ordinary_inactive_history_rows=len(result['inactive_history_rows']),canonical_inactive_rows=sum(x['source_fact']['player_master_id'] is not None for x in result['inactive_history_rows']),
 separate_DNP_or_emergency_rows=len(result['excluded_source_domains']),offensive_return_profiles=len(result['return_status_rows']),
 proven_first_returns=sum(x['first_return_proven'] is True for x in result['return_status_rows']),known_role_continuity=sum(x['observed_source_role_continuity'] is not None for x in result['return_status_rows']),
 inherited_identity_readback=a['identity_readback'],semantic_sha256=result['semantic_sha256'],source_fetches=0,database_writes=0,parent_inflations=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
