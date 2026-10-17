"""Read-only artifact replay and scope audit; writes only verification receipt."""
import sys,json
from pathlib import Path
import numpy as np,pandas as pd,joblib
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import study as s
from threadpoolctl import threadpool_limits
# The direct-entry-point trainer serialized these class names under __main__.
# Restore those exact names without changing frozen model bytes.
import __main__
__main__.HistoryModel=s.HistoryModel
__main__.WeightedPreprocess=s.WeightedPreprocess

def verify():
 freeze=json.loads((HERE/'freeze.json').read_text());results=json.loads((HERE/'results.json').read_text())
 for path,digest in freeze['dependencies'].items():assert s.sha(s.ROOT/path)==digest,path
 assert s.sha(HERE/'training_manifest.parquet')==freeze['training_manifest_hash'];assert s.sha(HERE/'assessment_manifest.csv')==freeze['assessment_manifest_hash'];assert s.sha(HERE/'predictions.parquet')==results['predictions_hash']
 f=pd.read_parquet(s.CTX/'feature_matrix_full_precision.parquet');s.guard(f,freeze['features']);f=f[f.positive_snap_population].copy();test=f[f.period==202605];assert s.hashframe(test,freeze['features']+['position'])==freeze['assessment_X_hash'];pred=pd.read_parquet(HERE/'predictions.parquet');manifest=pd.read_parquet(HERE/'training_manifest.parquet');checks={}
 with threadpool_limits(limits=1):
  for key,record in results['records'].items():
   arm,target,method=key.split('/');train=s.select(f,arm,target);m=manifest[(manifest.arm==arm)&(manifest.target==target)];w=s.weights(train,arm,pd.Timestamp(freeze['weight_anchor']));assert np.array_equal(m.row_index,train.index);assert np.allclose(w,m.sample_weight,atol=0,rtol=0);assert np.isclose(w.sum(),len(w));assert train.period.max()==202604;assert s.hashframe(train,freeze['features']+['position'])==freeze['coverage'][arm+'/'+target]['train_X_hash'];assert s.hashframe(train,[target])==freeze['coverage'][arm+'/'+target]['train_y_hash']
   path=HERE/record['checkpoint'];assert s.sha(path)==record['checkpoint_hash'];model=joblib.load(path);assert model.pre.fit_hash==record['preprocessing_fit_hash'];assert model.pre.fit_rows==len(train);assert model.pre.fit_end==202604;assert model.train_keys==train[s.KEY].to_dict('records')
   g=pred[(pred.arm==arm)&(pred.target==target)&(pred.method==method)];rows=f.loc[g.row_index];p=model.predict(rows);assert np.allclose(p,g.prediction,rtol=0,atol=0),key;assert np.array_equal(g.actual,rows[target]);assert np.array_equal(g.player_master_id,rows.player_master_id);assert np.array_equal(g.game_id,rows.game_id);assert len(g)==len(test[test[target].notna()]);assert not g.duplicated(s.KEY).any();assert np.isfinite(p).all()
   primary=g[g.sunday_main];metric=s.measure(primary);saved=results['metrics']['sunday_main/'+key];assert all(np.isclose(metric[v],saved[v]) for v in ['mae','rmse','bias']);checks[key]=dict(replay_rows=len(g),primary_rows=len(primary),max_reload_delta=float(np.max(abs(p-g.prediction))),training_rows=len(train))
   # Enforce priors/scalers fitted exclusively to train and actual weights.
   assert np.allclose(model.pre.scaler.mean_,np.average(model.pre.numeric(train),axis=0,weights=w))
   if method=='residual_nn':assert np.allclose(model.target_scale.mean_,np.average((train[target]-model.history(train)).to_numpy(),weights=w));assert len(model.estimator.loss_curve_)==s.EPOCHS
 for (target,method),g in pred.groupby(['target','method']):
  reference=None
  for arm,part in g.groupby('arm'):
   rows=part.sort_values('row_index')[s.KEY+['row_index','actual','sunday_main']].reset_index(drop=True)
   if reference is None:reference=rows
   else:pd.testing.assert_frame_equal(reference,rows)
 out=dict(models_replayed=len(checks),exact_replay=True,canonical_row_parity=True,train_only_preprocessing=True,window_bounds=True,weight_sums=True,frozen_hashes=True,prediction_rows=len(pred),checks=checks);s.dump(HERE/'verification.json',out);print(json.dumps({k:v for k,v in out.items() if k!='checks'},indent=2))
if __name__=='__main__':verify()
