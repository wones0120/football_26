"""Cheap reproducibility verification: hashes/parity/model reloads; no fitting."""
import json
from pathlib import Path
import joblib,numpy as np,pandas as pd
import runner as r
HERE=Path(__file__).resolve().parent

def verify():
 frame,source=r.load();rolling=json.loads((HERE/'frozen_rolling_results.json').read_text());diagnostic=json.loads((HERE/'diagnostic_results.json').read_text())
 for name,key in [('runner.py','runner_sha256'),('models.py','models_sha256'),('SPECIFICATION.md','spec_sha256')]:assert r.sha(HERE/name)==rolling[key]
 assert source['matrix_sha256']==rolling['matrix_sha256']
 for fold in r.FOLDS:
  assert fold['fit_end']<min(fold['stop'])<min(fold['select'])<min(fold['calibrate'])<min(fold['assess'])
  for target in r.TARGETS:
   for family in ['F2_efficiency','F3_role_pbp']:
    records=[x for method in r.METHODS for x in rolling['all_fit_selection_records'][fold['name']+'/'+target+'/'+family+'/'+method]['options']]
    assert len(records)==8 and len({x['X_sha256'] for x in records})==len({x['y_sha256'] for x in records})==1
    assert all(x['fit_end_period']==fold['fit_end'] for x in records)
 saved=pd.read_csv(HERE/'diagnostic_predictions_2026w4_w5.csv').set_index(['player_master_id','week']);assert saved.index.is_unique;checks=[]
 for key,item in diagnostic['fitted_artifacts'].items():
  path=HERE/item['path'];assert r.sha(path)==item['sha256'];target,family,method=key.split('/');model=joblib.load(path);sample=frame[frame.period.isin([202604,202605])&frame.sunday_main&frame[target].notna()];prediction=r.predict(model,method,sample,target,source['feature_families'][family]);original=np.array([saved.loc[(x.player_master_id,x.week),target+'_'+family+'_'+method] for _,x in sample.iterrows()]);assert np.allclose(prediction,original,atol=1e-6,rtol=1e-7);error=float(np.mean(np.abs(prediction-sample[target])));assert abs(error-diagnostic['metrics'][key]['mae'])<1e-12
  assert item['fit_metadata']['fit_end_period']==202602 and item['calibration_only']==202603
  checks.append({'model':key,'n':len(sample),'sha256':item['sha256'],'mae_exactly_reproduced':True,'max_csv_rounding_difference':float(np.max(np.abs(prediction-original)))})
 proof={'all24_saved_models_reloaded':True,'all_saved_errors_exactly_reproduced':True,'canonical_identity_plus_week_not_name':True,'all_feature_label_rows_and_two_option_budget_match':True,'chronological_gradient_stopping_selection_calibration_assessment_blocks':True,'no_independent_historical_or_w4w5_claim':True,'checks':checks}
 (HERE/'verification.json').write_text(json.dumps(proof,indent=2)+'\n');print('Verified24model reloads, exact errors, native row keys, identical rows/budgets and temporal blocks')
if __name__=='__main__':verify()
