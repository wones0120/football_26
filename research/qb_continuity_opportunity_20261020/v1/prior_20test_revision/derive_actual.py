from pathlib import Path
from datetime import datetime, UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.weekly_passing_air_efficiency import load_reviewed_weekly_input
from backend.app.product_services.workload_starting_qb_context import load_starting_qb_context
from backend.app.product_services.qb_continuity_opportunity import build_qb_continuity_opportunity
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services import active_workload_distributions as active_producer
ROOT=Path('research/qb_continuity_opportunity_20261020/v1'); start=time.monotonic(); now=datetime.now(UTC)
def load(ref, directory, limit):
 p=Path(ref['path']).resolve();assert p.parent==Path(directory).resolve() and p.name==ref['sha256']+'.json' and ref['bytes']<=limit
 raw=p.read_bytes();assert len(raw)==ref['bytes'] and hashlib.sha256(raw).hexdigest()==ref['sha256'];return json.loads(raw)
r=json.loads(Path('research/weekly_effectiveness_catalog_features_20261020/v1/actual_derivation_receipt.json').read_text());weekly_ref=r['full_ref']
weekly=load_reviewed_weekly_input(weekly_ref,cutoff=now);extract_ref=weekly['provenance']['source_extract_ref'];source=load(extract_ref,'artifacts/weekly_effectiveness_sources',64*1024*1024)
active_path=Path('artifacts/active_workload_distributions/287d669a3c24c92ee7533170ccceb3adb543d3e39e23ae92819cfff8fbaf506b.json')
active_ref=dict(path=str(active_path.resolve()),sha256=active_path.stem,bytes=10537497)
active=load(active_ref,'artifacts/active_workload_distributions',16*1024*1024)
assert active['provenance']['producer_code_sha256']==hashlib.sha256(Path(active_producer.__file__).read_bytes()).hexdigest()
assert active['provenance']['weekly_input_ref']==weekly_ref
assert active['before_period']==weekly['before_period'] and active['pregame_serving_eligible'] is False
with Session(engine) as session:
 snapshot=session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b');schedule,starters=load_starting_qb_context(snapshot,cutoff=now)
read_end=datetime.now(UTC)
result=build_qb_continuity_opportunity(weekly,schedule,starters,source,before_period=weekly['before_period'],cutoff=now,
 positive_participants_missing_weekly=active['positive_participants_missing_weekly_rows'])
producer=Path('backend/app/product_services/qb_continuity_opportunity.py');result['provenance'].update(weekly_input_ref=weekly_ref,source_extract_ref=extract_ref,
 active_input_ref=active_ref,starter_source=starters['provenance'],actual_read_started_at=now.isoformat(),actual_read_completed_at=read_end.isoformat(),
 actual_derived_at=datetime.now(UTC).isoformat(),producer_code_sha256=hashlib.sha256(producer.read_bytes()).hexdigest(),actual_publication_at=datetime.now(UTC).isoformat())
def save(value):
 data=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(data)<=96*1024*1024
 sha=hashlib.sha256(data).hexdigest();p=Path('artifacts/qb_continuity_opportunity')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==data
 else:
  with p.open('xb') as out:out.write(data)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(data))
full=save(result);selected={k:v for k,v in result.items() if k not in {'rows','semantic_sha256','provenance'}}
selected['rows']=[r for r in result['rows'] if r['team'] in {'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};small=save(selected)
coverage={}
for mid in ('X03-M03','X03-M04'):
 rows=[r for r in result['rows'] if r['candidate_id']==mid]
 coverage[mid]=dict(actor_team_season_profiles=len(rows),canonical_profiles=sum(r['player_master_id'] is not None for r in rows),
 known_target_mean_contrasts=sum(r['changed_minus_same_target_mean'] is not None for r in rows),known_pooled_share_contrasts=sum(r['changed_minus_same_pooled_target_share'] is not None for r in rows),
 unknown_continuity_logs=sum(r['unknown_continuity_logs'] for r in rows))
receipt=dict(completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=small,
 weekly_input_ref=weekly_ref,source_extract_ref=extract_ref,active_input_ref=active_ref,schedule_provenance=schedule['provenance'],
 semantic_sha256=result['semantic_sha256'],selected_rows=len(selected['rows']),source_raw_rows=len(source['rows']),
 positive_participants_missing_weekly_retained=len(result['missing_positive_participants']),coverage=coverage,
 evidence_use=result['evidence_use'],source_fetches=0,database_writes=0,parent_inflations=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
