"""Frozen retrospective rolling training study; production-independent."""
from __future__ import annotations
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
import argparse,hashlib,importlib.util,json,signal,sys,time,warnings
from pathlib import Path
import joblib,numpy as np,pandas as pd
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
HERE=Path(__file__).resolve().parent;V3=HERE.parent/'expanded_v3';ROOT=HERE.parents[2]
sys.path.insert(0,str(V3));import train as v3
sys.path.insert(0,str(HERE));from models import ResidualNetwork,PositionNetwork,SETTINGS,preprocess,baseline,floor
TARGETS=['targets','carries','fantasy_points_ppr'];METHODS=['tree','prior_nn','residual_nn','position_nn']
FOLDS=[dict(name='A_2024',fit_end=202404,stop=[202405,202406],select=[202407],calibrate=[202408],assess=[202409,202410,202411,202412]),dict(name='B_2025',fit_end=202504,stop=[202505,202506],select=[202507],calibrate=[202508],assess=[202509,202510,202511,202512]),dict(name='C_2025',fit_end=202508,stop=[202509,202510],select=[202511],calibrate=[202512],assess=[202513,202514,202515,202516])]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def hash_frame(f,cols):return hashlib.sha256(f[cols].to_csv(index=False,float_format='%.10g').encode()).hexdigest()
def load():
 m=json.loads((V3/'input_manifest.json').read_text())
 if sha(V3/'feature_matrix.csv')!=m['matrix_sha256']:raise ValueError('V3 matrix changed')
 f=pd.read_csv(V3/'feature_matrix.csv');f=f[f.positive_snap_population].copy();f['period']=f.season*100+f.week;return f,m

def scoring(train,sample,target,pred):
 means=train.groupby('position')[target].apply(lambda x:float(np.mean(np.abs(x)))).to_dict()
 return float(np.mean([np.mean(np.abs(pred[(sample.position==p).to_numpy()]-sample.loc[sample.position==p,target].to_numpy()))/max(1,means[p]) for p in sorted(sample.position.unique())]))

def fit(method,columns,config,train,stop,target,epoch_template=None):
 started=time.perf_counter()
 with threadpool_limits(limits=1),warnings.catch_warnings(record=True) as caught:
  warnings.simplefilter('always')
  if method in ['residual_nn','position_nn']:
   model=(ResidualNetwork(columns,SETTINGS[config]) if method=='residual_nn' else PositionNetwork(columns,SETTINGS[config]))
   if method=='residual_nn':model.fit(train,target,stop,fixed_epochs=(epoch_template or {}).get('shared/residual'))
   else:model.fit(train,target,stop,epoch_template=epoch_template)
   metadata=model.metadata if method=='position_nn' else {'shared/residual':model.metadata}
  else:
   pre=preprocess(columns)
   if method=='tree':reg=HistGradientBoostingRegressor(**v3.CONFIGS['tree'][config],early_stopping=False,random_state=261013)
   else:reg=TransformedTargetRegressor(regressor=MLPRegressor(**v3.CONFIGS['neural'][config],activation='relu',solver='adam',learning_rate_init=.001,early_stopping=False,shuffle=True,random_state=261013),transformer=StandardScaler())
   model=make_pipeline(pre,reg);signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120-second comparator fit')));signal.alarm(120)
   try:model.fit(train[columns+['position']],train[target])
   finally:signal.alarm(0)
   metadata={'global':{'iterations':int(model[-1].n_iter_ if method=='tree' else model[-1].regressor_.n_iter_),'loss_curve':list(model[-1].regressor_.loss_curve_) if method=='prior_nn' else None}}
  pred=predict(model,method,stop,target,columns)
 record={'seconds':time.perf_counter()-started,'fit_rows':len(train),'stopping_rows':len(stop),'X_sha256':hash_frame(train,columns+['position']),'y_sha256':hash_frame(train,[target]),'fit_end_period':int(train.period.max()),'stop_periods':sorted(int(v) for v in stop.period.unique()),'training_metadata':metadata,'warnings':[str(w.message) for w in caught],'training_actual_mae':float(np.mean(np.abs(predict(model,method,train,target,columns)-train[target]))),'stopping_actual_mae':float(np.mean(np.abs(pred-stop[target])))}
 return model,record

def predict(model,method,f,target,columns):
 p=model.predict(f) if method in ['residual_nn','position_nn'] else model.predict(f[columns+['position']]);return floor(p,target)

