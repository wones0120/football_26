"""One serial nine-column historical diagnostic, no grid/model/full-row decode."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,time,os,gc,math
import pyarrow.parquet as pq
from backend.app.product_services.historical_native_pace_diagnostic import build_historical_pace_diagnostic,COLUMNS,VERSION
from backend.app.product_services.personnel_package_continuity import load_package_physical_component
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.factual_designation import clock

OUT=Path('research/historical_native_pace_diagnostic_20261020/v1')


def now():return datetime.now(timezone.utc)
def sha(b):return hashlib.sha256(b).hexdigest()
def timing(stage,evidence):
    row=dict(package='historical_native_pace_diagnostic_20261020/v1',agent='B',stage=stage,timestamp=now().isoformat(),evidence=evidence)
    fd=os.open('research/feature_platform_implementation_20261019/v1/PACKAGE_TIMINGS.jsonl',os.O_WRONLY|os.O_APPEND)
    try:os.write(fd,(json.dumps(row)+'\n').encode())
    finally:os.close(fd)


def save(v,kind):
    raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=32*1024*1024
    path=Path('artifacts',kind)/(sha(raw)+'.json');path.parent.mkdir(exist_ok=True)
    if path.exists():assert path.read_bytes()==raw
    else:
        with path.open('xb') as f:f.write(raw)
        path.chmod(0o444)
    return dict(path=str(path.resolve()),sha256=sha(raw),bytes=len(raw))


def main():
    start=now();tick=time.monotonic();timing('source_start','One serial original3Parquet nine-column chronology projection; approved physical flags reused')
    parents=json.loads(Path('research/personnel_package_continuity_20261020/v1/actual_receipt.json').read_text())
    schema=json.loads(Path('research/remaining_feature_closure_audit_20261020/v1/historical_pace_schema.json').read_text())
    sreceipt=json.loads(Path('research/schedule_context_features_20261020/v1/actual_receipt.json').read_text());sref=sreceipt['artifact_ref'];raw=Path(sref['path']).read_bytes()
    assert len(raw)==sref['bytes'] and sha(raw)==sref['sha256'];schedule_block=json.loads(raw);schedule=schedule_block['game_rows']
    assert schedule_block['producer_code_sha256']==sha(Path('backend/app/product_services/schedule_context_features.py').read_bytes())
    assert schedule_block['semantic_sha256']==sreceipt['semantic_sha256'] and clock(schedule_block['actual_derived_at'])<=clock(sreceipt['actual_completed_at'])<=start
    outputs=[]
    for source,pinput in zip(schema['outputs'],parents['source_inputs']):
        year=source['season'];assert year==pinput['season']
        descriptor=source['source_descriptor'];manifest=descriptor['manifest'];path=Path(descriptor['path']);assert path.stat().st_size==manifest['bytes']<=64*1024*1024
        assert manifest['url']==f'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{year}.parquet' and clock(manifest['received_at'])<=start
        h=hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
        assert h.hexdigest()==manifest['sha256']
        physical=load_package_physical_component(pinput['physical_component_ref'],cutoff=start)
        assert physical['source_sha256']==manifest['sha256']
        parquet=pq.ParquetFile(path);assert parquet.metadata.num_rows<=100000 and set(COLUMNS)<=set(parquet.schema_arrow.names)
        projection=[{k:None if isinstance(v,float) and not math.isfinite(v) else v for k,v in row.items()} for row in parquet.read(columns=list(COLUMNS)).to_pylist()]
        projection_core=dict(version='historical_native_clock_minimal_projection_v1',season=year,rows=projection,columns=list(COLUMNS),source_descriptor=descriptor,source_total_rows=parquet.metadata.num_rows,actual_projected_at=now().isoformat())
        pref=save(projection_core,'historical_native_clock_minimal_projection')
        result=build_historical_pace_diagnostic(projection,physical,schedule,season=year)
        result['provenance']=dict(original_source_descriptor=descriptor,projection_ref=pref,physical_ref=pinput['physical_component_ref'],schedule_ref=sref,actual_read_at=start.isoformat(),actual_publication_at=now().isoformat(),producer_code_hashes={str(p):sha(p.read_bytes()) for p in [Path('backend/app/product_services')/(n+'.py') for n in ('historical_native_pace_diagnostic','personnel_package_continuity','pfr_pressure_cohort','fumble_event_components','game_clock_pace_catalog','joint_pace_play_budgets')]},original_availability='Revised historical capture/FTN postseason caches; original contemporaneous availability unknown')
        ref=save(result,'historical_native_pace_diagnostic');profile=result['joint_diagnostic']['home_away_pooled_observed_profile']
        outputs.append(dict(season=year,full_ref=ref,projection_ref=pref,source_keys=result['source_keys'],exact_team_game_pace_rows=result['exact_team_game_pace_rows'],native_unknown_order_games=[p['game_id'] for p in result['native_order_proof']['game_proofs'] if p['missing_order_sequences'] or p['duplicate_order_sequences']],interval_rejections=result['interval_rejections'],reference_cutpoints=result['joint_diagnostic']['reference_cutpoints'],evaluation_games=len(result['joint_diagnostic']['evaluation_game_ids']),cell_coverage={h:{a:dict(known_sample_games=c['known_complete_sample']['games'],exact_games=c['exact_full_cell']['games'],unknown_membership=len(c['unknown_membership_game_ids']),unknown_response=len(c['unknown_response_game_ids'])) for a,c in groups.items()} for h,groups in profile['cells'].items()},exact_conditional_contrasts=profile['fast_minus_slow_by_fixed_opposing_axis'],exact_both_axes_difference=profile['both_axes_difference_of_differences']))
        print(json.dumps(outputs[-1]),flush=True);del physical,projection,projection_core,result;gc.collect()
    receipt=dict(version=VERSION,status='coverage_diagnostic_zero_promotions',source_start=start.isoformat(),source_end=now().isoformat(),elapsed_seconds=time.monotonic()-tick,outputs=outputs,parquet_projection_passes=3,columns_per_pass=list(COLUMNS),full_width_row_decodes=0,source_captures=0,DB_reads=0,alias_queries=0,parent_inflations=0,models=0,threshold_searches=0,IDs_promoted=0)
    with (OUT/'actual_receipt.json').open('x') as f:json.dump(receipt,f,sort_keys=True,indent=2);f.write('\n')
    timing('source_end','Diagnostic complete, zero promotions');print(json.dumps(dict(stage='END',elapsed_seconds=receipt['elapsed_seconds'])))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        timing('source_failed',type(exc).__name__+': '+str(exc));raise
