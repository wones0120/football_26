"""Serial verified retained-source descriptions only; no training or source fetch."""
from pathlib import Path
from datetime import datetime,UTC
import hashlib,json,time,gc
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.historical_team_interaction_context import load_historical_team_interaction_context,compose_historical_team_interactions
from backend.app.product_services.workload_market_contexts import load_archived_market_context
from backend.app.product_services.evaluation_record import digest
root=Path('research/historical_team_interaction_context_20261020/v1');start=time.monotonic();read=datetime.now(UTC)
sources=json.loads(Path('research/player_opportunity_history_20261020/v1/source_coverage.json').read_text())
with Session(engine) as session:schedule=session.get(SourceSnapshot,'6a346947-eca2-5c0d-abf0-95e52ac72e5b')
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/historical_team_interaction_context')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
outputs=[]
for item in sources:
 season=item['season'];began=time.monotonic();boundary=season*100+18;reference=season*100+4
 context=load_historical_team_interaction_context(item['descriptor'],before_period=boundary,cutoff=read)
 _,markets=load_archived_market_context(schedule,before_period=boundary,cutoff=read)
 result=compose_historical_team_interactions(context,markets,reference_before_period=reference)
 result['provenance']['actual_publication_at']=datetime.now(UTC).isoformat()
 full=save(result);selected={k:v for k,v in result.items() if k not in {'rows','semantic_sha256','provenance'}}
 selected['rows']=[r for r in result['rows'] if r['team']in {'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected)
 selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
 def count(mid,ch):
  field='home_minus_away_covariance' if mid in {'X01-M04','X01-M05'} else 'favorite_minus_underdog_mean' if mid in {'X01-M06','X01-M07'} else 'close_minus_large_mean'
  return sum(r['metrics'][mid][field][ch]is not None for r in result['rows'])
 coverage={mid:dict(defined_population_covariance=sum(r['metrics'][mid]['observed_response']['population_covariance']is not None for r in result['rows'])) for mid in ('X01-M01','X01-M02','X01-M03')}
 coverage.update({f'X01-M{i:02}':{ch:count(f'X01-M{i:02}',ch) for ch in ('physical_snaps','called_pass_fraction','official_carries')} for i in range(4,9)})
 outputs.append(dict(season=season,before_period=boundary,reference_before_period=reference,elapsed_seconds=time.monotonic()-began,
  full_ref=full,selected_ref=sel,global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],
  team_profiles=len(result['rows']),evaluation_game_slots=sum(len(r['logs']) for r in result['rows']),selected_profiles=len(selected['rows']),
  coverage=coverage,source_provenance=context['provenance'],reference=result['reference'],cutpoints=result['cutpoints']))
 print(json.dumps(dict(season=season,elapsed_seconds=outputs[-1]['elapsed_seconds'],coverage=coverage)),flush=True)
 del context,result,selected,markets;gc.collect()
receipt=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,outputs=outputs,
 source_scope='Each retained 2023–25 source: REG strictly before week18; reference targets before week4; evaluated targets weeks4–17',
 evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,
 source_fetches=0,database_writes=0,parent_inflates=0,retained_parquet_season_reads=3,models=0)
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(dict(status='complete',elapsed_seconds=receipt['elapsed_seconds'])),flush=True)
