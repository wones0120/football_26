import sys
from pathlib import Path
import joblib,numpy as np,pandas as pd,pytest
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import models as m
import runner as r


def fixture(n=180,seed=261013):
 rng=np.random.default_rng(seed);f=pd.DataFrame({'x':rng.normal(size=n),'position':np.resize(['QB','RB','WR','TE'],n),'targets_mean3':rng.uniform(0,6,n)})
 f['targets']=np.where(f.position=='QB',0,np.where(rng.uniform(size=n)<.4,0,np.round(np.maximum(0,f.targets_mean3+f.x))))
 f['fantasy_points_ppr_mean3']=f.targets_mean3+3;f['fantasy_points_ppr']=f.fantasy_points_ppr_mean3+2*f.x
 return f


def test_partial_fit_preserves_optimizer_and_fixed_epochs_are_deterministic():
 fit=fixture();stop=fixture(80,2)
 a=m.ResidualNetwork(['x','targets_mean3'],m.SETTINGS[0]).fit(fit,'targets',stop,fixed_epochs=15)
 b=m.ResidualNetwork(['x','targets_mean3'],m.SETTINGS[0]).fit(fit,'targets',stop,fixed_epochs=15)
 assert a.model.t_==len(fit)*15
 assert a.metadata['epochs_run']==15
 assert np.array_equal(a.predict(stop),b.predict(stop))


def test_preprocessing_and_fallback_priors_do_not_use_stopping_targets():
 fit=fixture();stop=fixture(80,2);changed=stop.copy();changed['targets']=10000
 a=m.ResidualNetwork(['x'],m.SETTINGS[0]).fit(fit,'targets',stop,fixed_epochs=3)
 b=m.ResidualNetwork(['x'],m.SETTINGS[0]).fit(fit,'targets',changed,fixed_epochs=3)
 assert a.priors==b.priors
 assert np.array_equal(a.pre.named_transformers_['numeric'][1].mean_,b.pre.named_transformers_['numeric'][1].mean_)
 assert np.array_equal(a.model.coefs_[0],b.model.coefs_[0])


def test_absent_label_is_rejected_while_observed_zero_remains_valid():
 fit=fixture();stop=fixture(80,2);fit.loc[0,'targets']=np.nan
 with pytest.raises(ValueError,match='Absent labels'):m.PositionNetwork(['x'],m.SETTINGS[0]).fit(fit,'targets',stop)
 fit.loc[0,'targets']=0;m.observed_labels(fit,'targets')


def test_hurdle_single_class_zero_sparse_fallback_and_roundtrip(tmp_path):
 fit=fixture(600);stop=fixture(160,2)
 template={p+'/'+h:3 for p in ['QB','RB','WR','TE'] for h in ['residual','classifier','amount']};template['shared/residual']=3
 model=m.PositionNetwork(['x','targets_mean3'],m.SETTINGS[0]).fit(fit,'targets',stop,epoch_template=template)
 pred,prob=model.predict_with_probability(stop)
 assert np.all(pred[stop.position=='QB']==0)
 assert np.all(prob[stop.position=='QB']==0)
 assert np.all(pred>=0)
 path=tmp_path/'model.joblib';joblib.dump(model,path);loaded=joblib.load(path)
 assert np.array_equal(pred,loaded.predict(stop))
 small=m.PositionNetwork(['x'],m.SETTINGS[0]).fit(fixture(100),'targets',fixture(40,2),epoch_template=template)
 assert all(h['kind']=='shared_fallback' for h in small.heads.values())


def test_folds_ordered_and_calibration_does_not_look_at_assessment():
 for fold in r.FOLDS:assert fold['fit_end']<min(fold['stop'])<min(fold['select'])<min(fold['calibrate'])<min(fold['assess'])
 cal=fixture(80);cal['period']=202408
 q=r.calibration(cal,'targets',np.zeros(len(cal)))
 assessment=fixture(80,3);assessment['week']=9;assessment['history_count']=2;assessment['team_changed_diagnostic']=False;assessment['targets_last']=assessment.targets_mean3
 met,lo,hi=r.summarize(assessment,'targets',np.zeros(len(assessment)),q)
 assert q['guarantee'] is False
 assert all(v['pooled_fallback'] for v in q['position'].values())
 assert np.all(lo>=0)
 assert 0<=met['interval']['empirical_coverage']<=1


def test_common_feature_rows_native_scope_and_no_future_source():
 frame,manifest=r.load()
 assert not frame.duplicated(['player_master_id','season','week']).any()
 measured=frame[frame.max_expanded_source_period.notna()]
 assert all(measured.max_expanded_source_period<measured.period)
 assert max(frame.period)==202605
 for fold in r.FOLDS:
  assert set(frame[frame.period<=fold['fit_end']].period).isdisjoint(set(fold['assess']))
 assert len(r.METHODS)==4
