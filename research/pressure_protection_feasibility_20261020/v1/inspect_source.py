"""Assess exact personnel-conditioned pressure response coverage, no IDs promoted."""
from pathlib import Path
from datetime import datetime,UTC
from collections import Counter
import hashlib,json,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.schedule_context_features import load_schedule_context
from backend.app.product_services.factual_designation import clock
from research.pressure_protection_feasibility_20261020.v1.assess import assess
root=Path('research/pressure_protection_feasibility_20261020/v1');start=time.monotonic();cutoff=datetime.now(UTC)
def read(ref,folder):
 p=Path(ref['path']);raw=p.read_bytes();assert p.resolve().parent==Path('artifacts',folder).resolve()and len(raw)==ref['bytes']<=8*1024*1024 and hashlib.sha256(raw).hexdigest()==ref['sha256'];return json.loads(raw)
for package in ('pfr_pressure_cohort','offensive_line_participation'):
 r=json.loads(Path('research',package+'_20261020','v1','receipt.json').read_text());assert r['review_status']=='High_FINAL_PASS_feature_only'
 for pin in r['pins']:
  p=Path(pin['path']);assert p.stat().st_size==pin['bytes']and hashlib.sha256(p.read_bytes()).hexdigest()==pin['sha256']
pressure_receipt=json.loads(Path('research/pfr_pressure_cohort_20261020/v1/actual_receipt.json').read_text());pressure=read(pressure_receipt['full_ref'],'pfr_pressure_catalog');assert clock(pressure['provenance']['actual_publication_at'])<=cutoff
line_receipt=json.loads(Path('research/offensive_line_participation_20261020/v1/actual_receipt.json').read_text());lines=[]
for item in line_receipt['outputs']:
 line=read(item['full_ref'],'offensive_line_participation');assert line['version']=='offensive_line_participation_v1'and line['pregame_serving_eligible']is False and clock(line['provenance']['actual_publication_at'])<=cutoff
 assert line['provenance']['producer_code_sha256']==hashlib.sha256(Path('backend/app/product_services/offensive_line_participation.py').read_bytes()).hexdigest();lines.append(line)
with Session(engine)as session:
 snapshot=session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b');schedule=load_schedule_context(snapshot,cutoff=cutoff)
result=assess(pressure,lines,schedule['game_rows']);summary=[]
for year in (2023,2024,2025):
 rows=[r for r in result['profiles']if r['season']==year]
 summary.append(dict(season=year,team_profiles=len(rows),known_three_axis_response_games=sum(r['known_three_axis_response_games']for r in rows),whole_profile_exact_contrasts=sum(r['whole_profile_exact_contrasts']for r in rows),strict_prior_window_exact_contrasts=sum(r['strict_prior_window_exact_contrasts']for r in rows)))
result['provenance']=dict(actual_read_at=cutoff.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),pressure_ref=pressure_receipt['full_ref'],line_refs=[r['full_ref']for r in line_receipt['outputs']],schedule=schedule['provenance'],producer_sha256=hashlib.sha256((root/'assess.py').read_bytes()).hexdigest())
raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/pressure_protection_feasibility')/(sha+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==raw
else:
 with p.open('xb')as f:f.write(raw)
 p.chmod(0o444)
receipt=dict(diagnostic_only=True,catalog_ids_completed=[],actual_started_at=cutoff.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,artifact_ref=dict(path=str(p.resolve()),bytes=len(raw),sha256=sha),coverage=summary,source_fetches=0,parent_inflates=0,aliases_or_queue_mutated=0,models=0)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2),flush=True)
