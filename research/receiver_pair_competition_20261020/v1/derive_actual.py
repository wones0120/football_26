"""New transformation of three reviewed native event bases; no raw adapter replay."""
from pathlib import Path
from datetime import datetime,UTC
from copy import deepcopy
import json,hashlib,time,os,gc
from backend.app.product_services.receiver_pair_competition_source import load_reviewed_pair_native
from backend.app.product_services.receiver_pair_competition import build_receiver_pair_competition
from backend.app.product_services.evaluation_record import digest
root=Path('research/receiver_pair_competition_20261020/v1');started=datetime.now(UTC);timer=time.monotonic()
def timing(stage):
 e=dict(package='receiver_pair_competition_v1',agent='B',stage=stage,timestamp=datetime.now(UTC).isoformat(),evidence=str(root/'actual_receipt.json'))
 f=os.open('research/feature_platform_implementation_20261019/v1/PACKAGE_TIMINGS.jsonl',os.O_WRONLY|os.O_APPEND)
 try:os.write(f,(json.dumps(e)+'\n').encode())
 finally:os.close(f)
timing('source_start')
parent_dir=Path('research/coverage_receiver_performance_20261020/v1');receipt=json.loads((parent_dir/'receipt.json').read_text());assert receipt['review_status']=='High_FINAL_PASS_feature_only'
for pin in receipt['pins']:
 raw=Path(pin['path']).read_bytes();assert len(raw)==pin['bytes']and hashlib.sha256(raw).hexdigest()==pin['sha256']
parent=json.loads((parent_dir/'actual_receipt.json').read_text());outputs=[]
code={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in [Path('backend/app/product_services')/(name+'.py')for name in ('receiver_pair_competition','receiver_pair_competition_source')]}
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=96*1024*1024,'96MiB bounded output; compact immutable scope before publication'
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/receiver_pair_competition')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb')as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
for entry in parent['outputs']:
 read=datetime.now(UTC);loaded=load_reviewed_pair_native(entry['native_ref'],entry['full_ref'],cutoff=read);result=build_receiver_pair_competition(loaded['native'],loaded['identities'])
 result['provenance']={**loaded['provenance'],'actual_derived_at':datetime.now(UTC).isoformat(),'actual_publication_at':datetime.now(UTC).isoformat(),'producer_code_hashes':code,'parent_receipt_sha256':hashlib.sha256((parent_dir/'receipt.json').read_bytes()).hexdigest()}
 full=save(result);selected={k:deepcopy(v)for k,v in result.items()if k not in('team_game_target_budgets','actor_game_channels','pair_game_rows','observed_profiles','strict_prior_windows','semantic_sha256')}
 for field in('team_game_target_budgets','actor_game_channels','pair_game_rows','observed_profiles','strict_prior_windows'):selected[field]=[r for r in result[field]if r['team']in {'SF','WAS'}]
 selected['selection_scope']='SF/WAS rows; global frozen identity evidence retained by full reviewed attached parent reference';selected['full_ref']=full;selected['selected_semantic_sha256']=digest({k:v for k,v in selected.items()if k!='provenance'});sel=save(selected)
 exact=[w for w in result['strict_prior_windows']if w['exact']is not None]
 item=dict(season=result['season'],native_parent_ref=entry['native_ref'],attached_identity_parent_ref=entry['full_ref'],full_ref=full,selected_ref=sel,global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],team_games=len(result['team_game_target_budgets']),complete_team_target_budgets=sum(r['exact_team_targets']is not None for r in result['team_game_target_budgets']),actor_games=len(result['actor_game_channels']),pair_game_rows=len(result['pair_game_rows']),pair_profiles=len(result['observed_profiles']),exact_whole_profiles=sum(p['exact']is not None for p in result['observed_profiles']),window_coverage=result['window_coverage'],reported_windows=len(result['strict_prior_windows']),exact_target_covariance_windows=len(exact),exact_efficiency_decomposition_windows=sum(w['exact']['EPA_decomposition']is not None for w in exact),known_sample_efficiency_decomposition_windows=sum(w['known_complete_sample']['EPA_decomposition']is not None for w in result['strict_prior_windows']),selected_windows=len(selected['strict_prior_windows']))
 outputs.append(item);print(json.dumps(item),flush=True);del loaded,result,selected;gc.collect()
actual=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,outputs=outputs,source_adapter_replays=0,new_source_queries=0,new_capture=0,identity_writes=0,models=0,pregame_serving_eligible=False)
(root/'actual_receipt.json').write_text(json.dumps(actual,indent=2)+'\n');timing('source_end');print(json.dumps(actual,indent=2))
