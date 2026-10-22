"""One typed-admin transformation of frozen minimal projections, no raw source I/O."""
from pathlib import Path
from datetime import datetime,UTC
from collections import Counter
import gzip,json,hashlib,signal,time,gc
from backend.app.product_services.game_state_reconstruction import reconstruct_game_transitions,build_original_drive_blocks,opening_state_evidence
from research.game_state_reconstruction_20261020.v1.run_actual import save,timing

OUT=Path('research/game_state_reconstruction_20261020/v1')
def now():return datetime.now(UTC).isoformat()
def ref(path):
 path=Path(path);b=path.read_bytes();return dict(path=str(path.resolve()),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def main():
 target=OUT/'CACHED_RECOMPOSE_RECEIPT.json'
 if target.exists():raise ValueError('Cached receipt exists; no automaticretry/overwrite')
 started=time.monotonic();r=dict(version='typed_admin_cached_recompose_v1',started_at=now(),status='RUNNING',original_measurement_receipt=ref(OUT/'ACTUAL_RECEIPT.json'),
     module_ref=ref('backend/app/product_services/game_state_reconstruction.py'),runner_ref=ref(__file__),source_reads=0,source_requests=0,DB_mutations=0,fits=0,pilot_runs=0,outputs=[])
 timing('typed_admin_cached_START',str(target.resolve()))
 def cap(*_):raise TimeoutError('Absolute60second cachedrecompose cap')
 previous=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,60)
 try:
  old=json.loads((OUT/'ACTUAL_RECEIPT.json').read_text())
  for source in old['source_inputs']:
   projection=source['projection_ref'];raw=Path(projection['path']).read_bytes()
   if len(raw)!=projection['bytes']or hashlib.sha256(raw).hexdigest()!=projection['sha256']:raise ValueError('Frozen projection bytes differ')
   decoded=gzip.decompress(raw)
   if len(decoded)!=projection['uncompressed_bytes']or len(decoded)>64*1024*1024:raise ValueError('Projection uncompressedcap/equality')
   value=json.loads(decoded);del raw,decoded
   columns=value['columns'];lineage=value['source_lineage'];rows=[dict(zip(columns,values))for values in value['rows']]
   if len(rows)!=lineage['projected_rows']:raise ValueError('Projection cardinality differs')
   del value;gc.collect()
   reconstruction=reconstruct_game_transitions(rows,source_lineage=lineage);del rows;gc.collect()
   data=build_original_drive_blocks(reconstruction);openings=opening_state_evidence(reconstruction)
   blocks_ref=save(data,'game_state_trajectory_blocks',True)
   openings_ref=save(dict(version='source_opening_evidence_v1',rows=openings,projection_ref=projection),'game_state_openings')
   proofs=[dict(game_id=g['game_id'],sides=g['sides'],native_order_verified=g['native_order_verified'],
               quarantine_threat_ordinals=g['quarantine_threat_ordinals'],global_quarantine_threat=g['global_quarantine_threat'],
               rows=[{k:s[k]for k in ('source_ordinal','play_id','source_order','original_drive','fixed_drive','next_play_id','barriers','next_state_binding','typed_admin_marker')if k in s}for s in g['rows']])for g in reconstruction['games']]
   index_ref=save(dict(version='game_state_reconstruction_index_v1',games=proofs,quarantine=reconstruction['quarantine'],input_rows=reconstruction['input_rows'],
        global_possible_REG_rows=reconstruction['global_possible_REG_rows'],explicit_out_of_scope_rows=reconstruction['explicit_out_of_scope_rows'],
        projection_ref=projection,blocks_ref=blocks_ref,deterministic_admin_markers=data['deterministic_admin_markers'],
        ledger='Allnativebefore/action/next labels retained in blocks.steps or certified deterministiczero-marker ledger; rawminimalprojection unchanged.'),'game_state_reconstruction_index',True)
   pairs=Counter()
   for opening in openings:
    if opening['certified']:pairs[opening['game_id']]+=1
   r['outputs'].append(dict(season=source['season'],projection_ref=projection,reconstruction_ref=index_ref,blocks_ref=blocks_ref,openings_ref=openings_ref,
       input_rows=reconstruction['input_rows'],games=len(reconstruction['games']),quarantine_rows=len(reconstruction['quarantine']),coverage=data['coverage'],
       certified_opening_halves=sum(o['certified']for o in openings),certified_opening_pairs=sum(n==2 for n in pairs.values()),
       opening_barriers=dict(Counter(x for o in openings for x in o['barriers'])),block_barriers=dict(Counter(x for b in data['blocks']for x in b['barriers'])),
       deterministic_markers_by_kind=dict(Counter(m['proof']['kind']for m in data['deterministic_admin_markers'])),
       all_row_partition_verified=sum(b['source_row_count']for b in data['blocks'])+len(data['deterministic_admin_markers'])+len(reconstruction['quarantine'])==reconstruction['input_rows']))
   target.write_text(json.dumps(r,indent=2)+'\n')
   del reconstruction,data,openings,proofs;gc.collect()
  r['status']='COMPLETED_CACHED_TRANSFORM_NO_RAW_REPLAY'
 except Exception as exc:r.update(status='FAILED_NO_AUTOMATIC_RETRY',error_type=type(exc).__name__,error=str(exc))
 finally:
  signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
  r.update(completed_at=now(),elapsed_seconds=time.monotonic()-started);target.write_text(json.dumps(r,indent=2)+'\n');timing('typed_admin_cached_END',str(target.resolve()))
  print(json.dumps(dict(status=r['status'],elapsed_seconds=r['elapsed_seconds'],outputs=[{k:o[k]for k in ('season','coverage','certified_opening_pairs','deterministic_markers_by_kind','all_row_partition_verified')}for o in r['outputs']],error=r.get('error'))))
 return 0 if r['status'].startswith('COMPLETED') else 1
if __name__=='__main__':raise SystemExit(main())
