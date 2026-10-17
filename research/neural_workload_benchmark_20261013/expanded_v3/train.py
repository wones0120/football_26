"""Equal-budget validation tuning, then fixed-model W4/W5 research evaluation."""
from __future__ import annotations
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
import argparse,hashlib,json,signal,time,warnings
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer,TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder,StandardScaler
from threadpoolctl import threadpool_limits
import data as d
HERE=Path(__file__).resolve().parent;SEED=261013
CONFIGS={'tree':[{'max_iter':150,'max_leaf_nodes':15,'learning_rate':.05,'l2_regularization':1,'min_samples_leaf':30},
                 {'max_iter':200,'max_leaf_nodes':31,'learning_rate':.05,'l2_regularization':2,'min_samples_leaf':30}],
         'neural':[{'hidden_layer_sizes':(16,8),'alpha':.01,'batch_size':128,'max_iter':300},
                   {'hidden_layer_sizes':(32,16),'alpha':.1,'batch_size':256,'max_iter':300}]}

def frame_hash(f,cols):return hashlib.sha256(f[cols].to_csv(index=False,float_format='%.10g').encode()).hexdigest()
def load():
 m=json.loads((HERE/'input_manifest.json').read_text())
 for path,k in [('feature_matrix.csv','matrix_sha256'),('SPECIFICATION.md','spec_sha256'),('data.py','adapter_sha256')]:
  if d.sha(HERE/path)!=m[k]:raise ValueError('Frozen input/spec changed: '+path)
 f=pd.read_csv(HERE/'feature_matrix.csv');return f[f.positive_snap_population].copy(),m

def make_model(kind,columns,config):
 pre=ColumnTransformer([('numeric',make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),StandardScaler()),columns),('position',OneHotEncoder(handle_unknown='ignore',sparse_output=False),['position'])])
 if kind=='tree':reg=HistGradientBoostingRegressor(**config,early_stopping=False,random_state=SEED)
 else:reg=TransformedTargetRegressor(regressor=MLPRegressor(**config,activation='relu',solver='adam',learning_rate_init=.001,early_stopping=False,shuffle=True,random_state=SEED),transformer=StandardScaler())
 return make_pipeline(pre,reg)
def predict(model,f,target,cols):
 p=model.predict(f[cols+['position']]);return np.maximum(0,p) if target!='fantasy_points_ppr' else p

def fit(kind,cols,config,f,target):
 signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120sec fit bound')));signal.alarm(120);start=time.perf_counter()
 with warnings.catch_warnings(record=True) as caught:
  warnings.simplefilter('always')
  try:
   with threadpool_limits(limits=1):model=make_model(kind,cols,config).fit(f[cols+['position']],f[target])
  finally:signal.alarm(0)
 return model,{'fit_seconds':time.perf_counter()-start,'warnings':[str(w.message) for w in caught],'train_rows':len(f),'X_sha256':frame_hash(f,cols+['position']),'y_sha256':frame_hash(f,[target]),'iterations':int(model[-1].n_iter_ if kind=='tree' else model[-1].regressor_.n_iter_)}

def tune():
 start=time.perf_counter();frame,manifest=load();records={};selected={}
 train=frame[frame.split=='tuning_train'];val=frame[frame.split=='validation']
 assert max(train.season*100+train.week)<min(val.season*100+val.week)
 for target in d.TARGETS:
  tr=train[train[target].notna()];validation=val[val[target].notna()]
  for family,cols in d.VARIANTS.items():
   for kind,options in CONFIGS.items():
    key=target+'/'+family+'/'+kind;choices=[]
    for i,config in enumerate(options):
     model,meta=fit(kind,cols,config,tr,target);p=predict(model,validation,target,cols);mae=float(np.mean(np.abs(p-validation[target].to_numpy())))
     choices.append({'configuration':i,'parameters':config,'validation_mae':mae,'validation_rows':len(validation),**meta})
     print('validation',key,i,'MAE',round(mae,4),'seconds',round(meta['fit_seconds'],2),flush=True)
    records[key]=choices;selected[key]=min(range(len(choices)),key=lambda i:(choices[i]['validation_mae'],i))
 result={'selection_criterion':'earlier validation MAE only; no2026test outcomes used','selected':selected,'all_candidates':records,'matrix_sha256':manifest['matrix_sha256'],'spec_sha256':manifest['spec_sha256'],'trainer_sha256':d.sha(Path(__file__)),'tune_seconds':time.perf_counter()-start}
 with (HERE/'frozen_selections.json').open('x') as output:json.dump(result,output,indent=2)
 print('Selections frozen',round(result['tune_seconds'],2),'sec')

