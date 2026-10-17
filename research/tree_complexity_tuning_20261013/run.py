"""Bounded, chronological tree complexity experiment; no application imports/writes."""
import os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
import sys,json,time,signal,copy,importlib.util,platform
from pathlib import Path
import numpy as np,pandas as pd,joblib,sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import make_pipeline
from threadpoolctl import threadpool_limits
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];CTX=HERE.parent/'neural_game_context_20261013';V4=HERE.parent/'neural_workload_benchmark_20261013/training_v4';V3=V4.parent/'expanded_v3'
spec=importlib.util.spec_from_file_location('tuning_v4',V4/'runner.py');v4=importlib.util.module_from_spec(spec);spec.loader.exec_module(v4)
CONFIGS=[dict(name='shallow',max_depth=3,max_leaf_nodes=8,min_samples_leaf=30,l2_regularization=1,learning_rate=.05,max_iter=400),dict(name='medium',max_depth=5,max_leaf_nodes=31,min_samples_leaf=30,l2_regularization=1,learning_rate=.05,max_iter=400),dict(name='deep',max_depth=None,max_leaf_nodes=63,min_samples_leaf=30,l2_regularization=1,learning_rate=.05,max_iter=400),dict(name='regularized',max_depth=5,max_leaf_nodes=15,min_samples_leaf=60,l2_regularization=10,learning_rate=.05,max_iter=400),dict(name='flexible',max_depth=8,max_leaf_nodes=31,min_samples_leaf=15,l2_regularization=0,learning_rate=.05,max_iter=400),dict(name='slow',max_depth=5,max_leaf_nodes=31,min_samples_leaf=30,l2_regularization=2,learning_rate=.03,max_iter=400),dict(name='fast',max_depth=5,max_leaf_nodes=31,min_samples_leaf=30,l2_regularization=2,learning_rate=.08,max_iter=300),dict(name='slow_shallow',max_depth=3,max_leaf_nodes=8,min_samples_leaf=60,l2_regularization=10,learning_rate=.03,max_iter=400)]

def load():
 receipt=json.loads((CTX/'exact_input_receipt.json').read_text());assert v4.sha(CTX/receipt['path'])==receipt['sha256']
 frame=pd.read_parquet(CTX/receipt['path']);frame=frame[frame.positive_snap_population].copy();manifest=json.loads((V3/'input_manifest.json').read_text());families={k:manifest['feature_families'][k] for k in ['F2_efficiency','F3_role_pbp']}
 assert all(not c.startswith('ctx_') and c not in v4.TARGETS for cols in families.values() for c in cols)
 for fold in v4.FOLDS:
  assert fold['fit_end']<min(fold['stop'])<=max(fold['stop'])<min(fold['select'])<min(fold['calibrate'])<min(fold['assess'])
 return frame,families

def complexity(reg):
 nodes=[p[0].nodes for p in reg._predictors]
 return {'iterations':int(reg.n_iter_),'tree_count':len(nodes),'maximum_actual_depth':int(max(n['depth'].max() for n in nodes)),'mean_leaves':float(np.mean([n['is_leaf'].sum() for n in nodes])),'total_leaves':int(sum(n['is_leaf'].sum() for n in nodes))}

def tuned_fit(columns,cfg,train,stop,target):
 start=time.perf_counter();pre=v4.preprocess(columns);X=pre.fit_transform(train[columns+['position']]);Z=pre.transform(stop[columns+['position']]);y=train[target].to_numpy();best=None;bestscore=float('inf');stale=0;curves=[]
 params={k:v for k,v in cfg.items() if k!='name'};cap=params.pop('max_iter');reg=HistGradientBoostingRegressor(**params,early_stopping=False,warm_start=True,random_state=261013)
 signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120second fit cap')));signal.alarm(120)
 try:
  for iterations in range(25,cap+1,25):
   reg.set_params(max_iter=iterations);reg.fit(X,y);p=v4.floor(reg.predict(Z),target);score=v4.scoring(train,stop,target,p);trainp=v4.floor(reg.predict(X),target)
   curves.append({'iterations':iterations,'stopping_selection_score':score,'train_mae':float(np.mean(np.abs(trainp-y))),'stop_mae':float(np.mean(np.abs(p-stop[target])))})
   if score<bestscore:best=copy.deepcopy(reg);bestscore=score;stale=0
   else:stale+=1
   if iterations>=50 and stale>=4:break
 finally:signal.alarm(0)
 model=make_pipeline(pre,best)
 return model,{'config':cfg,'seconds':time.perf_counter()-start,'curve':curves,'best_stop_score':bestscore,'complexity':complexity(best),'fit_rows':len(train),'stop_rows':len(stop),'preprocessing_X_sha256':v4.hash_frame(train,columns+['position']),'training_y_sha256':v4.hash_frame(train,[target]),'fit_period_end':int(train.period.max()),'stop_periods':sorted(int(x) for x in stop.period.unique())}

