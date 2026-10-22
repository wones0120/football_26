"""Saved-only matched comparisons; no fitting, selection or recalibration."""
from pathlib import Path
import hashlib,json
import numpy as np
from backend.app.product_services.raw_count_player_models import count_metrics
ROOT=Path('research/workload_direct_count_fits_20261020/v1')
PRIOR=Path('research/pressure_count_model_fits_20261020/v1')
def readref(ref):
 b=Path(ref['path']).read_bytes();assert len(b)==ref['bytes']and hashlib.sha256(b).hexdigest()==ref['sha256'];return json.loads(b)
def key(r,grain):return (r['game_id'],r['team'],r.get('player_master_id'))if grain=='player'else(r['game_id'],r['team'])
def metrics(rows,t,field='predicted'):
 rs=[r for r in rows if r['actual'][t]is not None];return count_metrics([r['actual'][t]for r in rs],[r[field][t]for r in rs])
results={};predictions={};matched={};roles={};accounting={}
for grain in('team','player'):
 for family in('tree','neural'):
  name=grain+'_'+family;job=json.loads((ROOT/(name+'.json')).read_text());results[name]=job;rows=readref(job['prediction_ref']);predictions[name]=rows
  priorjob=json.loads((PRIOR/(name+'.json')).read_text());old=readref(priorjob['prediction_ref']);oldmap={(r['split'],key(r,grain)):r for r in old};matched[name]={};roles[name]={}
  for split in sorted({r['split']for r in rows}):
   rs=[r for r in rows if r['split']==split];matched[name][split]={};roles[name][split]={}
   for t in job['receipt']['target_columns']:
    pairs=[(r,oldmap[(split,key(r,grain))])for r in rs if (split,key(r,grain))in oldmap and r['actual'][t]is not None and oldmap[(split,key(r,grain))]['actual'][t]is not None]
    actual=[r['actual'][t]for r,o in pairs];same=[(r,o)for r,o in pairs if r['actual'][t]==o['actual'][t]]
    matched[name][split][t]=dict(identical_known_key_rows=len(pairs),changed_labels=sum(r['actual'][t]!=o['actual'][t]for r,o in pairs),new=count_metrics(actual,[r['predicted'][t]for r,o in pairs]),saved_prior_on_NEW_labels=count_metrics(actual,[o['predicted'][t]for r,o in pairs]),unchanged_label_rows=len(same),new_on_unchanged=count_metrics([r['actual'][t]for r,o in same],[r['predicted'][t]for r,o in same]),saved_prior_on_unchanged=count_metrics([r['actual'][t]for r,o in same],[o['predicted'][t]for r,o in same]))
   groups={'ALL':rs}
   if grain=='player':groups.update({p:[r for r in rs if r['position']==p]for p in sorted({r['position']for r in rs})})
   for position,pr in groups.items():
    roles[name][split][position]={}
    for t in job['receipt']['target_columns']:
     known=[r for r in pr if r['actual'][t]is not None]
     roles[name][split][position][t]=dict(all=metrics(known,t),raw=metrics(known,t,'raw_predicted'),positive_actual=metrics([r for r in known if r['actual'][t]>0],t),zero_actual=metrics([r for r in known if r['actual'][t]==0],t),observed_sum=sum(r['actual'][t]for r in known),predicted_sum=sum(r['predicted'][t]for r in known),all_predicted_rows=len(pr))
for family in('tree','neural'):
 accounting[family]={}
 team=predictions['team_'+family];player=predictions['player_'+family]
 for split in sorted({r['split']for r in team}):
  teams={key(r,'team'):r for r in team if r['split']==split};groups={}
  for r in player:
   if r['split']!=split:continue
   g=groups.setdefault(key(r,'team'),dict(actual={t:0 for t in('pass_attempts','rush_attempts','targets')},predicted={t:0. for t in('pass_attempts','rush_attempts','targets')},known_prediction={t:0. for t in('pass_attempts','rush_attempts','targets')},unknown_prediction={t:0. for t in('pass_attempts','rush_attempts','targets')},unknown={t:0 for t in('pass_attempts','rush_attempts','targets')}))
   for t in g['actual']:
    if r['actual'][t]is None:g['unknown'][t]+=1;g['unknown_prediction'][t]+=r['predicted'][t]
    else:g['actual'][t]+=r['actual'][t];g['known_prediction'][t]+=r['predicted'][t]
    g['predicted'][t]+=r['predicted'][t]
  keys=set(teams)&set(groups);diagnostic={}
  for t in('pass_attempts','rush_attempts'):
   diagnostic[t]=dict(mean_known_source_minus_scored_actual=float(np.mean([teams[k]['actual'][t]-groups[k]['actual'][t]for k in keys])),mean_scored_prediction_minus_scored_actual=float(np.mean([groups[k]['known_prediction'][t]-groups[k]['actual'][t]for k in keys])),mean_team_prediction_minus_source_actual=float(np.mean([teams[k]['predicted'][t]-teams[k]['actual'][t]for k in keys])),mean_scored_prediction_minus_team_prediction=float(np.mean([groups[k]['predicted'][t]-teams[k]['predicted'][t]for k in keys])),scored_unknown_label_rows=sum(groups[k]['unknown'][t]for k in keys),mean_predictions_on_unknown_label_rows=float(np.mean([groups[k]['unknown_prediction'][t]for k in keys])))
  accounting[family][split]=dict(sides=len(keys),decomposition=diagnostic,player_target_prediction_exceeds_team_pass_prediction=sum(groups[k]['predicted']['targets']>teams[k]['predicted']['pass_attempts']for k in keys),actual_known_scored_targets_exceed_source_passes=sum(groups[k]['actual']['targets']>teams[k]['actual']['pass_attempts']for k in keys),scope='Known label sums only; unknown and excluded mass retained separately, not zero or forecast repaired. Source-observed weekly total not certified NFL census; no forced normalization.')
summary=dict(version='workload_direct_count_fit_summary_v1',jobs={n:{k:j[k]for k in('status','recipe','recipe_parameters','started_at','completed_at','elapsed_seconds','model_ref','prediction_ref','evaluation','feature_columns')}for n,j in results.items()},matched_saved_prior=matched,role_zero_positive_diagnostics=roles,accounting=accounting,fits=len(results),baseline_fits=0,grid_or_retry=0,live_activation=False,scope='Previously inspected retrospective2025; added features plus target-transform/source-label changes jointly confound attribution. Identical known-key comparisons do not isolate incremental feature causality. No own probability calibration or complete-roster forecast claim.')
(ROOT/'SUMMARY.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
for name,j in results.items():
 print(name,j['status'],{t:d['supported_metrics']for t,d in j['evaluation'].get('retrospective_test',{}).items()})
print('QB', {n:roles[n].get('retrospective_test',{}).get('QB',{}).get('pass_attempts')for n in('player_tree','player_neural')})
