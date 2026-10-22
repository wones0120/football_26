"""Serial shared-position cache + minimal PBP transform, frozen canonical evidence."""
from pathlib import Path
from datetime import datetime,UTC
from collections import Counter
import csv,json,hashlib,time,gc
from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.participation_position_components import load_position_component
from backend.app.product_services.personnel_package_continuity import build_personnel_package_continuity,load_package_physical_source,persist_package_identity_requests,PHYSICAL_VERSION
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.factual_designation import clock
from backend.app.product_services.market_snapshots import canonical_team
ROOT=Path('research/personnel_package_continuity_20261020/v1');start=time.monotonic();started=datetime.now(UTC);outputs=[];blocks=[];source_inputs=[]
def sha(b):return hashlib.sha256(b).hexdigest()
def load(ref,kind,max_bytes=96*1024*1024):
 p=Path(ref['path']).resolve();assert p.parent==Path('artifacts',kind).resolve() and p.name==ref['sha256']+'.json'
 b=p.read_bytes();assert len(b)==ref['bytes']<=max_bytes and sha(b)==ref['sha256'];return json.loads(b)
def save(value,kind='personnel_package_continuity'):
 b=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(b)<=96*1024*1024
 p=Path('artifacts',kind)/(sha(b)+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==b
 else:
  with p.open('xb') as f:f.write(b)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha(b),bytes=len(b))
# SHA-reuse the reviewed schedule/registry parent; no schedule adapter or database replay.
venue_ref=json.loads(Path('research/scheduled_venue_displacement_20261020/v1/actual_receipt.json').read_text())['full_ref'];venue=load(venue_ref,'scheduled_venue_displacement')
schedule_ref=venue['provenance']['schedule_csv_ref'];raw=Path(schedule_ref['path']).read_bytes();assert len(raw)==schedule_ref['bytes'] and sha(raw)==schedule_ref['sha256']
raw_schedule=list(csv.DictReader(raw.decode().splitlines()));assert len(raw_schedule)<=50000
schedule=[]
for row in raw_schedule:
 if row['season'] not in {'2023','2024','2025'} or row['game_type']!='REG':continue
 schedule.append(dict(game_id=row['game_id'],season=int(row['season']),week=int(row['week']),game_type='REG',
  game_date=row['gameday'],home_team=canonical_team(row['home_team']),away_team=canonical_team(row['away_team'])))
assert Counter(g['season'] for g in schedule)=={2023:272,2024:272,2025:272}
for year in (2023,2024,2025):
 counts=Counter(t for g in schedule if g['season']==year for t in (g['home_team'],g['away_team']));assert len(counts)==32 and set(counts.values())=={17}
# Frozen identity proof already reviewed over global native universe; no current alias assertion/read.
g16=json.loads(Path('research/coverage_receiver_performance_20261020/v1/actual_receipt.json').read_text());identity_ref=g16['outputs'][0]['full_ref'];identity=load(identity_ref,'coverage_receiver_performance')
assert identity['pregame_serving_eligible'] is False and identity['catalog_id']=='G16-M10'
core={k:v for k,v in identity.items() if k not in {'semantic_sha256','provenance','evidence_use','pregame_serving_eligible','forecast'}};assert digest(core)==identity['semantic_sha256']
assert clock(identity['provenance']['actual_alias_cutoff_at'])<=clock(identity['provenance']['actual_publication_at'])<=started
for filename,expected in identity['provenance']['producer_code_hashes'].items():assert sha(Path(filename).read_bytes())==expected
identities=identity['native_identity_receipts'];assert len(identities)==2570
# Validate original eligible alias/master clocks from the frozen proof; do not refresh alias truth.
alias_cutoff=clock(identity['provenance']['actual_alias_cutoff_at'])
for native,proof in identities.items():
 for evidence in proof['original_alias_evidence']:
  assert evidence['source_system']=='nflreadpy' and evidence['source_key']==native
  assert clock(evidence['created_at'])<=alias_cutoff and clock(evidence['player_master_created_at'])<=alias_cutoff
