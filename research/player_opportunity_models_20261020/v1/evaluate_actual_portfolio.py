from datetime import UTC,datetime
import hashlib,json,time
from pathlib import Path
from backend.app.product_services.player_opportunity_replay import evaluate
R=Path('research/player_opportunity_models_20261020/v1');start=time.monotonic();fit=json.loads((R/'actual_adam_fit_receipt.json').read_text());ref=json.loads((R/'corrected_preprocessing_receipt.json').read_text())['matrix_ref'];raw=Path(ref['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==ref['sha256'];matrix=json.loads(raw);del raw
config=json.loads((R/'source_optimizer_config.json').read_text());prepared=json.loads(Path('research/opportunity_component_response_20261019/v1/fullshape_retry_prepare_job.json').read_text())['result']
# No new authored endorsement: these same frozen mechanisms are reused only
# as explicitly dated conditional sensitivity examples after lock.
packet_ref=json.loads(Path('research/opportunity_component_response_20261019/v1/authored_numeric_publication_receipt.json').read_text())
print(json.dumps({'stage':'starting_isolated_model_count_world_optimizer','actual_at':datetime.now(UTC).isoformat()}),flush=True)
result=evaluate(config,prepared,model_result_sha256=fit['result_ref']['sha256'],matrix=matrix,packet=__import__('backend.app.product_services.analyst_packets',fromlist=['load_packet']).load_packet(packet_ref['identity']['packet_sha256']),generation_seconds=30)
D=Path('artifacts/player_opportunity_replays');D.mkdir(exist_ok=True);identity=dict(purpose='isolated_offline_diagnostic_not_public_activation',model_result=fit['result_ref']['sha256'],matrix_ref=ref,source_optimizer_sha256=hashlib.sha256((R/'source_optimizer_config.json').read_bytes()).hexdigest(),source_prepare_job_id='f9639e11-8b21-48ca-82ac-f80a67bbdf78')
from backend.app.product_services.analyst_shadow import digest
key=digest(identity);result.update(replay_id=key,input_identity=identity);result['artifact_sha256']=digest(result);path=D/(key+'.json')
if path.exists():assert json.loads(path.read_text())==result
else:path.write_text(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False))
summary=dict(status=result['status'],actual_at=result['actual_created_at'],elapsed_seconds=time.monotonic()-start,replay_id=key,path=str(path.resolve()),requested=result['requested'],achieved=result['achieved'],selected=result['selected'],entry_ready=False,public_acceptance=False)
(R/'actual_portfolio_diagnostic_receipt.json').write_text(json.dumps(summary,indent=2));print(json.dumps({k:v for k,v in summary.items() if k!='selected'}),flush=True)
