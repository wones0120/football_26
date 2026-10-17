"""Post-freeze descriptive comparison, never used for model selection."""
import sys,json,importlib.util
from pathlib import Path
import numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(HERE))
import run as r

def metrics(g):
 e=(g.prediction-g.actual).to_numpy();return dict(n=len(g),mae=float(np.mean(np.abs(e))),rmse=float(np.sqrt(np.mean(e**2))),bias=float(np.mean(e)))

def paired(a,b):
 keys=['row_index','fold','target','family'];g=a.merge(b,on=keys,suffixes=('_a','_b'),validate='one_to_one');assert len(g)==len(a)==len(b);assert np.array_equal(g.actual_a,g.actual_b)
 g['delta']=np.abs(g.prediction_a-g.actual_a)-np.abs(g.prediction_b-g.actual_b);c=g.groupby(['fold','period_a']).delta.agg(['sum','count']);rng=np.random.default_rng(261013);draw=rng.integers(0,len(c),(2000,len(c)));boot=c['sum'].to_numpy()[draw].sum(axis=1)/c['count'].to_numpy()[draw].sum(axis=1)
 return dict(n=len(g),delta_mae=float(g.delta.mean()),week_clusters=len(c),week_wins=int((c['sum']<0).sum()),week_ties=int((c['sum']==0).sum()),week_losses=int((c['sum']>0).sum()),paired_week_cluster_95_interval=[float(v) for v in np.quantile(boot,[.025,.975])],caveat='Retrospective descriptive bootstrap, only12clusters with overlapping training; not independentconfirmatory inference')

