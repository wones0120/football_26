import sys
from pathlib import Path
import importlib.util
import joblib,numpy as np,pandas as pd,pytest
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import capacity_models as m
spec=importlib.util.spec_from_file_location('capacity_run',HERE/'run.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

def fixture(n=180,seed=261013):
 rng=np.random.default_rng(seed);f=pd.DataFrame({'x':rng.normal(size=n),'position':np.resize(['QB','RB','WR','TE'],n),'targets_mean3':rng.uniform(0,6,n)})
 f['targets']=np.where(f.position=='QB',0,np.maximum(0,np.round(f.targets_mean3+f.x)))
 return f

def test_current_controls_match_untouched_original_training():
 fit=fixture();stop=fixture(80,2)
 for index in [0,1]:
  a=m.ResidualNetwork(['x','targets_mean3'],r.CONFIGS[index]).fit(fit,'targets',stop,fixed_epochs=7)
  b=r.v4.ResidualNetwork(['x','targets_mean3'],r.v4.SETTINGS[index]).fit(fit,'targets',stop,fixed_epochs=7)
  assert np.array_equal(a.predict(stop),b.predict(stop))
  assert a.metadata['parameter_count']==sum(v.size for v in a.model.coefs_+a.model.intercepts_)

def test_preprocessor_target_scaling_and_prior_are_training_only():
 fit=fixture();stop=fixture(80,2);changed=stop.copy();changed['targets']=10000;changed['x']=10000
 a=m.ResidualNetwork(['x'],r.CONFIGS[2]).fit(fit,'targets',stop,fixed_epochs=3)
 b=m.ResidualNetwork(['x'],r.CONFIGS[2]).fit(fit,'targets',changed,fixed_epochs=3)
 assert a.priors==b.priors
 assert np.array_equal(a.scale.mean_,b.scale.mean_)
 assert np.array_equal(a.pre.named_transformers_['numeric'][1].mean_,b.pre.named_transformers_['numeric'][1].mean_)
 assert np.array_equal(a.model.coefs_[0],b.model.coefs_[0])

def test_full_precision_chronology_native_identity_and_exact_scope():
 frame,families=r.load();assert max(frame.period)==202605
 assert not frame.duplicated(['player_master_id','season','week']).any()
 measured=frame[frame.max_expanded_source_period.notna()];assert (measured.max_expanded_source_period<measured.period).all()
 for fold in r.v4.FOLDS:assert fold['fit_end']<min(fold['stop'])<=max(fold['stop'])<min(fold['select'])<min(fold['calibrate'])<min(fold['assess'])
 assert list(map(len,families.values()))==[50,68]

def test_missing_zero_and_model_roundtrip(tmp_path):
 fit=fixture();stop=fixture(80,2);fit.loc[0,'targets']=np.nan
 with pytest.raises(ValueError,match='Absent labels'):m.ResidualNetwork(['x'],r.CONFIGS[4]).fit(fit,'targets',stop)
 fit.loc[0,'targets']=0;a=m.ResidualNetwork(['x'],r.CONFIGS[4]).fit(fit,'targets',stop,fixed_epochs=5);path=tmp_path/'model.joblib';joblib.dump(a,path);assert np.array_equal(a.predict(stop),joblib.load(path).predict(stop))

def test_comparison_artifacts_join_exactly_and_rankings_keep_seasons_separate():
 import json
 summary=json.loads((HERE/'summary.json').read_text());p=pd.read_parquet(HERE/'comparison_predictions.parquet')
 assert not p.duplicated(['row_index','fold','target','family','method']).any()
 for (target,family),group in p.groupby(['target','family']):
  keys=['row_index','fold'];baseline=group[group.method=='tuned_tree'].set_index(keys).actual
  for method,sample in group.groupby('method'):
   assert sample.set_index(keys).actual.sort_index().equals(baseline.sort_index())
 assert p.period.nunique()==12
 for key,rank in summary['rankings'].items():
  assert len({entry['period'] for entry in rank['upside']})==12
  assert len({entry['period'] for entry in rank['pairs']})==12
  assert all(entry['period']==entry['season']*100+entry['week'] for entry in rank['upside'])