def calibration(cal,target,pred):
 residual=np.abs(cal[target].to_numpy()-pred)
 def radius(vals):
  return float(np.quantile(vals,min(1,np.ceil((len(vals)+1)*.9)/len(vals)),method='higher'))
 pooled=radius(residual);positions={}
 for pos in sorted(cal.position.unique()):
  vals=residual[(cal.position==pos).to_numpy()];positions[pos]={'radius':radius(vals) if len(vals)>=30 else pooled,'n':len(vals),'pooled_fallback':len(vals)<30}
 return {'nominal_coverage':.9,'pooled_radius':pooled,'position':positions,'calibration_periods':sorted(int(x) for x in cal.period.unique()),'guarantee':False,'scope':'Empirical marginal residual intervals; time drift/small groups; no calibrated ceilings/joint lineup distribution'}

def summarize(f,target,pred,cal,prob=None):
 delta=pred-f[target].to_numpy();r={'n':len(f),'mae':float(np.mean(np.abs(delta))),'rmse':float(np.sqrt(np.mean(delta**2))),'bias':float(np.mean(delta))}
 radii=np.array([cal['position'].get(p,{'radius':cal['pooled_radius']})['radius'] for p in f.position]);lower=pred-radii;upper=pred+radii
 if target!='fantasy_points_ppr':lower=np.maximum(0,lower)
 y=f[target].to_numpy();r['interval']={'empirical_coverage':float(np.mean((y>=lower)&(y<=upper))),'mean_width':float(np.mean(upper-lower)),'upper_miss_rate':float(np.mean(y>upper)),'lower_miss_rate':float(np.mean(y<lower))}
 groups={'position':f.position,'observed_zero':f[target]==0,'high_workload':f[target]>=dict(targets=6,carries=10,fantasy_points_ppr=15)[target],'sparse_history':f.history_count<=1,'team_changed':f.team_changed_diagnostic,'workload_shift':(f[target]-f[target+'_last']).abs()>=4}
 for name,labels in groups.items():
  r[name]={}
  for value in sorted(labels.unique()):
   mask=(labels==value).to_numpy();dlt=delta[mask];r[name][str(value)]={'n':int(mask.sum()),'descriptive_only':int(mask.sum())<30,'mae':float(np.mean(np.abs(dlt))),'rmse':float(np.sqrt(np.mean(dlt**2))),'bias':float(np.mean(dlt)),'coverage':float(np.mean((y[mask]>=lower[mask])&(y[mask]<=upper[mask])))}
 if prob is not None:
  mask=np.isfinite(prob);actual=(y>0).astype(float);r['positive_probability']={'n':int(mask.sum()),'brier':float(np.mean((actual[mask]-prob[mask])**2)),'bins':[]}
  for a,b in [(0,.1),(.1,.3),(.3,.6),(.6,.9),(.9,1.00001)]:
   selected=mask&(prob>=a)&(prob<b)
   if selected.any():r['positive_probability']['bins'].append({'lower':a,'upper':min(b,1),'n':int(selected.sum()),'mean_probability':float(np.mean(prob[selected])),'observed_positive_rate':float(np.mean(actual[selected]))})
 return r,lower,upper

