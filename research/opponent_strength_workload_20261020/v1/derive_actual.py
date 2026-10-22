"""Serial original historical EPA contexts, then one reviewed weekly cohort join."""
from pathlib import Path
from datetime import datetime,UTC
import hashlib,json,time,gc
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.schedule_context_features import load_schedule_context
from backend.app.product_services.opponent_strength_workload import load_retained_defense_strength_context,build_opponent_strength_workload
from backend.app.product_services.weekly_passing_air_efficiency import load_reviewed_weekly_input
from backend.app.product_services.evaluation_record import digest
root=Path('research/opponent_strength_workload_20261020/v1');start=time.monotonic();read=datetime.now(UTC);before=202607

def save(value,kind=''):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=96*1024*1024
 sha=hashlib.sha256(raw).hexdigest();path=Path('artifacts/opponent_strength_workload')/(sha+'.json');path.parent.mkdir(exist_ok=True)
 if path.exists():assert path.read_bytes()==raw
 else:
  with path.open('xb')as stream:stream.write(raw)
  path.chmod(0o444)
 return dict(path=str(path.resolve()),sha256=sha,bytes=len(raw))

with Session(engine)as session:
 snapshot=session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b');schedule=load_schedule_context(snapshot,cutoff=read)
history={r['season']:r['descriptor']for r in json.loads(Path('research/player_opportunity_history_20261020/v1/source_coverage.json').read_text())};contexts=[];source_outputs=[]
for season in(2023,2024,2025):
 context=load_retained_defense_strength_context(history[season],schedule,before_period=before,actual_read_at=datetime.now(UTC))
 context['provenance']['actual_publication_at']=datetime.now(UTC).isoformat();ref=save(context)
 source_outputs.append(dict(season=season,context_ref=ref,semantic_sha256=context['semantic_sha256'],expected_game_sides=len(context['game_rows']),
  reference=context['reference_terciles'],known_strength_groups={group:sum(row['week']>=4 and row['group']==group for row in context['contexts'])for group in('strong','weak','middle')},
  unknown_evaluation_groups=sum(row['week']>=4 and row['group']is None for row in context['contexts'])))
 contexts.append({k:v for k,v in context.items()if k not in('event_basis','game_rows')})
 print(json.dumps(source_outputs[-1]),flush=True);del context;gc.collect()
weekly_receipt=json.loads(Path('research/weekly_effectiveness_catalog_features_20261020/v1/actual_derivation_receipt.json').read_text());weekly_ref=weekly_receipt['full_ref']
weekly=load_reviewed_weekly_input(weekly_ref,cutoff=datetime.now(UTC));extract=weekly['provenance']['source_extract_ref'];path=Path(extract['path']).resolve()
assert path.parent==Path('artifacts/weekly_effectiveness_sources').resolve()and path.name==extract['sha256']+'.json'and path.stat().st_size==extract['bytes']and extract['bytes']<=96*1024*1024
h=hashlib.sha256()
with path.open('rb')as stream:
 for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
assert h.hexdigest()==extract['sha256']
result=build_opponent_strength_workload(weekly,schedule,contexts,before_period=before)
result['provenance'].update(weekly_input_ref=weekly_ref,source_extract_ref=extract,defense_context_refs=[r['context_ref']for r in source_outputs],actual_read_at=read.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),
 producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/opponent_strength_workload.py').read_bytes()).hexdigest(),weekly_reader_code_sha256=hashlib.sha256(Path('backend/app/product_services/weekly_passing_air_efficiency.py').read_bytes()).hexdigest())
full=save(result);selected={k:v for k,v in result.items()if k not in('rows','strength_context_rows','semantic_sha256','provenance')}
selected['rows']=[r for r in result['rows']if r['season']in(2023,2024,2025)and r['team']in{'SF','WAS'}];selected['strength_context_rows']=[r for r in result['strength_context_rows']if r['defense']in{'SF','WAS'}]
selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};slice_ref=save(selected)
receipt=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,context_sources=source_outputs,full_ref=full,selected_ref=slice_ref,
 global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],weekly_input_ref=weekly_ref,source_extract_ref=extract,
 actor_profiles=len(result['rows']),canonical_profiles=sum(r['player_master_id']is not None for r in result['rows']),selected_profiles=len(selected['rows']),selected_scope='SF/WAS historical2023–25, not current2026',
 per_season={season:dict(profiles=sum(r['season']==season for r in result['rows']),defined_strong_minus_weak={ch:sum(r['season']==season and r['channels'][ch]['strong_minus_weak']is not None for r in result['rows'])for ch in('pass_attempts','rush_attempts','targets')},
 unknown_strength_membership=sum(r['unknown_strength_membership']for r in result['rows']if r['season']==season))for season in(2023,2024,2025,2026)},
 source_fetches=0,parent_inflates=0,database_writes=0,models=0,evidence_use=result['evidence_use'],pregame_serving_eligible=False,
 current2026='No historical EPA context loaded for2026; nativeweeklyrows retained with unknown group, not zero or backfilled strength')
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