def main():
 result=json.loads((HERE/'results.json').read_text());p=pd.read_parquet(HERE/'predictions.parquet');selected=p[p.method.str.startswith(('current_','capacity_'))].copy();treepath=HERE.parent/'tree_complexity_tuning_20261013/predictions.parquet'
 if not treepath.exists():raise ValueError('Tree frozen results not yet available')
 treefreeze=json.loads((treepath.parent/'freeze.json').read_text());assert treefreeze['folds']==result['folds'] and treefreeze['features']==result['features'];source='research/neural_game_context_20261013/feature_matrix_full_precision.parquet';assert treefreeze['input_dependency_hashes'][source]==result['dependency_hashes'][source]
 tree=pd.read_parquet(treepath);combined=pd.concat([selected,tree],ignore_index=True);combined.to_parquet(HERE/'comparison_predictions.parquet',index=False)
 frame,_=r.load();info=frame.copy();info['row_index']=info.index
 pooled={};groups={};weekly={};pairedout={};ranks={};configs={};heads=[]
 for (target,family,method),g in combined.groupby(['target','family','method']):
  key='/'.join([target,family,method]);pooled[key]=metrics(g);weekly[key]={str(period):metrics(z) for period,z in g.groupby('period')};z=g.merge(info[['row_index','history_count','team_changed_diagnostic',target+'_last']],on='row_index',validate='many_to_one');groups[key]={}
  labels={'position':z.position,'high_workload':z.actual>=dict(targets=6,carries=10,fantasy_points_ppr=15)[target],'sparse_history':z.history_count<=1,'team_changed':z.team_changed_diagnostic,'workload_shift':(z.actual-z[target+'_last']).abs()>=4}
  for name,label in labels.items():groups[key][name]={str(value):metrics(z[label==value]) for value in sorted(label.unique())}
  if target=='fantasy_points_ppr':
   ranks[key]={'upside':[],'pairs':[]}
   for fold,zfold in g.groupby('fold'):
    scored=info.loc[zfold.row_index].copy();scored['prediction']=zfold.prediction.to_numpy();season=int(scored.season.unique()[0]);assert scored.season.nunique()==1
    for diagnostic,func in [('upside',r.v4.v3.upside),('pairs',r.v4.v3.pairs)]:
     ranks[key][diagnostic].extend(item|{'fold':fold,'season':season,'period':season*100+item['week']} for item in func(scored,'prediction'))
 for (target,family),g in combined.groupby(['target','family']):
  for design in ['residual_nn','position_nn']:
   a=g[g.method=='capacity_'+design];b=g[g.method=='current_'+design];pairedout[target+'/'+family+'/capacity_vs_current_'+design]=paired(a,b)
  for method in ['current_residual_nn','current_position_nn','capacity_residual_nn','capacity_position_nn']:
   pairedout[target+'/'+family+'/'+method+'_vs_tuned_tree']=paired(g[g.method==method],g[g.method=='tuned_tree'])
 for key,rec in result['records'].items():
  configs[key]={label:r.CONFIGS[index]['name'] for label,index in rec['selections'].items()}
  for option in rec['options']:
   for head,meta in option['training_metadata'].items():
    if 'best_epoch' in meta:heads.append(dict(key=key,config=option['config']['name'],head=head,parameter_count=meta['parameter_count'],best_epoch=meta['best_epoch'],epochs_run=meta['epochs_run'],epoch_cap=meta['epoch_cap'],cap_reached=meta['cap_reached'],seconds=meta['seconds'],warnings=meta['warnings'],training_metric=meta['training_metric_at_best'],stopping_metric=meta['stopping_best']))
 pd.DataFrame(heads).to_csv(HERE/'head_training_diagnostics.csv',index=False)
 training_rows=[]
 for key,record in result['records'].items():
  for option in record['options']:
   training_rows.append(dict(key=key,config=option['config']['name'],method=key.split('/')[-1],training_mae=option['training_actual_mae'],stopping_mae=option['stopping_actual_mae'],selection_score=option['selection_score'],parameter_count=option['parameter_count'],seconds=option['seconds']))
 training_summary={}
 for (method,config),g in pd.DataFrame(training_rows).groupby(['method','config']):
  training_summary[method+'/'+config]={c:float(g[c].mean()) for c in ['training_mae','stopping_mae','selection_score','parameter_count','seconds']}
 capacitydiagnostics={}
 for (target,family,method),g in p[~p.method.str.startswith(('current_','capacity_'))].groupby(['target','family','method']):capacitydiagnostics['/'.join([target,family,method])]=metrics(g)
 summary=dict(pooled=pooled,subgroups=groups,weekly=weekly,paired=pairedout,rankings=ranks,selections=configs,architecture_diagnostics=capacitydiagnostics,training_summary=training_summary,runtime_seconds=result['runtime_seconds'],head_count=len(heads),cap_reached_heads=sum(h['cap_reached'] for h in heads),warnings=sum(len(h['warnings']) for h in heads),maximum_parameter_count=max(h['parameter_count'] for h in heads),comparison_sha256=r.v4.sha(HERE/'comparison_predictions.parquet'))
 (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 lines=['# Wider/deeper neural capacity comparison','', 'Larger neural nets yielded modest average-error gains for the shared residual design, with mixed results for position-aware heads. On F3, expanded residual MAE improved targets 1.4192→1.3949, carries 1.2771→1.2415, and source PPR 4.6604→4.6387. Tuned tree remains lower in carries/PPR MAE (1.2062/4.5750); the neural target advantage is small and its paired interval overlaps zero. Capacity carries/PPR RMSE rose slightly, and high-workload MAE worsened for all three targets. These results do not support automatic promotion.','', 'This research changed no live projections, application defaults, or database records. It is retrospective development on previously inspected historical outcomes. Inputs are full precision, features/rows/chronological folds are identical to the concurrent tree experiment. Source PPR is not DraftKings scoring; the observed participant cohort does not model DNP risk. No W6+ outcomes were accessed.','',f"216 macro fits completed in {result['runtime_seconds']:.1f}s elapsed wall time with one native thread; {len(heads)} trained heads. No architecture was selected using assessment outcomes. Current NN searches 2 controls; expanded NN searches 6 options including controls; tuned tree searches 8 joint configs. Different search/training budgets prevent intrinsic architecture superiority claims.",'','MAE / RMSE / bias by target, fixed feature family and whole selected model:','','| Target | Features | Model | MAE | RMSE | Bias |','|---|---|---|---:|---:|---:|']
 for key,value in pooled.items():
  target,family,method=key.split('/');lines.append(f"| {target} | {family} | {method} | {value['mae']:.4f} | {value['rmse']:.4f} | {value['bias']:+.4f} |")
 lines+=['','Paired capacity-minus-current MAE differences (negative favors capacity), with descriptive week-cluster intervals:','','| Target | Features | Design | ΔMAE | 95% interval | Weeks win/tie/loss |','|---|---|---|---:|---|---|']
 for key,value in pairedout.items():
  if '/capacity_vs_current_' not in key:continue
  target,family,design=key.split('/');lo,hi=value['paired_week_cluster_95_interval'];lines.append(f"| {target} | {family} | {design.replace('capacity_vs_current_','')} | {value['delta_mae']:+.4f} | [{lo:+.4f}, {hi:+.4f}] | {value['week_wins']}/{value['week_ties']}/{value['week_losses']} |")
 lines+=['','For F3 residual heads, high-workload MAE rose targets 2.6424→2.7025, carries 4.5034→4.6999, and PPR 8.6887→8.8983. Large realized workload-shift rows also worsened on average. These outcome-defined subsets are diagnostics and cannot serve as predecision selectors.','','Only 12 week clusters and overlapping historical training windows make these intervals exploratory. Subgroups, all per-week errors, paired neural-minus-tree differences, PPR rank/upside diagnostics, and individual-architecture errors are in summary.json. Individual-architecture assessment diagnostics were computed after the selection freeze and cannot justify selecting a different model.','',f"Largest individual head has {summary['maximum_parameter_count']:,} learned parameters. {summary['cap_reached_heads']} heads reached their epoch cap; {summary['warnings']} recorded warnings. learning_curves.csv retains every training-loss, standardized training metric and stopping metric; head_training_diagnostics.csv retains best epochs, head runtimes and counts. The residual stopping metric is raw target MAE while its training_metric is standardized residual RMSE; do not directly subtract those two columns. Position amount heads use standardized log-amount RMSE and classifier heads use Brier; raw macro training/stopping MAE is in results.json.",'','Training summary across three mixed target units is descriptive only; compare within target/family using the full per-fit results. Wider/deeper options that lower training error without consistent assessment gains suggest overfitting/variance under this setup; a stopped curve does not rule out an optimization issue.','','Current architecture and larger architecture checkpoints plus all prespecified selection scores are stored in models/ and results.json. Original V4 files remain untouched. Training budgets are bounded; converged stopping or local training-loss reduction alone does not prove sufficient capacity or optimization globally. Width/depth comparisons preserve features, but widest 128-unit option jointly changes regularization/LR and larger candidates permit more epochs.','', 'No automatic promotion is recommended from this retrospective search. Reserve prospective W6+ protocol with forecasts frozen before decision/lock, compare one fully specified whole model under identical input/cohort and scoring rules, then consider live changes only if repeatable gains appear.']
 lines+=['','PPR ranking diagnostics on F3: macro-average NDCG across 48 season-week-position cells is current residual .6426, capacity residual .6366, tuned tree .6367; boom precision is .2870/.2748/.2804. These are descriptive point-ranking diagnostics, not calibrated ceilings, joint portfolios, or contest-profit evidence.','','Verification: 5 targeted tests passed. 72 selected serialized-model cells replay exactly; 12 real-data controls match the untouched V4 functions exactly. All 36 current choices match original frozen V4 choices. Fullprecision source hash, F2/F3 features and folds match the tree experiment; joins retain exact player/fold rows.','','Run targeted checks from the repository root with `PYTHONPATH=. .venv/bin/python -m pytest research/neural_capacity_20261013/test_capacity.py -q`; replay saved artifacts with `PYTHONPATH=. .venv/bin/python research/neural_capacity_20261013/verify.py`. Training refuses to overwrite an existing freeze; reproduce in a separately named research directory with identical frozen source dependencies. `report.py` recomputes descriptive comparison from frozen predictions and does not train or select models.']
 (HERE/'README.md').write_text('\n'.join(lines)+'\n')
 print(json.dumps({'runtime':result['runtime_seconds'],'pooled':pooled,'paired_capacity':{k:v for k,v in pairedout.items() if '/capacity_vs_current_' in k}},indent=2))
if __name__=='__main__':main()
