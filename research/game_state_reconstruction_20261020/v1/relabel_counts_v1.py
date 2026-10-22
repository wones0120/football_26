"""One label-only cached pass; no trajectories, source adapters or models."""
from pathlib import Path
from datetime import datetime,UTC
from collections import Counter
from copy import deepcopy
import json,gzip,hashlib,signal,time,gc
from backend.app.product_services.game_state_reconstruction import state_before,_event,event_count_label_proof,COUNT_LABEL_FIELDS
from research.game_state_reconstruction_20261020.v1.run_actual import save,timing
D=Path(__file__).resolve().parent
FIELDS=(*COUNT_LABEL_FIELDS.values(),'physical_plays')

def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p.resolve()),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))

def load(r,cap):
 b=Path(r['path']).read_bytes()
 if len(b)!=r['bytes'] or hashlib.sha256(b).hexdigest()!=r['sha256']:raise ValueError('Immutable cachedref differs')
 raw=gzip.decompress(b) if r.get('encoding')=='gzip_json_v1' else b
 if len(raw)!=r['uncompressed_bytes'] or len(raw)>cap:raise ValueError('Bounded inflated cachedref differs')
 return json.loads(raw)

def preflight(coverage,receipt):
 rows=coverage['scheduled_2026_side_statuses']
 assert len(rows)==214 and len({(r['game_id'],r['team']) for r in rows})==214
 assert len({r['game_id']for r in rows if r['completed_full_game_proof']})==79
 assert receipt['status']=='COMPLETED_CACHED_TRANSFORM_NO_RAW_REPLAY'
 assert [o['season']for o in receipt['outputs']]==[2023,2024,2026]
 for o in receipt['outputs']:
  for k in ('projection_ref','reconstruction_ref','regulation_truth_ref'):
   r=o[k];assert r['encoding']=='gzip_json_v1' and Path(r['path']).stat().st_size==r['bytes']
 return dict(sides=214,completed_games=79,seasons=[2023,2024,2026],validated_before_decode=True)

def noncount_core(value):
 value=deepcopy(value)
 for side in range(2):
  for key in ('production_by_side','known_production_sums_by_side','unknown_production_play_ids_by_side'):
   for field in FIELDS:value[key][side].pop(field,None)
 value.pop('count_label_replacement',None)
 return value

