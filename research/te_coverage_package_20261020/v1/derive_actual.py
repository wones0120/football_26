"""New TE/package response from shared position cache and reviewed target events."""
from pathlib import Path
from datetime import datetime,UTC
from copy import deepcopy
import json,hashlib,time,os,gc
from backend.app.product_services.te_coverage_package import build_te_coverage_package
from backend.app.product_services.participation_position_components import load_position_component
from backend.app.product_services.receiver_pair_competition_source import load_reviewed_pair_native
from backend.app.product_services.evaluation_record import digest
root=Path('research/te_coverage_package_20261020/v1');started=datetime.now(UTC);timer=time.monotonic()
def timing(stage):
 e=dict(package='te_coverage_package_v1',agent='B',stage=stage,timestamp=datetime.now(UTC).isoformat(),evidence=str(root/'actual_receipt.json'));fd=os.open('research/feature_platform_implementation_20261019/v1/PACKAGE_TIMINGS.jsonl',os.O_WRONLY|os.O_APPEND)
 try:os.write(fd,(json.dumps(e)+'\n').encode())
 finally:os.close(fd)
timing('source_start')
def reviewed(directory,status,field):
 directory=Path(directory);r=json.loads((directory/'receipt.json').read_text());assert r[field]==status
 evidence=json.loads((directory/'EVIDENCE.json').read_text())if(directory/'EVIDENCE.json').exists()else r
 for p in evidence['pins']:
  if '/artifacts/'in p['path']:continue
  b=Path(p['path']).read_bytes();assert len(b)==p['bytes']and hashlib.sha256(b).hexdigest()==p['sha256']
 return json.loads((directory/'actual_receipt.json').read_text())
position=reviewed('research/participation_position_components_20261020/v1','High_FINAL_PASS_source_only','status')
target=reviewed('research/coverage_receiver_performance_20261020/v1','High_FINAL_PASS_feature_only','review_status');target_by={x['season']:x for x in target['outputs']};outputs=[]
code={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in [Path('backend/app/product_services')/(n+'.py')for n in('te_coverage_package','participation_position_components','receiver_pair_competition_source','defensive_front_rush_exposure','participation_defense_catalog')]}
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=64*1024*1024
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/te_coverage_package')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb')as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
for item in position['outputs']:
 year=item['season'];read=datetime.now(UTC);positions=load_position_component(item['full_ref'],cutoff=read);entry=target_by[year];native=load_reviewed_pair_native(entry['native_ref'],entry['full_ref'],cutoff=read)
 old=native['native']['provenance']['native_participation'];assert old['snapshot_id']==positions['provenance']['source_ref']['snapshot_id']and old['source_sha256']==positions['provenance']['source_ref']['sha256']
 result=build_te_coverage_package(positions,native['native'],native['identities'])
 assert not result['global_identity_scope']['novel_conflicts_requiring_UI_incident'],'Checkpoint new identity conflict before publication; append-only evidence helper required'
 result['provenance']=dict(position_component_ref=item['full_ref'],native_target_ref=entry['native_ref'],attached_global_identity_ref=entry['full_ref'],position_provenance=positions['provenance'],target_provenance=native['provenance'],actual_read_at=read.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_hashes=code,source_kind='Historical FTN postseason/revised original PBP; original historical pregame availability unknown',identity_policy='Complete inherited global native receipts plus all-edge conflict closure; prior withheld keys never reattached; no new alias query/repair')
 full=save(result);selected={k:deepcopy(v)for k,v in result.items()if k not in('actor_game_rows','event_basis','unassigned_TE_candidate_residual','semantic_sha256')}
 selected['actor_game_rows']=[r for r in result['actor_game_rows']if r['team']in {'SF','WAS'}];selected['event_basis']=[e for e in result['event_basis']if e['offense']in {'SF','WAS'}];selected['unassigned_TE_candidate_residual']=[e for e in result['unassigned_TE_candidate_residual']if e['offense']in {'SF','WAS'}];selected['provenance']['full_ref']=full;selected['selected_semantic_sha256']=digest({k:v for k,v in selected.items()if k!='provenance'});sel=save(selected)
 coverage={field:sum(r['DB_ge6_minus_le5'][c][field]is not None for r in result['actor_game_rows']for c in('man','zone'))for field in('target_rate','completion_rate','provider_EPA_per_TE_target')}
 out=dict(season=year,full_ref=full,selected_ref=sel,global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],source_position_ref=item['full_ref'],native_target_ref=entry['native_ref'],actor_games=len(result['actor_game_rows']),canonical_actor_games=sum(r['canonical_qualified']for r in result['actor_game_rows']),exact_game_contrasts=coverage,source_attempt_events=len(result['event_basis']),unknown_TE_candidate_residual_events=len(result['unassigned_TE_candidate_residual']),global_identity_scope=result['global_identity_scope'],selected_actor_games=len(selected['actor_game_rows']));outputs.append(out);print(json.dumps(out),flush=True)
 del positions,native,result,selected;gc.collect()
actual=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,outputs=outputs,raw_participation_reads=0,raw_PBP_reads=0,source_adapter_replays=0,new_source_queries=0,new_captures=0,identity_writes=0,models=0,pregame_serving_eligible=False)
(root/'actual_receipt.json').write_text(json.dumps(actual,indent=2)+'\n');timing('source_end');print(json.dumps(actual,indent=2))
