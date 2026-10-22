"""Exactly one fixed family fit each on the reviewed immutable prepared matrix."""
from datetime import UTC,datetime
import hashlib,json,signal,time
from pathlib import Path
from io import BytesIO
import joblib
from backend.app.product_services.feature_block_model_inputs import fit_player_family,predict_player_families
R=Path('research/player_opportunity_models_20261020/v1');D=Path('artifacts/player_opportunity_models');D.mkdir(parents=True,exist_ok=True)
def now():return datetime.now(UTC).isoformat()
def save_bytes(raw,suffix):
 sha=hashlib.sha256(raw).hexdigest();p=D/(sha+suffix)
 if p.exists():assert p.read_bytes()==raw
 else:p.write_bytes(raw)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
def save_json(value):return save_bytes(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode(),'.json')
def checkpoint(stage,**kwargs):
 v=dict(stage=stage,actual_at=now(),**kwargs);(R/'actual_fit_progress.json').write_text(json.dumps(v,indent=2));print(json.dumps(v),flush=True)
def timeout(*_):raise TimeoutError('Bounded fixed player-family fit exceeded300seconds; no automatic retry/tuning')
signal.signal(signal.SIGALRM,timeout)
start=time.monotonic();ref=json.loads((R/'corrected_preprocessing_receipt.json').read_text())['prepared_ref'];raw=Path(ref['path']).read_bytes();assert len(raw)==ref['bytes'] and hashlib.sha256(raw).hexdigest()==ref['sha256'];p=json.loads(raw);del raw
bundles={};refs={};receipts={}
try:
 for family in ('tree','neural'):
  checkpoint('fitting_'+family,actual_family_fits_started=len(bundles)+1,prepared_ref=ref)
  signal.alarm(300);b=fit_player_family(p,family=family);signal.alarm(0);bundles[family]=b
  envelope=dict(contract='player_opportunity_model_artifact_v1',published_at=now(),bundle=b)
  stream=BytesIO();joblib.dump(envelope,stream,compress=3);mr=save_bytes(stream.getvalue(),'.joblib');mr.update(contract=envelope['contract'],published_at=envelope['published_at'],family=family,receipt_sha256=hashlib.sha256(json.dumps(b['receipt'],sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest())
  refs[family]=mr;receipts[family]=b['receipt'];checkpoint(family+'_fit_complete',status=b['receipt']['status'],convergence=b['receipt']['convergence_by_target'],model_ref=mr)
 matrix_ref=json.loads((R/'corrected_preprocessing_receipt.json').read_text())['matrix_ref'];raw=Path(matrix_ref['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==matrix_ref['sha256'];m=json.loads(raw);del raw
 rows=[v for v in m['rows'] if v['current_inference']];predictions=None
 if all(b['receipt']['status']=='fit_complete' for b in bundles.values()):predictions=predict_player_families(bundles['tree'],bundles['neural'],rows,before_period=m['before_period'])
 result=dict(status='actual_two_player_families_fitted_not_registered_or_app_consumed',started_at=datetime.fromtimestamp(time.time()-(time.monotonic()-start),UTC).isoformat(),completed_at=now(),elapsed_seconds=time.monotonic()-start,actual_family_fits=2,model_refs=refs,receipts=receipts,prepared_ref=ref,matrix_ref=matrix_ref,forward_predictions=predictions,forward_rows=len(rows),chronology='Postlock isolated retrospective inference on frozen inputs; not Monday entry-ready.2025test distinct from inspected2026diagnostic. Revised-source original historical availability unproven.')
 rr=save_json(result);(R/'actual_fit_receipt.json').write_text(json.dumps(dict(result_ref=rr,**{k:v for k,v in result.items() if k not in {'receipts','forward_predictions'}}),indent=2));checkpoint('all_fits_complete',result_ref=rr,elapsed_seconds=result['elapsed_seconds'],statuses={k:v['status'] for k,v in receipts.items()},forward_predictions=len(predictions) if predictions else None)
except Exception as e:
 signal.alarm(0);checkpoint('failed',error_type=type(e).__name__,error=str(e),completed_family_refs=refs);raise
