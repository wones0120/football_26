from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,joblib
import numpy as np,pandas as pd
from sklearn.base import clone
from backend.app.product_services.predictions import TARGET_COL,blend_point_predictions
from backend.app.product_services.canonical_projection_inputs import FEATURE_COLUMNS
from backend.app.product_services.opponent_qb_context import FEATURE_COLUMNS as QB_FEATURES
P=Path(__file__).resolve().parent; C=Path('research/dst_scoring_repair_20261015/v1')
a=joblib.load(P/'incumbent.joblib'); original=a['train'].copy();features=a['feature_columns'];assert features==FEATURE_COLUMNS and not(set(features)&set(QB_FEATURES))
from backend.app.product_services.dst_training_labels import read_verified_correction,select_corrected_dst_labels
receipt=json.load(open(C/'full_matrix_version_receipt.json'));corr=read_verified_correction(receipt['artifact_path'],expected_sha256=receipt['content_sha256'])
fixed,label_audit=select_corrected_dst_labels(original,corr,target_season=2026,target_week=6);changed=label_audit['changed_rows']
assert label_audit['selected_rows']==804 and changed==285
fixed['period']=fixed.season*100+fixed.week;original['period']=original.season*100+original.week
folds=[('2025_retrospective',202414,202501,202599),('2026_w1_3_retrospective',202515,202601,202603),('2026_w4_5_inspected',202515,202604,202605)]
rows=[]; metrics=[]
for name,calstart,teststart,testend in folds:
 cal=fixed[(fixed.period>=calstart)&(fixed.period<(202601 if teststart>=202601 else teststart))];test=fixed[(fixed.period>=teststart)&(fixed.period<=testend)];test=test[test.position.eq('DST')];cal=cal[cal.position.eq('DST')]
 for arm,frame in [('incumbent_policy',original),('corrected_labels',fixed)]:
  tr=frame[frame.period<calstart];m=clone(a['model']);m.fit(tr[features].apply(pd.to_numeric,errors='coerce').fillna(0),tr[TARGET_COL])
  def predict(t):return np.maximum(0,blend_point_predictions(m.predict(t[features].apply(pd.to_numeric,errors='coerce').fillna(0)),tr,t))
  cp=predict(cal);tp=predict(test);lo,hi=np.quantile(cal[TARGET_COL]-cp,[.1,.9]);err=tp-test[TARGET_COL].to_numpy()
  metric=dict(block=name,arm=arm,n=len(test),train_n=len(tr),calibration_n=len(cal),mae=float(abs(err).mean()),rmse=float(np.sqrt((err**2).mean())),bias=float(err.mean()),coverage80=float(((test[TARGET_COL]>=tp+lo)&(test[TARGET_COL]<=tp+hi)).mean()),interval_width=float(hi-lo))
  metrics.append(metric);print(metric,flush=True)
  for r,p in zip(test.to_dict('records'),tp):rows.append(dict(block=name,arm=arm,season=int(r['season']),week=int(r['week']),team=r['team'],player_id=r['player_id'],matrix_id=int(r['player_game_feature_matrix_id']),actual=r[TARGET_COL],prediction=float(p),covered=bool(r[TARGET_COL]>=p+lo and r[TARGET_COL]<=p+hi)))
f=pd.DataFrame(rows);wide=f.pivot(index=['season','week','team'],columns='arm',values='prediction');truth=f.drop_duplicates(['season','week','team']).set_index(['season','week','team']).actual
agg={}
for arm in ['incumbent_policy','corrected_labels']:
 err=wide[arm]-truth;sub=f[f.arm==arm];agg[arm]=dict(n=len(err),mae=float(abs(err).mean()),rmse=float(np.sqrt((err**2).mean())),bias=float(err.mean()),coverage80=float(sub.covered.mean()),current2026_mae=float(abs(err[err.index.get_level_values('season')==2026]).mean()))
d=(wide.corrected_labels-truth).abs()-(wide.incumbent_policy-truth).abs();g=d.groupby(level=['season','week']).agg(['sum','size']);rng=np.random.default_rng(261016);boots=[]
for _ in range(3000):
 x=g.iloc[rng.integers(0,len(g),len(g))];boots.append(x['sum'].sum()/x['size'].sum())
ci=list(map(float,np.quantile(boots,[.025,.975])));old=agg['incumbent_policy'];new=agg['corrected_labels'];gates=dict(mae=new['mae']<=old['mae']+.10,rmse=new['rmse']<=old['rmse']*1.02,current2026=new['current2026_mae']<=old['current2026_mae']+.25,bias=abs(new['bias'])<=1 or abs(new['bias'])<abs(old['bias']),coverage=.7<=new['coverage80']<=.9 and new['coverage80']>=old['coverage80']-.05,uncertainty=ci[1]<=.4)
report=dict(created_at=datetime.now(UTC).isoformat(),version='v4.2-dst-exact-label-candidate-20261016',production_features=features,opponent_qb_features_excluded=True,training_rows=len(fixed),dst_rows=804,changed_dst_labels=changed,criteria_sha256=hashlib.sha256((P/'CRITERIA.md').read_bytes()).hexdigest(),source_snapshot_id='e81b5772-5d81-505b-a44c-0660480098c4',source_scoring_contract=corr['contract_id'],metrics=metrics,aggregate=agg,paired_mae_difference=float(d.mean()),week_cluster95=ci,week_clusters=len(g),gates=gates,passed=all(gates.values()),chronology='Retrospective season/week cutoffs; original historical source clocks incomplete; 2025/2026 outcomes previously inspected. No fresh holdout claim.')
(P/'validation.json').write_text(json.dumps(report,indent=2)+'\n');(P/'heldout_predictions.json').write_text(json.dumps(rows,indent=2)+'\n');joblib.dump(dict(train=fixed,features=features,source_snapshot_id=report['source_snapshot_id']),P/'candidate_training.joblib');print('AGG',agg,'CI',ci,'GATES',gates,flush=True)
