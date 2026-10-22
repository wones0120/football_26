from datetime import UTC,datetime
from pathlib import Path
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.observed_depth_changes import load_observed_depth_sources
import backend.app.product_services.observed_depth_changes as producer
R=Path('research/observed_depth_changes_20261020/v1');now=datetime.now(UTC);start=time.monotonic()
role_path=Path('artifacts/player_role_features/4bb624af9759f84969d1dea42608a552f05ed4775f459d9e3be474a9514764dc.json');raw=role_path.read_bytes();assert hashlib.sha256(raw).hexdigest()==role_path.stem
role=json.loads(raw);aliases={}
for a in role['extracted']['actors']:aliases.setdefault(a['source_player_id'],set()).add(a['player_master_id'])
ids=['038d9b0b-5340-5bdf-92fb-02ab2dd78801','fea6a15b-42ff-56fa-b934-054aa8715b0f','dcb27ca6-dbcb-5695-967a-9667f25a5f28','a7f5f27b-9bfa-5a60-8809-32dc0b4dad80']
with Session(engine) as s:
 result=load_observed_depth_sources([s.get(SourceSnapshot,i) for i in ids],aliases,season=2026,week=6,teams=['SF','WAS'],cutoff=now)
result['provenance'].update(producer_sha256=hashlib.sha256(Path(producer.__file__).read_bytes()).hexdigest(),actual_derived_at=datetime.now(UTC).isoformat(),identity_attachment=dict(path=str(role_path.resolve()),sha256=role_path.stem,bytes=len(raw),basis='Previously reviewed frozen native GSIS to canonical actor map; no historical role transplant'))
b=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(b).hexdigest();p=Path('artifacts/observed_depth_changes')/(sha+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==b
else:
 with p.open('xb') as f:f.write(b)
coverage=[]
for c in result['comparisons']:
 changes=[r for r in c['matched_roles'] if r['rank_delta'] not in (None,0)]
 coverage.append(dict(prior=c['prior_snapshot_id'],current=c['current_snapshot_id'],matched_roles=len(c['matched_roles']),known_deltas=sum(r['rank_delta'] is not None for r in c['matched_roles']),rank_changes=len(changes),special_team_rank_changes=sum(r['unit']=='special_teams' for r in changes),new_roles=len(c['newly_observed_roles']),not_observed_roles=len(c['not_observed_roles'])))
receipt=dict(artifact_ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(b)),coverage=coverage,identity_review_requests=result['identity_review_requests'],actual_read_at=now.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,source_snapshots=ids,evidence_use=result['evidence_use'],model_fits=0,source_fetches=0,database_writes=0)
(R/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
