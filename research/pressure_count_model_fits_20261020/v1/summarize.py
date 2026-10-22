from pathlib import Path
import json,hashlib
import numpy as np
ROOT=Path('research/pressure_count_model_fits_20261020/v1');jobs={};rows={}
for grain in('team','player'):
 for family in('tree','neural'):
  name=grain+'_'+family;r=json.loads((ROOT/(name+'.json')).read_text());jobs[name]=r
  ref=r['prediction_ref'];b=Path(ref['path']).read_bytes();assert len(b)==ref['bytes']and hashlib.sha256(b).hexdigest()==ref['sha256'];rows[name]=json.loads(b)
role={};budget={}
for family in('tree','neural'):
 source=rows['player_'+family];role[family]={};budget[family]={}
 for split in sorted({r['split']for r in source}):
  selected=[r for r in source if r['split']==split];role[family][split]={}
  for position in sorted({r['position']for r in selected}):
   rs=[r for r in selected if r['position']==position];heads={}
   for t in('pass_attempts','rush_attempts','targets'):
    known=[r for r in rs if r['actual'][t]is not None];errors=[r['predicted'][t]-r['actual'][t]for r in known]
    heads[t]=dict(rows=len(known),mae=float(np.mean(abs(np.asarray(errors)))),bias=float(np.mean(errors)),observed_sum=sum(r['actual'][t]for r in known),predicted_sum=sum(r['predicted'][t]for r in known))
   role[family][split][position]=heads
  team={(r['game_id'],r['team']):r for r in rows['team_'+family]if r['split']==split};groups={}
  for r in selected:
   g=groups.setdefault((r['game_id'],r['team']),dict.fromkeys(('pass_attempts','rush_attempts','targets'),0.))
   for t in g:g[t]+=r['predicted'][t]
  matched=set(team)&set(groups)
  budget[family][split]=dict(matched_team_sides=len(matched),mean_player_minus_team_passes=float(np.mean([groups[k]['pass_attempts']-team[k]['predicted']['pass_attempts']for k in matched]))if matched else None,mean_player_minus_team_rushes=float(np.mean([groups[k]['rush_attempts']-team[k]['predicted']['rush_attempts']for k in matched]))if matched else None,recorded_player_target_sum_exceeds_team_pass_prediction=sum(groups[k]['targets']>team[k]['predicted']['pass_attempts']for k in matched),scope='Incomplete recorded player cohort and independently fitted point heads; discrepancies diagnose missing reconciliation, not proof of a complete expected budget. No normalization or live activation.')
summary=dict(version='pressure_count_fit_summary_v1',jobs={n:{k:r[k]for k in('status','recipe','recipe_parameters','started_at','completed_at','elapsed_seconds','prepared_ref','model_ref','prediction_ref','evaluation','accounting','new_feature_columns','added_input_coverage')}for n,r in jobs.items()},role_diagnostics=role,budget_diagnostics=budget,scope='Revised-history retrospective count research; previously inspected outcomes; no probability/interval calibration, no incremental pressure attribution, no activation',fits=4,baseline_fits=0,solver_or_recipe_restarts=0,source_jobs=0)
(ROOT/'SUMMARY.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
for family in('tree','neural'):
 print(family,'QB2025',role[family]['retrospective_test'].get('QB'), 'budget',budget[family]['retrospective_test'])