def metrics(y,p):
 delta=p-y
 return {'n':len(y),'descriptive_only':len(y)<30,'mae':float(np.mean(np.abs(delta))),'rmse':float(np.sqrt(np.mean(delta**2))),'bias':float(np.mean(delta)),'residual_quantiles':{str(q):float(np.quantile(-delta,q)) for q in [.1,.5,.9]}}
def diagnostics(f,target,p):
 r=metrics(f[target].to_numpy(),p)
 labels={'position':f.position,'week':f.week,'observed_zero':f[target]==0,'sparse_history':f.history_count<=1,'high_opportunity':f[target]>=dict(targets=6,carries=10,fantasy_points_ppr=15)[target],'workload_shift':(f[target]-f[target+'_last']).abs()>=4}
 for name,group in labels.items():
  r[name]={str(value):metrics(f.loc[group==value,target].to_numpy(),p[(group==value).to_numpy()]) for value in sorted(group.unique())}
 g=f.assign(prediction=p).groupby(['week','team'])[[target,'prediction']].sum();r['partial_team_aggregate']=metrics(g[target].to_numpy(),g.prediction.to_numpy())
 return r

def upside(f,prediction):
 # Mean ranking diagnostics, no uncertainty/ceiling calibration assertion.
 records=[];topk={'QB':3,'RB':8,'WR':10,'TE':5};threshold={'QB':25,'RB':20,'WR':20,'TE':15}
 for (week,pos),g in f[f.fantasy_points_ppr.notna()].groupby(['week','position']):
  k=min(topk[pos],len(g));ordered=g.sort_values([prediction,'player_master_id'],ascending=[False,True]);chosen=ordered.head(k);actual=g.sort_values(['fantasy_points_ppr','player_master_id'],ascending=[False,True]).head(k)
  boom=g.fantasy_points_ppr>=threshold[pos];hits=int((chosen.fantasy_points_ppr>=threshold[pos]).sum());ideal=np.sort(np.maximum(0,g.fantasy_points_ppr.to_numpy()))[::-1][:k];gains=np.maximum(0,chosen.fantasy_points_ppr.to_numpy());weights=1/np.log2(np.arange(k)+2)
  records.append({'week':int(week),'position':pos,'n':len(g),'k':k,'boom_count':int(boom.sum()),'boom_precision_at_k':hits/k,'boom_recall_at_k':hits/int(boom.sum()) if boom.sum() else None,'actual_topk_overlap':len(set(chosen.player_master_id)&set(actual.player_master_id))/k,'ndcg_at_k':float(np.sum(gains*weights)/np.sum(ideal*weights)) if np.sum(ideal*weights)>0 else None,'selected_actual_mean_ppr':float(chosen.fantasy_points_ppr.mean())})
 return records