def main():
 target=D/'COUNT_LABEL_ACTUAL_RECEIPT.json'
 if target.exists():raise ValueError('No automaticretry or overwrite')
 r=dict(version='count_label_actual_v1',started_at=datetime.now(UTC).isoformat(),status='RUNNING',outputs=[],raw_reads=0,full_block_reads=0,block_reconstruction=0,fits=0,DB_queries=0,
        runner_ref=ref(__file__),producer_ref=ref('backend/app/product_services/game_state_reconstruction.py'),
        original_receipt_ref=ref(D/'COHERENT_CACHED_RECEIPT_v2b.json'),pure_gate_ref=ref(D/'HIGH_COUNT_LABEL_PURE_REVIEW.json'))
 start=time.monotonic()
 def deadline(*_):raise TimeoutError('Absolute30second labelonly cap')
 oldsignal=signal.signal(signal.SIGALRM,deadline);signal.setitimer(signal.ITIMER_REAL,30)
 timing('count_label_only_START',str(target))
 try:
  coverage=json.loads((D/'CACHED_COVERAGE.json').read_text());old=json.loads((D/'COHERENT_CACHED_RECEIPT_v2b.json').read_text())
  r['preflight']=preflight(coverage,old)
  for source in old['outputs']:
   projection=load(source['projection_ref'],64*1024*1024)
   index=load(source['reconstruction_ref'],40*1024*1024)
   previous=load(source['regulation_truth_ref'],2*1024*1024)
   assert len(projection['rows'])==index['input_rows']==source['input_rows']
   mapped={row['source_ordinal']:(g['game_id'],g['sides'],row)for g in index['games']for row in g['rows']}
   assert len(mapped)==sum(len(g['rows'])for g in index['games'])
   aggregates={g['game_id']:dict(sums=[dict.fromkeys(FIELDS,0)for _ in range(2)],unknown=[{f:[]for f in FIELDS}for _ in range(2)],REG_rows=0,OT_rows=0,basis=Counter())for g in previous['games']}
   columns=projection['columns']
   for ordinal,values in enumerate(projection['rows']):
    scope=mapped.get(ordinal)
    if scope is None:continue # Exact quarantine retained in index/oldtruth scope barriers.
    gid,sides,proof=scope;bucket=aggregates[gid]
    if proof['regulation_scope']=='EXPLICIT_OT':bucket['OT_rows']+=1;continue
    raw=dict(zip(columns,values));assert raw['game_id']==gid and str(int(float(raw['play_id'])))==proof['play_id']
    marker=proof.get('typed_admin_marker');bucket['REG_rows']+=1
    if proof['regulation_scope']!='REGULATION':
     counts=[dict.fromkeys(FIELDS)for _ in range(2)];basis='UNKNOWN_REGULATION_SCOPE'
    else:
     state=state_before(raw,sides)
     event={} if marker and marker.get('certified') else _event(raw,state,sides)
     countproof=event_count_label_proof(raw,state,event,typed_marker=marker)
     counts=countproof['production_by_side'];basis=countproof['basis'] if isinstance(countproof['basis'],str) else 'PER_FIELD_NATIVE_COUNT_PROOF'
    bucket['basis'][basis]+=1
    for side in range(2):
     for field in FIELDS:
      value=counts[side][field]
      if value is None:bucket['unknown'][side][field].append(proof['play_id'])
      else:
       assert value in (0,1);bucket['sums'][side][field]+=value
   result=deepcopy(previous);changed=Counter()
   for game in result['games']:
    before=deepcopy(game);bucket=aggregates[game['game_id']]
    game['count_label_replacement']=dict(version='event_local_official_count_labels_v1',previous_truth_ref=source['regulation_truth_ref'],
       old_values=[{f:before['production_by_side'][s][f]for f in FIELDS}for s in range(2)],
       old_known_sums=[{f:before['known_production_sums_by_side'][s][f]for f in FIELDS}for s in range(2)],
       old_unknown_play_ids=[{f:before['unknown_production_play_ids_by_side'][s][f]for f in FIELDS}for s in range(2)],
       native_REG_rows=bucket['REG_rows'],OT_rows_excluded=bucket['OT_rows'],proof_basis_counts=dict(bucket['basis']),
       chronology='RECONSTRUCTED_LABEL_ONLY_NOT_PREGAME_FEATURES')
    for side in range(2):
     for field in FIELDS:
      game['known_production_sums_by_side'][side][field]=bucket['sums'][side][field]
      game['unknown_production_play_ids_by_side'][side][field]=bucket['unknown'][side][field]
      value=bucket['sums'][side][field] if game['regulation_score_certified'] and not bucket['unknown'][side][field] else None
      game['production_by_side'][side][field]=value
      if before['production_by_side'][side][field]!=value:changed[field]+=1
    assert noncount_core(game)==noncount_core(before)
   result['version']='regulation_source_truth_countlabels_v2'
   result['count_label_producer_ref']=r['producer_ref'];result['previous_truth_ref']=source['regulation_truth_ref']
   out=save(result,'game_state_regulation_count_truth',True)
   r['outputs'].append(dict(season=source['season'],projection_ref=source['projection_ref'],index_ref=source['reconstruction_ref'],previous_truth_ref=source['regulation_truth_ref'],regulation_truth_ref=out,
     games=len(result['games']),changed_side_label_counts=dict(changed),noncount_game_core_parity=True,
     known_side_label_counts={f:sum(g['production_by_side'][s][f]is not None for g in result['games']for s in range(2))for f in FIELDS},
     fixed_2026=[{k:g[k]for k in ('game_id','regulation_scores','production_by_side','metrics_admitted')}for g in result['games']if g['game_id']in {'2026_01_DEN_KC','2026_02_MIN_CHI','2026_03_SEA_WAS','2026_04_LA_PHI','2026_05_MIN_NO'}]))
   target.write_text(json.dumps(r,indent=2)+'\n');del projection,index,previous,result,mapped,aggregates;gc.collect()
  r['status']='COMPLETED_LABEL_ONLY_NO_BLOCK_OR_SOURCE_REPLAY'
 except Exception as exc:r.update(status='FAILED_NO_AUTOMATIC_RETRY',error_type=type(exc).__name__,error=str(exc))
 finally:
  signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,oldsignal)
  r.update(completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start);target.write_text(json.dumps(r,indent=2)+'\n');timing('count_label_only_END',str(target))
  print(json.dumps(dict(status=r['status'],seconds=r['elapsed_seconds'],seasons=[{k:o[k]for k in ('season','known_side_label_counts','changed_side_label_counts')}for o in r['outputs']],error=r.get('error'))))
 return 0 if r['status'].startswith('COMPLETED')else 1
if __name__=='__main__':raise SystemExit(main())
