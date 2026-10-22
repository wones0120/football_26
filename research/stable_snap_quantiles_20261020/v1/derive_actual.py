from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.weekly_passing_air_efficiency import load_reviewed_weekly_input
from backend.app.product_services.schedule_context_features import load_schedule_context
from backend.app.product_services.recent_snap_features import load_frozen_snap_revision
from backend.app.product_services.stable_snap_quantiles import normalize_stability_snaps,build_stable_snap_quantiles
from backend.app.product_services.evaluation_record import digest
ROOT=Path('research/stable_snap_quantiles_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
wr=json.loads(Path('research/weekly_effectiveness_catalog_features_20261020/v1/actual_derivation_receipt.json').read_text());weekly_ref=wr['full_ref'];weekly=load_reviewed_weekly_input(weekly_ref,cutoff=now)
extract_ref=weekly['provenance']['source_extract_ref'];path=Path(extract_ref['path']).resolve();assert path.parent==Path('artifacts/weekly_effectiveness_sources').resolve() and path.name==extract_ref['sha256']+'.json' and extract_ref['bytes']<=64*1024*1024
h=hashlib.sha256();size=0
with path.open('rb') as f:
 while b:=f.read(1024*1024):h.update(b);size+=len(b)
assert size==extract_ref['bytes'] and h.hexdigest()==extract_ref['sha256']
with Session(engine) as session:
 snapshot=session.get(SourceSnapshot,'706735c7-e1c2-5e98-a662-52021f0406b3');validated=load_frozen_snap_revision(snapshot,cutoff=now)
 frozen=json.loads(Path(snapshot.artifact_path).read_text());snap_ref=dict(snapshot_id=str(snapshot.snapshot_id),sha256=snapshot.content_sha256,bytes=snapshot.byte_count,path=snapshot.artifact_path)
 schedule=load_schedule_context(session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b'),cutoff=now)
 sn=normalize_stability_snaps(frozen,validated,before_period=202606)
result=build_stable_snap_quantiles(weekly,schedule,sn,before_period=202606,cutoff=now)
result['provenance'].update(weekly_input_ref=weekly_ref,source_extract_ref=extract_ref,snap_source_ref=snap_ref,
 actual_read_at=now.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),
 producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/stable_snap_quantiles.py').read_bytes()).hexdigest(),
 snap_reader_code_sha256=hashlib.sha256(Path('backend/app/product_services/recent_snap_features.py').read_bytes()).hexdigest())
def save(x):
 raw=json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=64*1024*1024
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/stable_snap_quantiles')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as out:out.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items() if k not in {'rows','semantic_sha256','provenance'}};selected['rows']=[r for r in result['rows'] if r['team'] in {'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};small=save(selected)
coverage={}
for mid in ('X02-M06','X02-M07'):
 metrics=[r['metrics'][mid] for r in result['rows']];coverage[mid]=dict(exact_quantiles=sum(m['exact_conditional_q90'] is not None for m in metrics),known_sample_quantiles=sum(m['known_sample_q90'] is not None for m in metrics),qualified_response_slots=sum(m['qualified_target_games'] for m in metrics),unknown_qualification_slots=sum(m['unknown_qualification_games'] for m in metrics),missing_qualified_responses=sum(m['missing_qualified_responses'] for m in metrics))
out=dict(completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=small,weekly_input_ref=weekly_ref,source_extract_ref=extract_ref,snap_source_ref=snap_ref,
 native_actor_profiles=len(result['rows']),canonical_profiles=sum(r['player_master_id'] is not None for r in result['rows']),selected_profiles=len(selected['rows']),coverage=coverage,
 semantic_sha256=result['semantic_sha256'],source_fetches=0,database_writes=0,parent_inflations=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
