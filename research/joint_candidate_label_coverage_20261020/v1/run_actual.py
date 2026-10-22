from pathlib import Path
from datetime import datetime,UTC
from collections import defaultdict,Counter
import hashlib,json,time
from contract import audit_group,CHANNEL_FIELDS
R=Path(__file__).resolve().parent;started=datetime.now(UTC);timer=time.monotonic();manifest=json.loads(Path('research/workload_efficiency_model_batch_20261020/v1/MANIFEST.json').read_text());contract=Path('research/direct_count_mechanism_diagnosis_20261020/v1/HIGH_CONTRACTS.json');refs={}
def readref(name,ref,maxsize):
 assert ref['bytes']<=maxsize;b=Path(ref['path']).read_bytes();assert len(b)==ref['bytes']and hashlib.sha256(b).hexdigest()==ref['sha256'];refs[name]=ref;return json.loads(b)
component=readref('source_component',manifest['component_ref'],96*1024*1024);context=readref('reviewed_prior_contexts',manifest['source_refs']['context_ref'],8*1024*1024)
assert context['source_component_ref']==manifest['component_ref']
actors=defaultdict(list)
for row in component['actor_rows']:actors[row['game_id'],row['team']].append(row)
teams={(r['game_id'],r['team']):r for r in component['team_game_rows']};contexts={(r['game_id'],r['team']):r for r in context['team_contexts']};assert set(teams)<=set(contexts)
rows=[audit_group(contexts[k],actors,teams)for k in sorted(teams)];summary={}
for season in sorted({r['period']//100 for r in rows}):
 rs=[r for r in rows if r['period']//100==season];achieved=[r for r in rs if r['history_achieved']];summary[str(season)]=dict(split={2023:'train',2024:'validation',2025:'inspected_retrospective_test',2026:'inspected_later_diagnostic'}[season],scheduled_sides=len(rs),achieved_prior3_sides=len(achieved),unachieved_sides=len(rs)-len(achieved),candidate_cells=sum(r['candidate_count']for r in achieved),prior_zero_candidate_cells=sum(r['candidate_prior_all_channels_zero']for r in achieved),channels={})
 for ch in CHANNEL_FIELDS:
  exact=[r for r in achieved if r['channels'][ch]['native_source_complete_group']];canonical=[r for r in achieved if r['channels'][ch]['canonical_complete_group']]
  summary[str(season)]['channels'][ch]=dict(exact_native_groups=len(exact),exact_canonical_candidate_groups=len(canonical),exact_positive_budget_native_groups=sum(r['channels'][ch]['source_observed_budget']>0 for r in exact),exact_positive_budget_canonical_groups=sum(r['channels'][ch]['source_observed_budget']>0 for r in canonical),unknown_candidate_cells=sum(r['channels'][ch]['unknown_candidate_count']for r in achieved),known_zero_candidate_cells=sum(r['channels'][ch]['known_zero_candidate_count']for r in achieved),canonical_unqualified_candidate_cells=sum(r['channels'][ch]['canonical_unqualified_candidate_count']for r in achieved),groups_budget_unknown=sum(r['channels'][ch]['source_observed_budget']is None for r in achieved),groups_with_unknown_candidate=sum(r['channels'][ch]['unknown_candidate_count']>0 for r in achieved),groups_unknown_outside_rest=sum(r['channels'][ch]['unknown_outside_count']>0 for r in achieved),known_outside_canonical_sum=sum(r['channels'][ch]['known_outside_canonical_sum']for r in achieved),known_outside_unresolved_sum=sum(r['channels'][ch]['known_outside_unresolved_sum']for r in achieved),min_missing_candidate_per_achieved_group=min([r['channels'][ch]['unknown_candidate_count']for r in achieved],default=None),max_missing_candidate_per_achieved_group=max([r['channels'][ch]['unknown_candidate_count']for r in achieved],default=None),unknown_candidate_count_histogram=dict(sorted(Counter(r['channels'][ch]['unknown_candidate_count']for r in achieved).items())))
 allnative=[r for r in achieved if all(r['channels'][ch]['native_source_complete_group']for ch in CHANNEL_FIELDS)];allcanonical=[r for r in achieved if all(r['channels'][ch]['canonical_complete_group']for ch in CHANNEL_FIELDS)]
 summary[str(season)].update(exact_allchannel_native_groups=len(allnative),exact_allchannel_canonical_groups=len(allcanonical),source_NFL_census='UNKNOWN',unconditional_participation_universe='NOT_IDENTIFIED')
# Managed new projection, immutable source parents unchanged.
b=json.dumps(dict(version='fixed_prior3_joint_candidate_label_audit_v1',groups=rows,source_refs=refs),sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(b).hexdigest();p=Path('artifacts/joint_candidate_label_coverage')/(sha+'.json');p.parent.mkdir(exist_ok=True)
if not p.exists():
 with p.open('xb')as f:f.write(b)
 p.chmod(0o444)
else:assert p.read_bytes()==b
receipt=dict(version='joint_candidate_label_coverage_actual_v1',started_at=started.isoformat(),completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),helper_sha256=hashlib.sha256((R/'contract.py').read_bytes()).hexdigest(),high_contract_ref=dict(path=str(contract.resolve()),sha256=hashlib.sha256(contract.read_bytes()).hexdigest()),source_refs=refs,full_ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(b)),coverage=summary,fits=0,source_requests=0,source_adapters_replayed=0,identity_queries=0,model_changes=0,activation=False)
(R/'ACTUAL_RECEIPT.json').write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n');print(json.dumps(receipt,indent=2))
