"""Four sequential historical raw-source captures and bounded native validation."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time,gc
from sqlalchemy import select
from sqlalchemy.orm import Session
import polars as pl
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import SourceCaptureService
from backend.app.product_services.participation_source_components import capture_participation_source,load_participation_snapshot,audit_native_participation_join,URL
root=Path('research/participation_source_components_20261020/v1');start=time.monotonic();outputs=[];errors=[]
history={r['season']:r['descriptor']for r in json.loads(Path('research/player_opportunity_history_20261020/v1/source_coverage.json').read_text())}
with Session(engine)as session:
 for season in (2022,2023,2024,2025):
  stage='existing_source_inventory'
  try:
   existing=session.scalars(select(SourceSnapshot).where(SourceSnapshot.source_uri==URL.format(season=season)).order_by(SourceSnapshot.captured_at.desc())).first()
   stage='source_capture'
   if existing is None:
    captured=capture_participation_source(SourceCaptureService(session),season=season,slate_lock_at=datetime(2026,10,20,0,15,tzinfo=UTC));session.commit();snapshot=captured.snapshot;reused=False
   else:snapshot=existing;reused=True
   stage='source_normalization';block=load_participation_snapshot(snapshot,actual_read_at=datetime.now(UTC))
   join=dict(status='unverified_no_retained2022PBPsource',meaning='No absent source/zero coverage inference')
   if season in history:
    stage='native_PBP_join';descriptor=history[season];p=Path(descriptor['path']);raw=p.read_bytes();assert len(raw)==descriptor['manifest']['bytes']and hashlib.sha256(raw).hexdigest()==descriptor['manifest']['sha256'];del raw
    frame=pl.read_parquet(p,columns=['game_id','play_id','season','week','season_type','posteam'])
    join=audit_native_participation_join(block,frame.iter_rows(named=True),season=season);join['original_PBP_manifest']=descriptor['manifest'];del frame
   source=dict(snapshot_id=str(snapshot.snapshot_id),source_uri=snapshot.source_uri,sha256=snapshot.content_sha256,bytes=snapshot.byte_count,artifact_path=snapshot.artifact_path,
    captured_at=str(snapshot.captured_at),observed_at=str(snapshot.observed_at),metadata=snapshot.metadata_json)
   output=dict(season=season,status='captured_and_validated',source_reused=reused,source=source,rows=len(block['rows']),source_columns=block['provenance']['source_columns'],
    known_measurement_rows=block['known_measurement_rows'],unknown_measurement_rows=block['unknown_measurement_rows'],native_list_issue_count=len(block['native_list_issues']),
    native_position_proven_rows={side:sum(r['participant_scopes'][side]['position_by_native_id']is not None for r in block['rows'])for side in ('offense','defense')},
    semantic_sha256=block['semantic_sha256'],native_PBP_join=join,actual_validation_at=datetime.now(UTC).isoformat(),
    evidence_use=block['evidence_use'],pregame_serving_eligible=False)
   outputs.append(output);del block;gc.collect()
  except Exception as exc:
   session.rollback();errors.append(dict(season=season,stage=stage,error_type=type(exc).__name__,error=str(exc)[:500]))
  (root/'capture_progress.json').write_text(json.dumps(dict(outputs=outputs,errors=errors,elapsed_seconds=time.monotonic()-start),indent=2)+'\n')
  print(json.dumps(dict(season=season,stage=stage,validated_rows=outputs[-1]['rows']if outputs and outputs[-1]['season']==season else None,errors=errors[-1:]if errors and errors[-1]['season']==season else [],elapsed_seconds=time.monotonic()-start)),flush=True)
receipt=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,outputs=outputs,errors=errors,
 source_scope='2022NFLNGS;2023–25FTNpostseasonhistorical;2026unsupportedbyinstalledprovidercontract',original_historical_publication='Unknown; actual capture/HTTP metadata retained',
 catalog_ids_promoted=[],models=0,raw_parent_inflates=0,canonical_alias_mutations=0)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
