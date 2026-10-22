"""Offline immutable source composition only; no training or serving registration."""
from datetime import datetime,UTC
from pathlib import Path
import hashlib,json,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.offensive_environment_catalog import load_reviewed_environment_context
from backend.app.product_services.workload_market_contexts import load_archived_market_context
from backend.app.product_services.team_market_interactions import build_team_market_interactions,PRODUCTS
from backend.app.product_services import official_workload_components,team_market_interactions
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.factual_designation import clock
root=Path('research/team_market_interactions_20261020/v1');now=datetime.now(UTC);start=time.monotonic()
env_receipt=json.loads(Path('research/environment_context_evidence_20261019/v1/actual_combined_receipt.json').read_text())
ref=json.loads(Path('research/official_workload_components_20261020/v1/actual_derivation_receipt.json').read_text())['full_ref']
p=Path('artifacts/official_workload_components').resolve()/(ref['sha256']+'.json')
assert str(p)==ref['path'] and p.stat().st_size==ref['bytes']<=16*1024*1024
raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()==ref['sha256'];official=json.loads(raw)
assert official['provenance']['producer_code_sha256']==hashlib.sha256(Path(official_workload_components.__file__).read_bytes()).hexdigest()
assert official['evidence_use']=='postlock_descriptive_not_pregame_or_serving' and official['pregame_serving_eligible'] is False
for field in ('actual_publication_at',):
 assert clock(official['provenance'][field])<=now
for field in ('actual_read_at','actual_derived_at'):
 assert clock(official['provenance']['retrospective_read'][field])<=now
with Session(engine) as session:
 snapshot=session.get(SourceSnapshot,'79230705-26c3-5cbd-af43-b26c9bb4e1bb')
 loaded=load_reviewed_environment_context(env_receipt['full_context'],snapshot,actual_read_at=now)
 schedule_snapshot=session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b')
 schedule,markets=load_archived_market_context(schedule_snapshot,before_period=202607,cutoff=now)
result=build_team_market_interactions(loaded['context'],official,markets,before_period=202607,reference_before_period=202604)
assert all(r['max_history_period'] is None or r['max_history_period']<r['period'] for r in result['game_rows'])
assert result['reference']['max_reference_target_period']<202604
result['provenance'].update(authenticated_environment_intake=loaded['provenance'],official_input_ref=ref,
 producer_code_sha256=hashlib.sha256(Path(team_market_interactions.__file__).read_bytes()).hexdigest(),
 actual_read_at=now.isoformat(),actual_publication_at=datetime.now(UTC).isoformat())
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/team_market_interactions')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items() if k not in {'game_rows','semantic_sha256','provenance'}}
selected['game_rows']=[r for r in result['game_rows'] if r['team'] in {'SF','WAS'}]
selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
receipt=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,
 full_ref=full,selected_ref=sel,global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],
 game_team_rows=len(result['game_rows']),selected_rows=len(selected['game_rows']),reference=result['reference'],
 coverage={mid:dict(known=sum(r['metrics'][mid]['value'] is not None for r in result['game_rows']),unknown=sum(r['metrics'][mid]['value'] is None for r in result['game_rows'])) for mid in PRODUCTS},
 evidence_use=result['evidence_use'],pregame_serving_eligible=False,source_fetches=0,database_writes=0,parent_inflates=0,models=0,
 source_market_semantic_sha256=markets['semantic_sha256'],source_environment_ref=env_receipt['full_context'],source_official_ref=ref)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
