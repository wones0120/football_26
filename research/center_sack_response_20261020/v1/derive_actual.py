"""Independent native center proofs, cutoff aliases and matched observed sacks."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time,gc
import polars as pl
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.schedule_context_features import load_schedule_context
from backend.app.product_services.participation_source_components import load_participation_snapshot
from backend.app.product_services.offensive_line_participation import load_line_alias_evidence
from backend.app.product_services.center_sack_response import build_first_snap_centers,build_center_sack_response,persist_center_identity_requests
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.factual_designation import clock
root=Path('research/center_sack_response_20261020/v1');start=time.monotonic();started=datetime.now(UTC);components=[];coverage=[];inputs=[];universe=set()
source_outputs=json.loads(Path('research/participation_source_components_20261020/v1/actual_receipt.json').read_text())['outputs']
history={r['season']:r['descriptor']for r in json.loads(Path('research/player_opportunity_history_20261020/v1/source_coverage.json').read_text())}
line_outputs={r['season']:r for r in json.loads(Path('research/offensive_line_participation_20261020/v1/actual_receipt.json').read_text())['outputs']}
coverage_outputs={r['season']:r for r in json.loads(Path('research/participation_defense_catalog_20261020/v1/actual_receipt.json').read_text())['outputs']}
fields=['game_id','play_id','season','week','season_type','posteam','defteam','play_type','play_type_nfl','desc','order_sequence','no_play','quarter_end','fumble','pass_attempt','rush_attempt','sack','qb_dropback','qb_spike','qb_kneel','qb_scramble','two_point_attempt']
def load(ref,folder):
 path=Path(ref['path']).resolve();assert path.parent==Path('artifacts',folder).resolve()and path.name==ref['sha256']+'.json'and ref['bytes']<=16*1024*1024
 raw=path.read_bytes();assert len(raw)==ref['bytes']and hashlib.sha256(raw).hexdigest()==ref['sha256'];return json.loads(raw)
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=32*1024*1024
 sha=hashlib.sha256(raw).hexdigest();path=Path('artifacts/center_sack_response')/(sha+'.json');path.parent.mkdir(exist_ok=True)
 if path.exists():assert path.read_bytes()==raw
 else:
  with path.open('xb')as stream:stream.write(raw)
  path.chmod(0o444)
 return dict(path=str(path.resolve()),sha256=sha,bytes=len(raw))
with Session(engine)as session:
 schedule=load_schedule_context(session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b'),cutoff=started)
 for entry in source_outputs:
  year=entry['season']
  if year not in history:continue
  read=datetime.now(UTC);p=load_participation_snapshot(session.get(SourceSnapshot,entry['source']['snapshot_id']),actual_read_at=read)
  assert p['semantic_sha256']==entry['semantic_sha256']
  descriptor=history[year];assert descriptor['manifest']['url']==f'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{year}.parquet'and clock(descriptor['manifest']['received_at'])<=read and descriptor['manifest']['bytes']<=128*1024*1024;path=Path(descriptor['path']);raw=path.read_bytes();assert len(raw)==descriptor['manifest']['bytes']and hashlib.sha256(raw).hexdigest()==descriptor['manifest']['sha256'];del raw
  schema=pl.read_parquet_schema(path);frame=pl.read_parquet(path,columns=[f for f in fields if f in schema])
  c=build_first_snap_centers(p,frame.iter_rows(named=True),schedule,before_period=202607,event_source_sha256=descriptor['manifest']['sha256'])
  c['provenance'].update(participation_source=p['provenance'],original_PBP_descriptor=descriptor,actual_read_at=read.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),
   producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/center_sack_response.py').read_bytes()).hexdigest(),firstsnap_helper_sha256=hashlib.sha256(Path('backend/app/product_services/offensive_line_participation.py').read_bytes()).hexdigest(),source_adapter_sha256=hashlib.sha256(Path('backend/app/product_services/participation_source_components.py').read_bytes()).hexdigest())
  center_ref=save(c);components.append(c)
  old=load(line_outputs[year]['full_ref'],'offensive_line_participation');assert old['provenance']['producer_code_sha256']==hashlib.sha256(Path('backend/app/product_services/offensive_line_participation.py').read_bytes()).hexdigest()and clock(old['provenance']['actual_publication_at'])<=read;assert old['provenance']['participation_semantic_sha256']==p['semantic_sha256'];universe.update(old['native_identity_receipts'])
  response=load(coverage_outputs[year]['full_ref'],'participation_defense_catalog');assert clock(response['provenance']['actual_publication_at'])<=read;assert response['provenance']['producer_code_sha256']==hashlib.sha256(Path('backend/app/product_services/participation_defense_catalog.py').read_bytes()).hexdigest();coverage.append(response)
  inputs.append(dict(season=year,center_ref=center_ref,old_line_ref=line_outputs[year]['full_ref'],coverage_ref=coverage_outputs[year]['full_ref'],known_first_centers=sum(u['source_proven_center']for u in c['units'])))
  print(json.dumps(inputs[-1]),flush=True);del p,frame,old,c;gc.collect()
old_count=len(universe);universe.update(u['source_center_id']for c in components for u in c['units']if u['source_proven_center']);alias_cutoff=datetime.now(UTC)
with engine.connect()as connection:aliases=load_line_alias_evidence(connection,universe,cutoff=alias_cutoff)
result=build_center_sack_response(components,coverage,aliases,cutoff=alias_cutoff,identity_universe=universe)
result['provenance'].update(source_inputs=inputs,actual_read_started_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),
 producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/center_sack_response.py').read_bytes()).hexdigest(),global_native_universe_policy='Prior complete352key OL universe plus independently proven additional C keys; no scoped conflict escape')
full=save(result);selected={k:v for k,v in result.items()if k not in('game_rows','profiles','semantic_sha256','provenance')};selected['game_rows']=[r for r in result['game_rows']if r['team']in{'SF','WAS'}];selected['profiles']=[r for r in result['profiles']if r['team']in{'SF','WAS'}]
selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};slice_ref=save(selected)
with engine.begin()as connection:queue=persist_center_identity_requests(connection,result,source_refs=[full])
if queue['records']:
 with engine.connect()as connection:
  queue['durable_readback_records']=[dict(r)for r in connection.execute(text("SELECT identity_quarantine_id,source_table,source_record_key,source_player_key,status,first_seen_at,updated_at FROM target.identity_quarantine WHERE source_schema='public' AND source_record_key=ANY(CAST(:keys AS text[]))"),dict(keys=[r['source_record_key']for r in queue['records']])).mappings()]
 assert len(queue['durable_readback_records'])==queue['requests']
queue['actual_readback_at']=datetime.now(UTC).isoformat()
prior_path=Path('research/offensive_line_participation_20261020/v1/actual_receipt.json');prior_raw=prior_path.read_bytes();prior_queue=json.loads(prior_raw)['queue']
from identity_receipt import compare_existing_cases
queue.update(compare_existing_cases(queue.get('durable_readback_records',[]),prior_queue))
queue['prior_case_receipt_ref']=dict(path=str(prior_path.resolve()),sha256=hashlib.sha256(prior_raw).hexdigest(),bytes=len(prior_raw))
receipt=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,source_inputs=inputs,full_ref=full,selected_ref=slice_ref,global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],
 native_universe_old=old_count,native_universe_expanded=len(universe),identity_status_counts=dict(__import__('collections').Counter(r['status']for r in result['native_identity_receipts'].values())),queue=queue,
 per_season={year:dict(expected_game_sides=sum(r['season']==year for r in result['game_rows']),known_classes={label:sum(r['season']==year and r['center_class']==label for r in result['game_rows'])for label in('same','changed')},
 unknown_classes=sum(r['season']==year and r['comparison_applicable']is not False and r['center_class']is None for r in result['game_rows']),
 defined_team_contrasts=sum(p['season']==year and p['same_minus_changed_sack_rate']is not None for p in result['profiles']))for year in sorted(centers['season']for centers in components)},
 selected_game_rows=len(selected['game_rows']),selected_profiles=len(selected['profiles']),source_fetches=0,parent_inflates=0,models=0,alias_mutations=0,
 evidence_use=result['evidence_use'],pregame_serving_eligible=False)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2,default=str)+'\n');print(json.dumps(receipt,default=str),flush=True)
