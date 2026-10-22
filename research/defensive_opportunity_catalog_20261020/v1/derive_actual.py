from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.defensive_opportunity_catalog import load_reviewed_defensive_events,read_spike_source,build_defensive_opportunities
ROOT=Path('research/defensive_opportunity_catalog_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
r=json.loads(Path('research/defensive_event_distributions_20261020/v1/actual_receipt.json').read_text());parent_ref=r['full_ref']
with Session(engine) as session:
 snapshot=session.get(SourceSnapshot,r['source_parent_ref']['source_snapshot_id'])
 parent=load_reviewed_defensive_events(parent_ref,snapshot,cutoff=now)
 spikes=read_spike_source(snapshot,before_period=parent['before_period'])
 source=dict(snapshot_id=str(snapshot.snapshot_id),path=snapshot.artifact_path,sha256=snapshot.content_sha256,bytes=snapshot.byte_count,source_uri=snapshot.source_uri,observed_at=snapshot.observed_at.isoformat(),captured_at=snapshot.captured_at.isoformat())
result=build_defensive_opportunities(parent,spike_records=spikes)
result['provenance']=dict(parent_input_ref=parent_ref,parent_provenance=parent['provenance'],source_ref=source,
 actual_read_at=now.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),
 producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/defensive_opportunity_catalog.py').read_bytes()).hexdigest(),
 original_availability='Original frozen parent clocks retained; this NONSPIKE wrapper is newly derived postlock, not original pregame input')
raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/defensive_opportunity_catalog')/(sha+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==raw
else:
 with p.open('xb') as f:f.write(raw)
 p.chmod(0o444)
ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(raw));metrics=[x['metrics']['G23-M07'] for x in result['game_rows']]
out=dict(completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=ref,parent_input_ref=parent_ref,source_ref=source,
 native_game_sides=len(result['game_rows']),team_profiles=len(result['team_profiles']),raw_spike_rows=len(spikes),source_event_basis_rows=len(parent['event_basis']),
 exact_game_exposures=sum(m['exact_observed_opportunities'] is not None for m in metrics),known_eligible_lower_bound=sum(m['known_eligible_exposures_lower_bound'] for m in metrics),
 unknown_eligible_events=sum(m['unknown_eligible_events'] for m in metrics),semantic_sha256=result['semantic_sha256'],source_fetches=0,database_writes=0,parent_inflations=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