def inspect_history():
 sources=[ROOT/'docs/slate_analysis_report_2024_2025.md',ROOT/'docs/matchup_ablation_full_2024_2025_v4_validation_blend.json',V3/'results.json',HERE.parent/'revised_v2/results.json']
 audit={'historical_outcome_blindness_proven':False,'evidence':{str(p.relative_to(ROOT)):{'sha256':sha(p),'meaning':'Prior broad2024/25 evaluations or inspected neural diagnostic outcomes'} for p in sources},'known_neural_inspection':{'2025W18':'V2test','2025W13–17':'V2/V3validation','2026W4/W5':'V3primary now diagnostics'},'historical_retrospective_only':True,'prospective_reserved_weeks':[202606,202607,202608,202609],'future_source_labels_loaded':False,'requirements':'Before each Sunday12:00ET decision save immutable forecasts/model/input hashes; no tuning/promoting from future observed results; fixed model/update policy; report missingness'}
 (HERE/'outcome_inspection_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
 return audit

def run_rolling():
 start=time.perf_counter();frame,manifest=load();inspect_history();families={k:manifest['feature_families'][k] for k in ['F2_efficiency','F3_role_pbp']};records={};metrics={};pred_rows=[];ranking={};pairing={}
 for fold in FOLDS:
  subsets={name:frame[frame.period.isin(fold[name])] for name in ['stop','select','calibrate','assess']};subsets['train']=frame[frame.period<=fold['fit_end']]
  assert max(subsets['train'].period)<min(subsets['stop'].period)<min(subsets['select'].period)<min(subsets['calibrate'].period)<min(subsets['assess'].period)
  for target in TARGETS:
   data={k:g[g[target].notna()].copy() for k,g in subsets.items()};train=data['train'];assessment=data['assess'][data['assess'].sunday_main].copy()
   priors=train.groupby('position')[target].mean().to_dict();hc=floor(baseline(data['calibrate'],target,priors),target);ha=floor(baseline(assessment,target,priors),target);cal=calibration(data['calibrate'],target,hc);base_result,lo,hi=summarize(assessment,target,ha,cal);metrics[fold['name']+'/'+target+'/history']=base_result
   for family,columns in families.items():
    for method in METHODS:
     key=fold['name']+'/'+target+'/'+family+'/'+method;options=[];fitted=[]
     for cfg in [0,1]:
      model,record=fit(method,columns,cfg,train,data['stop'],target);p=predict(model,method,data['select'],target,columns);record['selection_score']=scoring(train,data['select'],target,p);record['configuration']=cfg;record['selection_mae']=float(np.mean(np.abs(p-data['select'][target])));options.append(record);fitted.append(model)
      print('rolling',key,cfg,'score',round(record['selection_score'],4),'seconds',round(record['seconds'],2),flush=True)
     chosen=min(range(2),key=lambda c:(options[c]['selection_score'],c));model=fitted[chosen];records[key]={'options':options,'selected':chosen};p=predict(model,method,assessment,target,columns);c=predict(model,method,data['calibrate'],target,columns);cal=calibration(data['calibrate'],target,c);prob=model.predict_with_probability(assessment)[1] if method=='position_nn' and target!='fantasy_points_ppr' else None;score,lo,hi=summarize(assessment,target,p,cal);metrics[key]=score|{'calibration':cal,'configuration':chosen}
     for i,point,l,u in zip(assessment.index,p,lo,hi):pred_rows.append({'row_index':int(i),'fold':fold['name'],'target':target,'family':family,'method':method,'prediction':float(point),'lower90':float(l),'upper90':float(u)})
     if target=='fantasy_points_ppr':
      assessment['prediction']=p;ranking[key]=v3.upside(assessment,'prediction');pairing[key]=v3.pairs(assessment,'prediction')
  (HERE/'rolling_progress.json').write_text(json.dumps({'complete_fold':fold['name'],'metrics':metrics,'seconds':time.perf_counter()-start},indent=2)+'\n')
 selected={};epochs={}
 for target in TARGETS:
  for family in families:
   for method in METHODS:
    key=target+'/'+family+'/'+method;averages=[float(np.mean([records[f['name']+'/'+key]['options'][cfg]['selection_score'] for f in FOLDS])) for cfg in [0,1]];chosen=min(range(2),key=lambda c:(averages[c],c));selected[key]={'configuration':chosen,'mean_selection_scores':averages}
    if method in ['residual_nn','position_nn']:
     collected={}
     for fold in FOLDS:
      heads=records[fold['name']+'/'+key]['options'][chosen]['training_metadata']
      for head,item in heads.items():
       if 'best_epoch' in item:collected.setdefault(head,[]).append(item['best_epoch'])
     template={head:int(np.median(values)) for head,values in collected.items()};default=int(np.median([e for vals in collected.values() for e in vals])) if collected else 100
     for head in ['shared/residual']+[p+'/'+h for p in ['QB','RB','WR','TE'] for h in ['residual','classifier','amount']]:template.setdefault(head,max(1,default))
     epochs[key]=template
 result={'study':'retrospective chronological development; no untouchedhistoricalclaim','folds':FOLDS,'all_fit_selection_records':records,'metrics':metrics,'upside_rankings':ranking,'pair_rankings':pairing,'global_selections':selected,'fixed_epoch_templates':epochs,'runtime_seconds':time.perf_counter()-start,'spec_sha256':sha(HERE/'SPECIFICATION.md'),'models_sha256':sha(HERE/'models.py'),'runner_sha256':sha(Path(__file__)),'matrix_sha256':manifest['matrix_sha256']}
 (HERE/'rolling_predictions.csv').write_text(pd.DataFrame(pred_rows).to_csv(index=False,float_format='%.8g'))
 with (HERE/'frozen_rolling_results.json').open('x') as output:json.dump(result,output,indent=2)
 print('Rolling complete',round(result['runtime_seconds'],2),'seconds')


def final_diagnostics():
 start=time.perf_counter();frame,manifest=load();rolling=json.loads((HERE/'frozen_rolling_results.json').read_text())
 for path,key in [('models.py','models_sha256'),('runner.py','runner_sha256'),('SPECIFICATION.md','spec_sha256')]:
  if sha(HERE/path)!=rolling[key]:raise ValueError('Frozen training code/spec changed')
 train=frame[frame.period<=202602];caldata=frame[frame.period==202603];assessment=frame[frame.period.isin([202604,202605])&frame.sunday_main].copy();dummy=train[train.period==train.period.max()]
 assert not set(train.period)&set(assessment.period)
 out=assessment[['player_master_id','name','position','team','game_id','season','week',*TARGETS]].copy();metrics={};artifacts={};rank={};pairs={}
 (HERE/'fitted_models').mkdir(exist_ok=True)
 for target in TARGETS:
  tr=train[train[target].notna()];calf=caldata[caldata[target].notna()];test=assessment[assessment[target].notna()];stopdummy=dummy[dummy[target].notna()]
  priors=tr.groupby('position')[target].mean().to_dict();p=floor(baseline(test,target,priors),target);c=floor(baseline(calf,target,priors),target);interval=calibration(calf,target,c);met,lo,hi=summarize(test,target,p,interval);metrics[target+'/history']=met;out.loc[test.index,target+'_history']=p
  for family in ['F2_efficiency','F3_role_pbp']:
   columns=manifest['feature_families'][family]
   for method in METHODS:
    key=target+'/'+family+'/'+method;cfg=rolling['global_selections'][key]['configuration'];template=rolling['fixed_epoch_templates'].get(key)
    model,metadata=fit(method,columns,cfg,tr,stopdummy,target,epoch_template=template);p=predict(model,method,test,target,columns);c=predict(model,method,calf,target,columns);interval=calibration(calf,target,c);prob=model.predict_with_probability(test)[1] if method=='position_nn' and target!='fantasy_points_ppr' else None;met,lo,hi=summarize(test,target,p,interval,prob);metrics[key]=met|{'calibration':interval}
    out.loc[test.index,target+'_'+family+'_'+method]=p;out.loc[test.index,target+'_'+family+'_'+method+'_lower90']=lo;out.loc[test.index,target+'_'+family+'_'+method+'_upper90']=hi
    path=HERE/'fitted_models'/(key.replace('/','__')+'.joblib');joblib.dump(model,path,compress=3);artifacts[key]={'path':str(path.relative_to(HERE)),'sha256':sha(path),'configuration':cfg,'fit_metadata':metadata,'fixed_epochs':template,'final_training_through':202602,'calibration_only':202603,'stopping_metadata_note':'Final fixed-epoch curves use training-tail rows for diagnostics only, no adaptive stopping; historical epoch selection remains frozen'}
    if target=='fantasy_points_ppr':
     scored=test.copy();scored['prediction']=p;rank[key]=v3.upside(scored,'prediction');pairs[key]=v3.pairs(scored,'prediction')
    print('finaldiagnostic',key,'mae',round(met['mae'],4),'seconds',round(metadata['seconds'],2),flush=True)
 out.to_csv(HERE/'diagnostic_predictions_2026w4_w5.csv',index=False,float_format='%.8g')
 result={'classification':'Already inspectedW4/W5 diagnostic; not independentholdout','training_through':202602,'calibration_only':202603,'metrics':metrics,'upside_rankings':rank,'pair_rankings':pairs,'fitted_artifacts':artifacts,'runtime_seconds':time.perf_counter()-start,'frozen_rolling_sha256':sha(HERE/'frozen_rolling_results.json')}
 (HERE/'diagnostic_results.json').write_text(json.dumps(result,indent=2)+'\n');print('Diagnostics complete',round(result['runtime_seconds'],2),'seconds')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--rolling',action='store_true');p.add_argument('--diagnostics',action='store_true');a=p.parse_args()
 if a.rolling:run_rolling()
 elif a.diagnostics:final_diagnostics()
 else:p.error('Choose --rolling or --diagnostics')