position_receipt=json.loads(Path('research/participation_position_components_20261020/v1/actual_receipt.json').read_text())
history={r['season']:r['descriptor'] for r in json.loads(Path('research/player_opportunity_history_20261020/v1/source_coverage.json').read_text())}
assert {o['season'] for o in position_receipt['outputs']}=={2023,2024,2025}
for entry in sorted(position_receipt['outputs'],key=lambda x:x['season']):
 read=datetime.now(UTC);season=entry['season'];part=load_position_component(entry['full_ref'],cutoff=read)
 assert part['semantic_sha256']==entry['semantic_sha256'] and part['season']==season
 pbp,physical_proof=load_package_physical_source(history[season],season=season,cutoff=read)
 physical_core=dict(version=PHYSICAL_VERSION,season=season,source_rows=len(pbp),rows=pbp,field_availability=physical_proof['field_availability'],source_sha256=physical_proof['source_sha256'],pregame_serving_eligible=False)
 physical_component=dict(**physical_core,semantic_sha256=digest(physical_core),provenance=dict(physical_proof,producer_code_sha256=sha(Path('backend/app/product_services/personnel_package_continuity.py').read_bytes()),actual_publication_at=datetime.now(UTC).isoformat()))
 physical_ref=save(physical_component,'package_physical_flags')
 block=build_personnel_package_continuity(part,pbp,schedule,identities,before_period=season*100+19)
 block['provenance']=dict(shared_position_ref=entry['full_ref'],shared_position_semantic_sha256=part['semantic_sha256'],shared_position_source_provenance=part['provenance'],
  physical_source=physical_proof,physical_component_ref=physical_ref,schedule_ref=schedule_ref,reviewed_schedule_parent_ref=venue_ref,frozen_identity_ref=identity_ref,
  frozen_identity_cutoff_at=alias_cutoff.isoformat(),frozen_identity_universe=len(identities),
  producer_code_sha256=sha(Path('backend/app/product_services/personnel_package_continuity.py').read_bytes()),
  actual_read_at=read.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),
  original_historical_availability='FTN postseason positions and revised historical PBP; no original-pregame or current2026 proof')
 full=save(block)
 selected=dict(block,game_rows=[r for r in block['game_rows'] if r['team'] in {'SF','WAS'}],continuity_rows=[r for r in block['continuity_rows'] if r['team'] in {'SF','WAS'}],
  profiles=[r for r in block['profiles'] if r['team'] in {'SF','WAS'}],
  event_basis=[r for r in block['event_basis'] if r['team'] in {'SF','WAS'} or r['team'] is None],
  selection=dict(teams=['SF','WAS'],full_ref=full,all_global_unit_and_identity_incidents_retained=True))
 sel=save(selected)
 output=dict(season=season,full_ref=full,selected_ref=sel,semantic_sha256=block['semantic_sha256'],expected_team_games=len(block['game_rows']),
  known_physical_snaps=sum(g['known_physical_snaps'] for g in block['game_rows']),unknown_physical_or_side=sum(g['unknown_physical_or_side'] for g in block['game_rows']),
  source_unit_unknown_snaps=sum(g['unknown_units'] for g in block['game_rows']),identity_unknown_snaps=sum(g['identity_unknown_snaps'] for g in block['game_rows']),
  native_units=len(block['unit_registry']),first_games_not_applicable=sum(r['first_game_not_applicable'] for r in block['continuity_rows']),
  exact_canonical_game_comparisons=sum(r['catalog_value'] is not None for r in block['continuity_rows']),
  exact_native_game_comparisons=sum(r['native_variant'] is not None and r['native_variant']['value'] is not None for r in block['continuity_rows']),
  exact_canonical_profiles=sum(p['canonical']['value'] is not None for p in block['profiles']),
  affected_identity_native_ids=block['identity_request_native_ids'],global_identity_withheld_native_ids=block['global_identity_withheld_native_ids'])
 outputs.append(output);blocks.append(block);source_inputs.append(dict(season=season,position_ref=entry['full_ref'],physical_source=physical_proof,physical_component_ref=physical_ref))
 print(json.dumps(dict(stage='season_END',**output)),flush=True);del part,pbp,physical_component,physical_core,selected;gc.collect()
# Append-only frozen-attachment incidents; no alias/master/resolved-row changes.
with engine.begin() as connection:queue=persist_package_identity_requests(connection,blocks,source_refs=[o['full_ref'] for o in outputs])
if queue['records']:
 keys=[r['source_record_key'] for r in queue['records']]
 with engine.connect() as connection:
  found=connection.execute(text("SELECT identity_quarantine_id,source_table,source_record_key,source_player_key,status,first_seen_at,updated_at FROM target.identity_quarantine WHERE source_schema='public' AND source_system='nflreadpy' AND source_table='source_snapshot' AND source_record_key=ANY(CAST(:keys AS text[]))"),dict(keys=keys)).mappings().all()
 lookup={r['source_record_key']:r for r in found};assert len(lookup)==len(keys)
 assert all(lookup[r['source_record_key']]['source_player_key']==r['source_player_key'] for r in queue['records'])
 queue['durable_readback_records']=[dict(r,first_seen_at=str(r['first_seen_at']),updated_at=str(r['updated_at'])) for r in found]
 queue['actual_readback_at']=datetime.now(UTC).isoformat()
receipt=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,
 outputs=outputs,source_inputs=source_inputs,frozen_identity_ref=identity_ref,queue=queue,
 exact_canonical_game_comparisons=sum(o['exact_canonical_game_comparisons'] for o in outputs),
 source_fetches=0,new_captures=0,raw_participation_reads=0,participation_adapter_replays=0,alias_queries=0,alias_mutations=0,parent_inflations=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(dict(stage='END',elapsed_seconds=receipt['elapsed_seconds'],exact_canonical_games=receipt['exact_canonical_game_comparisons'],identity_requests=queue['requests'])),flush=True)
