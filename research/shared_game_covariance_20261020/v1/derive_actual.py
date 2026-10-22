"""Read reviewed physical context and completed native team-score parents."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.offensive_environment_catalog import read_reviewed_environment_catalog
from backend.app.product_services.scoreboard_result_features import read_indexed_scoreboard,build_opponent_team_point_distributions
from backend.app.product_services.shared_game_covariance import build_shared_game_covariance
from backend.app.product_services.factual_designation import clock
from backend.app.product_services.evaluation_record import digest
root=Path('research/shared_game_covariance_20261020/v1');started=datetime.now(UTC);start=time.monotonic()
env_receipt=json.loads(Path('research/environment_context_evidence_20261019/v1/actual_combined_receipt.json').read_text());score_receipt=json.loads(Path('research/scoreboard_result_features_20261020/v1/actual_receipt.json').read_text());ref=score_receipt['full_ref']
p=Path(ref['path']);assert p.resolve().parent==Path('artifacts/scoreboard_result_features').resolve();raw=p.read_bytes();assert len(raw)==ref['bytes']and hashlib.sha256(raw).hexdigest()==ref['sha256'];scores=json.loads(raw)
assert scores['pregame_serving_eligible']is False and clock(scores['provenance']['actual_publication_at'])<=started
assert scores['provenance']['producer_code_sha256']==hashlib.sha256(Path('backend/app/product_services/scoreboard_result_features.py').read_bytes()).hexdigest()
replayed=build_opponent_team_point_distributions([o for g in scores['game_rows']for o in g['source_observations']],{g['game_id']:g['corroboration']for g in scores['game_rows']},before_period=scores['before_period'])
assert replayed['semantic_sha256']==scores['semantic_sha256']
source_refs=[]
with Session(engine)as session:
 snapshot=session.get(SourceSnapshot,env_receipt['parent_artifact_ref']['source_snapshot_id']);plays=read_reviewed_environment_catalog(env_receipt['full_context'],snapshot,actual_read_at=datetime.now(UTC))
 for source in scores['provenance']['scoreboard_sources']:
  observed=read_indexed_scoreboard(session.get(SourceSnapshot,source['snapshot_id']),actual_read_at=datetime.now(UTC))
  assert observed['source_ref']['sha256']==source['sha256'];source_refs.append(observed['source_ref'])
result=build_shared_game_covariance(plays,scores)
result['provenance'].update(physical_context_ref=env_receipt['full_context'],physical_source_provenance=plays['provenance'],completed_score_ref=ref,completed_score_provenance=scores['provenance'],reverified_indexed_score_sources=source_refs,
 actual_read_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in[Path('backend/app/product_services/'+name+'.py')for name in('shared_game_covariance','offensive_environment_catalog','scoreboard_result_features')]})
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=8*1024*1024
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/shared_game_covariance')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb')as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
full=save(result);selected={k:v for k,v in result.items()if k not in('game_rows','team_season_profiles','semantic_sha256','provenance')};selected['team_season_profiles']=[p for p in result['team_season_profiles']if p['team']in{'SF','WAS'}]
gids={g for p in selected['team_season_profiles']for g in p['unique_game_ids']};selected['game_rows']=[g for g in result['game_rows']if g['game_id']in gids]
selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
r=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],
 unique_games=len(result['game_rows']),team_profiles=len(result['team_season_profiles']),known_complete_pairs=sum(len(p['known_complete_game_ids'])for p in result['global_season_profiles']),unknown_pairs=sum(len(p['unknown_pair_game_ids'])for p in result['global_season_profiles']),
 exact_team_covariances=sum(p['exact_full_observed_cohort']['population_covariance']is not None for p in result['team_season_profiles']),known_sample_team_covariances=sum(p['known_complete_sample']['population_covariance']is not None for p in result['team_season_profiles']),
 global_covariance_exact=all(p['exact_full_observed_cohort']['population_covariance']is not None for p in result['global_season_profiles']),reverified_score_source_refs=source_refs,
 source_fetches=0,PBP_record_reads=0,raw_PBP_byte_hash_verification=True,compressed_parent_hash_only=True,parent_inflates=0,alias_reads=0,database_writes=0,models=0,evidence_use=result['evidence_use'],pregame_serving_eligible=False)
(root/'actual_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
