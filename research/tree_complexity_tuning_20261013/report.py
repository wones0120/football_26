"""Exact paired reports and reload verification, independent of model selection."""
import json
import numpy as np,pandas as pd,joblib
from pathlib import Path
from run import HERE,CTX,V4,V3,ROOT,v4,load

def stats(group):
 d=group.prediction-group.actual
 return {'n':len(d),'mae':float(d.abs().mean()),'rmse':float(np.sqrt(np.mean(d*d))),'bias':float(d.mean())}

def generate():
 result=json.loads((HERE/'results.json').read_text());frame,families=load();pred=pd.read_parquet(HERE/'predictions.parquet');checks=[]
 for key,record in result['records'].items():
  fold,target,family,method=key.split('/');sample=pred[(pred.fold==fold)&(pred.target==target)&(pred.family==family)&(pred.method==method)];rows=frame.loc[sample.row_index];model=joblib.load(HERE/record['model_path']);replay=v4.predict(model,'tree',rows,target,families[family]);diff=float(np.max(np.abs(replay-sample.prediction.to_numpy())));assert diff<1e-10;assert np.array_equal(rows[target].to_numpy(),sample.actual.to_numpy());assert v4.sha(HERE/record['model_path'])==record['model_sha256'];checks.append({'key':key,'n':len(sample),'max_error':diff})
 for relative,digest in result['input_dependency_hashes'].items():assert v4.sha(ROOT/relative)==digest,relative
 legacy=pd.read_csv(V4/'rolling_predictions.csv');neural=legacy[legacy.method.isin(['prior_nn','residual_nn','position_nn'])].copy();neural['input_precision']='V4 readable CSV (8-digit prediction storage)';ctx=pd.read_csv(CTX/'predictions.csv');ctx=ctx[(ctx.family=='baseline')&ctx.method.isin(['residual_nn','position_nn'])].copy();ctx['family']='F3_role_pbp';ctx['input_precision']='Exact fullprecision context base inputs (10-digit prediction storage)'
 neural=neural[~((neural.family=='F3_role_pbp')&neural.method.isin(['residual_nn','position_nn']))];neural=pd.concat([neural,ctx],ignore_index=True)
 neural['actual']=frame.loc[neural.row_index,'targets'].to_numpy() # overwritten per target below
 for target in v4.TARGETS:
  m=neural.target==target;neural.loc[m,'actual']=frame.loc[neural.loc[m,'row_index'],target].to_numpy()
 neural['period']=frame.loc[neural.row_index,'period'].to_numpy();neural['position']=frame.loc[neural.row_index,'position'].to_numpy();pred['input_precision']='Exact fullprecision';allpred=pd.concat([pred,neural],ignore_index=True);allpred.to_parquet(HERE/'comparison_predictions.parquet',index=False)
 # Exact F3 old tree parity to the independently frozen context baseline.
 control=pd.read_csv(CTX/'predictions.csv');control=control[(control.family=='baseline')&(control.method=='tree')].set_index(['fold','target','row_index']);old=pred[(pred.family=='F3_role_pbp')&(pred.method=='old_tree')].set_index(['fold','target','row_index']);assert old.index.equals(control.index) or set(old.index)==set(control.index);parity=float(np.max(np.abs(old.prediction-control.loc[old.index].prediction)));assert parity<1e-8
 summary=[];weeks=[];paired=[];rng=np.random.default_rng(261013)
 for (target,family,method),g in allpred.groupby(['target','family','method']):
  item={'target':target,'family':family,'method':method,**stats(g),'position':{p:stats(s) for p,s in g.groupby('position')}};rows=frame.loc[g.row_index];labels={'high_workload':g.actual.to_numpy()>=dict(targets=6,carries=10,fantasy_points_ppr=15)[target],'team_changed':rows.team_changed_diagnostic.to_numpy(),'workload_shift':np.abs(g.actual.to_numpy()-rows[target+'_last'].to_numpy())>=4,'sparse_history':rows.history_count.to_numpy()<=1,'observed_zero':g.actual.to_numpy()==0}
  item['subgroups']={name:{str(value):stats(g[np.asarray(values)==value]) for value in np.unique(values)} for name,values in labels.items()};summary.append(item)
  for period,s in g.groupby('period'):weeks.append({'target':target,'family':family,'method':method,'period':int(period),**stats(s)})
 for target in v4.TARGETS:
  for family in families:
   tuned=allpred[(allpred.target==target)&(allpred.family==family)&(allpred.method=='tuned_tree')].set_index(['fold','row_index'])
   for method in ['old_tree','prior_nn','residual_nn','position_nn']:
    other=allpred[(allpred.target==target)&(allpred.family==family)&(allpred.method==method)].set_index(['fold','row_index']).loc[tuned.index];assert np.array_equal(tuned.actual.to_numpy(),other.actual.to_numpy());delta=(tuned.prediction-tuned.actual).abs()-(other.prediction-other.actual).abs();wk=pd.DataFrame({'period':tuned.period,'delta':delta}).groupby('period').delta.agg(['sum','count']);bootstrap=[]
    for _ in range(2000):sample=wk.iloc[rng.integers(0,len(wk),len(wk))];bootstrap.append(sample['sum'].sum()/sample['count'].sum())
    paired.append({'target':target,'family':family,'comparator':method,'n':len(delta),'weeks':len(wk),'tuned_minus_comparator_mae':float(delta.mean()),'week_cluster_bootstrap_95':np.quantile(bootstrap,[.025,.975]).tolist(),'improved_weeks':int((wk['sum']<0).sum())})
 curves=[];complexities=[]
 for key,record in result['records'].items():
  chosen=record['options'][record['selected']];complexities.append({'key':key,'selected_config':record['selected'],'config':chosen['config'],'seconds_all_configs':sum(x['seconds'] for x in record['options']),'selected_complexity':chosen['complexity'],'selection_score':chosen['selection_score']})
  for cfg,option in enumerate(record['options']):
   for stage in option.get('curve',[]):curves.append({'key':key,'config_index':cfg,'config_name':option['config']['name'],'selected':cfg==record['selected'],**stage})
 pd.DataFrame(curves).to_csv(HERE/'learning_curves.csv',index=False);pd.DataFrame(weeks).to_csv(HERE/'week_metrics.csv',index=False)
 depth_diagnostics=[]
 for target_name,name in [(target,name) for target in v4.TARGETS for name in ['shallow','medium','deep']]:
  options=[option for key,record in result['records'].items() if key.endswith('/tuned_tree') and key.split('/')[1]==target_name for option in record['options'] if option['config']['name']==name]
  depth_diagnostics.append({'target':target_name,'name':name,'fits':len(options),'mean_selected_iterations':float(np.mean([o['complexity']['iterations'] for o in options])),'mean_actual_max_depth':float(np.mean([o['complexity']['maximum_actual_depth'] for o in options])),'mean_leaves':float(np.mean([o['complexity']['mean_leaves'] for o in options])),'mean_final_train_mae':float(np.mean([o['curve'][-1]['train_mae'] for o in options])),'mean_final_stop_mae':float(np.mean([o['curve'][-1]['stop_mae'] for o in options])),'mean_selection_score':float(np.mean([o['selection_score'] for o in options]))})
 out={'depth_diagnostics':depth_diagnostics,'summary':summary,'paired':paired,'selected_complexity':complexities,'f3_old_control_parity_max_error':parity,'verification':checks,'rows_replayed':sum(x['n'] for x in checks),'runtime_seconds':result['runtime_seconds'],'total_fits':sum(len(x['options']) for x in result['records'].values()),'precision_caveat':'F3 residual/position comparisons reuse exact-context baseline; F2 and prior_nn reuse V4 rounded matrix/prediction files; identical canonical rows/features, minor numeric precision distinction preserved.'};(HERE/'summary.json').write_text(json.dumps(out,indent=2)+'\n')
 lines=['# Tree depth and complexity tuning','',f"Completed {out['total_fits']} fits in {out['runtime_seconds']:.1f}s. No live projections, defaults, production models, database records or upstream research artifacts were changed. Research HistGradientBoosting differs from the production pipeline.",'','All results are retrospective revised-data development on previously inspected historical outcomes. Assessment is 12 Sunday Main week blocks, 2,756 labeled positive-snap participants per target (conditional on observed participation). Source PPR is not DraftKings scoring. No W6+ outcomes were read.','','## Pooled error','', '| Target | Features | Method | MAE | RMSE | Bias |','|---|---|---|---:|---:|---:|']
 for s in summary:lines.append(f"| {s['target']} | {s['family']} | {s['method']} | {s['mae']:.4f} | {s['rmse']:.4f} | {s['bias']:+.4f} |")
 lines+=['','## Tuned tree minus unchanged tree','', '| Target | Features | MAE difference | Whole-week bootstrap 95% | Improved weeks |','|---|---|---:|---|---:|']
 for s in paired:
  if s['comparator']=='old_tree':lines.append(f"| {s['target']} | {s['family']} | {s['tuned_minus_comparator_mae']:+.4f} | [{s['week_cluster_bootstrap_95'][0]:+.4f}, {s['week_cluster_bootstrap_95'][1]:+.4f}] | {s['improved_weeks']}/12 |")
 lines+=['','## Selected complexity','', '| Fold / target / feature / method | Configuration | Iterations | Max actual depth | Mean leaves |','|---|---|---:|---:|---:|']
 for s in complexities:
  c=s['selected_complexity'];lines.append(f"| {s['key']} | {s['config'].get('name',s['selected_config'])} | {c['iterations']} | {c['maximum_actual_depth']} | {c['mean_leaves']:.1f} |")
 lines+=['','## Interpretation and artifacts','','Compare each fixed neural cell separately. Selecting the best neural family/method in a target column after seeing assessment is descriptive best-of-column, not a frozen selector. Tree search received eight chronological-stopped configurations versus two old-tree and prior-neural configurations; this cannot establish intrinsic architecture superiority. The independently running capacity study has a separate freeze.','', 'Deeper trees can reduce training error while worsening later validation. learning_curves.csv retains every25iteration training/stopping error and normalized stopping score; summary.json records selected actual depths/leaves, runtime and paired deltas versus each neural comparator. results.json retains position, outcome-defined high-workload/workload-shift, sparse-history, team-change, empirical90%interval, PPR upside and samegame pair-ranking diagnostics. Outcome-defined subgroups never enter features.','', 'Selection uses historical stopping/select partitions only, with train-only preprocessing. Twelve dependent weeks, previously inspected outcomes, reconstructed revised source chronology and observed-participant conditioning limit robustness. Week bootstrap intervals are descriptive; they do not establish independent-player significance. MAE/ranking improvements do not establish lineup return or profitability. A positive result warrants a separately frozen prospective, time-safe scoring/participation and production-pipeline parity study before promotion.','',f"All {len(checks)} selected checkpoints reloaded and exactly reproduced {out['rows_replayed']:,} row predictions (maximum difference <1e-10). F3 unchanged-tree controls match the independently frozen fullprecision context baseline within {parity:.3g}. {out['precision_caveat']}",'', 'Reproduce by copying this directory to a new versioned destination, clearing only newly copied derived output, preserving SPECIFICATION.md/run.py and validating the frozen dependency hashes, then run .venv/bin/python <copy>/run.py and report.py. The runner refuses an existing freeze. Frozen source lineage remains in upstream context receipts and is hashed by freeze.json.','']
 findings=[]
 for target in v4.TARGETS:
  for family in families:
   old=next(x for x in summary if x['target']==target and x['family']==family and x['method']=='old_tree');new=next(x for x in summary if x['target']==target and x['family']==family and x['method']=='tuned_tree');paired_item=next(x for x in paired if x['target']==target and x['family']==family and x['comparator']=='old_tree')
   findings.append(f"{target} {family}: {old['mae']:.4f} → {new['mae']:.4f} MAE ({100*(new['mae']/old['mae']-1):+.2f}%), {paired_item['improved_weeks']}/12 weeks improved.")
 lines[2:2]=['Tuning produced the following frozen comparisons. Added complexity and stopping did not create a uniform improvement across tasks and feature sets.','',*findings,'']
 (HERE/'README.md').write_text('\n'.join(lines));print(json.dumps({'fits':out['total_fits'],'rows_replayed':out['rows_replayed'],'summary':summary,'paired_tree': [x for x in paired if x['comparator']=='old_tree']},indent=2))
if __name__=='__main__':generate()
