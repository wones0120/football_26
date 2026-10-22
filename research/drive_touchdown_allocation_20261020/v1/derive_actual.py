"""One bounded native-drive-link CSV projection plus approved compact transforms."""
from pathlib import Path
from datetime import datetime,UTC
from copy import deepcopy
import csv,io,json,hashlib,time,os
from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.drive_touchdown_allocation import build_drive_touchdown_allocation,project_original_drive_links,PAIRS
from backend.app.product_services.drive_scoring_range import load_reviewed_range_component
from backend.app.product_services.qb_teammate_rushing_td_source import read_managed_parent
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.factual_designation import clock

root=Path('research/drive_touchdown_allocation_20261020/v1');started=datetime.now(UTC);timer=time.monotonic()
def timing(stage):
    e=dict(package='drive_touchdown_allocation_v1',agent='B',stage=stage,timestamp=datetime.now(UTC).isoformat(),evidence=str(root/'actual_receipt.json'))
    fd=os.open('research/feature_platform_implementation_20261019/v1/PACKAGE_TIMINGS.jsonl',os.O_WRONLY|os.O_APPEND)
    try:os.write(fd,(json.dumps(e)+'\n').encode())
    finally:os.close(fd)
def actual(folder,name='actual_receipt.json'):return json.loads((Path('research')/(folder+'_20261020')/'v1'/name).read_text())
def approved(candidate,folder):
    rows=list(csv.DictReader(Path('research/feature_platform_implementation_20261019/v1/FEATURE_ONLY_REGISTER.csv').open()));r=next(r for r in rows if r['candidate_id']==candidate);assert r['feature_only_status']=='verifiedfull'
    p=Path('research')/(folder+'_20261020')/'v1';e=json.loads((p/'EVIDENCE.json').read_text())
    for pin in e['pins']:
        if '/artifacts/'in pin['path']:continue
        b=Path(pin['path']).read_bytes();assert len(b)==pin['bytes']and hashlib.sha256(b).hexdigest()==pin['sha256']
def load(ref,folder,cap=32*1024*1024):
    p=Path(ref['path']);assert p.resolve().parent==Path('artifacts',folder).resolve()and p.name==ref['sha256']+'.json'and 0<ref['bytes']<=cap
    b=p.read_bytes();assert len(b)==ref['bytes']and hashlib.sha256(b).hexdigest()==ref['sha256'];return json.loads(b)
def save(value,folder='drive_touchdown_allocation'):
    b=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False,default=str).encode();assert len(b)<=32*1024*1024
    sha=hashlib.sha256(b).hexdigest();p=Path('artifacts',folder)/(sha+'.json');p.parent.mkdir(exist_ok=True)
    if p.exists():assert p.read_bytes()==b
    else:
        with p.open('xb')as f:f.write(b)
        p.chmod(0o444)
    return dict(path=str(p.resolve()),sha256=sha,bytes=len(b))
timing('source_start')
for candidate,folder in(('G23-M05','drive_scoring_range'),('G22-M10','sourcewide_post_fumble_workload'),('G24-M01','shared_scoring_pair_covariance')):approved(candidate,folder)
range_receipt=actual('drive_scoring_range');terminal=load(range_receipt['full_ref'],'drive_scoring_range');prov=terminal['provenance']
assert prov['producer_code_sha256']==hashlib.sha256(Path('backend/app/product_services/drive_scoring_range.py').read_bytes()).hexdigest()
assert clock(prov['actual_publication_at'])<=started
assert digest({k:terminal[k]for k in('version','candidate_id','before_period','nominal_range_yards','game_rows','definition')})==terminal['semantic_sha256']
original_ref=range_receipt['input_refs']['original_drive_field_context'];original=load_reviewed_range_component(original_ref,'original_drive_field_context',cutoff=started)
official_receipt=actual('sourcewide_post_fumble_workload');official_ref=official_receipt['official_component_ref'];official=load(official_ref,'sourcewide_official_channels')
assert digest({k:v for k,v in official.items()if k!='semantic_sha256'})==official['semantic_sha256']
assert clock(official_receipt['actual_completed_at'])<=started
pair_receipt=actual('shared_scoring_pair_covariance');pair=read_managed_parent(pair_receipt['full_ref'],'artifacts/shared_scoring_pair_covariance',cutoff=started)
scoring_ref=actual('scoring_share_components','actual_derivation_receipt.json')['full_ref'];scoring=read_managed_parent(scoring_ref,'artifacts/scoring_share_components',cutoff=started)
assert pair['provenance']['scoring_ref']==scoring_ref
assert original['source_event_sha256']==official['source_event_sha256']==scoring['provenance']['event_receipt_sha256']
source=prov['source_ref'];order=official['native_order']
assert(source['snapshot_id'],source['sha256'])==(order['source_snapshot_id'],order['source_byte_sha256'])
assert source['sha256']==official['source_ref']['source_sha256']and source['snapshot_id']==official['source_ref']['source_snapshot_id']
assert clock(source['observed_at'])<=clock(source['captured_at'])<=clock(official['source_ref']['decision_cutoff_at'])<=started
assert 0<source['bytes']<=64*1024*1024
checkpoint=root/'source_stage_checkpoint.json'
if checkpoint.exists():
    import ast
    saved=json.loads(checkpoint.read_text());link_ref=saved['link_ref'];projection=load(link_ref,'original_drive_native_links')
    producer=Path(saved['original_projection_producer']);assert hashlib.sha256(producer.read_bytes()).hexdigest()==projection['producer_sha256']
    def function_body(path):
        module=ast.parse(Path(path).read_text());return ast.dump(next(n for n in module.body if isinstance(n,ast.FunctionDef)and n.name=='project_original_drive_links'),include_attributes=False)
    assert function_body(producer)==function_body('backend/app/product_services/drive_touchdown_allocation.py')
    assert projection['source_ref']==source and projection['native_order_semantic_sha256']==order['semantic_sha256']and projection['before_period']==original['before_period']
    assert clock(projection['actual_publication_at'])<=started
    links=projection['rows'];raw_projections=0
