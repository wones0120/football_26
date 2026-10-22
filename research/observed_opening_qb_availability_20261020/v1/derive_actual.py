"""New measured opening-QB binding from approved immutable parents only."""
from pathlib import Path
from datetime import datetime,UTC
from collections import Counter
import json,hashlib,csv,time,gc
from backend.app.product_services.observed_opening_qb_availability import build_observed_opening_qb_availability,load_reviewed_first_snap_component
from backend.app.product_services.participation_position_components import load_position_component
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.factual_designation import clock
from backend.app.product_services.market_snapshots import canonical_team
ROOT=Path('research/observed_opening_qb_availability_20261020/v1');started=datetime.now(UTC);timer=time.monotonic()
def sha(b):return hashlib.sha256(b).hexdigest()
def read(ref,kind):
 p=Path(ref['path']).resolve();assert p.parent==Path('artifacts',kind).resolve() and p.name==ref['sha256']+'.json'
 b=p.read_bytes();assert len(b)==ref['bytes']<=96*1024*1024 and sha(b)==ref['sha256'];return json.loads(b)
def receipt(path):
 p=Path(path);b=p.read_bytes();return json.loads(b),dict(path=str(p.resolve()),sha256=sha(b),bytes=len(b))
def save(x):
 b=json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode();p=Path('artifacts/observed_opening_qb_availability')/(sha(b)+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==b
 else:
  with p.open('xb') as f:f.write(b)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha(b),bytes=len(b))
venue,_=receipt('research/scheduled_venue_displacement_20261020/v1/actual_receipt.json');venue_ref=venue['full_ref'];v=read(venue_ref,'scheduled_venue_displacement');schedule_ref=v['provenance']['schedule_csv_ref'];b=Path(schedule_ref['path']).read_bytes();assert len(b)==schedule_ref['bytes'] and sha(b)==schedule_ref['sha256']
games=[]
for r in csv.DictReader(b.decode().splitlines()):
 if r['season'] in {'2023','2024','2025'} and r['game_type']=='REG':
  games.append(dict(game_id=r['game_id'],season=int(r['season']),week=int(r['week']),game_type=r['game_type'],game_date=r['gameday'],home_team=canonical_team(r['home_team']),away_team=canonical_team(r['away_team']),home_qb_id=r['home_qb_id'],away_qb_id=r['away_qb_id']))
assert Counter(g['season']for g in games)=={2023:272,2024:272,2025:272}
g16,_=receipt('research/coverage_receiver_performance_20261020/v1/actual_receipt.json');identity_ref=g16['outputs'][0]['full_ref'];identity=read(identity_ref,'coverage_receiver_performance')
core={k:v for k,v in identity.items()if k not in {'semantic_sha256','provenance','evidence_use','pregame_serving_eligible','forecast'}};assert digest(core)==identity['semantic_sha256']
assert identity['pregame_serving_eligible']is False and identity['catalog_id']=='G16-M10'
for filename,expected in identity['provenance']['producer_code_hashes'].items():assert sha(Path(filename).read_bytes())==expected
cutoff=clock(identity['provenance']['actual_alias_cutoff_at']);assert cutoff<=clock(identity['provenance']['actual_publication_at'])<=started
identities=identity['native_identity_receipts'];assert len(identities)==2570
for native,proof in identities.items():
 for e in proof['original_alias_evidence']:
  assert e['source_system']=='nflreadpy'and e['source_key']==native and clock(e['created_at'])<=cutoff and clock(e['player_master_created_at'])<=cutoff
centers,_=receipt('research/center_sack_response_20261020/v1/actual_receipt.json');positions,_=receipt('research/participation_position_components_20261020/v1/actual_receipt.json')
center_refs={r['season']:r['center_ref']for r in centers['source_inputs']};position_refs={r['season']:r['full_ref']for r in positions['outputs']};assert set(center_refs)==set(position_refs)=={2023,2024,2025}
components=[];matched=[];source_inputs=[]
for year in (2023,2024,2025):
 read_at=datetime.now(UTC);c=load_reviewed_first_snap_component(center_refs[year],cutoff=read_at);p=load_position_component(position_refs[year],cutoff=read_at)
 assert c['season']==p['season']==year
 wanted={(u['game_id'],str(u['proof'].get('first_physical_play_id')))for u in c['units']}
 rows=[r for r in p['rows']if (r['game_id'],r['play_id'])in wanted];matched.extend(rows);components.append(c)
 source_inputs.append(dict(season=year,center_ref=center_refs[year],position_ref=position_refs[year],matched_native_rows=len(rows),position_semantic_sha256=p['semantic_sha256'],first_snap_semantic_sha256=c['semantic_sha256'],actual_read_at=read_at.isoformat()))
 del p;gc.collect()
x=build_observed_opening_qb_availability(components,games,identities,matched)
# Source-qualified missing frozen identities must already have explicit inherited durable evidence.
packages,queue_ref=receipt('research/personnel_package_continuity_20261020/v1/actual_receipt.json');assert packages['frozen_identity_ref']==identity_ref
q=packages['queue'];records={r['source_player_key']:r for r in q['records']};readbacks={r['source_player_key']:r for r in q['durable_readback_records']}
assert set(x['affected_identity_native_ids'])<=set(records)&set(readbacks)
for native in x['affected_identity_native_ids']:
 assert records[native]['source_record_key']==readbacks[native]['source_record_key'] and records[native]['intended_identity_quarantine_id']==readbacks[native]['identity_quarantine_id']
queue=dict(inherited_receipt_ref=queue_ref,records=[records[n]for n in x['affected_identity_native_ids']],original_durable_readbacks=[readbacks[n]for n in x['affected_identity_native_ids']],original_readback_at=q['actual_readback_at'],current_database_replay=False,new_cases=0,case_updates=0)
x['provenance']=dict(source_inputs=source_inputs,schedule_ref=schedule_ref,reviewed_schedule_parent_ref=venue_ref,frozen_identity_ref=identity_ref,frozen_identity_cutoff_at=cutoff.isoformat(),inherited_identity_evidence=queue,producer_code_sha256=sha(Path('backend/app/product_services/observed_opening_qb_availability.py').read_bytes()),actual_read_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),historical_availability='Revised postseason positions/PBP/schedule; original pregame availability unknown. Source participation proof is same measured game, not future status.')
full=save(x);selected=dict(x,game_rows=[r for r in x['game_rows']if r['team']in {'SF','WAS'}],profiles=[r for r in x['profiles']if r['team']in {'SF','WAS'}],selection=dict(teams=['SF','WAS'],full_ref=full,global_identity_evidence_retained=True));selected_ref=save(selected)
coverage=[]
for year in (2023,2024,2025):
 rs=[r for r in x['game_rows']if r['season']==year];coverage.append(dict(season=year,scheduled_team_games=len(rs),native_proven_opening=sum(r['native_observed_opening_presence']is True for r in rs),canonical_proven_opening=sum(r['observed_opening_available']is True for r in rs),unknown_reasons=dict(Counter(reason for r in rs for reason in r['unknown_reasons']))))
out=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,full_ref=full,selected_ref=selected_ref,semantic_sha256=x['semantic_sha256'],coverage=coverage,source_inputs=source_inputs,affected_identity_native_ids=x['affected_identity_native_ids'],inherited_identity_evidence=queue,raw_participation_reads=0,raw_PBP_reads=0,source_adapter_replays=0,database_reads=0,queue_writes=0,alias_queries=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out),flush=True)
