"""Read-only artifact and temporal-fold validation; no additional model fits."""
from collections import defaultdict
from datetime import datetime,timezone
import gzip,hashlib,json,math,pathlib
from backend.app.product_services.lineup_top_decile_research import CORE_FEATURES,RICH_FEATURES,CONTRACT
P=pathlib.Path(__file__).resolve().parent
manifest=json.loads((P/'model_manifest.json').read_text());metrics=json.loads((P/'metrics.json').read_text());rows=[];checks=defaultdict(int);contexts={};semantic={}
for name,expected in manifest['source_hashes'].items():
 path=P/name;assert hashlib.sha256(path.read_bytes()).hexdigest()==expected
 with gzip.open(path,'rt')as f:payload=json.load(f)
 semantic[name]=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest();c=payload['context'];contexts[c['contest_id']]=c
 for r in payload['rosters']:
  assert r['label']==int(round(r['points'],2)>=c['points_cutoff'])
  assert len(r['signature'])==(6 if c['contest_format']=='showdown'else 9)
  assert len({p[0]for p in r['signature']})==len(r['signature'])
  assert sum(p[1]for p in r['signature'])==(1 if c['contest_format']=='showdown'else 0)
  assert hashlib.sha256(json.dumps(r['signature']).encode()).hexdigest()==r['roster_key']
  assert len(r['features'])==len(CORE_FEATURES) and all(math.isfinite(v)for v in r['features'])
  rows.append(dict(fmt=c['contest_format'],week=c['week'],roster=r['roster_key'],run=c['projection_run_id'],contest=c['contest_id'],label=r['label'],corehash=hashlib.sha256(json.dumps(r['features']).encode()).hexdigest(),richhash=hashlib.sha256(json.dumps(r['rich_features']).encode()).hexdigest()if r['rich_features']is not None else None))
  checks['validated_canonical_feature_rows']+=1
calibration=[]
for path in sorted((P/'models').glob('*.json')):
 model=json.loads(path.read_text());assert model['contract_id']==CONTRACT and model['C']==.1
 assert all(w<model['test_week']for w in model['train_weeks'])
 assert model['features']in[CORE_FEATURES,CORE_FEATURES+RICH_FEATURES]
 assert all(len(model[k])==len(model['features'])for k in ['mean','scale','coefficients'])
 checks['validated_models']+=1
 rich='rich' in model['model_id'];variants=defaultdict(dict);counts=defaultdict(set)
 for r in rows:
  if r['fmt']!=model['format']or r['week']not in model['train_weeks']:continue
  h=r['richhash']if rich else r['corehash']
  if h is None:continue
  canonical=(r['week'],r['roster']);key=(*canonical,r['run'],h);variants[key][r['contest']]=r['label'];counts[canonical].add(key)
 numerator=denominator=0
 for key,labels in variants.items():
  w=1/len(counts[key[:2]]);numerator+=w*sum(labels.values())/len(labels);denominator+=w
 prior=numerator/denominator
 for m in metrics:
  if m['model_id']==model['model_id']:
   q=m['positive_rate'];calibration.append(dict(model_id=m['model_id'],contest_id=m['contest_id'],train_only_dedup_prevalence=prior,constant_baseline_brier=(1-q)*prior**2+q*(1-prior)**2,model_brier=m['brier']))
result=dict(checks=dict(checks),semantic_dataset_hashes=semantic,temporal_policy='every training week strictly precedes test week; no same-week game/slate crosses folds',class_label_contract='contest decile boundary, ties included at DK-cent precision',strict_original_source_code_chronology_certified=False,projection_imputation=False,additional_model_fits=0)
(P/'validation.json').write_text(json.dumps(result,indent=2));(P/'calibration_baseline.json').write_text(json.dumps(calibration,indent=2));print(dict(checks))
