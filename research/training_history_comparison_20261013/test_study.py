import sys
from pathlib import Path
import numpy as np,pandas as pd,pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import study as s
@pytest.fixture(scope='module')
def frame():return pd.read_parquet(s.CTX/'feature_matrix_full_precision.parquet').query('positive_snap_population').copy()
def test_windows_and_canonical_parity(frame):
 for target in s.TARGETS:
  for arm in s.ARMS:
   f=s.select(frame,arm,target);assert f.period.max()==202604;assert set(f.loc[f.season==2026,'week'])=={1,2,3,4};assert not f.duplicated(s.KEY).any()
   assert f.period.min()==(202601 if arm=='2026_only' else 202501 if arm=='2025_plus_2026' else 202301)
 assert len(s.select(frame,'full_equal','targets'))==len(s.select(frame,'full_recency','targets'))
def test_leakage_guards(frame):
 s.guard(frame,s.columns())
 for col in ['max_expanded_source_period']:
  bad=frame.head(2).copy();bad[col]=bad.period
  with pytest.raises(ValueError):s.guard(bad,s.columns())
 bad=frame.head(2).copy();bad['max_expanded_completed_at']=bad.decision_cutoff_at
 with pytest.raises(ValueError):s.guard(bad,s.columns())
 with pytest.raises(ValueError):s.guard(frame,s.columns()+['targets'])
 with pytest.raises(ValueError):s.guard(pd.concat([frame.head(1)]*2),s.columns())
def test_weight_sum_and_monotonicity(frame):
 f=s.select(frame,'full_recency','targets');anchor=pd.to_datetime(frame[frame.period==202604].kickoff_at,utc=True).max();w=s.weights(f,'full_recency',anchor);assert np.isclose(w.sum(),len(f));assert (w>0).all();order=np.argsort(pd.to_datetime(f.kickoff_at,utc=True).astype('int64'));assert (np.diff(w[order])>=-1e-12).all();assert np.array_equal(s.weights(f,'full_equal',anchor),np.ones(len(f)))
def test_preprocessing_train_scope_and_weighted_statistics(frame):
 f=s.select(frame,'2026_only','targets').head(30);w=np.arange(1,len(f)+1,dtype=float);pre=s.WeightedPreprocess(s.columns()).fit(f,w);mean=np.average(pre.numeric(f),axis=0,weights=w);assert np.allclose(pre.scaler.mean_,mean);prior=pre.scaler.mean_.copy();test=frame[frame.period==202605].head(3).copy();test[s.columns()]=1e6;pre.transform(test);assert np.array_equal(pre.scaler.mean_,prior);assert pre.fit_end<=202604;assert pre.fit_hash==s.hashframe(f,s.columns()+['position']);assert s.weighted_median(np.array([0.,10.,20.]),np.array([1.,8.,1.]))==10.
def test_nn_weights_enter_gradient_not_just_preprocessing(monkeypatch,frame):
 from sklearn.neural_network import MLPRegressor
 X=np.array([[0.,0.],[1.,1.],[2.,2.],[3.,3.]]);y=np.array([0.,1.,2.,20.]);params=s.NN|dict(batch_size=4)
 a=MLPRegressor(**params);b=MLPRegressor(**params);a.partial_fit(X,y,sample_weight=np.ones(4));b.partial_fit(X,y,sample_weight=np.array([1.,1.,1.,10.]));assert not np.allclose(a.predict(X),b.predict(X));assert a.loss_!=b.loss_
 calls=[];original=MLPRegressor.partial_fit
 def capture(self,X,y,sample_weight=None):calls.append(np.array(sample_weight));return original(self,X,y,sample_weight=sample_weight)
 monkeypatch.setattr(MLPRegressor,'partial_fit',capture);monkeypatch.setattr(s,'EPOCHS',2);f=s.select(frame,'2026_only','targets').head(20);w=np.linspace(.5,1.5,len(f));s.HistoryModel(s.columns(),'residual_nn','targets').fit(f,w);assert len(calls)==2;assert all(np.array_equal(c,w) for c in calls)
def test_week5_fit_rejected(frame):
 f=frame[frame.period==202605].head(10)
 with pytest.raises(ValueError):s.HistoryModel(s.columns(),'tree','targets').fit(f,np.ones(len(f)))
