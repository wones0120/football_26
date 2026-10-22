"""Bounded saved-only retrospective decomposition: no fit or source acquisition."""
from pathlib import Path
from datetime import datetime,UTC
import hashlib,json,time
import numpy as np
R=Path('research/direct_count_mechanism_diagnosis_20261020/v1');NEW=Path('research/workload_direct_count_fits_20261020/v1');OLD=Path('research/pressure_count_model_fits_20261020/v1');started=datetime.now(UTC);timer=time.monotonic();refs=[]
def readref(ref):
 b=Path(ref['path']).read_bytes();assert len(b)==ref['bytes']and hashlib.sha256(b).hexdigest()==ref['sha256'];refs.append(ref);return json.loads(b)
def key(r):return(r['split'],r['game_id'],r['team'],r.get('player_master_id'))
def stat(pairs,t):
 pairs=[(n,o)for n,o in pairs if n['actual'][t]is not None and o['actual'][t]is not None]
 if not pairs:return dict(rows=0)
 y=np.array([n['actual'][t]for n,o in pairs]);a=np.array([n['predicted'][t]for n,o in pairs]);b=np.array([o['predicted'][t]for n,o in pairs])
 return dict(rows=len(y),known_zero=int((y==0).sum()),new_mae=float(abs(a-y).mean()),old_mae_on_SAME_NEW_labels=float(abs(b-y).mean()),new_rmse=float(np.sqrt(np.mean((a-y)**2))),old_rmse=float(np.sqrt(np.mean((b-y)**2))),new_bias=float((a-y).mean()),old_bias=float((b-y).mean()),absolute_error_delta_sum=float((abs(a-y)-abs(b-y)).sum()),signed_error_delta_sum=float((a-b).sum()),observed_sum=float(y.sum()),new_prediction_sum=float(a.sum()),old_prediction_sum=float(b.sum()))
# One approved prepared-array load; extract only prior exposure/context masks.
job0=json.loads((NEW/'player_tree.json').read_text());prepared=readref(job0['prepared_ref']);p=prepared['preprocessing'];cols=p['columns'];features=['scheduled3_carries_exposure','scheduled3_targets_exposure','scheduled3_known_actor_rows','scheduled3_unknown_actor_rows','latest_prior_role_QB','latest_prior_role_RB','latest_prior_role_WR','latest_prior_role_TE','scheduled3_role_consistent'];indices={f:cols.index(f)for f in features};prior={}
for split,part in prepared['splits'].items():
 for k,x in zip(part['keys'],part['x']):
  prior[(split,k['game_id'],k['team'],k['player_master_id'])]={f:None if x[len(cols)+j]else x[j]*p['scale'][j]+p['center'][j]for f,j in indices.items()}
