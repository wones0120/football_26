"""One shared minimal position projection; no full source-adapter replay."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time,os,gc
import polars as pl
from backend.app.product_services.participation_position_components import project_participation_positions,COLUMNS
from backend.app.product_services.participation_source_components import VERSION as ORIGINAL_VERSION,URL
from backend.app.product_services.factual_designation import clock
root=Path('research/participation_position_components_20261020/v1');started=datetime.now(UTC);timer=time.monotonic()
def timing(stage):
 e=dict(package='participation_position_components_v1',agent='B',stage=stage,timestamp=datetime.now(UTC).isoformat(),evidence=str(root/'actual_receipt.json'));fd=os.open('research/feature_platform_implementation_20261019/v1/PACKAGE_TIMINGS.jsonl',os.O_WRONLY|os.O_APPEND)
 try:os.write(fd,(json.dumps(e)+'\n').encode())
 finally:os.close(fd)
timing('source_start')
parent=Path('research/participation_source_components_20261020/v1');approved=json.loads((parent/'receipt.json').read_text());assert approved['review_status']=='High_FINAL_PASS_sourceadapter_only'
for pin in approved['pins']:
 b=Path(pin['path']).read_bytes();assert len(b)==pin['bytes']and hashlib.sha256(b).hexdigest()==pin['sha256']
original=json.loads((parent/'actual_receipt.json').read_text());outputs=[]
code={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in [Path('backend/app/product_services')/(n+'.py')for n in('participation_position_components','participation_source_components')]}
for item in original['outputs']:
 year=item['season']
 if year not in(2023,2024,2025):continue
 source=item['source'];path=Path(source['artifact_path']);metadata=source['metadata']
 assert source['source_uri']==URL.format(season=year)and metadata['contract_id']==ORIGINAL_VERSION and metadata['provider_generation']=='FTN'and metadata['original_remote_parquet_bytes']is True and metadata['original_sha256']==source['sha256']and clock(source['captured_at'])<=started
 b=path.read_bytes();assert len(b)==source['bytes']<=64*1024*1024 and hashlib.sha256(b).hexdigest()==source['sha256'];del b
 schema=pl.read_parquet_schema(path);assert {'nflverse_game_id','play_id','offense_players','offense_positions','defense_players','defense_positions'}<=set(schema)
 read=datetime.now(UTC);frame=pl.read_parquet(path,columns=[k for k in COLUMNS if k in schema]);value=project_participation_positions(frame.iter_rows(named=True),season=year);assert value['row_count']==frame.height
 value['provenance']=dict(source_ref=source,original_review_receipt_sha256=hashlib.sha256((parent/'receipt.json').read_bytes()).hexdigest(),source_projection_columns=[k for k in COLUMNS if k in schema],source_field_presence={k:k in schema for k in COLUMNS},actual_read_at=read.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_hashes=code,source_generation='FTN2023onward',source_license='CC-BY-SA4.0; FTN Data via nflverse',original_availability='Published after postseason; actual2026capture; original historical pregame availability unknown',semantic_scope='All source rows, including postseason/control/unknown phase; physical eligibility requires independent native PBP evidence')
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=96*1024*1024,'96MiBcomponent bound; compact repeated metadata before publication'
 sha=hashlib.sha256(raw).hexdigest();out=Path('artifacts/participation_position_components')/(sha+'.json');out.parent.mkdir(exist_ok=True)
 if out.exists():assert out.read_bytes()==raw
 else:
  with out.open('xb')as f:f.write(raw)
  out.chmod(0o444)
 result=dict(season=year,full_ref=dict(path=str(out.resolve()),sha256=sha,bytes=len(raw)),source_ref=source,native_rows=value['row_count'],coverage=value['coverage'],semantic_sha256=value['semantic_sha256']);outputs.append(result);print(json.dumps({k:v for k,v in result.items()if k!='source_ref'}),flush=True)
 del frame,value,raw;gc.collect()
actual=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,outputs=outputs,source_adapter_replays=0,minimal_projection_only=True,new_source_queries=0,new_captures=0,canonical_attachments=0,identity_writes=0,models=0)
(root/'actual_receipt.json').write_text(json.dumps(actual,indent=2)+'\n');timing('source_end');print(json.dumps(actual,indent=2))
