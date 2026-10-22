from pathlib import Path
from datetime import datetime,UTC
from collections import Counter
import hashlib,json,time
from proof import physical_scope,target_scope,proof_zero
R=Path(__file__).resolve().parent;started=datetime.now(UTC);timer=time.monotonic();refs={}
def load(name,ref,cap):
 assert ref['bytes']<=cap;b=Path(ref['path']).read_bytes();assert len(b)==ref['bytes']and hashlib.sha256(b).hexdigest()==ref['sha256'];refs[name]=ref;return json.loads(b)
weekly_receipt=json.loads(Path('research/joint_candidate_label_coverage_20261020/v1/ACTUAL_RECEIPT.json').read_text());original=load('fixed_prior3_candidate_groups',weekly_receipt['full_ref'],48*1024*1024)['groups']
G18=json.loads(Path('research/personnel_package_continuity_20261020/v1/actual_receipt.json').read_text());G15=json.loads(Path('research/contact_cohort_reconciliation_20261020/v1/actual_receipt.json').read_text());G16=json.loads(Path('research/coverage_receiver_performance_20261020/v1/actual_receipt.json').read_text())
rush=load('G15_official_rush_credit_cohort',G15['cohort_ref'],20*1024*1024);rushmap={(r['game_id'],r['offense']):r for r in rush['game_rows']};rushsource={r['season']:r['descriptor']['manifest']['sha256']for r in rush['provenance']['original_PBP_sources']};del rush
physical={};targets={};sourcechecks={}
for season in(2023,2024,2025):
 p=next(r for r in G18['outputs']if r['season']==season);b=load('G18_'+str(season),p['full_ref'],32*1024*1024);physical.update(physical_scope(b));del b
 c=next(r for r in G16['source_inputs']if r['season']==season);b=load('G16_'+str(season),c['native_ref'],24*1024*1024);targets.update(target_scope(b))
 expected=next(r for r in G18['source_inputs']if r['season']==season)['physical_source']['source_sha256'];assert expected==rushsource[season]==b['provenance']['original_PBP_sha256'];sourcechecks[str(season)]=dict(same_original_native_PBP_sha256=expected,reg_game_ids=len(b['expected_games']),missing_PBP_game_ids=b['missing_PBP_game_ids']);del b
rows=[];summary={}
for group in original:
 key=group['game_id'],group['team'];season=group['period']//100;new=dict(game_id=key[0],team=key[1],period=group['period'],prior_games=group['prior_games'],history_achieved=group['history_achieved'],candidate_count=group['candidate_count'],channels={},missing_candidate_proofs=[])
 for channel,old in group['channels'].items():
  unknown=0;zero=0;canonical_unknown=0;reasons=Counter()
  for candidate in group['candidate_native_labels']:
   count=candidate['counts'][channel]
   if count is None:
    proof=proof_zero(candidate['source_player_id'],channel,physical.get(key),rushmap.get(key),targets.get(key))if season in(2023,2024,2025)else dict(zero=False,reason='NO_APPROVED_2026_EVENT_CACHE_SUPPORT')
    new['missing_candidate_proofs'].append(dict(source_player_id=candidate['source_player_id'],channel=channel,original_count=None,canonical_prior_attachment=candidate['canonical_prior_attachment'],**proof));reasons[proof['reason']]+=1
    if proof['zero']:zero+=1
    else:unknown+=1
    if not candidate['canonical_prior_attachment']or candidate['canonical_prior_attachment_conflict']:canonical_unknown+=1
   elif not candidate['canonical_same_native_label_qualified']:canonical_unknown+=1
  complete=bool(group['history_achieved']and group['candidate_count']and old['source_observed_budget']is not None and not unknown and old['numeric_disjoint_outside_rest']is not None)
  if complete:assert old['known_candidate_sum']+old['numeric_disjoint_outside_rest']==old['source_observed_budget']
  new['channels'][channel]=dict(original_unknown_candidate_count=old['unknown_candidate_count'],proposed_source_log_zero_count=zero,unknown_candidate_count_after_event_proof=unknown,original_known_candidate_sum=old['known_candidate_sum'],known_candidate_sum_after_only_zero_proofs=old['known_candidate_sum'],source_observed_budget=old['source_observed_budget'],numeric_disjoint_outside_rest=old['numeric_disjoint_outside_rest'],known_outside_canonical_sum=old['known_outside_canonical_sum'],known_outside_unresolved_sum=old['known_outside_unresolved_sum'],native_labels_complete_with_scoped_event_zero_proofs=complete,canonical_candidate_labels_complete=complete and canonical_unknown==0,canonical_unqualified_candidate_count=canonical_unknown,zero_proof_reasons=dict(reasons),unreported_or_unknown_mass_inferred_zero=False,independent_NFL_census='UNKNOWN',learned_allocation_fit_authorized=False)
 rows.append(new)
