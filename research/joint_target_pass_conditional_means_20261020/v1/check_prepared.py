"""Small saved-tensor audit: no source reconstruction, fit, or model load."""
from pathlib import Path
from collections import Counter
import hashlib,json
import numpy as np
from backend.app.product_services import joint_target_pass_conditional_means as model
R=Path(__file__).resolve().parent
m=json.loads((R/'MANIFEST.json').read_text())
def verified(ref):
 b=Path(ref['path']).read_bytes();assert len(b)==ref['bytes']and hashlib.sha256(b).hexdigest()==ref['sha256'];return b
from io import BytesIO
meta=json.loads(verified(m['group_metadata_ref']));z=np.load(BytesIO(verified(m['tensor_ref'])),allow_pickle=False)
raw,X=z['raw_inputs'],z['X'];y,B,offsets=z['labels'],z['budgets'],z['offsets'];years=z['group_years'];p=m['preprocessing']
assert len(meta)==279 and Counter(str(g['period']//100)for g in meta)=={'2023':88,'2024':102,'2025':89}
assert X.shape==(12884,140) and raw.shape==(12884,70) and len(offsets)==280 and offsets[-1]==len(y)
assert not any(any(s in k for s in ('label','proof','current','eligible','budget'))for k in m['feature_columns'])
assert np.isfinite(X).all() and np.isfinite(y).all() and np.equal(np.floor(y),y).all() and (y>=0).all()
train=np.concatenate([np.arange(a,b)for a,b,year in zip(offsets[:-1],offsets[1:],years)if year==2023])
med=np.asarray([np.nanmedian(raw[train,j])if np.isfinite(raw[train,j]).any()else 0. for j in range(raw.shape[1])])
assert np.array_equal(med,p['medians'])
filled=np.where(np.isnan(raw[train]),med,raw[train]);center=filled.mean(0);scale=filled.std(0);scale[scale==0]=1.
assert np.array_equal(center,p['centers']) and np.array_equal(scale,p['scales'])
expected=raw.copy()
for name in p['entirely_missing_train_columns']:expected[:,m['feature_columns'].index(name)]=np.nan
missing=np.isnan(expected);expectX=np.concatenate(((np.where(missing,med,expected)-center)/scale,missing.astype(float)),axis=1)
assert np.array_equal(X,expectX)
assert p['cell_label_scale']==max(1.,float(y[train].std()))
assert p['budget_label_scale']==max(1.,float(B[years==2023].std()))
zero=Counter();labels_from_metadata=[]
for i,g in enumerate(meta):
 a,b=offsets[i:i+2];assert b-a==len(g['cells'])and [c['kind']for c in g['cells'][-2:]]==['outside_target_rest','source_pass_minus_target_remainder']
 assert y[a:b].sum()==B[i]==g['pass_budget_label'] and y[a:b-1].sum()==z['target_budgets'][i]==g['target_budget_label']
 assert len(g['prior_games'])==3 and all(int(prior[:4])==g['period']//100 and int(prior[:4])*100+int(prior.split('_')[1])<g['period']for prior in g['prior_games'])
 for c in g['cells']:
  labels_from_metadata.append(c['label'])
  if c['kind']=='candidate' and c['label_basis']!='KNOWN_CURRENT_SOURCE_ROW':assert c['label']==0;zero[str(g['period']//100)]+=1
assert np.array_equal(y,labels_from_metadata) and dict(zero)==m['source_zero_label_cells']
admission=json.loads(Path(m['target_admission_ref']['path']).read_text())
assert {(g['game_id'],g['team'])for g in meta}=={tuple(k)for k in admission['qualified_fixed_keys']}
assert p['target_budget_label_scale']==max(1.,float(z['target_budgets'][years==2023].std()))
# The initial objective is finite; evaluating it is NOT optimization/fitting.
ids=np.flatnonzero(years==2023);last=offsets[len(ids)]
d=dict(X=X[:last],labels=y[:last],budgets=B[ids],target_budgets=z['target_budgets'][ids],offsets=offsets[:len(ids)+1].tolist())
loss,grad=model.objective(model.core.initial_parameters(X.shape[1]),d,p)
assert np.isfinite(loss) and np.isfinite(grad).all()
result=dict(status='PASS',groups=len(meta),cells=len(y),source_zero_labels=dict(zero),train_cells=len(train),objective_evaluations=1,optimizer_calls=0,fits=0)
(R/'PREPARED_CHECK.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