def run():
 if (HERE/'freeze.json').exists():raise ValueError('Existing freeze: reproduce in separate versioned directory')
 started=time.perf_counter();frame,families=load();paths=[HERE/'SPECIFICATION.md',HERE/'run.py',CTX/'feature_matrix_full_precision.parquet',CTX/'exact_input_receipt.json',CTX/'freeze.json',CTX/'context_lineage.json',CTX/'predictions.csv',V4/'runner.py',V4/'models.py',V4/'rolling_predictions.csv',V4/'frozen_rolling_results.json',V3/'train.py',V3/'data.py',V3/'input_manifest.json']
 freeze={'input_dependency_hashes':{str(p.relative_to(ROOT)):v4.sha(p) for p in paths},'configs':CONFIGS,'old_configs':v4.v3.CONFIGS['tree'],'folds':v4.FOLDS,'features':families,'targets':v4.TARGETS,'versions':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'sklearn':sklearn.__version__,'joblib':joblib.__version__},'classification':'Retrospective previously inspected revised-data development','production_mutations':False,'future_labels_loaded':False,'fit_budget':180}
 (HERE/'freeze.json').write_text(json.dumps(freeze,indent=2)+'\n');(HERE/'models').mkdir();records={};metrics={};preds=[];rankings={}
 for fold in v4.FOLDS:
  for target in v4.TARGETS:
   train=frame[(frame.period<=fold['fit_end'])&frame[target].notna()].copy();parts={k:frame[frame.period.isin(fold[k])&frame[target].notna()].copy() for k in ['stop','select','calibrate','assess']};test=parts['assess'][parts['assess'].sunday_main].copy()
   for family,columns in families.items():
    for method,configs in [('old_tree',range(2)),('tuned_tree',CONFIGS)]:
     key='/'.join([fold['name'],target,family,method]);options=[];selectedmodel=None;selectedscore=float('inf');chosen=None
     for index,cfg in enumerate(configs):
      if time.perf_counter()-started>1200:raise TimeoutError('1200second global budget')
      with threadpool_limits(limits=1):
       if method=='old_tree':model,record=v4.fit('tree',columns,cfg,train,parts['stop'],target);record['complexity']=complexity(model[-1]);record['config']=v4.v3.CONFIGS['tree'][cfg]
       else:model,record=tuned_fit(columns,cfg,train,parts['stop'],target)
       pred=v4.predict(model,'tree',parts['select'],target,columns);score=v4.scoring(train,parts['select'],target,pred);record['selection_score']=score;record['selection_mae']=float(np.mean(np.abs(pred-parts['select'][target])));options.append(record)
       if score<selectedscore:selectedmodel=model;selectedscore=score;chosen=index
      print(key,index,'score',round(score,5),'seconds',round(record['seconds'],1),flush=True)
     model=selectedmodel;p=v4.predict(model,'tree',test,target,columns);cal=v4.calibration(parts['calibrate'],target,v4.predict(model,'tree',parts['calibrate'],target,columns));met,lo,hi=v4.summarize(test,target,p,cal);metrics[key]=met|{'calibration':cal};path=HERE/'models'/(key.replace('/','__')+'.joblib');joblib.dump(model,path,compress=3);records[key]={'options':options,'selected':chosen,'model_path':str(path.relative_to(HERE)),'model_sha256':v4.sha(path)}
     for i,point,lower,upper in zip(test.index,p,lo,hi):preds.append({'row_index':int(i),'fold':fold['name'],'target':target,'family':family,'method':method,'period':int(test.loc[i,'period']),'position':test.loc[i,'position'],'actual':float(test.loc[i,target]),'prediction':float(point),'lower90':float(lower),'upper90':float(upper)})
     if target=='fantasy_points_ppr':scored=test.copy();scored['prediction']=p;rankings[key]={'upside':v4.v3.upside(scored,'prediction'),'pairs':v4.v3.pairs(scored,'prediction')}
     print('ASSESS',key,'MAE',round(met['mae'],5),flush=True)
   (HERE/'progress.json').write_text(json.dumps({'complete_fold':fold['name'],'complete_target':target,'elapsed_seconds':time.perf_counter()-started},indent=2))
 predictions=pd.DataFrame(preds);predictions.to_parquet(HERE/'predictions.parquet',index=False);predictions.to_csv(HERE/'predictions.csv',index=False)
 (HERE/'results.json').write_text(json.dumps(freeze|{'runtime_seconds':time.perf_counter()-started,'records':records,'metrics':metrics,'rankings':rankings,'prediction_sha256':v4.sha(HERE/'predictions.parquet')},indent=2)+'\n');print('COMPLETE',time.perf_counter()-started,flush=True)
if __name__=='__main__':run()
