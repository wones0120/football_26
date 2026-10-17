"""Prespecified wider/deeper neural experiment; production independent."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
import sys,json,time,importlib.util,platform
from pathlib import Path
import numpy as np,pandas as pd,joblib,sklearn
from threadpoolctl import threadpool_limits
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];CTX=HERE.parent/'neural_game_context_20261013';V4=HERE.parent/'neural_workload_benchmark_20261013/training_v4';V3=V4.parent/'expanded_v3'
spec=importlib.util.spec_from_file_location('capacity_v4',V4/'runner.py');v4=importlib.util.module_from_spec(spec);spec.loader.exec_module(v4)
sys.path.insert(0,str(HERE));import capacity_models as cm
CONFIGS=[dict(name='current16',hidden_layer_sizes=(16,8),alpha=.05,batch_size=128,epoch_cap=300),dict(name='current32',hidden_layer_sizes=(32,16),alpha=.2,batch_size=256,epoch_cap=300),dict(name='wide64',hidden_layer_sizes=(64,32),alpha=.2,batch_size=256,epoch_cap=500),dict(name='wide128',hidden_layer_sizes=(128,64),alpha=.5,batch_size=256,epoch_cap=500,learning_rate_init=.0007),dict(name='deep32',hidden_layer_sizes=(32,16,8),alpha=.2,batch_size=256,epoch_cap=500),dict(name='deep64',hidden_layer_sizes=(64,32,16),alpha=.2,batch_size=256,epoch_cap=500)]

def load():
 receipt=json.loads((CTX/'exact_input_receipt.json').read_text());assert v4.sha(CTX/receipt['path'])==receipt['sha256']
 f=pd.read_parquet(CTX/receipt['path']);f=f[f.positive_snap_population].copy();m=json.loads((V3/'input_manifest.json').read_text());families={k:m['feature_families'][k] for k in ['F2_efficiency','F3_role_pbp']}
 assert f.index.is_unique and all(not c.startswith('ctx_') and c not in v4.TARGETS for cols in families.values() for c in cols)
 return f,families

def neural_fit(method,columns,cfg,train,stop,target):
 start=time.perf_counter();model=(cm.ResidualNetwork if method=='residual_nn' else cm.PositionNetwork)(columns,cfg)
 with threadpool_limits(limits=1):model.fit(train,target,stop)
 heads=model.metadata if method=='position_nn' else {'shared/residual':model.metadata}
 return model,{'config':cfg,'seconds':time.perf_counter()-start,'fit_rows':len(train),'stop_rows':len(stop),'X_sha256':v4.hash_frame(train,columns+['position']),'y_sha256':v4.hash_frame(train,[target]),'fit_end_period':int(train.period.max()),'stop_periods':sorted(int(v) for v in stop.period.unique()),'training_metadata':heads,'parameter_count':sum(x.get('parameter_count',0) for x in heads.values()),'training_actual_mae':float(np.mean(np.abs(model.predict(train)-train[target]))),'stopping_actual_mae':float(np.mean(np.abs(model.predict(stop)-stop[target])))}

def run():
 if (HERE/'freeze.json').exists():raise ValueError('Existing frozen run: use separate directory to reproduce')
 start=time.perf_counter();frame,families=load();paths=[HERE/'SPECIFICATION.md',HERE/'run.py',HERE/'capacity_models.py',CTX/'feature_matrix_full_precision.parquet',CTX/'exact_input_receipt.json',V4/'runner.py',V4/'models.py',V4/'frozen_rolling_results.json',V3/'train.py',V3/'input_manifest.json']
 freeze={'dependency_hashes':{str(p.relative_to(ROOT)):v4.sha(p) for p in paths},'configs':CONFIGS,'folds':v4.FOLDS,'features':families,'targets':v4.TARGETS,'versions':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'sklearn':sklearn.__version__},'classification':'Retrospective previously inspected historical outcomes; no heldout claim','fit_budget':216,'seconds_budget':1200,'production_mutations':False,'future_labels_loaded':False}
 (HERE/'freeze.json').write_text(json.dumps(freeze,indent=2)+'\n');(HERE/'models').mkdir();records={};metrics={};preds=[];curves=[];ranks={}
 for fold in v4.FOLDS:
  for target in v4.TARGETS:
   train=frame[(frame.period<=fold['fit_end'])&frame[target].notna()].copy();parts={k:frame[frame.period.isin(fold[k])&frame[target].notna()].copy() for k in ['stop','select','calibrate','assess']};test=parts['assess'][parts['assess'].sunday_main].copy()
   for family,columns in families.items():
    for method in ['residual_nn','position_nn']:
     key='/'.join([fold['name'],target,family,method]);options=[];models=[]
     for index,cfg in enumerate(CONFIGS):
      if time.perf_counter()-start>1200:raise TimeoutError('1200sec global cap')
      model,record=neural_fit(method,columns,cfg,train,parts['stop'],target);p=model.predict(parts['select']);record['selection_score']=v4.scoring(train,parts['select'],target,p);record['selection_mae']=float(np.mean(np.abs(p-parts['select'][target])));options.append(record);models.append(model)
      for head,meta in record['training_metadata'].items():
       for point in meta.get('curve',[]):curves.append(dict(fold=fold['name'],target=target,family=family,method=method,config=cfg['name'],head=head,**point))
      print(key,cfg['name'],'score',round(record['selection_score'],5),'seconds',round(record['seconds'],2),flush=True)
     selections={'current_'+method:min(range(2),key=lambda c:(options[c]['selection_score'],c)),'capacity_'+method:min(range(6),key=lambda c:(options[c]['selection_score'],c))}
     records[key]={'options':options,'selections':selections,'models':{}}
     for label,index in selections.items():
      model=models[index];p=model.predict(test);cal=v4.calibration(parts['calibrate'],target,model.predict(parts['calibrate']));prob=model.predict_with_probability(test)[1] if method=='position_nn' and target!='fantasy_points_ppr' else None;met,lo,hi=v4.summarize(test,target,p,cal,prob);fullkey='/'.join([fold['name'],target,family,label]);metrics[fullkey]=met|{'calibration':cal,'selected_config':CONFIGS[index]['name']};path=HERE/'models'/(fullkey.replace('/','__')+'.joblib');joblib.dump(model,path,compress=3);records[key]['models'][label]={'index':index,'path':str(path.relative_to(HERE)),'sha256':v4.sha(path)}
      for i,point,lower,upper in zip(test.index,p,lo,hi):preds.append(dict(row_index=int(i),fold=fold['name'],target=target,family=family,method=label,period=int(test.loc[i,'period']),position=test.loc[i,'position'],actual=float(test.loc[i,target]),prediction=float(point),lower90=float(lower),upper90=float(upper)))
      if target=='fantasy_points_ppr':scored=test.copy();scored['prediction']=p;ranks[fullkey]={'upside':v4.v3.upside(scored,'prediction'),'pairs':v4.v3.pairs(scored,'prediction')}
      print('ASSESS',fullkey,round(met['mae'],5),flush=True)
     # All per-configuration predictions are descriptive diagnostics; never feed selection.
     for index,model in enumerate(models):
      p=model.predict(test)
      for i,point in zip(test.index,p):preds.append(dict(row_index=int(i),fold=fold['name'],target=target,family=family,method=method+'__'+CONFIGS[index]['name'],period=int(test.loc[i,'period']),position=test.loc[i,'position'],actual=float(test.loc[i,target]),prediction=float(point),lower90=np.nan,upper90=np.nan))
   (HERE/'progress.json').write_text(json.dumps(dict(complete_fold=fold['name'],complete_target=target,elapsed_seconds=time.perf_counter()-start),indent=2)+'\n')
 pd.DataFrame(preds).to_parquet(HERE/'predictions.parquet',index=False);pd.DataFrame(curves).to_csv(HERE/'learning_curves.csv',index=False)
 result=freeze|{'runtime_seconds':time.perf_counter()-start,'records':records,'metrics':metrics,'rankings':ranks,'predictions_sha256':v4.sha(HERE/'predictions.parquet')};(HERE/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('COMPLETE',result['runtime_seconds'],flush=True)
if __name__=='__main__':run()
