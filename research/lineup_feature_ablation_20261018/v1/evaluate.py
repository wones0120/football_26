"""Evaluation phase: consumes only hash-frozen models; never retrains or retunes."""
from pathlib import Path
from collections import defaultdict
import gzip,hashlib,json,statistics
import numpy as np
from sklearn.metrics import roc_auc_score,average_precision_score,brier_score_loss
from backend.app.product_services.lineup_ablation_research import predict
P=Path(__file__).resolve().parent;manifest=json.load(open(P/'model_manifest.json'));contexts=[]
for name,sha in manifest['source_hashes'].items():
 path=Path(name)
 if hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError('Cohort source changed')
 with gzip.open(path,'rt')as f:contexts.append(json.load(f))
metrics=[]
for ref in manifest['models']:
 path=Path(ref['path'])
 if hashlib.sha256(path.read_bytes()).hexdigest()!=ref['sha256']:raise ValueError('Frozen ablation model changed')
 model=json.load(open(path));assert max(model['train_weeks'])<model['test_week']
 for d in contexts:
  c=d['context']
  if c['week']!=model['test_week']:continue
  rows=[r for r in d['rosters']if model['family']=='core'or r['rich_features']is not None]
  def full(r):return r['rich_features']if model['family']=='rich'else r['rich_features'][:22]if r['rich_features']is not None else r['features']
  scores=np.asarray([predict(model,full(r))for r in rows]);y=np.asarray([r['label']for r in rows]);rank=sorted(range(len(rows)),key=lambda i:(-scores[i],rows[i]['roster_key']));meanrank=sorted(range(len(rows)),key=lambda i:(-full(rows[i])[0],rows[i]['roster_key']));k=min(5,len(rows));bins=[]
  for lo,hi in [(0,.1),(.1,.2),(.2,.4),(.4,.6),(.6,1.0001)]:
   mask=(scores>=lo)&(scores<hi)
   if mask.any():bins.append({'lo':lo,'hi':hi,'n':int(mask.sum()),'mean_model_score':float(scores[mask].mean()),'observed_label_rate':float(y[mask].mean())})
  metrics.append({'model_id':model['model_id'],'family':model['family'],'treatment':model['treatment'],'week':c['week'],'slate':c['slate'],'contest_id':c['contest_id'],'source_file_id':c['source_file_id'],'projection_run_id':c['projection_run_id'],'field_size':c['field_size'],'ties_at_boundary':c['ties_at_boundary'],'points_cutoff':c['points_cutoff'],'sampled_distinct_rosters':len(rows),'positive_rate':float(y.mean()),'auc':float(roc_auc_score(y,scores))if len(set(y))==2 else None,'average_precision':float(average_precision_score(y,scores)),'brier':float(brier_score_loss(y,scores)),'requested':5,'achieved':k,'top5_hits':int(y[rank[:k]].sum()),'mean_top5_hits':int(y[meanrank[:k]].sum()),'coverage_upper_bound':min(5,int(y.sum())),'ranking_tie_policy':'Canonical roster hash order; all tied field-label boundary entries positive','calibration':bins,'selected_rosters':[{'roster_key':rows[i]['roster_key'],'signature':rows[i]['signature'],'model_score':float(scores[i]),'actual_points':rows[i]['points'],'label':int(y[i])}for i in rank[:k]],'portfolio_constraints':'Field-sample ranking only; not an operational constrained portfolio'})
summary=[]
for family in ['core','rich']:
 for week in [4,5,6]:
  for treatment in ['original','remove_salary','remove_stacking','remove_both']:
   rows=[r for r in metrics if r['family']==family and r['week']==week and r['treatment']==treatment]
   summary.append({'family':family,'week':week,'treatment':treatment,'contests':len(rows),'unique_slate_scopes':sorted({r['slate']for r in rows}),'projection_snapshots':len({r['projection_run_id']for r in rows}),'sampled_roster_contexts':sum(r['sampled_distinct_rosters']for r in rows),'auc_contest_average':statistics.mean(r['auc']for r in rows),'brier_contest_average':statistics.mean(r['brier']for r in rows),'top5_hits':sum(r['top5_hits']for r in rows),'mean_top5_hits':sum(r['mean_top5_hits']for r in rows),'requested':sum(r['requested']for r in rows),'achieved':sum(r['achieved']for r in rows)})
with(P/'temporal_metrics.json').open('x')as f:json.dump({'manifest_sha256':hashlib.sha256((P/'model_manifest.json').read_bytes()).hexdigest(),'metrics':metrics,'summary':summary,'retrospective':True,'live_promoted':False},f,indent=2)
for row in summary:print(row['family'],row['week'],row['treatment'],'hits',row['top5_hits'],'/',row['achieved'],'mean',row['mean_top5_hits'],'AUC',round(row['auc_contest_average'],3),'Brier',round(row['brier_contest_average'],4),'slates',row['unique_slate_scopes'])
