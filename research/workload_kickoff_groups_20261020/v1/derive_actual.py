from pathlib import Path
from datetime import datetime,UTC
import hashlib,json,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.workload_kickoff_groups import load_kickoff_context
from backend.app.product_services.workload_kickoff_groups import build_workload_kickoff_groups
from backend.app.product_services import weekly_effectiveness_catalog_features as producer
from backend.app.product_services.evaluation_record import digest
root=Path('research/workload_kickoff_groups_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
r=json.loads(Path('research/weekly_effectiveness_catalog_features_20261020/v1/actual_derivation_receipt.json').read_text());ref=r['full_ref'];p=Path(ref['path']).resolve();raw=p.read_bytes()
assert p.parent==Path('artifacts/weekly_effectiveness_catalog').resolve() and p.name==ref['sha256']+'.json' and len(raw)==ref['bytes'] and len(raw)<=96*1024*1024 and hashlib.sha256(raw).hexdigest()==ref['sha256'];weekly=json.loads(raw)
assert weekly['provenance']['producer_code_sha256']==hashlib.sha256(Path(producer.__file__).read_bytes()).hexdigest()
extract=weekly['provenance']['source_extract_ref'];path=Path(extract['path']).resolve();raw=path.read_bytes();assert path.parent==Path('artifacts/weekly_effectiveness_sources').resolve() and path.name==extract['sha256']+'.json' and len(raw)==extract['bytes'] and hashlib.sha256(raw).hexdigest()==extract['sha256'];frozen=json.loads(raw)

with Session(engine) as session:
 snapshot=session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b');schedule,kickoff=load_kickoff_context(snapshot,before_period=weekly['before_period'],cutoff=now)
result=build_workload_kickoff_groups(weekly,schedule,kickoff,before_period=weekly['before_period']);result['provenance'].update(weekly_input_ref=ref,source_extract_ref=extract,actual_read_at=now.isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/workload_kickoff_groups.py').read_bytes()).hexdigest())
def save(v):
 raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=96*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/workload_kickoff_groups')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items() if k not in {'rows','provenance','semantic_sha256'}};selected['rows']=[row for row in result['rows'] if row['season']==2026 and row['team'] in {'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
import csv,re
qb_fields=('home_qb_id','away_qb_id');qb_coverage={};qb_field_availability={}
with Path(snapshot.artifact_path).open(newline='') as stream:
 reader=csv.DictReader(stream);qb_field_availability={field:field in (reader.fieldnames or []) for field in qb_fields}
 for row in reader:
  season=int(row['season']);week=int(row['week']);phase=row['game_type'];scope='prior' if season*100+week<weekly['before_period'] else 'current_or_future'
  key=f'{season}:{phase}:{scope}';entry=qb_coverage.setdefault(key,dict(native_game_rows=0,home_qb_known_GSIS=0,away_qb_known_GSIS=0,home_qb_missing_or_invalid=0,away_qb_missing_or_invalid=0));entry['native_game_rows']+=1
  for field in qb_fields:
   prefix=field[:4];known=bool(re.fullmatch(r'00-\d{7}',row.get(field) or ''));entry[prefix+('_qb_known_GSIS' if known else '_qb_missing_or_invalid')]+=1
receipt=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,weekly_input_ref=ref,source_extract_ref=extract,schedule_provenance=schedule['provenance'],actor_team_rows=len(result['rows']),known_differences={mid:{ch:sum(row['metrics'][mid]['channels'][ch]['night_minus_earlier'] is not None for row in result['rows']) for ch in ['pass_attempts','rush_attempts','targets']} for mid in ['G21-M06']},selected_rows=len(selected['rows']),global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],kickoff_context_provenance=kickoff['provenance'],kickoff_native_prior_games=len(kickoff['rows']),starting_QB_native_field_availability=qb_field_availability,starting_QB_native_coverage=qb_coverage,starting_QB_scope_warning='Source-native reported starting QB only; revised later capture does not establish original pregame availability or future target starter',evidence_use=result['evidence_use'],models=0,source_fetches=0,database_writes=0)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
