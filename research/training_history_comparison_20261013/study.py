"""Frozen research-only history study with genuine weighted MLP gradients."""
from __future__ import annotations
import os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
import hashlib,json,platform,time,warnings
from pathlib import Path
import numpy as np,pandas as pd,joblib,sklearn
from sklearn.preprocessing import StandardScaler,OneHotEncoder
from sklearn.neural_network import MLPRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
CTX=HERE.parent/'neural_game_context_20261013'
V3=HERE.parent/'neural_workload_benchmark_20261013/expanded_v3'
TARGETS=['targets','carries','fantasy_points_ppr']; ARMS=['2026_only','2025_plus_2026','full_equal','full_recency']
NN=dict(hidden_layer_sizes=(64,32),alpha=.2,batch_size=256,random_state=261013,learning_rate_init=.001,early_stopping=False,max_iter=1,shuffle=True)
TREE=dict(max_depth=5,max_leaf_nodes=15,min_samples_leaf=60,l2_regularization=10,learning_rate=.05,max_iter=200,early_stopping=False,random_state=261013)
EPOCHS=100;HALFLIFE=365.;KEY=['player_master_id','game_id']
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,obj):Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def hashframe(f,cols):return hashlib.sha256(pd.util.hash_pandas_object(f[cols],index=True).values.tobytes()).hexdigest()
def columns():return json.loads((V3/'input_manifest.json').read_text())['feature_families']['F3_role_pbp']
def guard(f,cols):
 if f[KEY].isna().any().any() or f.duplicated(KEY).any():raise ValueError('Canonical keys absent/duplicated')
 if any(c in TARGETS or c in ['positive_snap_population','name','player_master_id','raw_source_id','team_changed_diagnostic'] or c.startswith('ctx_') for c in cols):raise ValueError('Unsafe model feature')
 if f.period.max()>202605 or not ((f.week>=1)&(f.week<=18)).all():raise ValueError('Unexpected future/window row')
 old=f.max_source_season*100+f.max_source_week
 if (old.notna()&(old>=f.period)).any():raise ValueError('Target/future base history')
 if (f.max_expanded_source_period.notna()&(f.max_expanded_source_period>=f.period)).any():raise ValueError('Target/future expanded history')
 clock=pd.to_datetime(f.max_expanded_completed_at,utc=True);cut=pd.to_datetime(f.decision_cutoff_at,utc=True)
 if (clock.notna()&(clock>=cut)).any():raise ValueError('Post-cutoff history')
def select(f,arm,target):
 minimum=202601 if arm=='2026_only' else 202501 if arm=='2025_plus_2026' else 202301
 g=f[(f.period>=minimum)&(f.period<=202604)&f[target].notna()].copy()
 if g.empty or g.period.max()!=202604:raise ValueError('Incomplete training window')
 return g

def weights(f,arm,anchor):
 if arm!='full_recency':return np.ones(len(f))
 age=(anchor-pd.to_datetime(f.kickoff_at,utc=True)).dt.total_seconds().to_numpy()/86400
 if (age<0).any():raise ValueError('Negative history age')
 w=np.exp2(-age/HALFLIFE);return w*(len(w)/w.sum())

def weighted_median(x,w):
 valid=np.isfinite(x);x=x[valid];w=w[valid]
 if not len(x):return 0.
 order=np.argsort(x,kind='stable');x=x[order];w=w[order]
 return float(x[np.searchsorted(np.cumsum(w),w.sum()/2,side='left')])
class WeightedPreprocess:
 def __init__(self,cols):self.columns=list(cols)
 def fit(self,f,w):
  a=f[self.columns].to_numpy(dtype=float);self.medians=np.array([weighted_median(a[:,i],w) for i in range(a.shape[1])]);self.indicators=np.flatnonzero(np.isnan(a).any(axis=0));self.scaler=StandardScaler();self.scaler.fit(self.numeric(f),sample_weight=w);self.encoder=OneHotEncoder(handle_unknown='ignore',sparse_output=False).fit(f[['position']]);self.fit_hash=hashframe(f,self.columns+['position']);self.fit_rows=len(f);self.fit_end=int(f.period.max());return self
 def numeric(self,f):
  a=f[self.columns].to_numpy(dtype=float);missing=np.isnan(a);return np.c_[np.where(missing,self.medians,a),missing[:,self.indicators].astype(float)]
 def transform(self,f):return np.c_[self.scaler.transform(self.numeric(f)),self.encoder.transform(f[['position']])]
