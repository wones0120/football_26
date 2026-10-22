"""One new observed event-allocation transform, no source adapters or DB work."""
from pathlib import Path
from datetime import datetime,UTC
from copy import deepcopy
import hashlib,json,time,os
from backend.app.product_services.qb_teammate_rushing_td import build_qb_teammate_rushing_td
from backend.app.product_services.qb_teammate_rushing_td_source import read_managed_parent,prepare_rushing_actor_rows
from backend.app.product_services.scoring_share_components import VERSION as SCORING_VERSION
from backend.app.product_services.evaluation_record import digest
root=Path('research/qb_teammate_rushing_td_20261020/v1');started=datetime.now(UTC);timer=time.monotonic()
def timing(stage):
 e=dict(package='qb_teammate_rushing_td_v1',agent='B',stage=stage,timestamp=datetime.now(UTC).isoformat(),evidence=str(root/'actual_receipt.json'));fd=os.open('research/feature_platform_implementation_20261019/v1/PACKAGE_TIMINGS.jsonl',os.O_WRONLY|os.O_APPEND)
 try:os.write(fd,(json.dumps(e)+'\n').encode())
 finally:os.close(fd)
timing('source_start')
pairdir=Path('research/shared_scoring_pair_covariance_20261020/v1');status=json.loads((pairdir/'receipt.json').read_text());assert status['status']=='High_FINAL_PASS_feature_only';pins=json.loads((pairdir/'EVIDENCE.json').read_text())['pins']
# Immutable parent code/receipt guards; full output bytes checked by managed reader.
for p in pins:
 if '/artifacts/'in p['path']:continue
 raw=Path(p['path']).read_bytes();assert len(raw)==p['bytes']and hashlib.sha256(raw).hexdigest()==p['sha256']
pr=json.loads((pairdir/'actual_receipt.json').read_text());pair=read_managed_parent(pr['full_ref'],'artifacts/shared_scoring_pair_covariance',cutoff=started)
ar=json.loads(Path('research/active_workload_distributions_20261020/v1/actual_receipt.json').read_text());active=read_managed_parent(ar['full_ref'],'artifacts/active_workload_distributions',cutoff=started)
sr=json.loads(Path('research/scoring_share_components_20261020/v1/actual_derivation_receipt.json').read_text());scoring=read_managed_parent(sr['full_ref'],'artifacts/scoring_share_components',cutoff=started)
assert scoring['version']==SCORING_VERSION and scoring['before_period']==pair['before_period']and pair['provenance']['scoring_ref']==sr['full_ref']and pair['provenance']['active_workload_ref']==ar['full_ref']
actors=prepare_rushing_actor_rows(pair,active);games=[dict(game_id=g['game_id'],team=g['team'],season=int(g['game_id'][:4]),week=int(g['game_id'].split('_')[1]))for g in pair['source_game_physical_passing_TDs']]
result=build_qb_teammate_rushing_td(actors,games,scoring['event_basis']);result['before_period']=scoring['before_period']
result['provenance']=dict(pair_parent_ref=pr['full_ref'],active_parent_ref=ar['full_ref'],scoring_parent_ref=sr['full_ref'],inherited_pair_identity_queue_receipt=dict(actual_receipt_sha256=hashlib.sha256((pairdir/'actual_receipt.json').read_bytes()).hexdigest(),requests=pr['queue']['requests'],durable_records=pr['queue'].get('durable_readback_records',[])),original_source_PBP=pair['provenance']['source_PBP'],publication='Retrospective revised historical/source capture; original historical pregame publication unknown',actual_read_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),source_actor_rows=actors,producer_code_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in [Path('backend/app/product_services')/(name+'.py')for name in ('qb_teammate_rushing_td','qb_teammate_rushing_td_source')]})
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False,default=str).encode();assert len(raw)<=48*1024*1024
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/qb_teammate_rushing_td')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb')as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:deepcopy(v)for k,v in result.items()if k not in('pair_game_rows','profiles','strict_prior_windows','physical_rushing_TD_evidence','team_game_budget','semantic_sha256')}
for field in('pair_game_rows','profiles','strict_prior_windows','physical_rushing_TD_evidence','team_game_budget'):selected[field]=[r for r in result[field]if r['team']in {'SF','WAS'}]
selected['selected_semantic_sha256']=digest({k:v for k,v in selected.items()if k!='provenance'});selected['provenance']['full_ref']=full;sel=save(selected)
actual=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,full_ref=full,selected_ref=sel,native_sides=len(games),source_actor_logs=len(actors),pair_game_rows=len(result['pair_game_rows']),pair_profiles=len(result['profiles']),exact_profiles=sum(r['exact']is not None for r in result['profiles']),exact_nondegenerate_profiles=sum(r['exact']is not None and r['exact']['rushing_TD_counts']['correlation']is not None for r in result['profiles']),exact_prior_windows=sum(r['exact']is not None for r in result['strict_prior_windows']),selected_profiles=len(selected['profiles']),known_source_rushing_TDs=sum(r['known_rushing_TDs']for r in result['team_game_budget']),unknown_eligibility=sum(r['unknown_eligibility']for r in result['team_game_budget']),unknown_scorer=sum(r['unknown_scorer']for r in result['team_game_budget']),carry_incompatible_pair_games=sum(r['carry_sanity_compatible']is False for r in result['pair_game_rows']),global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],new_source_queries=0,source_adapter_replays=0,new_capture=0,identity_writes=0,models=0,pregame_serving_eligible=False)
(root/'actual_receipt.json').write_text(json.dumps(actual,indent=2)+'\n');timing('source_end');print(json.dumps(actual,indent=2))
