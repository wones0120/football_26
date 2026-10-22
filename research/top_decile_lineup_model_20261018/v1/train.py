"""Single bounded interpretable prototype; source outcomes are labels only."""
from collections import Counter,defaultdict
import gzip,hashlib,json,pathlib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score,average_precision_score,brier_score_loss
from threadpoolctl import threadpool_limits
from backend.app.product_services.lineup_top_decile_research import CORE_FEATURES,RICH_FEATURES,CONTRACT
P=pathlib.Path(__file__).resolve().parent
records=[];contexts={};sources={}
for path in sorted((P/'contests_v2').glob('*.json.gz')):
 sources[str(path.relative_to(P))]=hashlib.sha256(path.read_bytes()).hexdigest()
 with gzip.open(path,'rt')as f:payload=json.load(f)
 c=payload['context'];contexts[c['contest_id']]=c
 for row in payload['rosters']:
  keep={key:row[key] for key in ['roster_key','features','rich_features','label','multiplicity']}
  if keep['rich_features'] is not None:keep['features']=keep['rich_features'][:len(CORE_FEATURES)]
  records.append({**keep,'contest_id':c['contest_id'],'week':c['week'],'slate':c['slate'],'format':c['contest_format'],'projection_run_id':c['projection_run_id']})

def dedup(rows,rich):
 groups={};variants=defaultdict(set)
 for r in rows:
  values=r['rich_features']if rich else r['features']
  if values is None:continue
  canonical=(r['week'],r['roster_key'])
  key=(*canonical,r['projection_run_id'],hashlib.sha256(json.dumps(values).encode()).hexdigest())
  variants[canonical].add(key)
  g=groups.setdefault(key,dict(values=values,labels={},canonical=canonical,contexts=set(),entry_multiplicity=0))
  g['labels'][r['contest_id']]=r['label'];g['contexts'].add((r['week'],r['slate']));g['entry_multiplicity']+=r['multiplicity']
 out=[]
 for g in groups.values():out.append({**g,'target':sum(g['labels'].values())/len(g['labels']),'weight':1/len(variants[g['canonical']])})
 return out

def fit(rows,rich):
 gs=dedup(rows,rich)
 X=np.asarray([g['values']for g in gs],dtype=float);target=np.asarray([g['target']for g in gs]);weights=np.asarray([g['weight']for g in gs])
 scaler=StandardScaler().fit(X,sample_weight=weights);Z=scaler.transform(X)
 # Exact fractional Bernoulli loss for one deduplicated roster-context variant.
 XX=np.concatenate([Z,Z]);yy=np.r_[np.zeros(len(Z)),np.ones(len(Z))];ww=np.r_[weights*(1-target),weights*target]
 model=LogisticRegression(C=.1,max_iter=400,solver='lbfgs')
 with threadpool_limits(limits=1):model.fit(XX,yy,sample_weight=ww)
 return scaler,model,dict(training_variants=len(gs),distinct_canonical_rosters=len({g['canonical']for g in gs}),contradictory_field_labels=sum(len(set(g['labels'].values()))>1 for g in gs),training_week_blocks=len({r['week']for r in rows}),training_scopes=len({x for g in gs for x in g['contexts']}),converged=bool(max(model.n_iter_)<400))

results=[];models=[]
for fmt in ['classic','showdown']:
 for rich in [False,True]:
  for testweek in [4,5,6]:
   train=[r for r in records if r['format']==fmt and r['week']<testweek and (not rich or r['rich_features']is not None)]
   test=[r for r in records if r['format']==fmt and r['week']==testweek and (not rich or r['rich_features']is not None)]
   if not train or not test:continue
   scaler,model,audit=fit(train,rich);names=CORE_FEATURES+(RICH_FEATURES if rich else[])
   version=f'{fmt}_{"rich"if rich else"core"}_train_before_w{testweek}'
   artifact=dict(contract_id=CONTRACT,model_id=version,format=fmt,features=names,mean=scaler.mean_.tolist(),scale=scaler.scale_.tolist(),coefficients=model.coef_[0].tolist(),intercept=float(model.intercept_[0]),C=.1,train_weeks=sorted({r['week']for r in train}),test_week=testweek,audit=audit,probability_status='retrospective sampled-contest top-decile label propensity; not validated forward contest probability',live_promoted=False)
   (P/'models').mkdir(exist_ok=True);(P/'models'/(version+'.json')).write_text(json.dumps(artifact,indent=2));models.append(artifact)
   for cid in sorted({r['contest_id']for r in test}):
    rs=[r for r in test if r['contest_id']==cid];X=np.asarray([r['rich_features']if rich else r['features']for r in rs]);y=np.asarray([r['label']for r in rs]);scores=model.predict_proba(scaler.transform(X))[:,1]
    indices=sorted(range(len(rs)),key=lambda i:(-scores[i],rs[i]['roster_key']));baseline=sorted(range(len(rs)),key=lambda i:(-rs[i]['features'][0],rs[i]['roster_key']));k=min(5,len(rs));c=contexts[cid]
    bins=[]
    for lo,hi in [(0,.1),(.1,.2),(.2,.4),(.4,.6),(.6,1.0001)]:
     mask=(scores>=lo)&(scores<hi)
     if mask.any():bins.append(dict(lo=lo,hi=hi,n=int(mask.sum()),mean_model_score=float(scores[mask].mean()),observed_label_rate=float(y[mask].mean())))
    results.append(dict(model_id=version,contest_id=cid,week=testweek,slate=c['slate'],format=fmt,rich=rich,cohort=len(rs),full_field=c['field_size'],positive_rate=float(y.mean()),roc_auc=float(roc_auc_score(y,scores))if len(set(y))==2 else None,average_precision=float(average_precision_score(y,scores))if y.sum()else None,brier=float(brier_score_loss(y,scores)),baseline_mean_auc=float(roc_auc_score(y,X[:,0]))if len(set(y))==2 else None,portfolio_size=k,model_top5_hits=int(y[indices[:k]].sum()),baseline_mean_top5_hits=int(y[baseline[:k]].sum()),candidate_coverage_hit_upper_bound=min(k,int(y.sum())),calibration=bins,selected_roster_keys=[rs[i]['roster_key']for i in indices[:k]],baseline_roster_keys=[rs[i]['roster_key']for i in baseline[:k]],training_audit=audit))
   print(version,'train',audit['distinct_canonical_rosters'],'scopes',audit['training_scopes'],'testcontests',len({r['contest_id']for r in test}),flush=True)
manifest=dict(contract_id=CONTRACT,source_hashes=sources,context_count=len(contexts),sampled_context_rows=len(records),distinct_canonical_rosters=len({(r['format'],r['week'],r['roster_key'])for r in records}),forecasts_imputed=False,postgame_predictors=False,fold_policy='whole weeks held out including overlapping games/slates',sampling='lowest5000SHA256canonicalrosterspercontest, label-independent',dedup_policy='one canonical roster total loss weight across input variants, per-context labels retained, multiplicity never predictor/weight',outcomes_previously_inspected=True,independent_source_code_chronology_verified=False,production_defaults_changed=False)
(P/'model_manifest.json').write_text(json.dumps(manifest,indent=2));(P/'metrics.json').write_text(json.dumps(results,indent=2));print('contexts',len(contexts),'sampled',len(records),'distinct',manifest['distinct_canonical_rosters'],'models',len(models),'metrics',len(results))
