from datetime import UTC,datetime
import hashlib,json,time
from pathlib import Path
from backend.app.product_services.feature_block_model_inputs import prepare_player_inputs
R=Path('research/player_opportunity_models_20261020/v1');D=Path('artifacts/player_opportunity_matrices')
r=json.loads((R/'actual_matrix_receipt.json').read_text());ref=r['matrix_ref'];start=time.monotonic();raw=Path(ref['path']).read_bytes()
assert len(raw)==ref['bytes'] and hashlib.sha256(raw).hexdigest()==ref['sha256']
m=json.loads(raw);del raw
p=prepare_player_inputs(m,train_before=202401,validation_before=202501)
b=json.dumps(p,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(b).hexdigest();path=D/(sha+'.json')
if path.exists():assert path.read_bytes()==b
else:path.write_bytes(b)
o=dict(status='corrected_preprocessing_frozen_not_fit',actual_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,matrix_ref=ref,prepared_ref=dict(path=str(path.resolve()),sha256=sha,bytes=len(b)),prepared_sha256=p['prepared_sha256'],matrix_sha256=p['matrix_sha256'],split_rows={k:len(v['keys']) for k,v in p['splits'].items()},entirely_missing_train_columns=p['preprocessing']['entirely_missing_train_columns'],raw_feature_columns=len(p['preprocessing']['columns']),fitted_numeric_support=len(p['preprocessing']['columns'])-len(p['preprocessing']['entirely_missing_train_columns']),chronology='2025 retrospective test separated from inspected2026 diagnostic; revised sources not original pregame proof')
(R/'corrected_preprocessing_receipt.json').write_text(json.dumps(o,indent=2));print(json.dumps(o),flush=True)
