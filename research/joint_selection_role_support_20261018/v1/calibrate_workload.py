"""Eight predeclared one-feature fits; diagnostic only, no FP/eligibility edits."""
from pathlib import Path
from collections import defaultdict
import hashlib,json,math,statistics
import numpy as np
from sklearn.linear_model import PoissonRegressor
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
P=Path(__file__).resolve().parent;source=P/'projection_component_diagnosis_v2.json';rs=[r for r in json.load(open(source))['rows']if r['component_matches_observed_dk']and type(r['recorded_workload_proxy'])in(int,float)and r['recorded_workload_proxy']>=0]
def metrics(y,p):return {'n':len(y),'mae':float(np.mean(abs(p-y))),'rmse':float(np.sqrt(np.mean((p-y)**2))),'bias':float(np.mean(p-y))}
def bootstrap(rows,calibrated,baseline):
 groups=defaultdict(list)
 for i,r in enumerate(rows):groups[r['game_id']].append(i)
 gids=sorted(groups);rng=np.random.default_rng(7);differences=[]
 for _ in range(1000):
  indices=np.concatenate([groups[gids[j]]for j in rng.integers(0,len(gids),len(gids))]);truth=np.asarray([r['actual_workload']for r in rows]);differences.append(float(np.mean(abs(calibrated[indices]-truth[indices])-abs(baseline[indices]-truth[indices]))))
 return {'clusters':len(gids),'mean_mae_difference':float(np.mean(differences)),'p025':float(np.quantile(differences,.025)),'p975':float(np.quantile(differences,.975)),'negative_favors_calibration':True}
results=[]
for testweek in [3,5]:
 for position in ['QB','RB','WR','TE']:
  train=[r for r in rs if r['week']<testweek and r['position']==position];test=[r for r in rs if r['week']==testweek and r['position']==position]
  if not train or not test:continue
  x=np.log1p([[r['recorded_workload_proxy']]for r in train]);y=np.asarray([r['actual_workload']for r in train]);scaler=StandardScaler().fit(x)
  with threadpool_limits(limits=1):model=PoissonRegressor(alpha=1,max_iter=100).fit(scaler.transform(x),y)
  target=np.asarray([r['actual_workload']for r in test]);proxy=np.asarray([r['recorded_workload_proxy']for r in test]);calibrated=model.predict(scaler.transform(np.log1p(proxy.reshape(-1,1))));constant=np.full(len(test),float(y.mean()))
  results.append({'test_week':testweek,'position':position,'training_weeks':sorted({r['week']for r in train}),'train_n':len(train),'test_games':len({r['game_id']for r in test}),'proxy':metrics(target,proxy),'calibrated':metrics(target,calibrated),'training_position_mean':metrics(target,constant),'paired_game_bootstrap_vs_proxy':bootstrap(test,calibrated,proxy),'paired_game_bootstrap_vs_constant':bootstrap(test,calibrated,constant),'model':{'coefficient':float(model.coef_[0]),'intercept':float(model.intercept_),'scale_mean':scaler.mean_.tolist(),'scale_std':scaler.scale_.tolist(),'alpha':1,'feature':'log1p(recorded_workload_proxy)','converged':model.n_iter_<100},'predictions':[{'player_id':r['player_id'],'game_id':r['game_id'],'actual':r['actual_workload'],'proxy':r['recorded_workload_proxy'],'calibrated':float(p)}for r,p in zip(test,calibrated)]})
out={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'protocol_sha256':hashlib.sha256((P/'WORKLOAD_CALIBRATION_PROTOCOL.md').read_bytes()).hexdigest(),'results':results,'fits':len(results),'live_promoted':False,'outcomes_previously_inspected':True,'component_definition':'Observed carriesQB/RB, targetsWR/TE; independent counts not yet team-conserving joint model','success':all(r['calibrated']['mae']<min(r['proxy']['mae'],r['training_position_mean']['mae'])for r in results)}
with(P/'workload_calibration.json').open('x')as f:json.dump(out,f,indent=2)
for r in results:print(r['test_week'],r['position'],'n',r['calibrated']['n'],'MAE proxy/cal/constant',*[round(r[n]['mae'],3)for n in ['proxy','calibrated','training_position_mean']], '95%diff',round(r['paired_game_bootstrap_vs_proxy']['p025'],3),round(r['paired_game_bootstrap_vs_proxy']['p975'],3))
print('consistent improvement',out['success'])
