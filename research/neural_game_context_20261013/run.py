"""Paired chronological context ablations, isolated from production."""
import os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='1'
import sys,json,time,importlib.util
from pathlib import Path
import numpy as np,pandas as pd,joblib
HERE=Path(__file__).resolve().parent
V4=HERE.parent/'neural_workload_benchmark_20261013/training_v4'
sys.path.insert(0,str(HERE));from context import build_matrix,FAMILIES,sha
spec=importlib.util.spec_from_file_location('context_v4_runner',V4/'runner.py');v4=importlib.util.module_from_spec(spec);spec.loader.exec_module(v4)
METHODS=['residual_nn','position_nn','tree']

def run():
 if (HERE/'results.json').exists():raise ValueError('Preserve frozen result: use a new versioned directory')
 started=time.perf_counter();frame,coverage=build_matrix();frame=frame[frame.positive_snap_population].copy();base=coverage['base_features']
 freeze={'spec_sha256':sha(HERE/'SPECIFICATION.md'),'context_sha256':sha(HERE/'context.py'),'runner_sha256':sha(HERE/'run.py'),'v4_model_sha256':sha(V4/'models.py'),'v4_runner_sha256':sha(V4/'runner.py'),'matrix_sha256':coverage['context_matrix_sha256'],'folds':v4.FOLDS,'families':FAMILIES,'methods':METHODS,'targets':v4.TARGETS,'classification':'Retrospective revised-data development; no original chronology/untouched holdout claim','future_2026w6_outcomes_loaded':False}
 with (HERE/'freeze.json').open('x') as out:json.dump(freeze,out,indent=2)
 records={};metrics={};predictions=[];rankings={};(HERE/'fitted_models').mkdir(exist_ok=True)
 for fold in v4.FOLDS:
  for target in v4.TARGETS:
   parts={k:frame[frame.period.isin(fold[k]) & frame[target].notna()].copy() for k in ['stop','select','calibrate','assess']};train=frame[(frame.period<=fold['fit_end']) & frame[target].notna()];test=parts['assess'][parts['assess'].sunday_main].copy()
   for family,extra in FAMILIES.items():
    columns=base+extra
    for method in METHODS:
     key='/'.join([fold['name'],target,family,method]);options=[];models=[]
     for config in [0,1]:
      model,record=v4.fit(method,columns,config,train,parts['stop'],target);pred=v4.predict(model,method,parts['select'],target,columns);record['selection_score']=v4.scoring(train,parts['select'],target,pred);record['config']=config;options.append(record);models.append(model)
     chosen=min(range(2),key=lambda c:(options[c]['selection_score'],c));model=models[chosen];p=v4.predict(model,method,test,target,columns);cp=v4.predict(model,method,parts['calibrate'],target,columns);cal=v4.calibration(parts['calibrate'],target,cp);met,lo,hi=v4.summarize(test,target,p,cal)
     met['context_subgroups']={}
     for field in ['ctx_home','ctx_neutral','ctx_retractable','ctx_short_rest','ctx_teammate_receiving_absent_last_targets','ctx_opponent_defense_absent_last_snaps']:
      groups=test[field].map(lambda value:'unknown' if pd.isna(value) else 'positive' if value>0 else 'zero')
      met['context_subgroups'][field]={str(label):{'n':int(mask.sum()),'mae':float(np.mean(np.abs(p[mask.to_numpy()]-test.loc[mask,target]))),'bias':float(np.mean(p[mask.to_numpy()]-test.loc[mask,target]))} for label in groups.unique() for mask in [groups==label]}
     metrics[key]=met;path=HERE/'fitted_models'/(key.replace('/','__')+'.joblib');joblib.dump(model,path,compress=3);records[key]={'options':options,'selected':chosen,'artifact':str(path.relative_to(HERE)),'artifact_sha256':sha(path)}
     for index,point in zip(test.index,p):predictions.append({'row_index':int(index),'fold':fold['name'],'period':int(test.loc[index,'period']),'position':test.loc[index,'position'],'target':target,'family':family,'method':method,'actual':float(test.loc[index,target]),'prediction':float(point)})
     if target=='fantasy_points_ppr':
      ranked=test.copy();ranked['prediction']=p;rankings[key]=v4.v3.upside(ranked,'prediction')
     print(key,'MAE',round(met['mae'],4),'total_seconds',round(time.perf_counter()-started,1),flush=True)
   (HERE/'progress.json').write_text(json.dumps({'complete_fold':fold['name'],'complete_target':target,'metrics':{k:{'mae':v['mae'],'bias':v['bias']} for k,v in metrics.items()},'elapsed_seconds':time.perf_counter()-started},indent=2)+'\n')
   pd.DataFrame(predictions).to_csv(HERE/'predictions_partial.csv',index=False)
 preds=pd.DataFrame(predictions);preds.to_csv(HERE/'predictions.csv',index=False,float_format='%.10g');summary=[];rng=np.random.default_rng(261013)
 for (target,method),group in preds.groupby(['target','method']):
  control=group[group.family=='baseline'].set_index(['fold','row_index']);weeks=sorted(control.period.unique())
  for family in FAMILIES:
   trial=group[group.family==family].set_index(['fold','row_index']).loc[control.index];assert (trial.actual==control.actual).all()
   delta=(trial.prediction-trial.actual).abs()-(control.prediction-control.actual).abs();week=pd.DataFrame({'period':control.period,'delta':delta}).groupby('period').delta.agg(['sum','count']);boot=[]
   for _ in range(2000):
    sample=week.iloc[rng.integers(0,len(week),len(week))];boot.append(sample['sum'].sum()/sample['count'].sum())
   summary.append({'target':target,'method':method,'family':family,'n':len(trial),'weeks':len(week),'mae':float(np.mean(np.abs(trial.prediction-trial.actual))),'bias':float(np.mean(trial.prediction-trial.actual)),'paired_mae_delta':float(delta.mean()),'week_cluster_bootstrap_95':np.quantile(boot,[.025,.975]).tolist(),'improved_weeks':int((week['sum']<0).sum()),'position':{pos:{'n':int(mask.sum()),'mae':float(np.mean(np.abs(trial.loc[mask,'prediction']-trial.loc[mask,'actual']))),'bias':float(np.mean(trial.loc[mask,'prediction']-trial.loc[mask,'actual'])),'paired_mae_delta':float(delta.loc[mask].mean())} for pos in trial.position.unique() for mask in [trial.position==pos]}})
 result=freeze|{'runtime_seconds':time.perf_counter()-started,'summary':summary,'metrics':metrics,'selection_records':records,'rankings':rankings,'prediction_sha256':sha(HERE/'predictions.csv'),'library_versions':{'numpy':np.__version__,'pandas':pd.__version__,'sklearn':v4.v3.sklearn.__version__ if hasattr(v4.v3,'sklearn') else __import__('sklearn').__version__},'uncertainty_note':'Paired whole-week bootstrap descriptive; only12 blocks, temporal dependence and historical inspection limit inference.'}
 with (HERE/'results.json').open('x') as out:json.dump(result,out,indent=2)
 print('COMPLETE',round(result['runtime_seconds'],1),flush=True)
if __name__=='__main__':run()
