from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.opportunity_source_capture import load_event_artifact
from backend.app.product_services.game_clock_pace_catalog import validated_native_order_map
from backend.app.product_services.sourcewide_post_fumble_workload import build_sourcewide_post_fumble,persist_sourcewide_identity_requests,NATIVE
from backend.app.product_services.offensive_line_participation import load_line_alias_evidence
from backend.app.product_services.personnel_package_continuity import physical_membership
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.factual_designation import clock
from backend.app.product_services.market_snapshots import canonical_team
ROOT=Path('research/sourcewide_post_fumble_workload_20261020/v1');started=datetime.now(UTC);tick=time.monotonic()
def sha(b):return hashlib.sha256(b).hexdigest()
def load(ref,kind,cap):
 p=Path(ref['path']).resolve();assert p.parent==Path('artifacts',kind).resolve()and p.name==ref['sha256']+'.json';b=p.read_bytes();assert len(b)==ref['bytes']<=cap and sha(b)==ref['sha256'];return json.loads(b)
def save(x,kind='sourcewide_post_fumble_workload'):
 b=json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(b)<=64*1024*1024;p=Path('artifacts',kind)/(sha(b)+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==b
 else:
  with p.open('xb')as f:f.write(b)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha(b),bytes=len(b))
fref=json.loads(Path('research/fumble_event_components_20261020/v1/actual_receipt.json').read_text())['full_ref'];fumbles=load(fref,'fumble_event_components',16*1024*1024)
fcore={k:fumbles[k]for k in('version','before_period','game_rows','team_recovery_rows','fumble_ledger','event_basis','definitions')};assert digest(fcore)==fumbles['semantic_sha256']
assert fumbles['provenance']['producer_code_sha256']==sha(Path('backend/app/product_services/fumble_event_components.py').read_bytes())
assert clock(fumbles['provenance']['actual_publication_at'])<=started
iref=json.loads(Path('research/coverage_receiver_performance_20261020/v1/actual_receipt.json').read_text())['outputs'][0]['full_ref'];identity=load(iref,'coverage_receiver_performance',64*1024*1024)
assert digest({k:v for k,v in identity.items()if k not in{'semantic_sha256','provenance','evidence_use','pregame_serving_eligible','forecast'}})==identity['semantic_sha256']
for path,h in identity['provenance']['producer_code_hashes'].items():assert sha(Path(path).read_bytes())==h
alias_cutoff=clock(identity['provenance']['actual_alias_cutoff_at']);assert alias_cutoff<=clock(identity['provenance']['actual_publication_at'])<=started
frozen=identity['native_identity_receipts'];alias_rows=[a for proof in frozen.values()for a in proof['original_alias_evidence']]
for a in alias_rows:assert clock(a['created_at'])<=alias_cutoff and clock(a['player_master_created_at'])<=alias_cutoff
ref=json.loads(Path('research/post_fumble_workload_20261020/v1/actual_receipt.json').read_text())['parent_artifact_ref']
# Exactly one original parent decode is needed: no inventoried compact retains the per-event three-channel actor ledger.
with Session(engine)as session:
 parent=load_event_artifact(ref,session.get(SourceSnapshot,ref['source_snapshot_id']),before_period=ref['before_period'],cutoff=ref['decision_cutoff_at'])
events=parent['event_evidence'];order=validated_native_order_map(parent,before_period=ref['before_period'],cutoff=started)
source_sha=ref['source_sha256'];assert fumbles['provenance']['source']['content_sha256']==source_sha
potential={r['native_id']for l in fumbles['fumble_ledger']for r in l['reported_fumblers']if isinstance(r['native_id'],str)and NATIVE.fullmatch(r['native_id'])}
universe=potential|{r['source_player_id']for r in events['players']};new_native=universe-set(frozen)
with engine.connect()as connection:extra_aliases=load_line_alias_evidence(connection,new_native,cutoff=alias_cutoff)
rows=alias_rows+extra_aliases;edges=[(a['source_key'],a['player_master_id'])for a in rows]+[(n,None)for n in universe|set(frozen)]
uncertain=[]
for field in('unscoped_nonoffensive_rows','scoped_administrative_rows'):
 for r in parent.get(field,[]):
  if physical_membership(r)is False:continue
  gid=r['game_id'];pair={canonical_team(t)for t in gid.split('_')[2:]};team=canonical_team(r['posteam'])if r.get('posteam')else None
  assert team is None or team in pair
  uncertain.append(dict(game_id=gid,play_id=str(int(r['play_id'])),possible_teams=sorted({team}if team else pair),possible_channels=['pass_attempts','rush_attempts','targets'],reason='Unscoped/admin original row does not prove absence of a physical offensive opportunity'))
