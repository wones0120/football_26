import json,hashlib
from pathlib import Path
from io import BytesIO
import joblib,numpy as np
from backend.app.product_services.feature_block_model_inputs import _predict
R=Path('research/player_opportunity_models_20261020/v1');r=json.loads((R/'actual_adam_fit_receipt.json').read_text());v=json.loads(Path(r['result_ref']['path']).read_text());ref=v['prepared_ref'];raw=Path(ref['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==ref['sha256'];p=json.loads(raw);del raw
out={}
for family,ref in v['model_refs'].items():
 raw=Path(ref['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==ref['sha256'];b=joblib.load(BytesIO(raw))['bundle'];splits={}
 for split,part in p['splits'].items():
  pred=_predict(b,np.asarray(part['x']));groups={}
  for position in sorted({k['position'] for k in part['keys']}):
   for channel in p['target_columns']:
    ids=[i for i,k in enumerate(part['keys']) if k['position']==position and part['labels'][i][channel] is not None]
    if ids:
     actual=np.array([part['labels'][i][channel] for i in ids]);a=pred[channel][ids];groups[position+':'+channel]=dict(rows=len(ids),zero_labels=int(sum(actual==0)),mean_actual=float(actual.mean()),mean_predicted=float(a.mean()),mae=float(abs(a-actual).mean()),bias=float((a-actual).mean()))
  splits[split]=groups
 out[family]=splits
(R/'actual_position_channel_metrics.json').write_text(json.dumps(out,indent=2));print('Position/channel metrics saved; no fit')
