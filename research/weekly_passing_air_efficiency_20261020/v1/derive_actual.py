"""Read/freeze only existing reviewed QB raw IDs; no source fetch or DB write."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from backend.app.db import engine
from backend.app.product_services.weekly_passing_air_efficiency import load_reviewed_weekly_input,read_retained_air_projection,build_weekly_passing_air_efficiency

def save(value,folder,bound=16*1024*1024):
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<bound
    sha=hashlib.sha256(raw).hexdigest();dest=Path('artifacts')/folder;dest.mkdir(parents=True,exist_ok=True);path=(dest/(sha+'.json')).resolve()
    if path.exists():assert path.read_bytes()==raw
    else:
        with path.open('xb') as f:f.write(raw)
        path.chmod(0o444)
    return dict(path=str(path),sha256=sha,bytes=len(raw))

def main():
    start=time.monotonic();actual=datetime.now(UTC).isoformat();directory=Path('research/weekly_passing_air_efficiency_20261020/v1')
    ref=json.loads(Path('research/weekly_effectiveness_catalog_features_20261020/v1/actual_derivation_receipt.json').read_text())['full_ref']
    weekly=load_reviewed_weekly_input(ref,cutoff=actual);extract=read_retained_air_projection(engine,weekly,cutoff=actual)
    extract['actual_frozen_at']=datetime.now(UTC).isoformat();source_ref=save(extract,'weekly_passing_air_sources')
    result=build_weekly_passing_air_efficiency(weekly,extract,cutoff=datetime.now(UTC).isoformat())
    result['provenance']=dict(weekly_input_ref=ref,air_projection_ref=source_ref,original_weekly_provenance=weekly['provenance'],actual_read_at=actual,actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_sha256=hashlib.sha256(Path('backend/app/product_services/weekly_passing_air_efficiency.py').read_bytes()).hexdigest())
    full=save(result,'weekly_passing_air_efficiency');selected={**result,'rows':[r for r in result['rows'] if r['team'] in {'SF','WAS'}]};selected.pop('semantic_sha256');selected['selected_from_full_ref']=full;sel=save(selected,'weekly_passing_air_efficiency')
    coverage=dict(expected_source_QB_rows=extract['expected_reviewed_QB_rows'],observed_raw_projection_rows=len(extract['rows']),rows=len(result['rows']),canonical_rows=sum(r['player_master_id'] is not None for r in result['rows']),known_ratios=sum(r['value'] is not None for r in result['rows']),missing_air_field=sum(not r['source_field_present'] for r in result['rows']),missing_or_conflicting_revision=sum(r['source_revision_issue'] is not None for r in result['rows']),selected_rows=len(selected['rows']))
    receipt=dict(full_ref=full,selected_ref=sel,weekly_input_ref=ref,air_projection_ref=source_ref,coverage=coverage,actual_read_at=actual,actual_publication_at=result['provenance']['actual_publication_at'],elapsed_seconds=time.monotonic()-start,source_fetches=0,database_writes=0,parent_inflations=0,models=0,review_status='pending High')
    (directory/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