result=build_sourcewide_post_fumble(events,order,fumbles,fumble_source_sha256=source_sha,identity_edges=edges,before_period=ref['before_period'],cutoff=started,uncertain_official_rows=uncertain)
# Reusable small per-event official channel and native order evidence, no raw flags or duplicate full parent cache.
component=dict(version='sourcewide_official_channel_component_v1',before_period=ref['before_period'],source_ref=ref,source_event_sha256=events['sha256'],official_channel_event_basis=result['official_channel_event_basis'],native_order=order,uncertain_official_rows=uncertain,source_player_identity=events['players'])
component['semantic_sha256']=digest(component);component_ref=save(component,'sourcewide_official_channels')
result['provenance']=dict(original_parent_ref=ref,reviewed_fumble_ref=fref,frozen_global_identity_ref=iref,frozen_alias_cutoff_at=alias_cutoff.isoformat(),expanded_native_keys=sorted(new_native),expanded_alias_evidence=extra_aliases,official_channel_component_ref=component_ref,source_lock_at='2026-10-20T00:15:00Z',actual_read_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_sha256=sha(Path('backend/app/product_services/sourcewide_post_fumble_workload.py').read_bytes()),original_availability='Revised historical source, later frozen attachment proof and new postlock feature; not original pregame evidence')
full=save(result)
with engine.begin()as connection:queue=persist_sourcewide_identity_requests(connection,result,artifact_ref=full)
if queue['records']:
 with engine.connect()as connection:
  found=connection.execute(text("SELECT identity_quarantine_id,source_record_key,source_player_key,status,first_seen_at,updated_at FROM target.identity_quarantine WHERE source_schema='public' AND source_table='source_snapshot' AND source_record_key=ANY(CAST(:keys AS text[]))"),dict(keys=[r['source_record_key']for r in queue['records']])).mappings().all()
 assert len(found)==len(queue['records']);queue['durable_readback_records']=[dict(r,first_seen_at=str(r['first_seen_at']),updated_at=str(r['updated_at']))for r in found]
 for r in queue['records']:
  match=next(f for f in found if f['source_record_key']==r['source_record_key']);assert match['source_player_key']==r['source_player_key']and match['identity_quarantine_id']==r['identity_quarantine_id']
selected=dict(result,rows=[r for r in result['rows']if r['team']in{'SF','WAS'}],selection=dict(teams=['SF','WAS'],full_ref=full,global_identity_and_possible_anchor_evidence_retained=True));sel=save(selected)
out=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-tick,full_ref=full,selected_ref=sel,official_component_ref=component_ref,parent_ref=ref,fumble_ref=fref,frozen_identity_ref=iref,original_frozen_keys=len(frozen),expanded_new_keys=len(new_native),extra_alias_rows=len(extra_aliases),actor_game_rows=len(result['rows']),exact_first_anchors=sum(r['exact_first_anchor']for r in result['rows']),canonical_eligible_rows=sum(r['canonical_feature_eligible']for r in result['rows']),special_only_undefined_rows=sum(not r['observed_official_usage']for r in result['rows']),unknown_possible_anchors=len(result['possible_anchor_evidence']),unscoped_possible_usage_rows=len(uncertain),known_share_changes={c:sum(r['metrics'][c]['after_minus_before']is not None for r in result['rows'])for c in('pass_attempts','rush_attempts','targets')},queue=queue,source_fetches=0,parent_decodes=1,alias_mutations=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k not in{'queue','parent_ref'}}))
