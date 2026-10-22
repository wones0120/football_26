"""One coherent phase-protocol transformation of frozen minimal projections, no raw source I/O."""
from pathlib import Path
from datetime import datetime,UTC
from collections import Counter
import gzip,json,hashlib,signal,time,gc
from backend.app.product_services.game_state_reconstruction import reconstruct_game_transitions,build_original_drive_blocks,opening_state_evidence,regulation_truth_evidence
from research.game_state_reconstruction_20261020.v1.run_actual import save,timing

OUT=Path('research/game_state_reconstruction_20261020/v1')
def now():return datetime.now(UTC).isoformat()
def ref(path):
 path=Path(path);b=path.read_bytes();return dict(path=str(path.resolve()),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def main():
 target=OUT/'COHERENT_CACHED_RECEIPT_v2b.json'
 if target.exists():raise ValueError('Cached receipt exists; no automaticretry/overwrite')
 started=time.monotonic();r=dict(version='coherent_event_cached_recompose_v2',started_at=now(),status='RUNNING',original_measurement_receipt=ref(OUT/'ACTUAL_RECEIPT.json'),
     prior_cached_receipt=ref(OUT/'CACHED_RECOMPOSE_RECEIPT.json'), amendment_ref=ref(OUT/'COHERENT_EVENT_PROTOCOL_AMENDMENT_v2.json'),
     module_ref=ref('backend/app/product_services/game_state_reconstruction.py'),runner_ref=ref(__file__),source_reads=0,source_requests=0,DB_mutations=0,fits=0,pilot_runs=0,outputs=[])
 timing('coherent_cached_v2_START',str(target.resolve()))
 def cap(*_):raise TimeoutError('Absolute60second cachedrecompose cap')
 previous=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,60)
 try:
  old=json.loads((OUT/'ACTUAL_RECEIPT.json').read_text())
  coverage=json.loads((OUT/'CACHED_COVERAGE.json').read_text())
  completed={row['game_id']for row in coverage['scheduled_2026_side_statuses']if row['completed_full_game_proof']}
  if len(completed)!=79 or len(coverage['scheduled_2026_side_statuses'])!=214:raise ValueError('Reviewed completion/status scope differs')
  r['completion_scope_ref']=ref(OUT/'CACHED_COVERAGE.json')
  r['preserved_zero_decode_failure']=ref(OUT/'coherent_metadata_failure/COHERENT_CACHED_RECEIPT_v2.json')
  r['preserved_failed_runner']=ref(OUT/'coherent_metadata_failure/recompose_coherent_v2.py')
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
   truth=regulation_truth_evidence(reconstruction,data,completed_game_ids=completed)
   truth_ref=save(truth,'game_state_regulation_truth',True)
   blocks_ref=save(data,'game_state_trajectory_blocks',True,cap=384*1024*1024)
   openings_ref=save(dict(version='source_opening_evidence_v1',rows=openings,projection_ref=projection),'game_state_openings')
   proofs=[dict(game_id=g['game_id'],sides=g['sides'],native_order_verified=g['native_order_verified'],
               quarantine_threat_ordinals=g['quarantine_threat_ordinals'],global_quarantine_threat=g['global_quarantine_threat'],
               rows=[{k:s[k]for k in ('source_ordinal','play_id','source_order','original_drive','fixed_drive','next_play_id','barriers','next_state_binding','typed_admin_marker','regulation_scope')if k in s}for s in g['rows']])for g in reconstruction['games']]
   index_ref=save(dict(version='game_state_reconstruction_index_v1',games=proofs,quarantine=reconstruction['quarantine'],input_rows=reconstruction['input_rows'],
        global_possible_REG_rows=reconstruction['global_possible_REG_rows'],explicit_out_of_scope_rows=reconstruction['explicit_out_of_scope_rows'],
        projection_ref=projection,blocks_ref=blocks_ref,deterministic_admin_markers=data['deterministic_admin_markers'],explicit_overtime_rows=data['explicit_overtime_rows'],regulation_truth_ref=truth_ref,
        ledger='Allnativebefore/action/next labels retained in blocks.steps or certified deterministiczero-marker ledger; rawminimalprojection unchanged.'),'game_state_reconstruction_index',True)
   pairs=Counter()
   for opening in openings:
    if opening['certified']:pairs[opening['game_id']]+=1
   r['outputs'].append(dict(season=source['season'],projection_ref=projection,reconstruction_ref=index_ref,blocks_ref=blocks_ref,openings_ref=openings_ref,regulation_truth_ref=truth_ref,
       input_rows=reconstruction['input_rows'],games=len(reconstruction['games']),quarantine_rows=len(reconstruction['quarantine']),coverage=data['coverage'],
       certified_opening_halves=sum(o['certified']for o in openings),certified_opening_pairs=sum(n==2 for n in pairs.values()),
       opening_barriers=dict(Counter(x for o in openings for x in o['barriers'])),block_barriers=dict(Counter(x for b in data['blocks']for x in b['barriers'])),
       state_transition_certified_groups=sum(b['state_transition_certified']for b in data['blocks']),
       regulation_score_certified_games=sum(g['regulation_score_certified']for g in truth['games']),
       independently_completed_with_regulation_score=sum(g['metrics_admitted']for g in truth['games']),
       kickoff_groups=len([b for b in data['blocks']if b['start_state']['phase']=='kickoff']),
       certified_kickoff_groups=sum(b['certified']for b in data['blocks']if b['start_state']['phase']=='kickoff'),
       state_certified_kickoff_groups=sum(b['state_transition_certified']for b in data['blocks']if b['start_state']['phase']=='kickoff'),
       kickoff_possession_proofs=sum(b['possession_start']['basis']=='qualified_kickoff_prefix_to_first_physical'for b in data['blocks']),
       marker_nonzero_runoff_rows=sum(not m['proof']['zero_event_seconds']for m in data['deterministic_admin_markers']),
       deterministic_markers_by_kind=dict(Counter(m['proof']['kind']for m in data['deterministic_admin_markers'])),
       all_row_partition_verified=sum(b['source_row_count']for b in data['blocks'])+len(data['deterministic_admin_markers'])+len(data['explicit_overtime_rows'])+len(reconstruction['quarantine'])==reconstruction['input_rows']))
   target.write_text(json.dumps(r,indent=2)+'\n')
   if not r['outputs'][-1]['all_row_partition_verified']:raise ValueError('All-row partition differs')
   del reconstruction,data,openings,proofs,truth;gc.collect()
  r['status']='COMPLETED_CACHED_TRANSFORM_NO_RAW_REPLAY'
 except Exception as exc:r.update(status='FAILED_NO_AUTOMATIC_RETRY',error_type=type(exc).__name__,error=str(exc))
 finally:
  signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
  r.update(completed_at=now(),elapsed_seconds=time.monotonic()-started);target.write_text(json.dumps(r,indent=2)+'\n');timing('coherent_cached_v2_END',str(target.resolve()))
  print(json.dumps(dict(status=r['status'],elapsed_seconds=r['elapsed_seconds'],outputs=[{k:o[k]for k in ('season','coverage','certified_opening_pairs','deterministic_markers_by_kind','all_row_partition_verified')}for o in r['outputs']],error=r.get('error'))))
 return 0 if r['status'].startswith('COMPLETED') else 1
if __name__=='__main__':raise SystemExit(main())
