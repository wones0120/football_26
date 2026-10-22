from pathlib import Path
from datetime import datetime,UTC
import hashlib,json,time
from backend.app.product_services.backup_qb_experience import build_backup_qb_experience
import backend.app.product_services.backup_qb_experience as producer
import backend.app.product_services.active_workload_distributions as history_producer
R=Path('research/backup_qb_experience_20261020/v1');now=datetime.now(UTC);start=time.monotonic()
href=json.loads(Path('research/active_workload_distributions_20261020/v1/actual_receipt.json').read_text())['full_ref']
def load(ref,root):
 p=Path(ref['path']).resolve();raw=p.read_bytes();assert p.parent==Path(root).resolve() and p.name==ref['sha256']+'.json' and len(raw)==ref['bytes'] and len(raw)<=16*1024*1024 and hashlib.sha256(raw).hexdigest()==ref['sha256'];return json.loads(raw)
history=load(href,'artifacts/active_workload_distributions');assert history['provenance']['producer_code_sha256']==hashlib.sha256(Path(history_producer.__file__).read_bytes()).hexdigest()
p=Path('artifacts/player_role_features/4bb624af9759f84969d1dea42608a552f05ed4775f459d9e3be474a9514764dc.json');rref=dict(path=str(p.resolve()),sha256=p.stem,bytes=p.stat().st_size);roles=load(rref,'artifacts/player_role_features')
result=build_backup_qb_experience(roles,history,season=2026,week=6,cutoff=now)
result['provenance']=dict(actual_read_at=now.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),history_ref=href,role_ref=rref,producer_sha256=hashlib.sha256(Path(producer.__file__).read_bytes()).hexdigest(),original_role_cutoff=roles['original_source_cutoff'],original_history_sources=history['provenance'])
raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/backup_qb_experience')/(sha+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==raw
else:
 with p.open('xb') as f:f.write(raw)
r=dict(artifact_ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(raw)),backup_actors=len(result['rows']),known_attempt_totals=sum(r['official_pass_attempts'] is not None for r in result['rows']),known_participation_counts=sum(r['proven_participating_games'] is not None for r in result['rows']),actor_summary=[{k:v for k,v in r.items() if k not in {'logs','role_proof'}} for r in result['rows']],history_ref=href,role_ref=rref,evidence_use=result['evidence_use'],elapsed_seconds=time.monotonic()-start,actual_completed_at=datetime.now(UTC).isoformat(),database_writes=0,source_fetches=0,model_fits=0,parent_inflates=0)
(R/'actual_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