def floor(p,target):return np.maximum(0,p) if target!='fantasy_points_ppr' else p
class HistoryModel:
 def __init__(self,cols,method,target):self.columns=cols;self.method=method;self.target=target
 def history(self,f):return f[self.target+'_mean3'].fillna(f.position.map(self.priors)).fillna(self.global_prior).to_numpy()
 def fit(self,f,w):
  if f.period.max()>202604 or f[self.target].isna().any():raise ValueError('Unsafe fit rows')
  self.pre=WeightedPreprocess(self.columns).fit(f,w);X=self.pre.transform(f);y=f[self.target].to_numpy();self.curves=[];self.fit_rows=len(f);self.train_keys=f[KEY].to_dict('records');self.weight_sum=float(w.sum())
  with warnings.catch_warnings(record=True) as caught:
   warnings.simplefilter('always')
   if self.method=='tree':self.estimator=HistGradientBoostingRegressor(**TREE).fit(X,y,sample_weight=w)
   else:
    self.global_prior=float(np.average(y,weights=w));self.priors={pos:float(np.average(g[self.target],weights=w[f.index.get_indexer(g.index)])) for pos,g in f.groupby('position')}
    self.target_scale=StandardScaler().fit((y-self.history(f)).reshape(-1,1),sample_weight=w)
    residual=self.target_scale.transform((y-self.history(f)).reshape(-1,1)).ravel();self.estimator=MLPRegressor(**NN)
    for epoch in range(1,EPOCHS+1):
     self.estimator.partial_fit(X,residual,sample_weight=w)
     if epoch==1 or epoch%10==0:self.curves.append(dict(epoch=epoch,weighted_loss=float(self.estimator.loss_),train_mae=float(np.mean(np.abs(self.predict(f)-y))),weighted_train_mae=float(np.average(np.abs(self.predict(f)-y),weights=w))))
  self.warnings=[str(v.message) for v in caught];return self
 def predict(self,f):
  p=self.estimator.predict(self.pre.transform(f))
  if self.method=='residual_nn':p=self.history(f)+self.target_scale.inverse_transform(p.reshape(-1,1)).ravel()
  return floor(p,self.target)
def measure(g):
 e=g.prediction-g.actual
 return dict(n=len(g),mae=float(np.mean(abs(e))),rmse=float(np.sqrt(np.mean(e**2))),bias=float(np.mean(e)),spearman=(float(g.actual.corr(g.prediction,method='spearman')) if g.actual.nunique()>1 and g.prediction.nunique()>1 else None))
def rankings(g):
 out={}
 for pos,p in g.groupby('position'):
  k=min(5,len(p));order=p.sort_values(['prediction','player_master_id'],ascending=[False,True]);ideal=p.sort_values(['actual','player_master_id'],ascending=[False,True]);discount=1/np.log2(np.arange(2,k+2));dcg=float((np.maximum(order.actual.to_numpy()[:k],0)*discount).sum());idcg=float((np.maximum(ideal.actual.to_numpy()[:k],0)*discount).sum());out[pos]=dict(n=len(p),ndcg_at5=dcg/idcg if idcg else None,top5_overlap=len(set(order.player_master_id.head(k))&set(ideal.player_master_id.head(k)))/k)
 return out

