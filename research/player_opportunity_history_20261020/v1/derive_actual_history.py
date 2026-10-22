"""One coordinated serial retained-source job; no fetch/fit/database write."""
from collections import defaultdict
from datetime import UTC,datetime
import hashlib,json,time
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import PlayerAlias,PlayerMaster
from backend.app.product_services.player_opportunity_history import load_retrospective_player_components

root=Path('research/player_opportunity_history_20261020/v1');descriptors=json.loads((root/'source_coverage.json').read_text());started=datetime.now(UTC).isoformat();timer=time.monotonic()
identities=defaultdict(set)
with Session(engine) as session:
 rows=session.execute(select(PlayerAlias.source_key,PlayerAlias.player_master_id).join(PlayerMaster,PlayerMaster.player_master_id==PlayerAlias.player_master_id).where(PlayerAlias.source_system=='nflreadpy',PlayerAlias.source_key.op('~')('^00-[0-9]{7}$'))).all()
 for native,pid in rows:identities[native].add(str(pid))
canonical={native:next(iter(pids)) for native,pids in identities.items() if len(pids)==1};ambiguous=sorted(native for native,pids in identities.items() if len(pids)!=1)
identity_semantic=hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode()).hexdigest()
managed=Path('artifacts/player_opportunity_history');managed.mkdir(parents=True,exist_ok=True);outputs=[]
for source in descriptors:
 began=time.monotonic();block=load_retrospective_player_components(source['descriptor'],cutoff=started,canonical_ids=canonical)
 block['provenance']['canonical_identity_resolution']=dict(source_system='nflreadpy',rule='Exact persisted native GSIS source_key joined to canonical PlayerMaster; no name matching',actual_resolved_at=started,unique_native_map_sha256=identity_semantic,unique_native_aliases=len(canonical),ambiguous_native_keys=ambiguous,queue_persistence='Returned requests require existing identity queue intake; no DB mutation in this job')
 block['provenance']['actual_publication_at']=datetime.now(UTC).isoformat()
 raw=json.dumps(block,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=64*1024*1024
 sha=hashlib.sha256(raw).hexdigest();path=(managed/(sha+'.json')).resolve()
 if path.exists():assert path.read_bytes()==raw
 else:
  with path.open('xb') as handle:handle.write(raw)
 position_counts=defaultdict(int)
 for actor in block['actor_game_rows']:position_counts[actor['position_status']]+=1
 result=dict(season=source['season'],managed_ref=dict(path=str(path),sha256=sha,bytes=len(raw),version=block['version'],semantic_measurements_sha256=block['semantic_measurements_sha256'],evidence_use=block['evidence_use'],pregame_serving_eligible=False),actor_games=len(block['actor_game_rows']),canonical_actor_games=sum(r['player_master_id'] is not None for r in block['actor_game_rows']),team_games=len(block['team_denominators']),identity_requests=len(block['identity_review_requests']),unattributed_events=len(block['unattributed_events']),position_status=dict(position_counts),source_rows=block['provenance']['source_rows'],source_sha256=source['verified_byte_sha256'],source_received_at=block['provenance']['actual_source_received_at'],actual_derived_at=block['provenance']['actual_derived_at'],elapsed_seconds=time.monotonic()-began)
 outputs.append(result);print(json.dumps(result),flush=True)
 summary=dict(status='actual_revised_retrospective_player_components_materialized_not_fit_or_served',actual_started_at=started,actual_completed_at=datetime.now(UTC).isoformat(),outputs=outputs,unique_native_aliases=len(canonical),ambiguous_native_keys=ambiguous,native_identity_map_sha256=identity_semantic,elapsed_seconds=time.monotonic()-timer,actual_source_loads=len(outputs),fits=0,source_fetches=0,database_writes=0,current_serving=False,source_chronology='Original2026receipt clocks retained; original historical pregame availability unknown',model_consumer='A03 offline retrospective player matrix only; later tree/NN fit/optimizer consumer tracked separately')
 (root/'actual_history_derivation_receipt.json').write_text(json.dumps(summary,indent=2)+'\n')
