from pathlib import Path
from datetime import datetime,UTC
from collections import defaultdict,Counter
import json,hashlib,time
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import PlayerAlias,SourceSnapshot
from backend.app.product_services.nextgen_tracking_features import derive_nextgen_features,VERSION
from backend.app.product_services.defense_context_evidence import _hash
ROOT=Path('research/nextgen_tracking_features_20261020/v1')
def save(x):
 raw=json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/nextgen_features')/f'{sha}.json';p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
start=time.monotonic();began=datetime.now(UTC).isoformat();source=json.loads(Path('research/nextgen_source_components_20261020/v1/actual_capture_receipt.json').read_text())
with Session(engine) as session:
 aliases=defaultdict(set)
 for native,pid in session.execute(select(PlayerAlias.source_key,PlayerAlias.player_master_id).where(PlayerAlias.source_system=='nflreadpy')):
  if native.startswith('00-'):aliases[native].add(str(pid))
 ids={k:next(iter(v)) for k,v in aliases.items() if len(v)==1}
 snapshots={x['stat_type']:session.get(SourceSnapshot,x['snapshot_id']) for x in source['families']}
 value=derive_nextgen_features(snapshots,before_period=202607,cutoff=datetime.now(UTC),canonical_ids=ids)
full=save(value);selected=json.loads(json.dumps(value));selected['rows']=[r for r in value['rows'] if r['season']==2026 and r['team'] in {'SF','WAS'}];selected['selected_scope']=dict(season=2026,teams=['SF','WAS'],parent_semantic_sha256=value['semantic_sha256']);selected['selected_semantic_sha256']=_hash(dict(version=VERSION,before_period=202607,selected_scope=selected['selected_scope'],rows=[{k:v for k,v in r.items() if k!='source_snapshot_id'} for r in selected['rows']]));selection=save(selected)
r=dict(version=VERSION,actual_started_at=began,actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=selection,global_semantic_sha256=value['semantic_sha256'],rows=len(value['rows']),selected_rows=len(selected['rows']),selected_semantic_sha256=selected['selected_semantic_sha256'],excluded=value['excluded'],canonical_attached=sum(x['player_master_id'] is not None for x in value['rows']),ambiguous_native_alias_keys=sum(len(v)>1 for v in aliases.values()),metric_known={m:sum(r['metrics'].get(m,{}).get('value') is not None for r in value['rows']) for m in ('G04-M02','G07-M10')},by_season={str(y):dict(Counter(r['stat_type'] for r in value['rows'] if r['season']==y)) for y in sorted({r['season'] for r in value['rows']})},source_snapshot_ids={k:str(s.snapshot_id) for k,s in snapshots.items()},evidence_use=value['evidence_use'],pregame_serving_eligible=False,model_consumer='Paused/pending; source measurements only',producer_code_sha256=value['provenance']['producer_code_sha256'])
(ROOT/'actual_derivation_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
