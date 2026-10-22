from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.weekly_passing_air_efficiency import load_reviewed_weekly_input
from backend.app.product_services.schedule_context_features import load_schedule_context
from backend.app.product_services.historical_workload_trends import build_historical_workload_trends
from backend.app.product_services import active_workload_distributions as active_producer
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.factual_designation import clock
root=Path('research/historical_workload_trends_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
def load(ref,directory,limit):
 p=Path(ref['path']).resolve();assert p.parent==Path(directory).resolve()and p.name==ref['sha256']+'.json'and ref['bytes']<=limit
 raw=p.read_bytes();assert len(raw)==ref['bytes']and hashlib.sha256(raw).hexdigest()==ref['sha256'];return json.loads(raw)
weekly_ref=json.loads(Path('research/weekly_effectiveness_catalog_features_20261020/v1/actual_derivation_receipt.json').read_text())['full_ref'];weekly=load_reviewed_weekly_input(weekly_ref,cutoff=now);raw_ref=weekly['provenance']['source_extract_ref'];raw=load(raw_ref,'artifacts/weekly_effectiveness_sources',64*1024*1024)
active_ref=json.loads(Path('research/active_workload_distributions_20261020/v1/actual_receipt.json').read_text())['full_ref'];active=load(active_ref,'artifacts/active_workload_distributions',16*1024*1024)
assert active['provenance']['producer_code_sha256']==hashlib.sha256(Path(active_producer.__file__).read_bytes()).hexdigest()and active['provenance']['weekly_input_ref']==weekly_ref
assert active['pregame_serving_eligible']is False and active['before_period']==weekly['before_period']and clock(active['provenance']['actual_publication_at'])<=now
normalized=[{**r,'logs':[{k:v for k,v in log.items()if k not in{'source_ref','participation_ref'}}for log in r['logs']]}for r in active['rows']]
assert active['semantic_sha256']==digest(dict(version=active['version'],before_period=active['before_period'],definitions=active['definitions'],rows=normalized))
with Session(engine)as session:schedule=load_schedule_context(session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b'),cutoff=now)
result=build_historical_workload_trends(weekly,schedule,raw,before_period=weekly['before_period'],cutoff=now,positive_participants_missing_weekly=active['positive_participants_missing_weekly_rows'])
result['provenance'].update(weekly_input_ref=weekly_ref,source_extract_ref=raw_ref,active_input_ref=active_ref,actual_read_at=now.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/historical_workload_trends.py').read_bytes()).hexdigest())
def save(value):
 b=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(b)<=96*1024*1024;sha=hashlib.sha256(b).hexdigest();p=Path('artifacts/historical_workload_trends')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==b
 else:
  with p.open('xb')as f:f.write(b)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(b))
full=save(result);selected={**result,'rows':[r for r in result['rows']if r['team']in{'SF','WAS'}],'selection':dict(teams=['SF','WAS'],full_ref=full,all_native_budget_and_missingness_evidence_retained=True)};sel=save(selected)
coverage={}
for mid in('G22-M01','G22-M02'):
 coverage[mid]={c:{field:sum(r['metrics'][mid]['channels'][c][field]is not None for r in result['rows'])for field in('count_mean_difference','pooled_share_difference')}for c in('pass_attempts','rush_attempts','targets')}
out=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,weekly_input_ref=weekly_ref,source_extract_ref=raw_ref,active_input_ref=active_ref,actor_team_season_profiles=len(result['rows']),canonical_profiles=sum(r['player_master_id']is not None for r in result['rows']),selected_profiles=len(selected['rows']),coverage=coverage,retained_positive_missing_rows=len(result['positive_participants_missing_weekly']),raw_rows=len(raw['rows']),source_fetches=0,parent_inflations=0,database_writes=0,models=0)
(root/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
