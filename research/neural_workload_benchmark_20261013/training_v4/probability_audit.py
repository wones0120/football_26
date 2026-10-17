"""Supplemental probability calibration replay; no retuning/point-result changes.

The original rolling scorer retained intervals but omitted positive probabilities
from its result JSON. Replay ONLY the previously selected hurdle models, verify
exact point MAE and saved CSV agreement, then report their probability diagnostics.
"""
import json,time
from pathlib import Path
import numpy as np,pandas as pd
import runner as r
HERE=Path(__file__).resolve().parent

def audit():
 started=time.perf_counter();frame,manifest=r.load();rolling=json.loads((HERE/'frozen_rolling_results.json').read_text())
 assert r.sha(HERE/'models.py')==rolling['models_sha256'] and r.sha(HERE/'runner.py')==rolling['runner_sha256']
 saved=pd.read_csv(HERE/'rolling_predictions.csv');reports={}
 for fold in r.FOLDS:
  for target in ['targets','carries']:
   train=frame[(frame.period<=fold['fit_end'])&frame[target].notna()];stop=frame[frame.period.isin(fold['stop'])&frame[target].notna()];test=frame[frame.period.isin(fold['assess'])&frame.sunday_main&frame[target].notna()]
   for family in ['F2_efficiency','F3_role_pbp']:
    key=fold['name']+'/'+target+'/'+family+'/position_nn';choice=rolling['all_fit_selection_records'][key]['selected'];model,_=r.fit('position_nn',manifest['feature_families'][family],choice,train,stop,target);point,prob=model.predict_with_probability(test)
    mae=float(np.mean(np.abs(point-test[target])));assert abs(mae-rolling['metrics'][key]['mae'])<1e-12
    original=saved[(saved.fold==fold['name'])&(saved.target==target)&(saved.family==family)&(saved.method=='position_nn')].set_index('row_index').loc[test.index,'prediction'].to_numpy();assert np.allclose(point,original,atol=1e-6,rtol=1e-7)
    valid=np.isfinite(prob);y=(test[target].to_numpy()>0).astype(float);bins=[]
    for a,b in [(0,.1),(.1,.3),(.3,.6),(.6,.9),(.9,1.00001)]:
     mask=valid&(prob>=a)&(prob<b)
     if mask.any():bins.append({'low':a,'high':min(b,1),'n':int(mask.sum()),'predicted_positive_rate':float(prob[mask].mean()),'observed_positive_rate':float(y[mask].mean())})
    reports[key]={'n':int(valid.sum()),'brier':float(np.mean((prob[valid]-y[valid])**2)),'reliability_bins':bins,'position':{pos:{'n':int(((test.position==pos).to_numpy()&valid).sum()),'brier':float(np.mean((prob[(test.position==pos).to_numpy()&valid]-y[(test.position==pos).to_numpy()&valid])**2))} for pos in sorted(test.position.unique())},'point_mae_exactly_reproduced':True,'point_csv_verified':True}
    print('probability replay',key,'Brier',round(reports[key]['brier'],4),flush=True)
 result={'supplemental_to_frozen_study':True,'no_selection_or_retuning':True,'conditional_positive_probability_not_availability_probability':True,'reports':reports,'runtime_seconds':time.perf_counter()-started,'original_frozen_sha256':r.sha(HERE/'frozen_rolling_results.json')}
 (HERE/'rolling_positive_probability_audit.json').write_text(json.dumps(result,indent=2)+'\n');print('Probability audit complete',round(result['runtime_seconds'],2),'seconds')
if __name__=='__main__':audit()
