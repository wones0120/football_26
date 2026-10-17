"""Same frozen features, cuts/models/seed; declared label correction only."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from backend.app.product_services.predictions import TARGET_COL,blend_point_predictions
from backend.app.product_services.opponent_qb_context import FEATURE_COLUMNS as QB_FEATURES
P=Path(__file__).resolve().parent;old=Path('research/opponent_qb_context_20261015/v1');previous=json.load(open(old/'metrics.json'));BASE_FEATURES=previous['baseline_features'];assert QB_FEATURES==previous['features']
f=pd.read_csv(old/'reconstructed_feature_frame.csv');f['period']=f.season*100+f.week;original=f.dk_points.copy();correction=json.load(open(P/'corrected_dst_matrix.json'));truth={r['player_game_feature_matrix_id']:r['dk_points'] for r in correction['rows']};assert set(f.player_game_feature_matrix_id)==set(truth)
f[TARGET_COL]=f.player_game_feature_matrix_id.map(truth);all_predictions=[];results=[];fits=0
folds=[('2025_holdout',202414,202501,202599),('2026_weeks1_3',202515,202601,202603),('2026_weeks4_5_inspected',202515,202604,202605)]
for fold,cal_start,test_start,test_end in folds:
 train=f.loc[f.period<cal_start].copy();cal=f.loc[(f.period>=cal_start)&(f.period<(202601 if test_start>=202601 else test_start))].copy();test=f.loc[(f.period>=test_start)&(f.period<=test_end)].copy()
 for target in [TARGET_COL,'label_opponent_qb_sacks','label_opponent_qb_interceptions']:
  for labels in (['corrected','legacy_training_labels'] if target==TARGET_COL else ['corrected']):
   tr=train.dropna(subset=[target]).copy();ca=cal.dropna(subset=[target]);te=test.dropna(subset=[target]);assert len(tr)>=100
   if labels=='legacy_training_labels':tr[TARGET_COL]=tr.dk_points
   for arm,columns in [('baseline',BASE_FEATURES),('plus_opponent_qb',BASE_FEATURES+QB_FEATURES)]:
    imp=SimpleImputer(strategy='median',keep_empty_features=True);model=GradientBoostingRegressor(random_state=42);model.fit(imp.fit_transform(tr[columns].apply(pd.to_numeric,errors='coerce')),tr[target]);fits+=1
    def predict(df):
     raw=model.predict(imp.transform(df[columns].apply(pd.to_numeric,errors='coerce')))
     return blend_point_predictions(raw,tr,df) if target==TARGET_COL else np.maximum(0,raw)
    cp=predict(ca);tp=predict(te);actual=te[target].to_numpy();errors=tp-actual;lo,hi=np.quantile(ca[target].to_numpy()-cp,[.1,.9]);bins=[]
    for ix in np.array_split(np.argsort(tp),3):bins.append(dict(n=len(ix),predicted_mean=float(tp[ix].mean()),actual_mean=float(actual[ix].mean())))
    result=dict(fold=fold,target=target,training_labels=labels,arm=arm,train_n=len(tr),calibration_n=len(ca),heldout_n=len(te),train_through=int(tr.period.max()),calibration_periods=sorted(ca.period.unique().tolist()),test_periods=sorted(te.period.unique().tolist()),mae=float(abs(errors).mean()),rmse=float(np.sqrt(np.mean(errors**2))),bias=float(errors.mean()),coverage80=float(((actual>=tp+lo)&(actual<=tp+hi)).mean()),interval_width80=float(hi-lo),calibration_bins=bins);results.append(result)
    for r,p,a in zip(te.to_dict('records'),tp,actual):all_predictions.append(dict(fold=fold,target=target,training_labels=labels,arm=arm,matrix_row_id=r['player_game_feature_matrix_id'],season=r['season'],week=r['week'],team=r['team'],prediction=float(p),actual=float(a)))
    print(fold,target,labels,arm,round(result['mae'],4),flush=True)
# Prove the control predictions reproduce the original experiment exactly.
prev=pd.DataFrame(json.load(open(old/'heldout_predictions.json')));now=pd.DataFrame(all_predictions);comparisons=[]
for row in prev.itertuples(index=False):
 candidate=now[(now.fold==row.fold)&(now.target==row.target)&(now.arm==row.arm)&(now.matrix_row_id==row.matrix_row_id)&(now.training_labels==('legacy_training_labels' if row.target==TARGET_COL else 'corrected'))]
 assert len(candidate)==1 and abs(candidate.iloc[0].prediction-row.prediction)<1e-9
for fold,target in now[['fold','target']].drop_duplicates().itertuples(index=False):
 q=now[(now.fold==fold)&(now.target==target)&(now.training_labels=='corrected')];wide=q.pivot(index=['season','week','team'],columns='arm',values='prediction');actual=q.drop_duplicates(['season','week','team']).set_index(['season','week','team']).actual;d=(wide.plus_opponent_qb-actual).abs()-(wide.baseline-actual).abs();g=d.groupby(level=['season','week']).agg(['sum','size']);rng=np.random.default_rng(261015);samples=[]
 for _ in range(2000):
  x=g.iloc[rng.integers(0,len(g),len(g))];samples.append(x['sum'].sum()/x['size'].sum())
 comparisons.append(dict(fold=fold,target=target,paired_mae_difference=float(d.mean()),week_cluster95=list(map(float,np.quantile(samples,[.025,.975]))),week_clusters=len(g)))
report=dict(contract='corrected_dst_opponent_qb_ablation_v1',created_at=datetime.now(UTC).isoformat(),corrected_dataset_sha256=correction['sha256'],frozen_feature_frame_sha256=hashlib.sha256((old/'reconstructed_feature_frame.csv').read_bytes()).hexdigest(),baseline_features=BASE_FEATURES,extended_features=QB_FEATURES,model=previous['model'],fit_count=fits,rows=len(f),original_control_predictions_exactly_reproduced=True,unchanged_sack_int_targets=True,live_activation=False,results=results,feature_effect=comparisons,source_clock_and_retrospective_limits=previous['limitations'])
(P/'ablation_metrics.json').write_text(json.dumps(report,indent=2)+'\n');(P/'ablation_predictions.json').write_text(json.dumps(all_predictions,indent=2)+'\n');print('final',fits,'fits; original controls reproduced',flush=True)
