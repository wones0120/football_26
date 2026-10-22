"""Authorized sequential public FTN captures; immutable existing source service."""
from datetime import datetime,UTC
from pathlib import Path
import csv,json,hashlib,subprocess,sys,time
from collections import Counter
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import SourceCaptureService,verify_snapshot_artifact
from backend.app.product_services.charting_source_components import capture_charting_source,load_charting_snapshot,BOOL_FIELDS,PROVIDER_URL,_integer

ROOT=Path('research/charting_source_components_20261020/v1')


def pbp_keys(season,session):
 if season==2026:
  snap=session.get(SourceSnapshot,'79230705-26c3-5cbd-af43-b26c9bb4e1bb');assert snap is not None;verify_snapshot_artifact(snap)
  path=Path(snap.artifact_path);source=dict(path=str(path),sha256=snap.content_sha256,source_snapshot_id=str(snap.snapshot_id))
  with path.open(newline='') as stream:rows=list(csv.DictReader(stream))
 else:
  import pyarrow.parquet as pq
  item=next(x for x in json.loads(Path('research/player_opportunity_history_20261020/v1/source_coverage.json').read_text()) if x['season']==season)
  d=item['descriptor'];path=Path(d['path']);raw=path.read_bytes();assert len(raw)==d['manifest']['bytes'] and hashlib.sha256(raw).hexdigest()==d['manifest']['sha256']
  fields=pq.ParquetFile(path).schema_arrow.names;rows=pq.read_table(path,columns=[x for x in ['game_id','play_id','season','week','season_type','play_type','no_play','two_point_attempt'] if x in fields]).to_pylist();source=dict(path=str(path),sha256=d['manifest']['sha256'],actual_received_at=d['manifest']['received_at'],original_availability='unknown_revised_history')
 keys=set();regular=set();offense=set()
 for row in rows:
  key=(str(row['game_id']),str(_integer(row['play_id'],'PBP native play')))
  if key in keys:raise ValueError('Duplicate PBP native game/play')
  keys.add(key)
  if row.get('season_type')=='REG' and int(row['season'])*100+int(row['week'])<202606:
   regular.add(key)
   if row.get('play_type') in {'pass','run','qb_spike','qb_kneel'} and str(row.get('no_play')) not in {'1','1.0','True','true'} and str(row.get('two_point_attempt')) not in {'1','1.0','True','true'}:offense.add(key)
 return keys,regular,offense,source


def child(season):
 start=time.monotonic();result=dict(season=season,actual_started_at=datetime.now(UTC).isoformat(),source_url=PROVIDER_URL.format(season=season),models=0,paid_API_calls=0)
 try:
  with Session(engine) as session:
   cap=capture_charting_source(SourceCaptureService(session),season=season,week=6,slate='offline_ftn_feature_inventory',slate_lock_at=datetime(2026,10,20,0,15,tzinfo=UTC));session.commit();snapshot=cap.snapshot
   result.update(capture_status='captured_immutable_existing_source_service',snapshot_id=str(snapshot.snapshot_id),artifact_path=snapshot.artifact_path,manifest_path=snapshot.manifest_path,source_uri=snapshot.source_uri,raw_representation='Installed provider dataframe native CSV, not original remote parquet bytes',sha256=snapshot.content_sha256,bytes=snapshot.byte_count,rows=snapshot.row_count,captured_at=snapshot.captured_at.isoformat(),observed_at=snapshot.observed_at.isoformat(),source_metadata=snapshot.metadata_json,pre_lock=cap.pre_lock)
   try:
    loaded=load_charting_snapshot(snapshot,cutoff=datetime.now(UTC));rows=loaded['rows'];keys={(r['game_id'],r['play_id']) for r in rows}
    try:rawkeys,reg,offense,pbp_source=pbp_keys(season,session)
    except StopIteration:rawkeys=set();reg=set();offense=set();pbp_source=dict(status='No retained PBP source descriptor for this season; join coverage unknown, not zero evidence')
    result.update(validation_status='verified_native_scope_types_clocks_unique_keys',field_availability=loaded['source']['field_availability'],field_missingness={k:sum(r['flags'][k] is None for r in rows) for k in BOOL_FIELDS},read_code_counts=dict(Counter(str(r['read_thrown']) for r in rows)),primary_known=sum(r['primary_read'] is not None for r in rows),date_pulled_status=dict(Counter(r['date_pulled']['status'] for r in rows)),date_pulled_aware_min=min((r['date_pulled']['aware_at'] for r in rows if r['date_pulled']['aware_at']),default=None),date_pulled_aware_max=max((r['date_pulled']['aware_at'] for r in rows if r['date_pulled']['aware_at']),default=None),inconsistent_count_fields=dict(Counter(k for r in rows for k in r['inconsistent_count_fields'])),source_quality_conflicts=sum(r['drop_catchability_conflict'] for r in rows),
     native_join=dict(pbp_source=pbp_source,pbp_raw_play_keys=len(rawkeys),FTN_raw_play_keys=len(keys),FTN_matched_raw_PBP=len(keys&rawkeys),FTN_unmatched_raw_PBP=len(keys-rawkeys),FTN_matched_prior_REG=len(keys&reg),pbp_prior_REG_keys=len(reg),pbp_prior_offensive_play_type_keys=len(offense),matched_prior_offensive_play_type_keys=len(keys&offense),unmatched_FTN_examples=[dict(game_id=g,play_id=p) for g,p in sorted(keys-rawkeys)[:10]],meaning='Exact normalized native game/play equality only; coverage gaps never become false charting flags'),original_pregame_availability='unknown_revised_retrospective; date_pulled is upstream API retrieval, not event/publication proof',remote_freshness='unknown; installed loader may use cache',feature_catalog_verified_claims=0)
   except Exception as exc:result.update(validation_status='captured_but_validation_failed',validation_error_type=type(exc).__name__,validation_error=str(exc))
 except Exception as exc:result.update(capture_status='unavailable_or_capture_failed',error_type=type(exc).__name__,error=str(exc),feature_catalog_verified_claims=0)
 result.update(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start)
 (ROOT/f'capture_{season}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


def main():
 started=datetime.now(UTC).isoformat();results=[]
 for season in (2023,2024,2025,2026):
  print('START',season,datetime.now(UTC).isoformat(),flush=True)
  with (ROOT/f'capture_{season}.log').open('w') as out:
   try:done=subprocess.run([sys.executable,__file__,'--season',str(season)],stdout=out,stderr=subprocess.STDOUT,timeout=60);code=done.returncode
   except subprocess.TimeoutExpired:code='timeout60seconds'
  path=ROOT/f'capture_{season}.json'
  result=json.loads(path.read_text()) if path.exists() else dict(season=season,capture_status='bounded_child_failed_or_timed_out',status=code)
  results.append(result);receipt=dict(actual_started_at=started,actual_updated_at=datetime.now(UTC).isoformat(),seasons=results,source_scope='Sequential installed public provider; no source fallback, original chronology unknown',feature_catalog_verified_claims=0,models=0)
  (ROOT/'actual_capture_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print('DONE',season,result.get('capture_status'),result.get('rows'),result.get('validation_status'),flush=True)

if __name__=='__main__':
 if '--season' in sys.argv:child(int(sys.argv[sys.argv.index('--season')+1]))
 else:main()
