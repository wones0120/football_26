from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time,gc
import polars as pl
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.provider_pressure_scramble import build_provider_pressure_scrambles,load_reviewed_pressure_basis,attach_pressure_identity,persist_pressure_identity_requests
from backend.app.product_services.participation_source_components import load_participation_snapshot
from backend.app.product_services import coverage_receiver_performance
from backend.app.product_services.factual_designation import clock
from backend.app.product_services.evaluation_record import digest
root=Path('research/provider_pressure_scramble_20261020/v1');start=time.monotonic();started=datetime.now(UTC)
receipt=json.loads(Path('research/participation_defense_catalog_20261020/v1/actual_receipt.json').read_text());old=json.loads(Path('research/coverage_receiver_performance_20261020/v1/actual_receipt.json').read_text());identity_ref=old['outputs'][0]['full_ref']
p=Path(identity_ref['path']).resolve();assert p.parent==Path('artifacts/coverage_receiver_performance').resolve()and p.name==identity_ref['sha256']+'.json'and identity_ref['bytes']<=32*1024*1024
raw=p.read_bytes();assert len(raw)==identity_ref['bytes']and hashlib.sha256(raw).hexdigest()==identity_ref['sha256'];identity=json.loads(raw);del raw
assert identity['pregame_serving_eligible']is False and identity['forecast']is None
assert identity['provenance']['producer_code_hashes']['backend/app/product_services/coverage_receiver_performance.py']==hashlib.sha256(Path(coverage_receiver_performance.__file__).read_bytes()).hexdigest()
corekeys=('version','catalog_id','source_components','game_rows','profiles','prior_windows','native_identity_receipts','identity_review_requests','future_alias_evidence_excluded','definitions','units');assert identity['semantic_sha256']==digest({k:identity[k]for k in corekeys})
cutoff=clock(identity['provenance']['actual_alias_cutoff_at']);assert cutoff<=clock(identity['provenance']['actual_publication_at'])<=started
universe=set(identity['native_identity_receipts']);aliases=[r for p in identity['native_identity_receipts'].values()for r in p['original_alias_evidence']];assert len(aliases)==len({(r['alias_id'],r['source_key'])for r in aliases});del identity
blocks=[];sources=[]
with Session(engine)as session:
 for entry in receipt['outputs']:
  read=datetime.now(UTC);basis=load_reviewed_pressure_basis(entry['full_ref'],cutoff=read);year=basis['season'];snapshot=session.get(SourceSnapshot,entry['native_source_snapshot_id']);part=load_participation_snapshot(snapshot,actual_read_at=read)
  assert part['season']==year and part['semantic_sha256']==basis['provenance']['participation_semantic_sha256'] and snapshot.content_sha256==entry['native_source_sha256']
  pr=basis['provenance'];manifest=pr['original_PBP_manifest'];p=Path(pr['original_PBP_path']);raw=p.read_bytes();assert len(raw)==manifest['bytes']<=64*1024*1024 and hashlib.sha256(raw).hexdigest()==manifest['sha256']
  assert manifest['url']==f'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{year}.parquet'and clock(manifest['received_at'])<=read;del raw
  fields=['game_id','play_id','season','week','season_type','posteam','passer_player_id','rusher_player_id','qb_scramble','rush_attempt'];assert set(fields)<=set(pl.read_parquet_schema(p));frame=pl.read_parquet(p,columns=fields)
  block=build_provider_pressure_scrambles(basis,part,frame.iter_rows(named=True));blocks.append(block)
  sources.append(dict(season=year,basis_ref=entry['full_ref'],basis_semantic_sha256=basis['semantic_sha256'],participation_snapshot_id=str(snapshot.snapshot_id),participation_sha256=snapshot.content_sha256,participation_semantic_sha256=part['semantic_sha256'],PBP_manifest=manifest,PBP_path=str(p.resolve()),actual_read_at=read.isoformat()))
  universe.update(block['native_identity_universe']);del basis,part,frame;gc.collect()
features=attach_pressure_identity(blocks,aliases,cutoff=cutoff,identity_universe=universe);outputs=[]
def save(x):
 raw=json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/provider_pressure_scramble')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb')as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
for b,s in zip(features,sources):
 b['provenance']=dict(source_input=s,frozen_identity_source_ref=identity_ref,frozen_alias_cutoff_at=cutoff.isoformat(),actual_read_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/provider_pressure_scramble.py').read_bytes()).hexdigest(),identity_resolver_sha256=hashlib.sha256(Path('backend/app/product_services/contact_cohort_reconciliation.py').read_bytes()).hexdigest(),identity_policy='Recompute all-edge collision closure on full inherited2570 plus all potential native passer/rusher universe; new keys without frozen evidence remain attachment-unknown, never current missing assertion',original_availability='FTN postseason and revised historical PBP; not contemporaneous pregame proof')
 full=save(b);selected={**b,'game_rows':[r for r in b['game_rows']if r['team']in{'SF','WAS'}],'profiles':[r for r in b['profiles']if r['team']in{'SF','WAS'}],'selection':dict(teams=['SF','WAS'],full_ref=full,all_batch_global_identity_and_residual_evidence_retained=True)};sel=save(selected)
 outputs.append(dict(season=b['season'],full_ref=full,selected_ref=sel,native_actor_games=len(b['game_rows']),canonical_actor_games=sum(r['player_master_id']is not None for r in b['game_rows']),defined_game_ratios=sum(r['scramble_fraction']is not None for r in b['game_rows']),defined_profiles=sum(r['scramble_fraction']is not None for r in b['profiles']),known_pressured_dropbacks=sum(r['known_pressured_dropbacks']for r in b['game_rows']),known_same_QB_scrambles=sum(r['known_same_QB_scrambles']for r in b['game_rows']),unknown_memberships=sum(r['unknown_pressured_membership']for r in b['game_rows']),unassigned_residual=len(b['unassigned_QB_residual'])))
with engine.begin()as connection:
 queue=persist_pressure_identity_requests(connection,features,source_refs=[x['full_ref']for x in outputs])
 if queue['records']:
  queue['durable_readback_records']=[dict(r)for r in connection.execute(text("SELECT identity_quarantine_id,source_table,source_record_key,source_player_key,status,first_seen_at,updated_at FROM target.identity_quarantine WHERE source_schema='public' AND source_record_key=ANY(CAST(:keys AS text[]))"),dict(keys=[r['source_record_key']for r in queue['records']])).mappings()]
  assert len(queue['durable_readback_records'])==len(queue['records'])
  for r in queue['durable_readback_records']:
   for k in('first_seen_at','updated_at'):r[k]=r[k].isoformat()
proofs=features[0]['identity_receipts'];out=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,source_inputs=sources,frozen_identity_source_ref=identity_ref,frozen_alias_cutoff_at=cutoff.isoformat(),outputs=outputs,global_native_identity_keys=len(proofs),uniquely_attached=sum(p['player_master_id']is not None for p in proofs.values()),queue=queue,source_fetches=0,parent_inflations=0,new_alias_reads=0,alias_mutations=0,models=0)
(root/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
