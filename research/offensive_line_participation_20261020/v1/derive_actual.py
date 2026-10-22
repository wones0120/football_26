"""Serial native first-unit proofs, one cutoff alias read, immutable publication."""
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
from backend.app.product_services.offensive_line_participation import build_offensive_line_continuity,reattach_line_identities,load_line_alias_evidence,persist_line_identity_requests
from backend.app.product_services.evaluation_record import digest
root=Path('research/offensive_line_participation_20261020/v1');start=time.monotonic();read=datetime.now(UTC);stages=[];outputs=[];final=[]
sources=json.loads(Path('research/participation_source_components_20261020/v1/actual_receipt.json').read_text())['outputs']
history={r['season']:r['descriptor']for r in json.loads(Path('research/player_opportunity_history_20261020/v1/source_coverage.json').read_text())}
fields=['game_id','play_id','season','week','season_type','posteam','defteam','play_type','play_type_nfl','desc','order_sequence','no_play','quarter_end','fumble','pass_attempt','rush_attempt','sack','qb_dropback','qb_spike','qb_kneel','qb_scramble','two_point_attempt']
with Session(engine)as session:
 schedule_source=session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b');schedule=load_schedule_context(schedule_source,cutoff=read)
 schedule_ref=dict(snapshot_id=str(schedule_source.snapshot_id),sha256=schedule_source.content_sha256)
 for item in sources:
  year=item['season']
  if year not in history:continue
  snapshot=session.get(SourceSnapshot,item['source']['snapshot_id']);block=load_participation_snapshot(snapshot,actual_read_at=datetime.now(UTC));assert block['semantic_sha256']==item['semantic_sha256']
  d=history[year];p=Path(d['path']);raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()==d['manifest']['sha256']and len(raw)==d['manifest']['bytes'];del raw
  schema=pl.read_parquet_schema(p);frame=pl.read_parquet(p,columns=[f for f in fields if f in schema])
  value=build_offensive_line_continuity(block,frame.iter_rows(named=True),schedule['game_rows'],[],before_period=202607,cutoff=read)
  provenance=dict(original_PBP_manifest=d['manifest'],original_PBP_path=str(p.resolve()),participation_source=block['provenance'],schedule_ref=schedule_ref,actual_source_read_at=datetime.now(UTC).isoformat())
  stages.append((value,provenance));print(json.dumps(dict(season=year,stage='native_start_units',qualified=sum(r['source_proven_starting_unit']for r in value['starting_units']))),flush=True)
  del value,block,frame;gc.collect()
universe={m['source_player_id']for value,_ in stages for u in value['starting_units']if u['source_proven_starting_unit']for m in u['native_line_members']}
alias_cutoff=datetime.now(UTC)
with engine.connect()as connection:alias_rows=load_line_alias_evidence(connection,universe,cutoff=alias_cutoff)
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/offensive_line_participation')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb')as stream:stream.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
for value,provenance in stages:
 result=reattach_line_identities(value,alias_rows,cutoff=alias_cutoff,identity_universe=universe)
 result['provenance'].update(**provenance,actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),
   producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/offensive_line_participation.py').read_bytes()).hexdigest(),
   source_adapter_sha256=hashlib.sha256(Path('backend/app/product_services/participation_source_components.py').read_bytes()).hexdigest(),
   eligibility_helper_sha256=hashlib.sha256(Path('backend/app/product_services/fumble_event_components.py').read_bytes()).hexdigest(),
   identity_scope='All source-proven native OL keys across the three-season extraction; all implicated aliases withheld across every period')
 full=save(result);selected={k:v for k,v in result.items()if k not in {'starting_units','continuity_rows','identity_review_requests','semantic_sha256','provenance'}}
 for name in ('starting_units','continuity_rows','identity_review_requests'):selected[name]=[r for r in result[name]if r['team']in {'SF','WAS'}]
 selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
 output=dict(season=result['season'],full_ref=full,selected_ref=sel,global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],
  expected_game_sides=len(result['starting_units']),source_proven_initial_units=sum(u['source_proven_starting_unit']for u in result['starting_units']),
  defined_native_continuity=sum(r['value']is not None for r in result['continuity_rows']),complete_canonical_continuity=sum(r['canonical_qualified_value']is not None for r in result['continuity_rows']),
  selected_unit_rows=len(selected['starting_units']),identity_incidents=len(result['identity_review_requests']),
  unknown_unit_reasons={reason:sum(u['unknown_reason']==reason for u in result['starting_units'])for reason in sorted({u['unknown_reason']for u in result['starting_units']if u['unknown_reason']})})
 outputs.append(output);final.append(result)
source_refs=[o['full_ref']for o in outputs]
with engine.begin()as connection:queue=persist_line_identity_requests(connection,final,source_refs=source_refs)
with engine.connect()as connection:
 keys=[r['source_record_key']for r in queue['records']]
 rows=connection.execute(text("""SELECT source_table,source_record_key,source_player_key,status,first_seen_at,updated_at
 FROM target.identity_quarantine WHERE source_schema='public' AND source_system='nflreadpy'
 AND source_record_key=ANY(CAST(:keys AS text[]))"""),dict(keys=keys)).mappings().all()
 lookup={(r['source_table'],r['source_record_key']):r for r in rows}
 assert all((r['source_table'],r['source_record_key'])in lookup and lookup[(r['source_table'],r['source_record_key'])]['source_player_key']==r['source_player_id']for r in queue['records'])
 queue['durable_readback_records']=[dict(r,first_seen_at=str(r['first_seen_at']),updated_at=str(r['updated_at']))for r in rows];queue['actual_queue_readback_at']=datetime.now(UTC).isoformat()
receipt=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,outputs=outputs,native_OL_identity_universe=len(universe),eligible_alias_rows=len(alias_rows),alias_cutoff_at=alias_cutoff.isoformat(),
 global_alias_status_counts={status:sum(r['status']==status for r in final[0]['native_identity_receipts'].values())for status in sorted({r['status']for r in final[0]['native_identity_receipts'].values()})},
 queue=queue,source_fetches=0,parent_inflates=0,models=0,alias_mutations=0,evidence_use='historical_postseason_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(dict(status='complete',elapsed_seconds=receipt['elapsed_seconds'],outputs=outputs,identity_status=receipt['global_alias_status_counts'],queue_requests=queue['requests'])),flush=True)
