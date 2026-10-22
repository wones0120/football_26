from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import verify_snapshot_artifact
from backend.app.product_services.weekly_passing_air_efficiency import load_reviewed_weekly_input
from backend.app.product_services.schedule_context_features import load_schedule_context
from backend.app.product_services.absence_return_opportunity import load_reviewed_absence_input,build_absence_return_opportunity
ROOT=Path('research/absence_return_opportunity_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
a=json.loads(Path('research/official_absence_path_20261020/v1/actual_receipt.json').read_text());absence_ref=a['artifact_ref']
absences=load_reviewed_absence_input(absence_ref,cutoff=now);weekly_ref=a['weekly_input_ref'];weekly=load_reviewed_weekly_input(weekly_ref,cutoff=now)
assert absences['provenance']['weekly_input_ref']==weekly_ref
with Session(engine) as session:
 for r in (a['pdf_source_ref'],a['roster_source_ref']):
  snapshot=session.get(SourceSnapshot,r['snapshot_id']);verify_snapshot_artifact(snapshot)
  assert snapshot.content_sha256==r['sha256'] and snapshot.byte_count==r['bytes'] and snapshot.artifact_path==r['path']
 schedule=load_schedule_context(session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b'),cutoff=now)
 assert absences['provenance']['schedule']['snapshot_id']==schedule['provenance']['snapshot_id']
 assert absences['provenance']['schedule']['sha256']==schedule['provenance']['sha256']
result=build_absence_return_opportunity(absences,weekly,schedule,before_period=202507,cutoff=now)
result['provenance'].update(absence_input_ref=absence_ref,weekly_input_ref=weekly_ref,actual_read_at=now.isoformat(),
 actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),
 producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/absence_return_opportunity.py').read_bytes()).hexdigest())
raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/absence_return_opportunity')/(sha+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==raw
else:
 with p.open('xb') as f:f.write(raw)
 p.chmod(0o444)
ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
coverage={}
for ordinal in (1,2,3):
 slots=[x for r in result['rows'] for x in r['scheduled_postabsence_slots'] if x['certified_active_ordinal']==ordinal]
 coverage[str(ordinal)]=dict(certified_active_rows=len(slots),known_differences={c:sum(x['baseline_difference'][c] is not None for x in slots) for c in ('pass_attempts','rush_attempts','targets')})
out=dict(completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=ref,absence_input_ref=absence_ref,
 weekly_input_ref=weekly_ref,source_adapter_receipt='research/official_absence_path_20261020/v1/actual_receipt.json',
 native_anchor_profiles=len(result['rows']),canonical_profiles=sum(r['player_master_id'] is not None for r in result['rows']),coverage=coverage,
 observed_prefix='2025 weeks1–6, three scheduled postanchor slots; fixed two scheduled preabsence baseline',
 inherited_identity_readback=a['identity_readback'],semantic_sha256=result['semantic_sha256'],source_fetches=0,database_writes=0,parent_inflations=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
