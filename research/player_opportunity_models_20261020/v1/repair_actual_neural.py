from datetime import UTC,datetime
import hashlib,json,signal,time
from pathlib import Path
from io import BytesIO
import joblib
from backend.app.product_services.feature_block_model_inputs import repair_neural_convergence,predict_player_families
R=Path('research/player_opportunity_models_20261020/v1');D=Path('artifacts/player_opportunity_models')
def read(ref):
 raw=Path(ref['path']).read_bytes();assert len(raw)==ref['bytes'] and hashlib.sha256(raw).hexdigest()==ref['sha256'];return raw
def save(raw,suffix):
 sha=hashlib.sha256(raw).hexdigest();path=D/(sha+suffix)
 if path.exists():assert path.read_bytes()==raw
 else:path.write_bytes(raw)
 return dict(path=str(path.resolve()),sha256=sha,bytes=len(raw))
def timeout(*_):raise TimeoutError('One approved1500-step neural warm restart exceeded300s; no automatic repeat')
start=time.monotonic();initial_ref=json.loads((R/'actual_fit_receipt.json').read_text())['result_ref'];initial=json.loads(read(initial_ref));prep=json.loads(read(initial['prepared_ref']));prior=joblib.load(BytesIO(read(initial['model_refs']['neural'])))['bundle']
signal.signal(signal.SIGALRM,timeout);signal.alarm(300);repaired=repair_neural_convergence(prior,prep);signal.alarm(0)
envelope=dict(contract='player_opportunity_model_artifact_v1',published_at=datetime.now(UTC).isoformat(),bundle=repaired);stream=BytesIO();joblib.dump(envelope,stream,compress=3);ref=save(stream.getvalue(),'.joblib');ref.update(contract=envelope['contract'],published_at=envelope['published_at'],family='neural',receipt_sha256=hashlib.sha256(json.dumps(repaired['receipt'],sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest())
result=dict(initial);result.update(completed_at=datetime.now(UTC).isoformat(),repair_elapsed_seconds=time.monotonic()-start,parent_result_ref=initial_ref,repair_operation='One deepcopied fitted-weight warm restart; L-BFGS history restarted; no tree refit/grid');result['model_refs']=dict(initial['model_refs'],neural=ref);result['receipts']=dict(initial['receipts'],neural=repaired['receipt']);result['forward_predictions']=None
if repaired['receipt']['status']=='fit_complete':
 tree=joblib.load(BytesIO(read(initial['model_refs']['tree'])))['bundle'];m=json.loads(read(initial['matrix_ref']));rows=[r for r in m['rows'] if r['current_inference']];result['forward_predictions']=predict_player_families(tree,repaired,rows,before_period=m['before_period'])
rr=save(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode(),'.json');summary=dict(result_ref=rr,parent_result_ref=initial_ref,model_refs=result['model_refs'],status=repaired['receipt']['status'],convergence=repaired['receipt']['convergence_by_target'],repair_elapsed_seconds=result['repair_elapsed_seconds'],forward_predictions=len(result['forward_predictions']) if result['forward_predictions'] else None)
(R/'actual_repaired_fit_receipt.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)