else:
    raw=Path(source['path']).read_bytes();assert len(raw)==source['bytes']and hashlib.sha256(raw).hexdigest()==source['sha256']
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8')));fields={'game_id','play_id','season','week','season_type','posteam','drive','order_sequence'};assert fields<=set(reader.fieldnames or [])
    links=project_original_drive_links(({k:r[k]for k in fields}for r in reader),order,before_period=original['before_period'])
    del raw
    projection=dict(version='original_drive_native_links_v1',before_period=original['before_period'],source_ref=source,native_order_semantic_sha256=order['semantic_sha256'],rows=links,actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_sha256=hashlib.sha256(Path('backend/app/product_services/drive_touchdown_allocation.py').read_bytes()).hexdigest());link_ref=save(projection,'original_drive_native_links');raw_projections=1
result=build_drive_touchdown_allocation(original,terminal,official,scoring,links,pair['provenance']['source_actor_rows'])
unresolved={r['native_GSIS']for r in result['actor_profiles']if not r['identity']['canonical_qualified']}
inherited=pair_receipt['queue']['records'];covered={r['source_player_key']for r in inherited}
assert unresolved<=covered,('Preserve checkpoint and create evidence-specific native identity requests before publication',sorted(unresolved-covered))
records=[r for r in inherited if r['source_player_key']in unresolved];readback=[]
if records:
    ids=[r['identity_quarantine_id']for r in records]
    with engine.connect()as connection:
        current=list(connection.execute(text('SELECT identity_quarantine_id,source_table,source_record_key,source_player_key,status,first_seen_at,updated_at FROM target.identity_quarantine WHERE identity_quarantine_id=ANY(CAST(:ids AS text[]))'),dict(ids=ids)).mappings())
    byid={r['identity_quarantine_id']:dict(r)for r in current};assert set(byid)==set(ids)
    for prior in records:
        current=byid[prior['identity_quarantine_id']]
        for k in('identity_quarantine_id','source_table','source_record_key','source_player_key','status'):assert str(current[k])==str(prior[k])
        for k in('first_seen_at','updated_at'):assert clock(current[k])==clock(prior[k])
        readback.append(current)
result['provenance']=dict(original_drive_ref=original_ref,typed_terminal_ref=range_receipt['full_ref'],official_channel_ref=official_ref,scoring_ref=scoring_ref,frozen_actor_identity_ref=pair_receipt['full_ref'],original_drive_link_ref=link_ref,source_ref=source,actual_read_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),inherited_identity_UI_cases=readback,producer_code_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in[Path('backend/app/product_services')/(n+'.py')for n in('drive_touchdown_allocation','drive_scoring_range','original_drive_field_context','scoring_share_components')]},original_source_availability='Later revised capture, original historical pregame availability/fullgame completeness unknown; observed actor cohort not all-onfield census')
full=save(result);selected=deepcopy(result)
for field in('drive_rows','actor_profiles','unbound_official_source_events','unbound_physical_TD_events','unknown_actor_residual','excluded_known_nonopportunity_nonTD_original_groups'):selected[field]=[r for r in result[field]if r['team']in{'SF','WAS'}]
selected['selection']='SF/WAS rows, full global identity scope retained';selected['provenance']['full_ref']=full;selected['selected_semantic_sha256']=digest({k:v for k,v in selected.items()if k!='provenance'});sel=save(selected)
coverage={channel:sum(any(c[channel]is not None for c in p['across_starting_field_bin_comparisons'].values())for p in result['actor_profiles'])for channel in PAIRS}
out=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,full_ref=full,selected_ref=sel,original_drive_link_ref=link_ref,global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],original_drives=len(result['drive_rows']),known_outcomes={v:sum(d['outcome']==v for d in result['drive_rows'])for v in('pass','rush','neither',None)},source_physical_TDs=sum(len(d['known_physical_TD_events'])for d in result['drive_rows']),unbound_physical_TDs=len(result['unbound_physical_TD_events']),native_actor_profiles=len(result['actor_profiles']),canonical_actor_profiles=sum(p['identity']['canonical_qualified']for p in result['actor_profiles']),exact_across_bin_actor_comparisons=coverage,selected_actor_profiles=len(selected['actor_profiles']),withheld_native_keys=sorted(unresolved),inherited_UI_case_readback=readback,new_identity_cases=0,alias_queries=0,source_fetches=0,source_adapter_replays=0,parent_inflates=0,raw_CSV_projections=raw_projections,total_raw_CSV_projections_including_prior_attempt=1,excluded_nonopportunity_original_groups=len(result['excluded_known_nonopportunity_nonTD_original_groups']),models=0,database_writes=0,pregame_serving_eligible=False)
(root/'actual_receipt.json').write_text(json.dumps(out,indent=2,default=str)+'\n');timing('source_end');print(json.dumps(out,indent=2,default=str))
