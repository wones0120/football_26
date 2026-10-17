"""Saved-artifact replay and chronology/parity verification without app imports."""
import sys,json
from pathlib import Path
import joblib,numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import run as r

def main():
 result=json.loads((HERE/'results.json').read_text());freeze=json.loads((HERE/'freeze.json').read_text())
 for relative,expected in freeze['dependency_hashes'].items():assert r.v4.sha(r.ROOT/relative)==expected,relative
 frame,families=r.load();p=pd.read_parquet(HERE/'predictions.parquet');assert r.v4.sha(HERE/'predictions.parquet')==result['predictions_sha256'];original=json.loads((r.V4/'frozen_rolling_results.json').read_text());replays=[];diffs=[];parity=[]
 for key,record in result['records'].items():
  foldname,target,family,method=key.split('/');fold=next(f for f in r.v4.FOLDS if f['name']==foldname);train=frame[(frame.period<=fold['fit_end'])&frame[target].notna()];stop=frame[frame.period.isin(fold['stop'])&frame[target].notna()];test=frame[frame.period.isin(fold['assess'])&frame[target].notna()&frame.sunday_main];columns=families[family]
  assert max(train.period)<min(stop.period)<min(fold['select'])<min(fold['calibrate'])<min(test.period)
  for option in record['options']:
   assert option['X_sha256']==r.v4.hash_frame(train,columns+['position'])
   assert option['y_sha256']==r.v4.hash_frame(train,[target])
  current=record['selections']['current_'+method];old=original['all_fit_selection_records'][key]['selected']
  if current!=old:diffs.append(dict(key=key,frozen_v4_index=old,full_precision_reselection=current))
  for label,artifact in record['models'].items():
   path=HERE/artifact['path'];assert r.v4.sha(path)==artifact['sha256'];model=joblib.load(path);actual=model.predict(test);saved=p[(p.fold==foldname)&(p.target==target)&(p.family==family)&(p.method==label)].set_index('row_index').loc[test.index].prediction.to_numpy();assert np.array_equal(actual,saved),key
   replays.append(dict(key=key+'/'+label,n=len(saved),max_abs_delta=float(np.max(np.abs(actual-saved)))))
  # Full actual-data control parity for both designs/features/targets on first fold.
  if foldname==r.v4.FOLDS[0]['name']:
   with r.threadpool_limits(limits=1):control,_=r.v4.fit(method,columns,current,train,stop,target)
   saved_model=joblib.load(HERE/record['models']['current_'+method]['path']);delta=np.max(np.abs(control.predict(test)-saved_model.predict(test)));assert delta==0,key;parity.append(dict(key=key,configuration=current,max_abs_delta=float(delta)))
 report=dict(saved_model_replays=replays,exact_current_control_replays=parity,all_dependency_hashes_verified=True,original_v4_selection_differences=diffs,original_v4_comparator_note='Original V4 decisions/predictions are retained unchanged in original directory. Fullprecision control replays unchanged algorithms/settings; if choices differ record both explicitly.',future_labels_loaded=False,production_mutations=False)
 (HERE/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(replayed=len(replays),actual_control_parity=len(parity),original_selection_differences=diffs),indent=2))
if __name__=='__main__':
 with r.threadpool_limits(limits=1):main()
