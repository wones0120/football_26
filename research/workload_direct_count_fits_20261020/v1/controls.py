"""One saved prepared-array read/grain for SAME-row history/constant controls."""
from pathlib import Path
import json,hashlib
import numpy as np
from backend.app.product_services.raw_count_player_models import count_metrics
R=Path('research/workload_direct_count_fits_20261020/v1');P=Path('research/pressure_count_model_fits_20261020/v1')
def refread(r):
 b=Path(r['path']).read_bytes();assert len(b)==r['bytes']and hashlib.sha256(b).hexdigest()==r['sha256'];return json.loads(b)
def key(r,g):return(r['game_id'],r['team'],r.get('player_master_id'))if g=='player'else(r['game_id'],r['team'])
out={}
for grain in('team','player'):
 job0=json.loads((R/(grain+'_tree.json')).read_text());prepared=refread(job0['prepared_ref']);cols=prepared['preprocessing']['columns'];p=prepared['preprocessing'];targets=prepared['target_columns'];train=prepared['splits']['train'];ys=train['labels']if grain=='player'else[dict(zip(targets,y))for y in train['y']];means={t:float(np.mean([r[t]for r in ys if r[t]is not None]))for t in targets}
 for family in('tree','neural'):
  name=grain+'_'+family;j=json.loads((R/(name+'.json')).read_text());rows=refread(j['prediction_ref']);old=refread(json.loads((P/(name+'.json')).read_text())['prediction_ref']);om={(r['split'],key(r,grain)):r for r in old};rm={(r['split'],key(r,grain)):r for r in rows};out[name]={}
  for split,part in prepared['splits'].items():
   out[name][split]={};groups={'ALL':list(range(len(part['keys'])))}
   if grain=='player':groups.update({position:[i for i,k in enumerate(part['keys'])if k['position']==position]for position in sorted({k['position']for k in part['keys']})})
   for position,ids in groups.items():
    out[name][split][position]={}
    for t in targets:
     known=[i for i in ids if rm[(split,key(part['keys'][i],grain))]['actual'][t]is not None];field=('pass_mean3'if t=='pass_attempts'else'rush_mean3')if grain=='team'else t+'_mean3';ci=cols.index(field);matched=[i for i in known if part['x'][i][len(cols)+ci]==0];rs=[rm[(split,key(part['keys'][i],grain))]for i in matched];actual=[r['actual'][t]for r in rs];history=[part['x'][i][ci]*p['scale'][ci]+p['center'][ci]for i in matched]
     common=[i for i in known if(split,key(part['keys'][i],grain))in om and om[(split,key(part['keys'][i],grain))]['actual'][t]is not None];nr=[rm[(split,key(part['keys'][i],grain))]for i in common];orr=[om[(split,key(part['keys'][i],grain))]for i in common];a=[r['actual'][t]for r in nr]
     out[name][split][position][t]=dict(history_matched_rows=len(matched),model_on_history_rows=count_metrics(actual,[r['predicted'][t]for r in rs]),history3_on_SAME_rows=count_metrics(actual,history),constant_on_SAME_rows=count_metrics(actual,[means[t]]*len(rs)),saved_prior_matched_rows=len(common),new_on_prior_rows=count_metrics(a,[r['predicted'][t]for r in nr]),saved_prior_on_NEW_labels=count_metrics(a,[r['predicted'][t]for r in orr]))
 del prepared
(R/'MATCHED_CONTROLS.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
