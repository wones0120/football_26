"""One admitted serial source pass; immutable minimal cache precedes derivation."""
from pathlib import Path
from datetime import datetime, UTC
from collections import Counter
import csv, gc, gzip, hashlib, json, math, signal, time, os
import pyarrow.parquet as pq
from backend.app.product_services.game_state_reconstruction import (
    PROJECTION_FIELDS, reconstruct_game_transitions, build_original_drive_blocks, opening_state_evidence)

ROOT=Path.cwd(); OUT=ROOT/'research/game_state_reconstruction_20261020/v1'

def now(): return datetime.now(UTC).isoformat()
def sha(b): return hashlib.sha256(b).hexdigest()
def clean(v):
    if isinstance(v,float) and not math.isfinite(v): return {'source_nonfinite':str(v)}
    if isinstance(v,dict): return {k:clean(x) for k,x in v.items()}
    if isinstance(v,list): return [clean(x) for x in v]
    return v

def save(v,kind,compressed=False,cap=256*1024*1024):
    raw=json.dumps(v,separators=(',',':'),allow_nan=False).encode()
    if len(raw)>cap: raise ValueError('Uncompressed output cap exceeded: '+kind)
    content=gzip.compress(raw,compresslevel=1,mtime=0) if compressed else raw
    if len(content)>64*1024*1024: raise ValueError('Immutable output byte cap exceeded: '+kind)
    digest=sha(content);folder=ROOT/'artifacts'/kind;folder.mkdir(exist_ok=True)
    path=folder/(digest+('.json.gz' if compressed else '.json'))
    if path.exists():
        if path.read_bytes()!=content: raise ValueError('Immutable artifact collision')
    else: path.write_bytes(content)
    return dict(path=str(path),sha256=digest,bytes=len(content),uncompressed_bytes=len(raw),encoding='gzip_json_v1' if compressed else 'json_v1')

def timing(stage,evidence):
    v=dict(package='game_state_reconstruction_v1',agent='B',stage=stage,timestamp=now(),evidence=evidence)
    fd=os.open(OUT.parent.parent/'feature_platform_implementation_20261019/v1/PACKAGE_TIMINGS.jsonl',os.O_WRONLY|os.O_APPEND)
    os.write(fd,(json.dumps(v)+'\n').encode());os.close(fd)

