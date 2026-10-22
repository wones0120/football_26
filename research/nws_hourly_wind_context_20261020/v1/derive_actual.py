from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from backend.app.product_services.nws_hourly_wind_context import build_nws_hourly_wind,load_reviewed_nws_hourly_parent
ROOT=Path('research/nws_hourly_wind_context_20261020/v1');started=datetime.now(UTC);tick=time.monotonic()
def sha(b):return hashlib.sha256(b).hexdigest()
ref=json.loads(Path('research/nws_hourly_precipitation_context_20261020/v1/actual_receipt.json').read_text())['full_ref'];parent=load_reviewed_nws_hourly_parent(ref,cutoff=started)
result=build_nws_hourly_wind(parent)
result['provenance']=dict(approved_hourly_native_parent_ref=ref,parent_semantic_sha256=parent['semantic_sha256'],parent_producer_code_sha256=parent['provenance']['producer_code_sha256'],original_nws_payload_ref=parent['provenance']['original_nws_payload_ref'],original_nws_manifest_ref=parent['provenance']['original_nws_manifest_ref'],original_nws_source_index=parent['provenance']['original_nws_source_index'],original_venue_schedule_binding=parent['provenance'],product_definition=dict(provider_grid_faq='https://weather-gov.github.io/api/gridpoints',official_hourly_migration='https://www.weather.gov/media/notification/pdf_2023_24/scn24-50_removal_of_digital_projects_from_forecast.pdf',official_dwml_hourly_design='https://graphical.weather.gov/xml/mdl/XML/Design/MDL_XML_Design.htm',chain_interpretation='Source-native prevailing/sustained hourly forecast; not inferred from10mph value',height_and_averaging='UNKNOWN for retained JSON'),producer_code_sha256=sha(Path('backend/app/product_services/nws_hourly_wind_context.py').read_bytes()),actual_parent_read_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),source_adapter_replays=0,database_reads=0,database_writes=0,new_captures=0,models=0)
b=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode();p=Path('artifacts/nws_hourly_wind_context')/(sha(b)+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==b
else:
 with p.open('xb')as f:f.write(b)
 p.chmod(0o444)
full=dict(path=str(p.resolve()),sha256=sha(b),bytes=len(b))
out=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-tick,full_ref=full,parent_ref=ref,semantic_sha256=result['semantic_sha256'],native_game_id=result['game_id'],source_observations=1,team_contexts=2,native_wind=result['wind'],height_unknown=result['forecast_height_meters']is None,averaging_unknown=result['averaging_duration']is None,gust_field_present=result['gust_field_present'],source_adapter_replays=0,database_reads=0,database_writes=0,new_captures=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
