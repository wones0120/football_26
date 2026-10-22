"""Three serial historical native coverage derivations; no new source capture."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time,gc
import polars as pl
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.participation_source_components import load_participation_snapshot
from backend.app.product_services.participation_defense_catalog import build_participation_defense_catalog
from backend.app.product_services.evaluation_record import digest
root=Path('research/participation_defense_catalog_20261020/v1');start=time.monotonic();outputs=[]
sources=json.loads(Path('research/participation_source_components_20261020/v1/actual_receipt.json').read_text())['outputs']
history={r['season']:r['descriptor']for r in json.loads(Path('research/player_opportunity_history_20261020/v1/source_coverage.json').read_text())}
columns=['game_id','play_id','season','week','season_type','posteam','defteam','play_type','play_type_nfl','desc','no_play','quarter_end','fumble','pass_attempt','rush_attempt','sack','qb_dropback','qb_spike','qb_kneel','qb_scramble','two_point_attempt']
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/participation_defense_catalog')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb')as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
with Session(engine)as session:
 for item in sources:
  year=item['season']
  if year not in history:continue
  read=datetime.now(UTC);snapshot=session.get(SourceSnapshot,item['source']['snapshot_id']);block=load_participation_snapshot(snapshot,actual_read_at=read)
  assert block['semantic_sha256']==item['semantic_sha256']
  d=history[year];p=Path(d['path']);raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()==d['manifest']['sha256']and len(raw)==d['manifest']['bytes'];del raw
  names=pl.read_parquet_schema(p);frame=pl.read_parquet(p,columns=[k for k in columns if k in names])
  result=build_participation_defense_catalog(block,frame.iter_rows(named=True),before_period=202607)
  result['provenance'].update(original_PBP_manifest=d['manifest'],original_PBP_path=str(p.resolve()),actual_read_at=read.isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),
   producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/participation_defense_catalog.py').read_bytes()).hexdigest(),
   source_adapter_sha256=hashlib.sha256(Path('backend/app/product_services/participation_source_components.py').read_bytes()).hexdigest(),
   eligibility_helper_sha256=hashlib.sha256(Path('backend/app/product_services/fumble_event_components.py').read_bytes()).hexdigest())
  full=save(result);selected={k:v for k,v in result.items()if k not in {'team_game_rows','team_season_rows','event_basis','semantic_sha256','provenance'}}
  selected['team_game_rows']=[r for r in result['team_game_rows']if r['team']in {'SF','WAS'}];selected['team_season_rows']=[r for r in result['team_season_rows']if r['team']in {'SF','WAS'}]
  gids={r['game_id']for r in selected['team_game_rows']};selected['event_basis']=[r for r in result['event_basis']if r['game_id']in gids];selected['selected_semantic_sha256']=digest(selected)
  selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected);rows=result['team_game_rows']
  output=dict(season=year,full_ref=full,selected_ref=sel,global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],
   team_games=len(rows),selected_rows=len(selected['team_game_rows']),native_source_snapshot_id=str(snapshot.snapshot_id),native_source_sha256=snapshot.content_sha256,
   known_nonspike_dropbacks=sum(r['known_eligible_dropbacks']for r in rows),unknown_eligible_dropbacks=sum(r['unknown_eligible_dropbacks']for r in rows),
   category_counts={k:sum(r[k+'_dropbacks']for r in rows)for k in ['classified','man','zone','mixed','other','unclassified']},
   exact_game_rates={mid:sum(r['metrics'][mid]['value']is not None for r in rows)for mid in ['G14-M04','G14-M05']},
   pressure_variant=dict(known_native_pressure_count=sum(r['source_pressure_count']for r in rows),unknown_outcomes=sum(r['unknown_pressure_outcomes']for r in rows),
      sack_conflicts=sum(r['sack_pressure_conflicts']for r in rows),definition_status='G14-M01notcompleted;vendorHHS taxonomy unknown'),
   missing_participation_rows=sum(r['missing_participation_rows']for r in rows),source_join_conflicts=sum(r['source_join_conflicts']for r in rows))
  outputs.append(output);(root/'actual_progress.json').write_text(json.dumps(dict(outputs=outputs,elapsed_seconds=time.monotonic()-start),indent=2)+'\n')
  print(json.dumps(output),flush=True);del block,frame,result,selected;gc.collect()
r=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,outputs=outputs,source_fetches=0,parent_inflates=0,models=0,database_writes=0,
 evidence_use='historical_postseason_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,unmaterialized_2022='No retainedPBPnativejoin;no source eligibility/phase assumption',candidate_full_ids=['G14-M04','G14-M05'],pressureM01='native measuredvariantonly;taxonomy gap retained')
(root/'actual_receipt.json').write_text(json.dumps(r,indent=2)+'\n')
