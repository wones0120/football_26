"""Three retained native coverage/target sources; no fetch/fit/current serving."""
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
from backend.app.product_services.coverage_receiver_performance import build_native_coverage_performance,attach_and_window_performance,persist_coverage_identity_requests
from backend.app.product_services.evaluation_record import digest
root=Path('research/coverage_receiver_performance_20261020/v1');start=time.monotonic();started=datetime.now(UTC);blocks=[];inputs=[];universe=set();outputs=[];features=[]
sources=json.loads(Path('research/participation_source_components_20261020/v1/actual_receipt.json').read_text())['outputs']
history={r['season']:r['descriptor']for r in json.loads(Path('research/player_opportunity_history_20261020/v1/source_coverage.json').read_text())}
code_paths=['backend/app/product_services/'+name+'.py'for name in('coverage_receiver_performance','participation_source_components','participation_defense_catalog','offensive_line_participation','fumble_event_components','schedule_context_features')]
code_hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest()for p in code_paths}
columns=['game_id','play_id','season','week','season_type','posteam','defteam','play_type','play_type_nfl','desc','no_play','quarter_end','fumble','pass_attempt','rush_attempt','sack','qb_dropback','qb_spike','qb_kneel','qb_scramble','two_point_attempt','receiver_player_id','complete_pass','epa']
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=96*1024*1024
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/coverage_receiver_performance')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb')as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
with Session(engine)as session:
 read=datetime.now(UTC);snapshot=session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b');schedule=load_schedule_context(snapshot,cutoff=read)
 schedule_ref=dict(snapshot_id=str(snapshot.snapshot_id),sha256=snapshot.content_sha256,actual_read_at=read.isoformat())
 for item in sources:
  year=item['season']
  if year not in history:continue
  read=datetime.now(UTC);snapshot=session.get(SourceSnapshot,item['source']['snapshot_id']);part=load_participation_snapshot(snapshot,actual_read_at=read)
  assert part['semantic_sha256']==item['semantic_sha256']
  d=history[year];p=Path(d['path']);raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()==d['manifest']['sha256']and len(raw)==d['manifest']['bytes'];del raw
  names=pl.read_parquet_schema(p);frame=pl.read_parquet(p,columns=[k for k in columns if k in names])
  block=build_native_coverage_performance(part,frame.iter_rows(named=True),schedule,before_period=202607,event_source_sha256=d['manifest']['sha256'])
  block['provenance'].update(original_PBP_descriptor=d,native_participation=part['provenance'],schedule_ref=schedule_ref,
   actual_read_at=read.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),producer_code_hashes=code_hashes,source_field_availability={k:k in names for k in columns})
  ref=save(block);blocks.append(block);universe.update(block['native_identity_universe']);inputs.append(dict(season=year,native_ref=ref,semantic_sha256=block['semantic_sha256'],source_snapshot_id=str(snapshot.snapshot_id),PBP_manifest=d['manifest']))
  print(json.dumps(dict(stage='native',season=year,actor_games=len(block['game_rows']),events=len(block['event_basis']),unassigned=len(block['unassigned_residual']),native_ref=ref)),flush=True)
  del part,frame;gc.collect()
cutoff=datetime.now(UTC)
with engine.connect()as connection:aliases=load_line_alias_evidence(connection,universe,cutoff=cutoff)
for block,entry in zip(blocks,inputs):
 result=attach_and_window_performance([block],aliases,cutoff=cutoff,identity_universe=universe)
 result['provenance']=dict(source_native_ref=entry['native_ref'],schedule_ref=schedule_ref,actual_read_at=started.isoformat(),actual_alias_cutoff_at=cutoff.isoformat(),
  actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_hashes=code_hashes,
  original_historical_availability='Postseason release; actual2026capture and revised PBP never contemporaneous historical pregame proof')
 full=save(result);selected={k:v for k,v in result.items()if k not in('game_rows','profiles','prior_windows','identity_review_requests','semantic_sha256','provenance')}
 for key in('game_rows','profiles','prior_windows'):selected[key]=[r for r in result[key]if r['team']in{'SF','WAS'}]
 selected['identity_review_requests']=[r for r in result['identity_review_requests']if r['team']in{'SF','WAS'}]
 selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
 output=dict(season=block['season'],native_ref=entry['native_ref'],full_ref=full,selected_ref=sel,global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],
  actor_games=len(result['game_rows']),profiles=len(result['profiles']),prior_windows=len(result['prior_windows']),selected_game_rows=len(selected['game_rows']),
  nonempty_exact_game_contrasts={name:sum(r[name]is not None for r in result['game_rows'])for name in('man_minus_zone_completion_rate','man_minus_zone_target_EPA')},
  nonempty_exact_profile_contrasts={name:sum(r[name]is not None for r in result['profiles'])for name in('man_minus_zone_completion_rate','man_minus_zone_target_EPA')},
  nonempty_exact_prior_contrasts={name:sum(r[name]is not None for r in result['prior_windows'])for name in('man_minus_zone_completion_rate','man_minus_zone_target_EPA')},
  unknown_recipient_events_excluded_by_verified_off_field=sum(r['unknown_recipient_events_excluded_by_verified_off_field']for r in result['game_rows']),
  unassigned_residual_events=len(block['unassigned_residual']),missing_PBP_games=block['missing_PBP_game_ids'])
 outputs.append(output);features.append(result);print(json.dumps(dict(stage='attached',**output)),flush=True)
with engine.begin()as connection:queue=persist_coverage_identity_requests(connection,features,source_refs=[r['full_ref']for r in outputs])
if queue['records']:
 with engine.connect()as connection:
  queue['durable_readback_records']=[dict(r)for r in connection.execute(text("SELECT identity_quarantine_id,source_table,source_record_key,source_player_key,status,first_seen_at,updated_at FROM target.identity_quarantine WHERE source_schema='public' AND source_record_key=ANY(CAST(:keys AS text[]))"),dict(keys=[r['source_record_key']for r in queue['records']])).mappings()]
 assert len(queue['durable_readback_records'])==queue['requests']
receipt=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,source_inputs=inputs,outputs=outputs,queue=queue,
 native_universe=len(universe),alias_rows=len(aliases),identity_status_counts=dict(__import__('collections').Counter(r['status']for r in features[0]['native_identity_receipts'].values())),
 source_fetches=0,parent_inflates=0,models=0,alias_mutations=0,evidence_use='historical_postseason_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2,default=str)+'\n');print(json.dumps(dict(stage='END',elapsed_seconds=receipt['elapsed_seconds'],identity_status_counts=receipt['identity_status_counts'],queue_requests=queue['requests'])),flush=True)
