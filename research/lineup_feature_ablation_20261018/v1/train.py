"""24 fixed small fits. This phase writes NO held-out evaluation metrics."""
from collections import defaultdict
from pathlib import Path
import gzip,hashlib,json
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
from backend.app.product_services.lineup_ablation_research import CONTRACT,TREATMENTS,active_indices
from backend.app.product_services.lineup_top_decile_research import CORE_FEATURES,RICH_FEATURES
P=Path(__file__).resolve().parent;T=Path('research/top_decile_lineup_model_20261018/v1');records=[];sources={}
for path in sorted((T/'contests_v2').glob('*.json.gz')):
 with gzip.open(path,'rt')as f:d=json.load(f)
 c=d['context']
 if c['contest_format']!='classic':continue
 sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
 for row in d['rosters']:
  core=row['rich_features'][:len(CORE_FEATURES)]if row['rich_features']is not None else row['features']
  records.append({'week':c['week'],'slate':c['slate'],'contest_id':c['contest_id'],'projection_run_id':c['projection_run_id'],'roster_key':row['roster_key'],'core':core,'rich':row['rich_features'],'label':row['label']})

def cohort(rows,family):
 groups={};variants=defaultdict(set)
 for row in rows:
  full=row[family]
  if full is None:continue
  canonical=(row['week'],row['roster_key']);key=(*canonical,row['projection_run_id'],hashlib.sha256(json.dumps(full).encode()).hexdigest());variants[canonical].add(key)
  g=groups.setdefault(key,{'full':full,'canonical':canonical,'labels':{},'contexts':set()});g['labels'][row['contest_id']]=row['label'];g['contexts'].add((row['week'],row['slate']))
 return [{**g,'target':sum(g['labels'].values())/len(g['labels']),'weight':1/len(variants[g['canonical']])}for g in groups.values()]
models=[];controls=[];proxy_audits=[]
(P/'models').mkdir(exist_ok=True)
for family in ['core','rich']:
 names=CORE_FEATURES+(RICH_FEATURES if family=='rich'else[])
 for testweek in [4,5,6]:
  rows=[r for r in records if r['week']<testweek];groups=cohort(rows,family);full=np.asarray([g['full']for g in groups]);target=np.asarray([g['target']for g in groups]);weights=np.asarray([g['weight']for g in groups]);cohort_hash=hashlib.sha256(json.dumps([{k:g[k]for k in ['full','canonical','target','weight']}for g in groups],sort_keys=True).encode()).hexdigest()
  # Feature-only association audit on training inputs, not selected using outcomes.
  cov=np.corrcoef(full,rowvar=False);correlations=[]
  removed=set().union(*(TREATMENTS[t]for t in ['remove_salary','remove_stacking']))
  for i,a in enumerate(names):
   if a not in removed:continue
   pairs=[{'retained_feature':b,'correlation':float(cov[i,j])}for j,b in enumerate(names)if b not in removed and np.isfinite(cov[i,j])]
   correlations.append({'removed_feature':a,'strongest_remaining_correlations':sorted(pairs,key=lambda p:-abs(p['correlation']))[:3]})
  proxy_audits.append({'family':family,'test_week':testweek,'training_only':True,'rows':len(groups),'correlations':correlations})
  for treatment in TREATMENTS:
   indices=active_indices(names,treatment);X=full[:,indices];scaler=StandardScaler().fit(X,sample_weight=weights);Z=scaler.transform(X);XX=np.concatenate([Z,Z]);yy=np.r_[np.zeros(len(Z)),np.ones(len(Z))];ww=np.r_[weights*(1-target),weights*target]
   model=LogisticRegression(C=.1,max_iter=400,solver='lbfgs')
   with threadpool_limits(limits=1):model.fit(XX,yy,sample_weight=ww)
   if max(model.n_iter_)>=400:raise ValueError('Ablation fit did not converge')
   key=f'classic_{family}_{treatment}_before_w{testweek}';artifact={'contract_id':CONTRACT,'model_id':key,'format':'classic','family':family,'treatment':treatment,'base_features':names,'features':[names[i]for i in indices],'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist(),'coefficients':model.coef_[0].tolist(),'intercept':float(model.intercept_[0]),'C':.1,'train_weeks':sorted({r['week']for r in rows}),'test_week':testweek,'cohort_sha256':cohort_hash,'training_variants':len(groups),'training_canonical_rosters':len({g['canonical']for g in groups}),'training_scopes':len({v for g in groups for v in g['contexts']}),'converged':True,'probability_status':'uncalibrated retrospective research propensity','live_promoted':False}
   if treatment=='original':
    old=json.load(open(T/'models'/f'classic_{family}_train_before_w{testweek}.json'));difference=max(abs(a-b)for field in ['mean','scale','coefficients']for a,b in zip(artifact[field],old[field]));difference=max(difference,abs(artifact['intercept']-old['intercept']));controls.append({'model_id':key,'maximum_original_numeric_difference':difference});assert difference<1e-9,(key,difference)
   path=P/'models'/(key+'.json')
   with path.open('x')as f:json.dump(artifact,f,indent=2)
   models.append({'model_id':key,'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'family':family,'treatment':treatment,'test_week':testweek,'cohort_sha256':cohort_hash});print(key,'train',len(groups),flush=True)
manifest={'contract_id':CONTRACT,'models':models,'source_hashes':sources,'protocol_sha256':hashlib.sha256((P/'PROTOCOL.md').read_bytes()).hexdigest(),'implementation_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'original_control_reproduction':controls,'outcomes_previously_inspected':True,'evaluation_not_run_by_this_script':True,'live_promoted':False}
with(P/'model_manifest.json').open('x')as f:json.dump(manifest,f,indent=2)
with(P/'retained_proxy_audit.json').open('x')as f:json.dump(proxy_audits,f,indent=2)
print('models frozen',len(models),'originals reproduced',len(controls))
