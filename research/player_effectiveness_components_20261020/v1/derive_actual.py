"""Coordinated descriptive source derivation only; no model/runtime/DB writes."""
from datetime import datetime,UTC
from pathlib import Path
import hashlib,json,time
from collections import Counter
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.factual_designation import clock
from backend.app.product_services.market_snapshots import canonical_team
from backend.app.product_services.player_effectiveness_components import derive_retrospective_player_effectiveness

def main():
 root=Path('research/player_effectiveness_components_20261020/v1');start=time.monotonic();actual=datetime.now(UTC).isoformat()
 source=json.loads(Path('research/player_opportunity_components_20261019/v1/actual_derivation_current_receipt.json').read_text());ref=source['parent_artifact_ref'];prior_ref=source['full_ref'];raw=Path(prior_ref['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==prior_ref['sha256'];prior=json.loads(raw)
 games={}
 for row in prior['team_denominators']:
  parts=row['game_id'].split('_');key=(row['team'],int(parts[0]),int(parts[1]));assert key not in games;games[key]=row['game_id']
 with engine.connect() as connection:
  positions=connection.execute(text("""SELECT DISTINCT ON(r.player_id,r.season,r.week) r.player_id,r.season,r.week,r.team,r.position,r.raw_nfl_weekly_stat_id,r.created_at
  FROM public.raw_nfl_weekly_stat r
  WHERE r.season=2026 AND r.week BETWEEN1 AND5 AND r.raw_row_json->>'season_type'='REG'
  AND r.position IN('QB','RB','FB','WR','TE') AND r.created_at<=:cutoff
  ORDER BY r.player_id,r.season,r.week,r.created_at DESC,r.raw_nfl_weekly_stat_id DESC""".replace('BETWEEN1 AND5','BETWEEN 1 AND 5')),dict(cutoff=actual)).mappings().all()
 proofs=[];unbound=0
 for row in positions:
  team=canonical_team(row['team']);game=games.get((team,int(row['season']),int(row['week'])))
  if game is None:unbound+=1;continue
  proofs.append(dict(game_id=game,team=team,source_player_id=row['player_id'],position=row['position'],player_master_id=None,
   source_id=str(row['raw_nfl_weekly_stat_id']),source_uri='nflreadpy://weekly_stats/2026',available_at=clock(row['created_at']).isoformat(),
   evidence_kind='Observed historical native game-stat position classification, not current availability or projected workload',clock_basis='Actual internal UTC import timestamp; original game-time publication unknown'))
 with Session(engine) as session:
  snapshot=session.get(SourceSnapshot,ref['source_snapshot_id']);assert snapshot is not None
  full=derive_retrospective_player_effectiveness(ref,snapshot,actual_read_at=actual,position_evidence=proofs)
 publication=dict(actual_publication_at=datetime.now(UTC).isoformat(),actual_started_at=actual,meaning='Postlock descriptive feature publication only; not current Monday/pregame serving',parent_artifact_ref=ref)
 full['provenance']['artifact_publication']=publication;destination=Path('artifacts/player_effectiveness_components');destination.mkdir(parents=True,exist_ok=True)
 def save(value,bound):
  raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=bound;sha=hashlib.sha256(raw).hexdigest();path=(destination/(sha+'.json')).resolve()
  if path.exists():assert path.read_bytes()==raw
  else:
   with path.open('xb') as f:f.write(raw)
  return dict(path=str(path),sha256=sha,bytes=len(raw),semantic_measurements_sha256=value.get('selected_semantic_measurements_sha256') or value['semantic_measurements_sha256'],evidence_use=value['evidence_use'],pregame_serving_eligible=False)
 full_ref=save(full,16*1024*1024);selected={k:v for k,v in full.items() if k not in {'actor_game_rows','team_denominators','identity_review_requests','unattributed_events','provenance','semantic_measurements_sha256'}};selected['teams']=['SF','WAS']
 for field in ('actor_game_rows','team_denominators','identity_review_requests','unattributed_events'):selected[field]=[r for r in full[field] if r['team'] in selected['teams']]
 selected['selected_semantic_measurements_sha256']=hashlib.sha256(json.dumps(selected,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest();selected['provenance']={**full['provenance'],'full_ref':full_ref,'global_semantic_measurements_sha256':full['semantic_measurements_sha256']};selected_ref=save(selected,2*1024*1024)
 coverage={}
 for key in full['definitions']:
  rows=[r for r in full['actor_game_rows'] if key in r['metrics']];coverage[key]=dict(actor_game_rows=len(rows),known_sample_rows=sum(r['metrics'][key]['known_attributed_sample_mean'] is not None for r in rows),exact_within_log_rows=sum(r['metrics'][key]['exact_within_log_mean'] is not None for r in rows),proven_QB_rows=sum(r['metrics'][key]['catalog_scope_status']=='source_proven_QB' for r in rows),unknown_scope_rows=sum(r['position'] is None for r in rows))
 r=dict(status='actual_postlock_descriptive_24_variant_feature_derivation_not_model_or_serving',full_ref=full_ref,selected_ref=selected_ref,parent_artifact_ref=ref,position_source_rows=len(positions),scoped_position_proofs=len(proofs),unbound_position_rows=unbound,full_actor_games=len(full['actor_game_rows']),selected_actor_games=len(selected['actor_game_rows']),position_status=dict(Counter(r['position_status'] for r in full['actor_game_rows'])),metric_coverage=coverage,source_gaps=full['source_gaps'],catalog_full_completion_claim=False,elapsed_seconds=time.monotonic()-start,fits=0,source_fetches=0,database_writes=0,model_optimizer_integration='Separatelypending/deferred by featuresONLYpriority',actual_publication=publication)
 (root/'actual_derivation_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))

if __name__ == "__main__":
 main()