del prepared
manifest=json.loads(Path('research/workload_efficiency_model_batch_20261020/v1/MANIFEST.json').read_text());ledger=readref(manifest['accounting_ledger_ref']);ledger={(r['game_id'],r['team']):r for r in ledger['team_game_rows']};diagnosis={};sides=[]
for family in('tree','neural'):
 nj=json.loads((NEW/('player_'+family+'.json')).read_text());oj=json.loads((OLD/('player_'+family+'.json')).read_text());new=readref(nj['prediction_ref']);old=readref(oj['prediction_ref']);om={key(r):r for r in old};team=readref(json.loads((NEW/('team_'+family+'.json')).read_text())['prediction_ref']);oldteam=readref(json.loads((OLD/('team_'+family+'.json')).read_text())['prediction_ref']);tm={(r['split'],r['game_id'],r['team']):r for r in team};otm={(r['split'],r['game_id'],r['team']):r for r in oldteam};diagnosis[family]={}
 for split in('train','validation','retrospective_test'):
  pairs=[(n,om[key(n)])for n in new if n['split']==split and key(n)in om];groups={}
  for n,o in pairs:groups.setdefault((n['split'],n['game_id'],n['team']),[]).append((n,o))
  stats={}
  for t,exposure in [('rush_attempts','scheduled3_carries_exposure'),('targets','scheduled3_targets_exposure')]:
   strata={}
   for n,o in pairs:
    state='unknown_label'if n['actual'][t]is None else'positive_label'if n['actual'][t]>0 else'zero_label'
    raw=prior[key(n)][exposure];exp='unknown_prior_exposure'if raw is None else'known_zero_prior_exposure'if abs(raw)<1e-8 else'known_positive_prior_exposure'
    count=len(groups[(split,n['game_id'],n['team'])]);countbin='<=8recorded'if count<=8 else'9to12recorded'if count<=12 else'>=13recorded'
    for tag in ['ALL','role:'+n['position'],'label:'+state,'role_label:'+n['position']+':'+state,'prior_exposure:'+exp,'role_exposure:'+n['position']+':'+exp,'recorded_count:'+countbin]:strata.setdefault(tag,[]).append((n,o))
   stats[t]={tag:stat(rows,t)for tag,rows in strata.items()}
  crossing=[]
  for g,ps in groups.items():
   if g not in tm:continue
   tr=tm[g];otr=otm[g];known=[(n,o)for n,o in ps if n['actual']['targets']is not None and o['actual']['targets']is not None];unknown=[(n,o)for n,o in ps if n['actual']['targets']is None or o['actual']['targets']is None]
   actual=sum(n['actual']['targets']for n,o in known);npred=sum(n['predicted']['targets']for n,o in ps);opred=sum(o['predicted']['targets']for n,o in ps);commonnew=sum(n['predicted']['targets']for n,o in known);commonold=sum(o['predicted']['targets']for n,o in known);upred=sum(n['predicted']['targets']for n,o in unknown);sourcepass=tr['actual']['pass_attempts'];teampred=tr['predicted']['pass_attempts'];oldteampred=otr['predicted']['pass_attempts'];lc=ledger[(g[1],g[2])]
   parts={}
   for role in sorted({n['position']for n,o in ps}):
    rp=[(n,o)for n,o in known if n['position']==role];parts[role]=dict(known_zero_prediction=sum(n['predicted']['targets']for n,o in rp if n['actual']['targets']==0),known_positive_error=sum(n['predicted']['targets']-n['actual']['targets']for n,o in rp if n['actual']['targets']>0),new_minus_old_prediction=sum(n['predicted']['targets']-o['predicted']['targets']for n,o in ps if n['position']==role))
   row=dict(family=family,split=split,game_id=g[1],team=g[2],recorded_player_rows=len(ps),source_actor_rows=lc['source_actor_rows'],canonical_scored_actors=lc['scored_source_actors'],source_passes=sourcepass,source_target_known_sum=lc['channels']['targets']['known_source_sum'],known_common_scored_targets=actual,new_target_prediction=npred,old_target_prediction=opred,new_team_pass_prediction=teampred,old_team_pass_prediction=oldteampred,new_crossing=npred>teampred,old_crossing=opred>oldteampred,new_common_known_crossing=commonnew>teampred,old_common_known_crossing=commonold>oldteampred,new_margin=npred-teampred,old_margin=opred-oldteampred,known_target_error=commonnew-actual,unknown_label_prediction=upred,source_pass_minus_known_common_targets=sourcepass-actual,source_pass_minus_team_prediction=sourcepass-teampred,new_target_prediction_minus_sourcepass=npred-sourcepass,role_parts=parts,source_target_ledger=lc['channels']['targets'])
   assert abs(row['new_margin']-(row['known_target_error']+upred-row['source_pass_minus_known_common_targets']+row['source_pass_minus_team_prediction']))<1e-8
   crossing.append(row);sides.append(row)
  cs=[r for r in crossing if r['new_crossing']];ns=[r for r in crossing if not r['new_crossing']]
  crossstat=dict(sides=len(crossing),crossings=len(cs),old_crossings=sum(r['old_crossing']for r in crossing),common_known_new_crossings=sum(r['new_common_known_crossing']for r in crossing),common_known_old_crossings=sum(r['old_common_known_crossing']for r in crossing),newly_crossed=sum(r['new_crossing']and not r['old_crossing']for r in crossing),ceased_crossing=sum(not r['new_crossing']and r['old_crossing']for r in crossing),crossings_target_prediction_gt_actual_source_pass=sum(r['new_target_prediction']>r['source_passes']for r in cs),crossings_team_prediction_lt_actual_source_pass=sum(r['new_team_pass_prediction']<r['source_passes']for r in cs),crossings_even_if_team_prediction_equals_actual_source=sum(r['new_target_prediction']>r['source_passes']for r in cs),groups={})
  for label,rows in [('crossing',cs),('not_crossing',ns)]:
   crossstat['groups'][label]=dict(rows=len(rows),means={f:float(np.mean([r[f]for r in rows]))if rows else None for f in('recorded_player_rows','source_actor_rows','known_target_error','unknown_label_prediction','source_pass_minus_known_common_targets','source_pass_minus_team_prediction','new_margin','new_target_prediction_minus_sourcepass')},role_means={role:{f:float(np.mean([r['role_parts'].get(role,{}).get(f,0)for r in rows]))if rows else None for f in('known_zero_prediction','known_positive_error','new_minus_old_prediction')}for role in('QB','RB','WR','TE')})
  diagnosis[family][split]=dict(common_row_regression_strata=stats,crossing_decomposition=crossstat)
result=dict(version='direct_count_mechanism_diagnosis_v1',started_at=started.isoformat(),completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,source_refs=refs,diagnosis=diagnosis,scope='Saved-model/prediction and prior-array diagnostics only; no target-based feature/cohort tuning. Previously inspected retrospective2025. Common-known-label strata; unknown-label prediction mass separated. Source-observed weekly census does not imply active/dressed participation.',fits=0,new_source_requests=0,activation=False)
(R/'DIAGNOSIS.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');(R/'SIDE_DECOMPOSITIONS.json').write_text(json.dumps(sides,separators=(',',':'),allow_nan=False)+'\n')
for family,d in diagnosis.items():
 print(family,json.dumps(d['retrospective_test']['crossing_decomposition']))
 for t,s in d['retrospective_test']['common_row_regression_strata'].items():print(t,{k:v for k,v in s.items()if k.startswith('label:')or k.startswith('prior_exposure:')})