def main():
    started=now();clockstart=time.monotonic();receipt=dict(version='game_state_reconstruction_actual_v1',started_at=started,status='RUNNING',source_inputs=[],outputs=[],source_requests=0,DB_mutations=0,alias_queries=0,fits=0,pilot_runs=0)
    if (OUT/'ACTUAL_RECEIPT.json').exists(): raise ValueError('Actual receipt exists; no automatic retry or overwrite')
    timing('source_START',str(OUT/'ACTUAL_RECEIPT.json'))
    def deadline(*_): raise TimeoutError('Absolute60second source/derivation cap')
    old=signal.signal(signal.SIGALRM,deadline);signal.setitimer(signal.ITIMER_REAL,60)
    try:
        metadata=json.loads((ROOT/'research/remaining_feature_closure_audit_20261020/v1/historical_pace_schema.json').read_text())
        descriptors=[]
        for r in metadata['outputs']:
            if r['season'] not in (2023,2024): continue
            d=r['source_descriptor'];m=d['manifest']
            descriptors.append(dict(season=r['season'],path=str((ROOT/d['path']).resolve()),bytes=m['bytes'],sha256=m['sha256'],captured_at=m['received_at'],rows=r['source_rows'],source_descriptor=d,kind='parquet'))
        p=json.loads((OUT.parent.parent/'verification_2026_20261020/v1/ACTUAL_RECEIPT.json').read_text())['source_refs']['PBP']
        descriptors.append(dict(season=2026,path=p['artifact_path'],bytes=p['byte_count'],sha256=p['content_sha256'],captured_at=p['captured_at'],rows=p['row_count'],source_descriptor=p,kind='csv'))
        for d in descriptors:
            path=Path(d['path']);read_at=now()
            if path.stat().st_size!=d['bytes']: raise ValueError('Previously verified immutable source byte count changed')
            if d['kind']=='parquet':
                file=pq.ParquetFile(path);available=file.schema_arrow.names
                fields=[f for f in PROJECTION_FIELDS if f in available]
                if file.metadata.num_rows!=d['rows']: raise ValueError('Source footer cardinality changed')
                rows=clean(file.read(columns=fields).to_pylist())
            else:
                with path.open(newline='') as f:
                    reader=csv.DictReader(f);available=reader.fieldnames
                    fields=[k for k in PROJECTION_FIELDS if k in available]
                    rows=[{k:r[k] for k in fields} for r in reader]
            if len(rows)!=d['rows'] or len(rows)>200000: raise ValueError('Whole source cardinality differs/cap')
            lineage=dict(sha256=d['sha256'],captured_at=d['captured_at'],actual_read_at=read_at,
                         all_source_rows_retained=True,projected_rows=len(rows),original_source=d,
                         original_source_hash='REUSED_PREVIOUSLY_HIGH_VERIFIED_IMMUTABLE_HASH_SIZE_AND_PATH_BOUND; no duplicate full-byte hash sweep',
                         field_presence={k:k in available for k in PROJECTION_FIELDS},
                         missing_fields=[k for k in PROJECTION_FIELDS if k not in available],
                         original_availability='RECONSTRUCTED_LATEST_NOT_ORIGINAL_PREGAME',projected_at=now())
            projection=dict(version='game_state_minimal_projection_v1',columns=fields,
                            rows=[[r.get(k) for k in fields] for r in rows],source_lineage=lineage)
            projection_ref=save(projection,'game_state_minimal_projection',True)
            receipt['source_inputs'].append(dict(season=d['season'],projection_ref=projection_ref,source_lineage=lineage))
            (OUT/'ACTUAL_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
            del projection;gc.collect()
            reconstruction=reconstruct_game_transitions(rows,source_lineage=lineage)
            del rows;gc.collect()
            block_data=build_original_drive_blocks(reconstruction)
            openings=opening_state_evidence(reconstruction)
            blocks_ref=save(block_data,'game_state_trajectory_blocks',True)
            openings_ref=save(dict(version='source_opening_evidence_v1',rows=openings,projection_ref=projection_ref),'game_state_openings')
            # All before/action/next-state/credit records occur once in block.steps;
            # exact original fields/ordinals are independently retained columnwise.
            row_proof=[dict(game_id=g['game_id'],sides=g['sides'],native_order_verified=g['native_order_verified'],
                            quarantine_threat_ordinals=g['quarantine_threat_ordinals'],global_quarantine_threat=g['global_quarantine_threat'],
                            rows=[{k:s[k] for k in ('source_ordinal','play_id','source_order','original_drive','fixed_drive','next_play_id','barriers')} for s in g['rows']]) for g in reconstruction['games']]
            reconstruction_ref=save(dict(version='game_state_reconstruction_index_v1',games=row_proof,quarantine=reconstruction['quarantine'],
                                         input_rows=reconstruction['input_rows'],global_possible_REG_rows=reconstruction['global_possible_REG_rows'],
                                         explicit_out_of_scope_rows=reconstruction['explicit_out_of_scope_rows'],projection_ref=projection_ref,
                                         blocks_ref=blocks_ref,ledger='blocks[].steps retains each valid native before/action/next-state label exactly once; raw source fields in columnar projection'),
                                    'game_state_reconstruction_index',True)
            counts=Counter(reason for b in block_data['blocks'] for reason in b['barriers'])
            receipt['outputs'].append(dict(season=d['season'],projection_ref=projection_ref,reconstruction_ref=reconstruction_ref,blocks_ref=blocks_ref,openings_ref=openings_ref,
                                           input_rows=reconstruction['input_rows'],games=len(reconstruction['games']),quarantine_rows=len(reconstruction['quarantine']),
                                           quarantine_classes=dict(Counter(q['threat'] for q in reconstruction['quarantine'])),
                                           coverage=block_data['coverage'],certified_opening_halves=sum(o['certified'] for o in openings),
                                           certified_opening_pairs=sum(all(o['certified'] for o in openings if o['game_id']==g['game_id']) for g in reconstruction['games']),
                                           block_barriers=dict(counts),opening_barriers=dict(Counter(reason for o in openings for reason in o['barriers'])),
                                           week_games=dict(Counter(g['game_id'].split('_')[1] for g in reconstruction['games'])),
                                           regulation_final_status='2026W1-5 independently finalized79games;W6UNKNOWN. Regulation-only truth not inferred from final score.' if d['season']==2026 else 'Regulation labels not certified by weekly/final totals'))
            (OUT/'ACTUAL_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
            del reconstruction,block_data,openings,row_proof;gc.collect()
        receipt['status']='COMPLETED_SOURCE_RECONSTRUCTION_NO_PILOT'
    except Exception as exc:
        receipt.update(status='FAILED_NO_AUTOMATIC_RETRY',error_type=type(exc).__name__,error=str(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
        receipt.update(completed_at=now(),elapsed_seconds=time.monotonic()-clockstart)
        (OUT/'ACTUAL_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n');timing('source_END',str(OUT/'ACTUAL_RECEIPT.json'))
        print(json.dumps(dict(status=receipt['status'],elapsed_seconds=receipt['elapsed_seconds'],frozen_projections=len(receipt['source_inputs']),outputs=[dict(season=x['season'],coverage=x['coverage'],opening_pairs=x['certified_opening_pairs']) for x in receipt['outputs']],error=receipt.get('error'))))
    return 0 if receipt['status'].startswith('COMPLETED') else 1

if __name__=='__main__': raise SystemExit(main())
