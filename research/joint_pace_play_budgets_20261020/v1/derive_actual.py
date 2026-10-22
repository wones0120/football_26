"""New transformation of three immutable reviewed managed caches, no raw readers."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time,os
from copy import deepcopy
from backend.app.product_services.joint_pace_play_budgets import build_joint_pace_play_budgets
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.factual_designation import clock

root=Path('research/joint_pace_play_budgets_20261020/v1');started=datetime.now(UTC);timer=time.monotonic()
def timing(stage):
    value=dict(package='joint_pace_play_budgets_v1',agent='B',stage=stage,timestamp=datetime.now(UTC).isoformat(),evidence=str(root/'actual_receipt.json'))
    fd=os.open('research/feature_platform_implementation_20261019/v1/PACKAGE_TIMINGS.jsonl',os.O_WRONLY|os.O_APPEND)
    try:os.write(fd,(json.dumps(value)+'\n').encode())
    finally:os.close(fd)
def load(ref,directory,cap):
    p=Path(ref['path']);assert p.resolve().parent==Path(directory).resolve()and 0<ref['bytes']<=cap
    raw=p.read_bytes();assert len(raw)==ref['bytes']and hashlib.sha256(raw).hexdigest()==ref['sha256']
    return json.loads(raw)
def receipt(directory):
    directory=Path(directory);r=json.loads((directory/'receipt.json').read_text());assert r.get('review_status',r.get('status'))=='High_FINAL_PASS_feature_only'
    for pin in r['pins']:
        if '/artifacts/'in pin['path']:continue
        raw=Path(pin['path']).read_bytes();assert len(raw)==pin['bytes']and hashlib.sha256(raw).hexdigest()==pin['sha256']
    actual=json.loads((directory/'actual_receipt.json').read_text());assert clock(actual['actual_completed_at'])<=started
    return actual
def save(value):
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024
    sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/joint_pace_play_budgets')/(sha+'.json');p.parent.mkdir(exist_ok=True)
    if p.exists():assert p.read_bytes()==raw
    else:
        with p.open('xb')as f:f.write(raw)
        p.chmod(0o444)
    return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
timing('source_start')
pace_receipt=receipt('research/game_clock_pace_catalog_20261020/v1');pair_receipt=receipt('research/shared_game_covariance_20261020/v1')
pace=load(pace_receipt['full_ref'],'artifacts/game_clock_pace_catalog',4*1024*1024);pairs=load(pair_receipt['full_ref'],'artifacts/shared_game_covariance',4*1024*1024)
schedule_receipt=json.loads(Path('research/schedule_context_features_20261020/v1/actual_receipt.json').read_text());schedule=load(schedule_receipt['artifact_ref'],'artifacts/schedule_context_features',16*1024*1024)
assert schedule['version']=='native_schedule_context_features_v1'and schedule['pregame_serving_eligible']is False
assert schedule['producer_code_sha256']==hashlib.sha256(Path('backend/app/product_services/schedule_context_features.py').read_bytes()).hexdigest()
assert schedule['semantic_sha256']==schedule_receipt['semantic_sha256']and len(schedule['game_rows'])==schedule_receipt['source_rows']
assert schedule['provenance']['snapshot_id']==schedule_receipt['source_snapshot_id']and schedule['provenance']['sha256']==schedule_receipt['source_sha256']
assert clock(schedule['provenance']['observed_at'])<=clock(schedule['provenance']['captured_at'])<=clock(schedule['actual_derived_at'])<=clock(schedule_receipt['actual_completed_at'])<=started
result=build_joint_pace_play_budgets(pace,pairs,schedule['game_rows'])
result['provenance']=dict(pace_ref=pace_receipt['full_ref'],paired_physical_play_ref=pair_receipt['full_ref'],schedule_context_ref=schedule_receipt['artifact_ref'],schedule_source_provenance=schedule['provenance'],actual_read_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in[Path('backend/app/product_services')/(n+'.py')for n in('joint_pace_play_budgets','game_clock_pace_catalog','shared_game_covariance','schedule_context_features')]},original_historical_availability='Unknown; revised/current2026 capture, retrospective observed source; not serving')
full=save(result)
selected=deepcopy(result);selected['game_rows']=[g for g in result['game_rows']if {g['home_team'],g['away_team']}&{'SF','WAS'}];selected['selection']='SF/WAS game rows; pooled comparison and fixed references retained globally, not recomputed from selected games';selected['provenance']['full_ref']=full;selected['selected_semantic_sha256']=digest({k:v for k,v in selected.items()if k!='provenance'});sel=save(selected)
profile=result['home_away_pooled_observed_profile'];r=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,full_ref=full,selected_ref=sel,global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],scheduled_games=len(result['game_rows']),evaluation_games=len(result['evaluation_game_ids']),reference_cutpoints=result['reference_cutpoints'],cell_coverage={h:{a:dict(known_sample_games=c['known_complete_sample']['games'],exact_games=c['exact_full_cell']['games'],unknown_membership=len(c['unknown_membership_game_ids']),unknown_response=len(c['unknown_response_game_ids']))for a,c in groups.items()}for h,groups in profile['cells'].items()},exact_conditional_contrasts=profile['fast_minus_slow_by_fixed_opposing_axis'],exact_both_axes_contrasts=profile['both_axes_difference_of_differences'],selected_games=len(selected['game_rows']),raw_source_reads=0,source_adapter_replays=0,database_queries=0,identity_writes=0,new_captures=0,models=0,pregame_serving_eligible=False)
(root/'actual_receipt.json').write_text(json.dumps(r,indent=2)+'\n');timing('source_end');print(json.dumps(r,indent=2))
