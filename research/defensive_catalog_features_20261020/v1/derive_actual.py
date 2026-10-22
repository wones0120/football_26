"""One explicit offline retrospective parent read, real current publication clocks."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time,sys,csv
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.factual_designation import clock
from backend.app.product_services.offensive_environment_catalog import load_reviewed_environment_context
from backend.app.product_services.opportunity_source_capture import load_event_artifact
from backend.app.product_services.defense_context_extensions import build_defense_context_extensions
from backend.app.product_services.defensive_catalog_features import build_defensive_catalog,DEFINITIONS,measure_yac_lateral_coverage
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services import defense_context_evidence as base_producer
root=Path('research/defensive_catalog_features_20261020/v1');start=time.monotonic();actual=datetime.now(UTC)
env=json.loads(Path('research/environment_context_evidence_20261019/v1/actual_combined_receipt.json').read_text());ref=env['parent_artifact_ref'];original=clock(ref['decision_cutoff_at'])
with Session(engine) as session:
 snapshot=session.get(SourceSnapshot,ref['source_snapshot_id']);lock=clock(snapshot.slate_lock_at)
 if not original<lock<=actual<=datetime.now(UTC):raise ValueError('Explicit retrospective original-boundary/current-read proof required')
 verified=load_reviewed_environment_context(env['full_context'],snapshot,actual_read_at=actual)
 if '--extensions' in sys.argv:
  ext_path=Path(sys.argv[sys.argv.index('--extensions')+1]).resolve();ext_raw=ext_path.read_bytes()
  if ext_path.parent!=Path('artifacts/defensive_catalog').resolve() or len(ext_raw)>16*1024*1024 or hashlib.sha256(ext_raw).hexdigest()!=ext_path.stem:raise ValueError('Managed immutable extensions required')
  ext=json.loads(ext_raw)
  if ext.get('evidence_use')!='postlock_descriptive_not_pregame_or_serving' or ext.get('pregame_serving_eligible') is not False or clock(ext['provenance']['retrospective_read']['actual_derived_at'])>actual:raise ValueError('Explicit prior retrospective extensions required')
 else:
  parent=load_event_artifact(ref,snapshot,before_period=ref['before_period'],cutoff=original)
  ext=build_defense_context_extensions(parent,before_period=ref['before_period'],cutoff=actual)
  ext.update(evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False)
  ext['provenance']['retrospective_read']=dict(original_evidence_boundary_at=original.isoformat(),actual_read_at=actual.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),source_lock_at=lock.isoformat(),meaning='Original cutoff verifies frozen parent only; output is not pregame evidence',parent_artifact_ref=ref);ext['provenance'].pop('decision_cutoff_at',None)
base_ref=json.loads(Path('research/defense_context_evidence_20261019/v1/actual_combined_receipt.json').read_text())['full_context'];path=Path(base_ref['path']).resolve();raw=path.read_bytes();assert path.parent==Path('artifacts/opportunity_context').resolve() and path.name==base_ref['sha256']+'.json' and len(raw)==base_ref['bytes'] and hashlib.sha256(raw).hexdigest()==base_ref['sha256']
base=json.loads(raw);assert base['provenance']['producer_code_sha256']==hashlib.sha256(Path(base_producer.__file__).read_bytes()).hexdigest()
def save(v):
 raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/defensive_catalog')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))

with Path(ext['provenance']['source']['artifact_path']).open() as f:lateral=measure_yac_lateral_coverage(csv.DictReader(f),before_period=ref['before_period'])
from backend.app.services.source_capture import verify_snapshot_artifact
verify_snapshot_artifact(snapshot)
ext_ref=save(ext);result=build_defensive_catalog(base,ext,before_period=ref['before_period'],yac_lateral_evidence=lateral);result['provenance'].update(actual_publication_at=datetime.now(UTC).isoformat(),immutable_input_refs=dict(base=base_ref,extensions=ext_ref),authenticated_intake=verified['provenance'],producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/defensive_catalog_features.py').read_bytes()).hexdigest())
full=save(result);selected={k:v for k,v in result.items() if k not in {'game_rows','team_windows','semantic_sha256','provenance'}};selected['game_rows']=[r for r in result['game_rows'] if r['defense_team'] in {'SF','WAS'}];selected['team_windows']=[r for r in result['team_windows'] if r['defense_team'] in {'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
receipt=dict(actual_read_at=actual.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,extension_ref=ext_ref,base_ref=base_ref,parent_ref=ref,global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],game_rows=len(result['game_rows']),team_windows=len(result['team_windows']),selected_game_rows=len(selected['game_rows']),coverage={m:dict(known_exact=sum(r['metrics'][m].get('catalog_value',r['metrics'][m]['value']) is not None for r in result['game_rows']),unknown_or_zero=sum(r['metrics'][m].get('catalog_value',r['metrics'][m]['value']) is None for r in result['game_rows'])) for m in DEFINITIONS},parent_inflates=0 if '--extensions' in sys.argv else 1,source_fetches=0,models=0,evidence_use=result['evidence_use'])
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
