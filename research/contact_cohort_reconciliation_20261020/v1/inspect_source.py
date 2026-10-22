"""Aggregate-only contact coverage diagnostic; not identity/cohort certification."""
from pathlib import Path
from collections import defaultdict
from datetime import datetime,UTC
import json,hashlib,time,gc,math
import polars as pl
from backend.app.product_services.contact_cohort_reconciliation import official_rush_eligibility
from backend.app.product_services.market_snapshots import canonical_team
from backend.app.product_services.factual_designation import clock
root=Path('research/contact_cohort_reconciliation_20261020/v1');started=datetime.now(UTC);start=time.monotonic()
r=json.loads(Path('research/pfr_advanced_features_20261020/v1/actual_receipt.json').read_text());ref=r['artifact_ref'];assert ref['bytes']<=32*1024*1024;p=Path(ref['path']);raw=p.read_bytes()
assert p.resolve().parent==Path('artifacts/pfr_advanced_features').resolve()and len(raw)==ref['bytes']and hashlib.sha256(raw).hexdigest()==ref['sha256']
f=json.loads(raw);del raw
assert clock(f['actual_derived_at'])<=started and f['producer_code_sha256']==hashlib.sha256(Path('backend/app/product_services/pfr_advanced_features.py').read_bytes()).hexdigest()
pfr=defaultdict(list)
for a in f['features']['actor_game_rows']:
 if int(a['game_id'][:4])not in(2023,2024,2025)or'G07-M07'not in a['metrics']:continue
 b=a['metrics']['G07-M07'];c=a['metrics']['G07-M08'];assert b['carry_exposure']==c['carry_exposure']
 pfr[(a['game_id'],a['team'])].append(dict(native=a['pfr_player_id'],canonical=a['player_master_id'],carries=b['carry_exposure'],before=b['value'],after=c['value']))
descriptors=json.loads(Path('research/player_opportunity_history_20261020/v1/source_coverage.json').read_text());assert {r['season']for r in descriptors}=={2023,2024,2025};outputs=[]
for item in descriptors:
 year=item['season'];d=item['descriptor'];assert d['manifest']['bytes']<=64*1024*1024;p=Path(d['path']);raw=p.read_bytes();assert len(raw)==d['manifest']['bytes']and hashlib.sha256(raw).hexdigest()==d['manifest']['sha256']and clock(d['manifest']['received_at'])<=started;del raw
 required={'game_id','play_id','season','week','season_type','posteam','defteam','play_type','play_type_nfl','rush_attempt','pass_attempt','sack','qb_scramble','qb_spike','qb_kneel','two_point_attempt','fumble','rusher_player_id','rushing_yards'}
 names=pl.read_parquet_schema(p);assert required<=set(names)
 frame=pl.read_parquet(p,columns=sorted(required|({'no_play','quarter_end','desc','lateral_rusher_player_id','lateral_rushing_yards','lateral_rush'}&set(names))))
 assert frame.height<=100000
 teams={};seen=set()
 for row in frame.iter_rows(named=True):
  if row['season_type']!='REG':continue
  gid=row['game_id'];play=str(int(row['play_id']));key=(gid,play);assert key not in seen;seen.add(key)
  assert int(row['season'])==year and gid.split('_')[:2]==[str(year),f"{int(row['week']):02d}"]
  pair={canonical_team(t)for t in gid.split('_')[2:]}
  for t in pair:teams.setdefault((gid,t),dict(known_rushes=0,unknown_rush_membership=0,missing_rusher=0,known_rushing_yards=0.,unknown_rushing_yards=0,lateral_rusher_events=0,native_rushers=set()))
  eligible=official_rush_eligibility(row)
  if eligible is False:continue
  off=canonical_team(row['posteam'])if row.get('posteam')else None
  if off is not None:assert off in pair
  for t in {off}if off else pair:
   c=teams[(gid,t)]
   if eligible is None or off is None:c['unknown_rush_membership']+=1;continue
   c['known_rushes']+=1
   if row.get('rusher_player_id'):c['native_rushers'].add(row['rusher_player_id'])
   else:c['missing_rusher']+=1
   y=row.get('rushing_yards')
   if y is None or not math.isfinite(float(y)):c['unknown_rushing_yards']+=1
   else:c['known_rushing_yards']+=float(y)
   if row.get('lateral_rusher_player_id'):c['lateral_rusher_events']+=1
 rows=[]
 for(gid,team),c in sorted(teams.items()):
  members=pfr.get((gid,team),[]);known=bool(members)and all(a['carries']is not None for a in members);n=sum(a['carries']for a in members)if known else None
  components=bool(members)and all(a['before']is not None and a['after']is not None for a in members)
  source_sum=sum(a['before']+a['after']for a in members)if components else None
  equal=n is not None and not c['unknown_rush_membership']and n==c['known_rushes']
  partition=source_sum is not None and not(c['unknown_rush_membership']or c['unknown_rushing_yards']or c['lateral_rusher_events'])and abs(source_sum-c['known_rushing_yards'])<1e-9
  rows.append(dict(game_id=gid,offense=team,**{k:v for k,v in c.items()if k!='native_rushers'},native_rushers=len(c['native_rushers']),PFR_actors=len(members),PFR_unmapped_actors=sum(a['canonical']is None for a in members),
   PFR_source_carries=n,PFR_components_known=components,PFR_before_plus_after_source_sum=source_sum,aggregate_carry_match=equal,aggregate_initial_rushing_yard_partition_match=partition,
   native_actor_cohort_certified=False))
 output=dict(season=year,original_PBP_descriptor=d,game_sides=len(rows),aggregate_carry_matches=sum(r['aggregate_carry_match']for r in rows),all_source_contact_components_known=sum(r['PFR_components_known']for r in rows),
  aggregate_carry_and_yard_partition_matches=sum(r['aggregate_carry_match']and r['aggregate_initial_rushing_yard_partition_match']for r in rows),
  unknown_rush_events=sum(r['unknown_rush_membership']for r in rows),missing_native_rushers=sum(r['missing_rusher']for r in rows),lateral_rusher_events=sum(r['lateral_rusher_events']for r in rows),game_rows=rows)
 outputs.append(output);del frame;gc.collect()
report=dict(actual_read_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,PFR_parent_ref=ref,outputs=outputs,
 definition='Diagnostic only: aggregate carry/yard agreement does not certify per-native-actor universe or identity; no G15 catalog completion',
 producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),source_fetches=0,parent_inflates=0,alias_reads=0,database_writes=0,models=0,pregame_serving_eligible=False)
(root/'source_inspection.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items()if k!='outputs'}),flush=True)
for o in outputs:print(json.dumps({k:v for k,v in o.items()if k!='game_rows'}),flush=True)
