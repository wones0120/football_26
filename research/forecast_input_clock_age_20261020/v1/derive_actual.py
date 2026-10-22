from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from backend.app.product_services.forecast_input_clock_age import build_forecast_input_clock_age
ROOT=Path('research/forecast_input_clock_age_20261020/v1');start=time.monotonic();now=datetime.now(UTC)
def sha(b):return hashlib.sha256(b).hexdigest()
ref=json.loads(Path('research/nws_hourly_precipitation_context_20261020/v1/actual_receipt.json').read_text())['full_ref'];p=Path(ref['path']).resolve()
assert p.parent==Path('artifacts/nws_hourly_precipitation_context').resolve() and p.name==ref['sha256']+'.json'
b=p.read_bytes();assert len(b)==ref['bytes']<=1024*1024 and sha(b)==ref['sha256'];parent=json.loads(b)
assert parent['provenance']['producer_code_sha256']==sha(Path('backend/app/product_services/nws_hourly_precipitation_context.py').read_bytes())
manifest_ref=parent['provenance']['original_nws_manifest_ref'];p=Path(manifest_ref['path']);b=p.read_bytes();assert len(b)==manifest_ref['bytes']<=64*1024 and sha(b)==manifest_ref['sha256'];manifest=json.loads(b)
result=build_forecast_input_clock_age(parent,manifest)
result['provenance']=dict(approved_forecast_input_ref=ref,original_source_manifest_ref=manifest_ref,parent_semantic_sha256=parent['semantic_sha256'],
 producer_code_sha256=sha(Path('backend/app/product_services/forecast_input_clock_age.py').read_bytes()),
 actual_read_at=now.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),
 original_source_clocks=parent['provenance']['original_nws_source_index'],
 source_adapter_replays=0,database_reads=0,database_writes=0,new_captures=0,models=0)
b=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode();p=Path('artifacts/forecast_input_clock_age')/(sha(b)+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==b
else:
 with p.open('xb') as f:f.write(b)
 p.chmod(0o444)
full=dict(path=str(p.resolve()),sha256=sha(b),bytes=len(b))
out=dict(actual_started_at=now.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,
 full_ref=full,semantic_sha256=result['semantic_sha256'],native_game_id=result['game_id'],source_observations=1,reference_points=len(result['reference_points']),
 clock_age_cells=sum(len(r['clock_ages']) for r in result['reference_points']),known_age_cells=sum(v['age_seconds'] is not None for r in result['reference_points'] for v in r['clock_ages'].values()),
 provider_issue_age_cells_unknown=2,reference_points_data=result['reference_points'],source_adapter_replays=0,database_reads=0,database_writes=0,new_captures=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
