"""One immutable provider download per NGS family, all returned historical seasons."""
from datetime import datetime,UTC
from pathlib import Path
from collections import Counter,defaultdict
import json,subprocess,sys,time,hashlib
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import PlayerAlias
from backend.app.services.source_capture import SourceCaptureService
from backend.app.product_services.nextgen_source_components import capture_nextgen_source,load_nextgen_snapshot,KINDS,FIELDS,URL
ROOT=Path('research/nextgen_source_components_20261020/v1')
def child(kind):
 started=time.monotonic();r=dict(stat_type=kind,source_uri=URL.format(kind=kind),actual_started_at=datetime.now(UTC).isoformat(),feature_catalog_verified_claims=0,models=0)
 try:
  with Session(engine) as session:
   cap=capture_nextgen_source(SourceCaptureService(session),stat_type=kind,season=2026,week=6,slate='offline_ngs_feature_inventory',slate_lock_at=datetime(2026,10,20,0,15,tzinfo=UTC));session.commit();s=cap.snapshot
   r.update(capture_status='captured_immutable_existing_source_service',snapshot_id=str(s.snapshot_id),artifact_path=s.artifact_path,manifest_path=s.manifest_path,sha256=s.content_sha256,bytes=s.byte_count,rows=s.row_count,captured_at=s.captured_at.isoformat(),observed_at=s.observed_at.isoformat(),metadata=s.metadata_json,pre_lock=cap.pre_lock)
   # Exact persisted native aliases only; ambiguity never becomes arbitrary UUID.
   aliases=defaultdict(set)
   for native,pid in session.execute(select(PlayerAlias.source_key,PlayerAlias.player_master_id).where(PlayerAlias.source_system=='nflreadpy')):
    if native and native.startswith('00-'):aliases[native].add(str(pid))
   ids={k:next(iter(v)) for k,v in aliases.items() if len(v)==1}
   loaded=load_nextgen_snapshot(s,stat_type=kind,cutoff=datetime.now(UTC),canonical_ids=ids);rows=loaded['rows']
   byyear={}
   for year in sorted({x['season'] for x in rows}):
    selected=[x for x in rows if x['season']==year]
    byyear[year]=dict(rows=len(selected),weekly_REG=sum(x['grain']=='weekly' and x['season_type']=='REG' for x in selected),weekly_POST=sum(x['grain']=='weekly' and x['season_type']=='POST' for x in selected),season_aggregate=sum(x['grain']=='season_aggregate' for x in selected),canonical_attached=sum(x['player_master_id'] is not None for x in selected),native_missing=sum(x['source_player_id'] is None for x in selected),field_missingness={f:sum(x['values'][f] is None for x in selected) for f in FIELDS[kind]},source_quality=dict(Counter(k for x in selected for k in x['source_quality'])))
   r.update(validation_status='verified_artifact_native_grain_types_missingness_unique_keys',by_season=byyear,field_availability=loaded['source']['field_availability'],source_columns=loaded['source']['source_columns'],canonical_alias_keys=len(ids),ambiguous_alias_keys=sum(len(v)>1 for v in aliases.values()),identity_review_request_count=len(loaded['identity_review_requests']),queue_status='Emitted immutable diagnostic requests; not persisted to identity queue by this job',weekly_feature_eligible=sum(x['weekly_feature_eligible'] for x in rows),original_historical_availability=loaded['original_historical_availability'],limitations=loaded['limitations'],evidence_use=loaded['evidence_use'],producer_code_sha256=loaded['producer_code_sha256'])
   # Preserve normalized source and all unresolved identities, independent of summary counts.
   payload=json.dumps(loaded,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(payload).hexdigest();dest=Path('artifacts/nextgen_source')/f'{sha}.json';dest.parent.mkdir(parents=True,exist_ok=True)
   if dest.exists():assert dest.read_bytes()==payload
   else:
    with dest.open('xb') as f:f.write(payload)
    dest.chmod(0o444)
   r['normalized_ref']=dict(path=str(dest.resolve()),sha256=sha,bytes=len(payload),rows=len(rows),pregame_serving_eligible=False)
 except Exception as exc:r.update(validation_status='unavailable_or_validation_failed',error_type=type(exc).__name__,error=str(exc))
 r.update(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-started)
 (ROOT/f'capture_{kind}.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
def main():
 start=datetime.now(UTC).isoformat();results=[]
 for kind in KINDS:
  print('START',kind,datetime.now(UTC).isoformat(),flush=True)
  with (ROOT/f'capture_{kind}.log').open('w') as out:
   try:code=subprocess.run([sys.executable,__file__,'--kind',kind],stdout=out,stderr=subprocess.STDOUT,timeout=90).returncode
   except subprocess.TimeoutExpired:code='timeout90seconds'
  p=ROOT/f'capture_{kind}.json';r=json.loads(p.read_text()) if p.exists() else dict(stat_type=kind,status='bounded_child_failure',returncode=code)
  results.append(r);(ROOT/'actual_capture_receipt.json').write_text(json.dumps(dict(actual_started_at=start,actual_updated_at=datetime.now(UTC).isoformat(),families=results,feature_catalog_verified_claims=0,models=0),indent=2)+'\n')
  print('DONE',kind,r.get('validation_status'),r.get('rows'),r.get('error'),flush=True)
if __name__=='__main__':
 if '--kind' in sys.argv:child(sys.argv[sys.argv.index('--kind')+1])
 else:main()