for season in(2023,2024,2025,2026):
 gs=[r for r in rows if r['period']//100==season];achieved=[r for r in gs if r['history_achieved']];out=dict(scheduled_sides=len(gs),prior3_achieved_sides=len(achieved),candidate_cells=sum(r['candidate_count']for r in achieved),channels={})
 for ch in('pass_attempts','rush_attempts','targets'):
  cs=[r['channels'][ch]for r in achieved];reasons=Counter()
  for c in cs:reasons.update(c['zero_proof_reasons'])
  exact=[c for c in cs if c['native_labels_complete_with_scoped_event_zero_proofs']];can=[c for c in cs if c['canonical_candidate_labels_complete']]
  out['channels'][ch]=dict(original_unknown_candidate_cells=sum(c['original_unknown_candidate_count']for c in cs),source_log_zeros_proved=sum(c['proposed_source_log_zero_count']for c in cs),remaining_unknown_cells=sum(c['unknown_candidate_count_after_event_proof']for c in cs),native_complete_source_scoped_groups=len(exact),native_complete_positive_budget_groups=sum(c['source_observed_budget']>0 for c in exact),canonical_complete_groups=len(can),unknown_budget_sides=sum(c['source_observed_budget']is None for c in cs),reason_counts=dict(reasons),known_outside_canonical_sum=sum(c['known_outside_canonical_sum']for c in cs),known_outside_unresolved_sum=sum(c['known_outside_unresolved_sum']for c in cs))
 out['all_channel_native_complete_groups']=sum(all(r['channels'][ch]['native_labels_complete_with_scoped_event_zero_proofs']for ch in('pass_attempts','rush_attempts','targets'))for r in achieved);out['all_channel_canonical_complete_groups']=sum(all(r['channels'][ch]['canonical_candidate_labels_complete']for ch in('pass_attempts','rush_attempts','targets'))for r in achieved);summary[str(season)]=out
b=json.dumps(dict(version='cached_event_zero_proof_audit_v1',groups=rows,source_refs=refs,source_scope='Original REG source-log official-play/credit evidence only; source-observed weekly labels, independent NFL completeness and unconditional participation unknown'),sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(b).hexdigest();p=Path('artifacts/cached_event_zero_proof')/(sha+'.json');p.parent.mkdir(exist_ok=True)
if not p.exists():
 with p.open('xb')as f:f.write(b)
 p.chmod(0o444)
else:assert p.read_bytes()==b
receipt=dict(version='cached_event_zero_proof_actual_v1',started_at=started.isoformat(),completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,source_refs=refs,source_checks=sourcechecks,full_ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(b)),coverage=summary,producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),helper_sha256=hashlib.sha256((R/'proof.py').read_bytes()).hexdigest(),fits=0,new_source_requests=0,raw_source_rereads=0,identity_queries=0,activation=False,scope='Feasibility evidence pending High; no labels changed in any matrix/model; no complete NFL census/unconditional participation proof')
(R/'ACTUAL_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