def run():
 if (HERE/'freeze.json').exists():raise ValueError('Frozen study exists; do not overwrite')
 started=time.perf_counter();cols=columns();receipt=json.loads((CTX/'exact_input_receipt.json').read_text());assert sha(CTX/receipt['path'])==receipt['sha256'];f=pd.read_parquet(CTX/receipt['path']);guard(f,cols);f=f[f.positive_snap_population].copy();anchor=pd.to_datetime(f[f.period==202604].kickoff_at,utc=True).max();test=f[f.period==202605].copy()
 deps=[HERE/'SPECIFICATION.md',HERE/'study.py',HERE/'test_study.py',CTX/receipt['path'],CTX/'exact_input_receipt.json',CTX/'context_lineage.json',V3/'input_manifest.json',V3/'data.py',HERE.parent/'neural_capacity_20261013/capacity_models.py',HERE.parent/'neural_capacity_20261013/run.py',HERE.parent/'tree_complexity_tuning_20261013/run.py']
 freeze=dict(dependencies={str(p.relative_to(ROOT)):sha(p) for p in deps},features=cols,nn=NN,tree=TREE,epochs=EPOCHS,arms=ARMS,targets=TARGETS,weight_half_life_days=HALFLIFE,weight_anchor=anchor.isoformat(),versions=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,sklearn=sklearn.__version__,joblib=joblib.__version__),classification='Retrospective previously inspected W5; revised data; conditional observed participation',production_mutations=False)
 manifests=[];weekcounts=[];coverage={}
 for arm in ARMS:
  for target in TARGETS:
   train=select(f,arm,target);w=weights(train,arm,anchor);coverage[arm+'/'+target]=dict(n=len(train),effective_n=float(w.sum()**2/np.sum(w**2)),positions=train.groupby('position').size().to_dict(),train_X_hash=hashframe(train,cols+['position']),train_y_hash=hashframe(train,[target]),weighted_y_hash=hashlib.sha256(np.c_[train[target],w].tobytes()).hexdigest(),w_sum=float(w.sum()))
   m=train[KEY+['season','week','period','position','kickoff_at']].copy();m['row_index']=m.index;m['target']=target;m['arm']=arm;m['sample_weight']=w;manifests.append(m)
   for (season,week),g in m.groupby(['season','week']):weekcounts.append(dict(arm=arm,target=target,season=int(season),week=int(week),n=len(g),weight_sum=float(g.sample_weight.sum()),weight_min=float(g.sample_weight.min()),weight_max=float(g.sample_weight.max())))
 pd.concat(manifests).to_parquet(HERE/'training_manifest.parquet',index=False);pd.DataFrame(weekcounts).to_csv(HERE/'training_counts.csv',index=False);test[KEY+['season','week','position','sunday_main','positive_snap_population']+TARGETS].to_csv(HERE/'assessment_manifest.csv',index=True);freeze['training_manifest_hash']=sha(HERE/'training_manifest.parquet');freeze['assessment_manifest_hash']=sha(HERE/'assessment_manifest.csv');freeze['assessment_X_hash']=hashframe(test,cols+['position']);freeze['coverage']=coverage;dump(HERE/'freeze.json',freeze)
 (HERE/'models').mkdir();preds=[];records={};curves=[]
 with threadpool_limits(limits=1):
  for arm in ARMS:
   for target in TARGETS:
    train=select(f,arm,target);w=weights(train,arm,anchor);assess=test[test[target].notna()]
    for method in ['tree','residual_nn']:
     key='/'.join([arm,target,method]);t=time.perf_counter();model=HistoryModel(cols,method,target).fit(train,w);seconds=time.perf_counter()-t;path=HERE/'models'/(key.replace('/','__')+'.joblib');joblib.dump(model,path,compress=3);p=model.predict(assess);g=assess[KEY+['name','season','week','period','team','position','sunday_main']].copy();g['row_index']=g.index;g['actual']=assess[target];g['prediction']=p;g['target']=target;g['arm']=arm;g['method']=method;g['error']=g.prediction-g.actual;g['absolute_error']=abs(g.error);preds.append(g)
     record=dict(seconds=seconds,fit_rows=len(train),train_mae=float(np.mean(np.abs(model.predict(train)-train[target]))),weighted_train_mae=float(np.average(np.abs(model.predict(train)-train[target]),weights=w)),warnings=model.warnings,checkpoint=str(path.relative_to(HERE)),checkpoint_hash=sha(path),preprocessing_fit_hash=model.pre.fit_hash,fit_end=model.pre.fit_end,weight_sum=model.weight_sum)
     if method=='tree':nodes=[a[0].nodes for a in model.estimator._predictors];record['complexity']=dict(iterations=int(model.estimator.n_iter_),maximum_actual_depth=int(max(n['depth'].max() for n in nodes)),mean_leaves=float(np.mean([n['is_leaf'].sum() for n in nodes])))
     else:record.update(epochs=EPOCHS,minibatch_updates=int(EPOCHS*np.ceil(len(train)/NN['batch_size'])),parameter_count=int(sum(a.size for a in model.estimator.coefs_)+sum(a.size for a in model.estimator.intercepts_)),first_loss=model.curves[0]['weighted_loss'],last_loss=model.curves[-1]['weighted_loss']);curves.extend([dict(arm=arm,target=target,method=method,**c) for c in model.curves])
     records[key]=record;print('FIT',key,'n',len(train),'seconds',round(seconds,2),flush=True);dump(HERE/'progress.json',dict(completed_models=len(records),elapsed_seconds=time.perf_counter()-started))
 pred=pd.concat(preds,ignore_index=True);control=pred[pred.arm=='2026_only'][['row_index','target','method','absolute_error','prediction']].rename(columns=dict(absolute_error='control_absolute_error',prediction='control_prediction'));pred=pred.merge(control,on=['row_index','target','method'],validate='many_to_one');pred['absolute_error_change']=pred.absolute_error-pred.control_absolute_error;pred['prediction_change']=pred.prediction-pred.control_prediction;pred.to_parquet(HERE/'predictions.parquet',index=False);pred.to_csv(HERE/'predictions.csv',index=False);pd.DataFrame(curves).to_csv(HERE/'learning_curves.csv',index=False)
 metrics={};flat=[];ranks={};thresholds=dict(targets=8,carries=15,fantasy_points_ppr=20)
 for (arm,target,method),g in pred.groupby(['arm','target','method']):
  for scope,part in [('sunday_main',g[g.sunday_main]),('all_games_secondary',g)]:
   key='/'.join([scope,arm,target,method]);m=measure(part);m['position']={pos:measure(v) for pos,v in part.groupby('position')};high=part[part.actual>=thresholds[target]];m['high_workload']=measure(high) if len(high) else dict(n=0);metrics[key]=m;flat.append(dict(scope=scope,arm=arm,target=target,method=method,**{k:v for k,v in m.items() if k not in ['position','high_workload']}))
   if target=='fantasy_points_ppr':ranks[key]=rankings(part)
 pd.DataFrame(flat).to_csv(HERE/'metrics.csv',index=False)
 # Map prior base-history source references; explicitly measure cross-season evidence.
 source_period=dict(zip(f.raw_source_id,f.period));lag_coverage={}
 for scope,part in [('train_2026W1_4',f[(f.season==2026)&(f.week<=4)]),('W5_sunday_main',test[test.sunday_main])]:
  count=0;unmapped=0
  for refs in part.source_ids_json:
   periods=[source_period.get(v) for v in json.loads(refs)];count+=any(v is not None and v<202601 for v in periods);unmapped+=any(v is None for v in periods)
  lag_coverage[scope]=dict(n=len(part),rows_with_confirmed_older_base_history=count,rows_with_unmapped_base_refs=unmapped)
 dump(HERE/'results.json',dict(metrics=metrics,rankings=ranks,records=records,runtime_seconds=time.perf_counter()-started,lag_history_coverage=lag_coverage,predictions_hash=sha(HERE/'predictions.parquet')));print('COMPLETE',round(time.perf_counter()-started,2),flush=True)
if __name__=='__main__':run()
