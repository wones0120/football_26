"""Authenticate the frozen diagnostic; compose catalog views and native UI evidence."""
from pathlib import Path
from datetime import datetime,UTC
from copy import deepcopy
import hashlib,json,time
from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.pfr_pressure_catalog import build_pressure_catalog,persist_pressure_identity_requests
from backend.app.product_services.factual_designation import clock
from backend.app.product_services.evaluation_record import digest
root=Path('research/pfr_pressure_cohort_20261020/v1');read=datetime.now(UTC);start=time.monotonic()
r=json.loads((root/'diagnostic_receipt.json').read_text());ref=r['artifact_ref'];assert ref['bytes']<=32*1024*1024
p=Path(ref['path']);raw=p.read_bytes();assert p.resolve().parent==Path('artifacts/pfr_pressure_cohort').resolve()and len(raw)==ref['bytes']and hashlib.sha256(raw).hexdigest()==ref['sha256'];source=json.loads(raw)
assert clock(source['provenance']['actual_derived_at'])<=read and source['provenance']['producer_code_sha256']==hashlib.sha256(Path('backend/app/product_services/pfr_pressure_cohort.py').read_bytes()).hexdigest()
core={k:v for k,v in source.items()if k not in {'provenance','semantic_sha256'}};assert digest(core)==source['semantic_sha256']
result=build_pressure_catalog(source)
result['provenance']=dict(source_diagnostic_ref=ref,original_source_read_at=source['provenance']['actual_read_at'],actual_catalog_read_at=read.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),
 producer_code_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in [Path('backend/app/product_services')/(n+'.py')for n in ('pfr_pressure_cohort','pfr_pressure_catalog','contact_cohort_reconciliation','pfr_advanced_features','pfr_source_components','offensive_line_participation','fumble_event_components')]},
 actual_source_runner_binding_at=datetime.now(UTC).isoformat(),source_runner_sha256=hashlib.sha256((root/'inspect_source.py').read_bytes()).hexdigest(),source_availability='Revised later captures/current alias receipts, not contemporaneous historical pregame evidence')
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False,default=str).encode();assert len(raw)<=32*1024*1024
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/pfr_pressure_catalog')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb')as handle:handle.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:deepcopy(v)for k,v in result.items()if k not in {'game_rows','profiles','semantic_sha256','provenance'}}
selected.update(game_rows=[g for g in result['game_rows']if g['offense']in {'SF','WAS'}or g['defense']in {'SF','WAS'}],profiles=[p for p in result['profiles']if p['team']in {'SF','WAS'}],identity_scope='All batch-global native identity incidents retained; metric rows select either native SF/WAS side')
selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
with engine.begin()as connection:queue=persist_pressure_identity_requests(connection,result,source_refs=[full,ref])
if queue['records']:
 with engine.connect()as connection:records=[dict(r)for r in connection.execute(text("SELECT identity_quarantine_id,source_table,source_record_key,source_player_key,status,first_seen_at,updated_at FROM target.identity_quarantine WHERE identity_quarantine_id=ANY(CAST(:ids AS text[]))"),dict(ids=[q['identity_quarantine_id']for q in queue['records']])).mappings()]
 assert len(records)==queue['requests'];queue['durable_readback_records']=records
coverage=[]
for season in (2023,2024,2025):
 gs=[g for g in result['game_rows']if g['season']==season];ps=[p for p in result['profiles']if p['season']==season]
 coverage.append(dict(season=season,native_game_sides=len(gs),exact_game_rates_perID=sum(g['pressure_rate']is not None for g in gs),exact_offense_profiles=sum(p['value']is not None and p['catalog_id']=='G13-M03'for p in ps),exact_defense_profiles=sum(p['value']is not None and p['catalog_id']=='G14-M01'for p in ps)))
receipt=dict(actual_started_at=read.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,source_diagnostic_ref=ref,full_ref=full,selected_ref=sel,global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],coverage=coverage,queue=queue,source_fetches=0,parent_inflates=0,aliases_mutated=0,models=0,pregame_serving_eligible=False)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2,default=str)+'\n');print(json.dumps({k:v for k,v in receipt.items()if k!='queue'},indent=2,default=str));print(json.dumps({k:queue[k]for k in ('requests','created_new','existing_unchanged')}))