def pairs(f,prediction):
 records=[]
 for week,g in f[f.fantasy_points_ppr.notna()].groupby('week'):
  candidates=[]
  for (game,club),members in g.groupby(['game_id','team']):
   for _,qb in members[members.position=='QB'].iterrows():
    for _,receiver in members[members.position.isin(['WR','TE'])].iterrows():
     candidates.append({'pair':qb.player_master_id+'/'+receiver.player_master_id,'game_id':game,'predicted':qb[prediction]+receiver[prediction],'actual':qb.fantasy_points_ppr+receiver.fantasy_points_ppr})
  pool=pd.DataFrame(candidates);ranked=pool.sort_values(['predicted','pair'],ascending=[False,True]).head(10);ideal=pool.sort_values(['actual','pair'],ascending=[False,True]).head(10)
  records.append({'week':int(week),'candidate_pairs':len(pool),'top10_actual_rank_overlap':len(set(ranked.pair)&set(ideal.pair))/len(ranked),'top10_actual_mean_ppr':float(ranked.actual.mean()),'top10_predicted_mean_ppr':float(ranked.predicted.mean()),'diagnostic_only':'Conditional same-team QB+WR/TE pairs; no salaries, lineup constraints or independent-pair inference'})
 return records

def evaluate():
 start=time.perf_counter();frame,manifest=load();selection=json.loads((HERE/'frozen_selections.json').read_text())
 if selection['trainer_sha256']!=d.sha(Path(__file__)) or selection['matrix_sha256']!=manifest['matrix_sha256']:raise ValueError('Frozen configuration/trainer/input changed')
 train=frame[frame.final_train];test=frame[frame.split=='test'].copy();assert max(train.season*100+train.week)<=202603 and min(test.season*100+test.week)==202604
 summary={};metadata={}
 for target in d.TARGETS:
  tr=train[train[target].notna()];priors=tr.groupby('position')[target].mean();p=test[target+'_mean3'].fillna(test.position.map(priors)).fillna(tr[target].mean()).to_numpy()
  if target!='fantasy_points_ppr':p=np.maximum(0,p)
  test[target+'_history']=p
  for family,cols in d.VARIANTS.items():
   for kind,configs in CONFIGS.items():
    key=target+'/'+family+'/'+kind;index=selection['selected'][key];model,meta=fit(kind,cols,configs[index],tr,target);prediction=target+'_'+family+'_'+kind
    test[prediction]=predict(model,test,target,cols);metadata[key]=meta|{'chosen_configuration':index}
    print('finalfit',key,'seconds',round(meta['fit_seconds'],2),flush=True)
  for scope,mask in [('sunday_main',test.sunday_main),('all_games',pd.Series(True,index=test.index))]:
   sample=test[mask&test[target].notna()]
   for method in ['history']+[family+'_'+kind for family in d.VARIANTS for kind in CONFIGS]:summary[target+'/'+scope+'/'+method]=diagnostics(sample,target,sample[target+'_'+method].to_numpy())
 test.to_csv(HERE/'player_predictions_2026w4_w5.csv',index=False,float_format='%.8g')
 ranking={};pairing={};sunday=test[test.sunday_main]
 for method in ['history']+[family+'_'+kind for family in d.VARIANTS for kind in CONFIGS]:
  prediction='fantasy_points_ppr_'+method;ranking[method]=upside(sunday,prediction);pairing[method]=pairs(sunday,prediction)
 improved=all(summary[t+'/sunday_main/F3_role_pbp_neural']['week'][str(w)]['mae']<min(summary[t+'/sunday_main/'+other]['week'][str(w)]['mae'] for other in ['F0_basic_neural','F1_production_neural','F3_role_pbp_tree']) for t in ['targets','carries'] for w in [4,5])
 result={'primary_test':'2026 W4/W5 SundayMain Classic; revised-data retrospective','metrics':summary,'upside_ranking':ranking,'conditional_pair_ranking':pairing,'fit_metadata':metadata,'frozen_selections_sha256':d.sha(HERE/'frozen_selections.json'),'matrix_sha256':manifest['matrix_sha256'],'spec_sha256':manifest['spec_sha256'],'evaluate_seconds':time.perf_counter()-start,'expansion_joint_workload_criterion_met':improved}
 (HERE/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('Evaluation complete',round(result['evaluate_seconds'],2),'sec')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--tune',action='store_true');p.add_argument('--evaluate',action='store_true');a=p.parse_args()
 if a.tune:tune()
 elif a.evaluate:evaluate()
 else:p.error('Choose --tune or --evaluate')
