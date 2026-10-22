"""Three serial existing-source native coverage-family/deep passing derivations."""
from pathlib import Path
from datetime import datetime,UTC
import gc,hashlib,json,time
from collections import Counter
import polars as pl
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.deep_coverage_response import build_deep_coverage_response,read_native_attempt_parent,FAMILIES
from backend.app.product_services.participation_source_components import load_participation_snapshot
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.factual_designation import clock
root=Path('research/deep_coverage_response_20261020/v1');start=time.monotonic();started=datetime.now(UTC);outputs=[]
receipt=json.loads(Path('research/coverage_receiver_performance_20261020/v1/actual_receipt.json').read_text())
paths=[Path('backend/app/product_services')/(p+'.py')for p in('deep_coverage_response','coverage_receiver_performance','participation_source_components','fumble_event_components')]
producer_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in paths}
def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=64*1024*1024
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/deep_coverage_response')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb')as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
with Session(engine)as session:
 for entry in receipt['source_inputs']:
  year=entry['season'];read=datetime.now(UTC)
  parent=read_native_attempt_parent(entry['native_ref'],actual_read_at=read,published_at=receipt['actual_completed_at'])
  assert parent['season']==year and parent['semantic_sha256']==entry['semantic_sha256']
  snapshot=session.get(SourceSnapshot,entry['source_snapshot_id']);part=load_participation_snapshot(snapshot,actual_read_at=read)
  assert part['semantic_sha256']==parent['provenance']['participation_semantic_sha256']
  assert parent['provenance']['native_participation']['source_sha256']==snapshot.content_sha256
  descriptor=parent['provenance']['original_PBP_descriptor'];manifest=descriptor['manifest'];p=Path(descriptor['path']);raw=p.read_bytes()
  assert manifest==entry['PBP_manifest']and len(raw)==manifest['bytes']and len(raw)<=64*1024*1024 and hashlib.sha256(raw).hexdigest()==manifest['sha256']==parent['provenance']['original_PBP_sha256']
  assert manifest['url']==f'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{year}.parquet'and clock(manifest['received_at'])<=read;del raw
  names=pl.read_parquet_schema(p);required={'game_id','play_id','season','week','season_type','posteam','defteam','air_yards'};assert required<=set(names)
  frame=pl.read_parquet(p,columns=sorted(required));possible={(e['game_id'],e['play_id'])for e in parent['event_basis']};depths=[];keys=set()
  for row in frame.iter_rows(named=True):
   key=(row['game_id'],str(int(row['play_id'])))
   assert key not in keys;keys.add(key)
   if key in possible:depths.append(row)
  assert len(depths)==len(possible)
  result=build_deep_coverage_response(parent,part,depths)
  result['provenance'].update(native_attempt_ref=entry['native_ref'],native_attempt_published_at=receipt['actual_completed_at'],native_attempt_provenance=parent['provenance'],
   participation_provenance=part['provenance'],original_PBP_descriptor=descriptor,original_PBP_rows=frame.height,possible_attempt_depth_rows=len(depths),
   actual_read_at=read.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_hashes=producer_hashes,
   primary_dictionary='https://nflreadr.nflverse.com/articles/dictionary_participation.html',source_license='CC-BY-SA4.0; FTN Data via nflverse',
   original_availability='Participation released after postseason; revised PBP/currentcapture not original pregame availability')
  full=save(result);selected={k:v for k,v in result.items()if k not in('game_rows','profiles','event_basis','semantic_sha256','provenance')}
  for name in('game_rows','profiles'):selected[name]=[r for r in result[name]if r['team']in{'SF','WAS'}]
  gids={r['game_id']for r in selected['game_rows']};selected['event_basis']=[e for e in result['event_basis']if e['game_id']in gids]
  selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
  def count(key,role='offense',profile=False):
   return sum(row[role][f][key]is not None for row in result['profiles'if profile else'game_rows']for f in FAMILIES)
  ev=result['event_basis']
  out=dict(season=year,full_ref=full,selected_ref=sel,global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],
   native_attempt_ref=entry['native_ref'],participation_snapshot_id=str(snapshot.snapshot_id),participation_sha256=snapshot.content_sha256,PBP_sha256=manifest['sha256'],team_games=len(result['game_rows']),profiles=len(result['profiles']),
   known_deep_events=sum(e['official_nonspike_attempt']is True and e['deep_at_least20']is True and e['reported_family']is not None and e['offense']is not None and e['defense']is not None for e in ev),
   unknown_possible_deep_events=sum(e['deep_at_least20']is not False and(e['official_nonspike_attempt']is None or e['deep_at_least20']is None or e['reported_family']is None or e['offense']is None or e['defense']is None)for e in ev),
   known_deep_by_family=dict(Counter(e['reported_family']for e in ev if e['official_nonspike_attempt']is True and e['deep_at_least20']is True and e['reported_family']is not None)),
   exact_game_EPA_contrasts=count('family_minus_other_deep_EPA'),exact_game_completion_contrasts=count('family_minus_other_deep_completion'),
   exact_team_EPA_contrasts=count('family_minus_other_deep_EPA',profile=True),exact_team_completion_contrasts=count('family_minus_other_deep_completion',profile=True),
   known_sample_game_EPA_contrasts=count('known_sample_EPA_difference'),missing_PBP_games=parent['missing_PBP_game_ids'])
  outputs.append(out);print(json.dumps(out),flush=True);(root/'actual_progress.json').write_text(json.dumps(dict(outputs=outputs),indent=2)+'\n')
  del parent,part,frame,result,selected,depths,keys;gc.collect()
r=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,outputs=outputs,
 source_fetches=0,parent_inflates=0,alias_reads=0,database_writes=0,models=0,evidence_use='historical_postseason_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False)
(root/'actual_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(stage='END',elapsed_seconds=r['elapsed_seconds'])),flush=True)
