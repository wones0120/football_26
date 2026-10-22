"""One bounded same-source cp projection; no original parent decode or DB."""
from pathlib import Path
from datetime import datetime,UTC
import json,csv,hashlib,time,io
from backend.app.product_services.receiver_completion_expectation import build_receiver_completion_expectation,FIELDS
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.factual_designation import clock
from backend.app.product_services.original_drive_field_context import _integer
ROOT=Path('research/receiver_completion_expectation_20261020/v1');started=datetime.now(UTC);timer=time.monotonic()
def sha(b):return hashlib.sha256(b).hexdigest()
def load(ref,kind):
 p=Path(ref['path']).resolve();b=p.read_bytes();assert p.parent==Path('artifacts',kind).resolve() and p.name==ref['sha256']+'.json' and len(b)==ref['bytes']<=64*1024*1024 and sha(b)==ref['sha256'];return json.loads(b)
def save(x,kind='receiver_completion_expectation'):
 b=json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode();p=Path('artifacts',kind)/(sha(b)+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==b
 else:
  with p.open('xb')as f:f.write(b)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha(b),bytes=len(b))
r=json.loads(Path('research/sourcewide_post_fumble_workload_20261020/v1/actual_receipt.json').read_text());official_ref=r['official_component_ref'];official=load(official_ref,'sourcewide_official_channels');assert digest({k:v for k,v in official.items()if k!='semantic_sha256'})==official['semantic_sha256']
assert not official['uncertain_official_rows'] # No source-wide unscoped possible target rows may be silently dropped.
identity_ref=r['full_ref'];identity=load(identity_ref,'sourcewide_post_fumble_workload')
keys=('version','candidate_id','before_period','rows','possible_anchor_evidence','excluded_anchor_evidence','official_channel_event_basis','unknown_order_games','potential_native_fumbler_ids','uncertain_official_rows','identity_qualification','identity_review_requests')
assert digest({k:identity[k]for k in keys})==identity['semantic_sha256']
assert identity['source_event_sha256']==official['source_event_sha256'] and identity['before_period']==official['before_period']
assert identity['provenance']['official_channel_component_ref']==official_ref and clock(identity['provenance']['actual_publication_at'])<=started
# Exact current guarded parent evidence, preserving separately identified original measurement producer.
e=json.loads(Path('research/sourcewide_post_fumble_workload_20261020/v1/EVIDENCE.json').read_text())
for pin in e['pins']:
 b=Path(pin['path']).read_bytes();assert len(b)==pin['bytes']and sha(b)==pin['sha256']
range_receipt=json.loads(Path('research/drive_scoring_range_20261020/v1/actual_receipt.json').read_text());range_ref=range_receipt['full_ref'];range_parent=load(range_ref,'drive_scoring_range');source=range_receipt['source_ref'];assert source==range_parent['provenance']['source_ref']
assert source['sha256']==identity['source_sha256']==official['source_ref']['source_sha256'] and source['snapshot_id']==official['source_ref']['source_snapshot_id']
assert clock(source['captured_at'])<=clock(official['source_ref']['decision_cutoff_at'])<=started and clock(range_parent['provenance']['actual_publication_at'])<=started
raw=Path(source['path']).read_bytes();assert len(raw)==source['bytes']<=64*1024*1024 and sha(raw)==source['sha256']
reader=csv.DictReader(io.StringIO(raw.decode()));assert set(FIELDS)<=set(reader.fieldnames or[]);rows=[]
for rawrow in reader:
 if rawrow['season_type']!='REG' or int(rawrow['season'])*100+int(rawrow['week'])>=official['before_period']:continue
 row={k:rawrow[k]for k in FIELDS};play=_integer(row['play_id']);assert play is not None
 row['play_id']=str(play)
 for f in('qb_spike','complete_pass'):
  value=row[f];row[f]=None if value==''else float(value)
 row['cp']=None if row['cp']==''else row['cp'];row['receiver_player_id']=row['receiver_player_id']or None;rows.append(row)
assert len(rows)==13842
projection=dict(version='receiver_completion_probability_projection_v1',before_period=official['before_period'],source_ref=source,source_event_sha256=official['source_event_sha256'],rows=rows,fields=list(FIELDS),actual_read_at=started.isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_sha256=sha(Path('backend/app/product_services/receiver_completion_expectation.py').read_bytes()));projection_ref=save(projection,'receiver_completion_probability_projection')
x=build_receiver_completion_expectation(official,rows,identity['identity_qualification'])
assert {a['source_player_id']for a in x['actor_game_rows']}<=set(identity['identity_qualification'])
affected=sorted({a['source_player_id']for a in x['actor_game_rows']if a['player_master_id']is None})
assert not affected,('New receiver frozen-attachment evidence required before publishing',affected)
x['provenance']=dict(official_component_ref=official_ref,frozen_global_identity_ref=identity_ref,source_ref=source,approved_range_source_parent_ref=range_ref,projection_ref=projection_ref,original_source_metadata=official['source_ref'],actual_read_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_sha256=sha(Path('backend/app/product_services/receiver_completion_expectation.py').read_bytes()),source_model_definition='https://nflfastr.com/reference/fast_scraper.html cp probability for completion based on comparable game situations; exact vendor model training/version chronology not supplied',original_availability='Original capture and later revised model-probability source observations distinct; no original historical pregame/model-training availability proof')
full=save(x);selected=dict(x,actor_game_rows=[a for a in x['actor_game_rows']if a['team']in{'SF','WAS'}],event_basis=[a for a in x['event_basis']if a['team']in{'SF','WAS'}],unattributed_events=[a for a in x['unattributed_events']if a['team']in{'SF','WAS'}],selection=dict(teams=['SF','WAS'],full_ref=full,global_identity_scope_retained=True));sel=save(selected)
out=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,full_ref=full,selected_ref=sel,projection_ref=projection_ref,official_component_ref=official_ref,frozen_global_identity_ref=identity_ref,source_projection_rows=len(rows),actor_games=len(x['actor_game_rows']),exact_canonical_rates=sum(a['catalog_value']is not None for a in x['actor_game_rows']),exact_native_rates=sum(a['native_exact_excess']is not None for a in x['actor_game_rows']),known_matched_targets=sum(a['known_matched_targets']for a in x['actor_game_rows']),unknown_outcomes=sum(a['unknown_outcomes']for a in x['actor_game_rows']),unattributed_events=len(x['unattributed_events']),affected_identity_native_ids=affected,parent_decodes=0,database_reads=0,alias_queries=0,queue_writes=0,source_fetches=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out),flush=True)
