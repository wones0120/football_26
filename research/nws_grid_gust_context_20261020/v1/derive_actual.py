"""Authenticated original NWS point/grid plus approved venue/schedule -> new gust transform."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time,csv
from backend.app.product_services.scheduled_venue_displacement import venue_for_game,kickoff_utc
from backend.app.product_services.nws_grid_gust_context import build_nws_grid_gust
from backend.app.product_services.nws_hourly_precipitation_context import _time
ROOT=Path('research/nws_grid_gust_context_20261020/v1');started=datetime.now(UTC);timer=time.monotonic()
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p.resolve()),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def read(r):
 b=Path(r['path']).read_bytes();assert len(b)==r['bytes']and hashlib.sha256(b).hexdigest()==r['sha256'];return b
r=json.loads((ROOT/'source_receipt.json').read_text());assert _time(r['actual_completed_at'])<=started
sources={s['kind']:s for s in r['sources']};assert set(sources)=={'point','grid'};payloads={};manifests={}
for kind,s in sources.items():
 b=read(s);payloads[kind]=json.loads(b);m=json.loads(Path(s['manifest_path']).read_text());assert m['snapshot_id']==s['snapshot_id']and m['source_uri']==s['source_uri']and m['content_sha256']==s['sha256']and m['byte_count']==s['bytes']
 assert m['metadata']['contract']=='nws_grid_gust_source_v1'and m['metadata']['kind']==kind and m['metadata']['native_game_id']==r['native_game']['game_id']and m['pre_lock']is True
 assert _time(m['captured_at'])==_time(s['captured_at'])and _time(m['observed_at'])==_time(s['observed_at'])and _time(m['slate_lock_at'])==_time(s['slate_lock_at'])and _time(m['effective_at'])==_time(s['snapshot_effective_at'])
 manifests[kind]=ref(s['manifest_path'])
parent=json.loads(read(r['approved_schedule_parent_ref']));assert parent['provenance']['registry_ref']==r['registry_ref']and parent['provenance']['schedule_csv_ref']==r['schedule_ref']
registry=json.loads(read(r['registry_ref']));schedule=list(csv.DictReader(read(r['schedule_ref']).decode().splitlines()));matches=[row for row in schedule if row['game_id']==r['native_game']['game_id']];assert len(matches)==1
native=dict(matches[0],season=int(matches[0]['season']),week=int(matches[0]['week']));native['kickoff_at']=kickoff_utc(native['gameday'],native['gametime']).isoformat();assert native==r['native_game']
venue,mapping=venue_for_game(native,registry);assert venue==r['native_venue']and mapping==r['mapping_method']
x=build_nws_grid_gust(payloads['grid'],sources['grid'],payloads['point'],sources['point'],r['native_game'],r['native_venue'],actual_cutoff=started)
x['provenance']=dict(original_sources=sources,original_manifest_refs=manifests,approved_schedule_parent_ref=r['approved_schedule_parent_ref'],registry_ref=r['registry_ref'],schedule_ref=r['schedule_ref'],native_game=r['native_game'],native_venue=r['native_venue'],mapping_method=r['mapping_method'],source_grid_geometry=payloads['grid']['geometry'],source_product_validTimes=payloads['grid']['properties']['validTimes'],source_point_grid_link=payloads['point']['properties']['forecastGridData'],primary_maximum_gust_definition_uri='https://github.com/weather-gov/api/blob/master/gridpoints.md',actual_source_read_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_ref=ref('backend/app/product_services/nws_grid_gust_context.py'),geometry_time_helper_ref=ref('backend/app/product_services/nws_hourly_precipitation_context.py'),database_reads=0,database_writes=0,models=0)
x['team_contexts']=[dict(team=r['native_game'][side],game_id=r['native_game']['game_id'],maximum_gust_m_s=x['maximum_gust_m_s'])for side in('home_team','away_team')]
b=json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(b).hexdigest();path=Path('artifacts/nws_grid_gust_context')/(sha+'.json');path.parent.mkdir(exist_ok=True)
if path.exists():assert path.read_bytes()==b
else:
 with path.open('xb')as f:f.write(b)
 path.chmod(0o444)
out=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,full_ref=ref(path),semantic_sha256=x['semantic_sha256'],game_id=x['game_id'],maximum_gust_native=x['maximum_gust_native'],native_unit=x['native_unit'],maximum_gust_m_s=x['maximum_gust_m_s'],native_interval=x['native_gust_interval'],unknown_reasons=x['unknown_reasons'],source_observations=1,team_contexts=2,new_captures=0,database_reads=0,database_writes=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
