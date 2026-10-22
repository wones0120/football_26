"""One bounded native weekly extract, frozen now; no original-source backdating."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time,sys
from backend.app.db import engine
from backend.app.product_services.weekly_effectiveness_catalog_features import load_weekly_effectiveness_sources,build_weekly_effectiveness,DEFINITIONS,SOURCE_FIELDS,persist_weekly_identity_requests
from backend.app.product_services.defense_context_evidence import _hash
ROOT=Path('research/weekly_effectiveness_catalog_features_20261020/v1')
def save(v,folder,bound):
 raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=bound;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts')/folder/f'{sha}.json';p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
start=time.monotonic();actual=datetime.now(UTC);before=202607
if '--source' in sys.argv:
 path=Path(sys.argv[sys.argv.index('--source')+1]).resolve();managed=Path('artifacts/weekly_effectiveness_sources').resolve()
 if path.parent!=managed or len(path.stem)!=64:raise ValueError('Only the explicit server-managed frozen source extract is accepted')
 raw=path.read_bytes()
 if len(raw)>128*1024*1024 or hashlib.sha256(raw).hexdigest()!=path.stem:raise ValueError('Frozen source hash/size mismatch')
 frozen=json.loads(raw)
 if frozen['before_period']!=before or tuple(frozen['projected_source_fields'])!=SOURCE_FIELDS or frozen['source_kind']!='actual_database_raw_weekly_revision_extract':raise ValueError('Frozen source scope/projection mismatch')
 from backend.app.product_services.factual_designation import clock
 if clock(frozen['actual_extracted_at'])>actual:raise ValueError('Frozen source from future')
 records=frozen['rows'];source=dict(path=str(path),sha256=path.stem,bytes=len(raw));del raw
else:
 records=load_weekly_effectiveness_sources(engine,before_period=before,cutoff=actual,start_season=2023)
 if not records:raise ValueError('No supported native REG weekly sources; not zero evidence')
 source=save(dict(source_kind='actual_database_raw_weekly_revision_extract',actual_extracted_at=actual.isoformat(),before_period=before,start_season=2023,original_source_file_availability='Unknown; legacy weekly ingestion can replace raw table rows; this new byte freeze preserves actual current revision, not original HTTP artifact',projected_source_fields=SOURCE_FIELDS,projection_meaning='Exact native scope/role and metric input fields only; original key presence/nulls retained; unrelated raw JSON excluded',rows=sorted(records,key=lambda r:r['source_id']),evidence_use='postlock_descriptive_not_pregame_or_serving'), 'weekly_effectiveness_sources',128*1024*1024)
value=build_weekly_effectiveness(records,before_period=before,cutoff=actual);value['provenance']['source_extract_ref']=source;
with engine.begin() as connection:
 queue=persist_weekly_identity_requests(connection,value,source_ref=source)
 from sqlalchemy import text
 states=connection.execute(text("SELECT source_record_key,status FROM target.identity_quarantine WHERE source_schema='public' AND source_table='raw_nfl_weekly_stat' AND source_record_key=ANY(CAST(:keys AS text[]))"),dict(keys=[r['key'] for r in queue['records']])).mappings().all()
 queue['verified_states']=[dict(r) for r in states]
 if len(states)!=queue['distinct_queue_keys']:raise ValueError('Durable queue readback mismatch')
(ROOT/'identity_persistence_receipt.json').write_text(json.dumps(queue,indent=2)+'\n')
value['provenance']['identity_review_persistence']=dict(distinct_queue_keys=queue['distinct_queue_keys'],source_incidents=queue['source_incidents'],readback_verified=True,policy=queue['policy']);value['provenance']['actual_publication_at']=datetime.now(UTC).isoformat();full=save(value,'weekly_effectiveness_catalog',96*1024*1024)
selected={k:v for k,v in value.items() if k not in {'rows','provenance','identity_review_requests','semantic_sha256'}};selected['selected_scope']=dict(teams=['SF','WAS'],season=2026,parent_semantic_sha256=value['semantic_sha256']);selected['rows']=[r for r in value['rows'] if r['season']==2026 and r['team'] in {'SF','WAS'}];selected['selected_semantic_sha256']=_hash(selected);selected['provenance']={**value['provenance'],'full_ref':full};selected_ref=save(selected,'weekly_effectiveness_catalog',4*1024*1024)
coverage={mid:dict(rows=sum(mid in r['metrics'] for r in value['rows']),known_ratios=sum(r['metrics'].get(mid,{}).get('value') is not None for r in value['rows']),unknown_or_zero_exposure=sum(mid in r['metrics'] and r['metrics'][mid]['value'] is None for r in value['rows'])) for mid in DEFINITIONS}
r=dict(actual_started_at=actual.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,source_extract_ref=source,full_ref=full,selected_ref=selected_ref,global_semantic_sha256=value['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],raw_source_rows=len(records),feature_rows=len(value['rows']),canonical_attached=sum(r['player_master_id'] is not None for r in value['rows']),quarantined_rows=len(value['quarantined_source_rows']),identity_review_requests=len(value['identity_review_requests']),coverage=coverage,by_season={str(y):sum(r['season']==y for r in value['rows']) for y in sorted({r['season'] for r in value['rows']})},native_QB_scope_rows=sum(r['QB_scope_source_proven'] for r in value['rows']),selected_rows=len(selected['rows']),original_availability='Unknown historical original capture; actual later import clocks retained; immutable current DB-extract revision newly frozen',producer_code_sha256=value['provenance']['producer_code_sha256'],evidence_use=value['evidence_use'],pregame_serving_eligible=False,source_fetches=0,models=0,consumer_status='Features only; models/optimizer/app paused/pending')
(ROOT/'actual_derivation_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
