"""Read-only immutable measured-block composition; no parent inflate or DB."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from backend.app.product_services.player_workload_catalog_components import build_player_workload_catalog_components
from backend.app.product_services.player_opportunity_components import require_component_use


def main():
 start=time.monotonic();actual=datetime.now(UTC).isoformat();directory=Path('research/player_workload_catalog_components_20261020/v1')
 inputs={}
 for name,path in [('opportunity','research/player_opportunity_components_20261019/v1/actual_derivation_current_receipt.json'),('effectiveness','research/player_effectiveness_components_20261020/v1/actual_derivation_receipt.json')]:
  ref=json.loads(Path(path).read_text())['full_ref'];raw=Path(ref['path']).read_bytes();assert len(raw)==ref['bytes'] and hashlib.sha256(raw).hexdigest()==ref['sha256'];inputs[name]=(json.loads(raw),ref)
 full=build_player_workload_catalog_components(inputs['opportunity'][0],inputs['effectiveness'][0],before_period=202606)
 full['provenance']['actual_composition_read_at']=actual;full['provenance']['actual_publication_at']=datetime.now(UTC).isoformat();full['provenance']['immutable_input_refs']={k:v[1] for k,v in inputs.items()}
 destination=Path('artifacts/player_workload_catalog_components');destination.mkdir(parents=True,exist_ok=True)
 def save(value):
  raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=16*1024*1024;sha=hashlib.sha256(raw).hexdigest();path=(destination/(sha+'.json')).resolve()
  if path.exists():assert path.read_bytes()==raw
  else:
   with path.open('xb') as stream:stream.write(raw)
  return dict(path=str(path),sha256=sha,bytes=len(raw),semantic_measurements_sha256=value.get('selected_semantic_measurements_sha256') or value['semantic_measurements_sha256'],evidence_use=value['evidence_use'],pregame_serving_eligible=False)
 full_ref=save(full);selected={k:v for k,v in full.items() if k not in {'actor_game_rows','full_team_denominators','identity_review_requests','provenance','semantic_measurements_sha256'}};selected['teams']=['SF','WAS']
 for field in ('actor_game_rows','full_team_denominators','identity_review_requests'):selected[field]=[r for r in full[field] if r['team'] in selected['teams']]
 selected['selected_semantic_measurements_sha256']=hashlib.sha256(json.dumps(selected,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest();selected['provenance']={**full['provenance'],'full_ref':full_ref,'global_semantic_measurements_sha256':full['semantic_measurements_sha256']};selected_ref=save(selected)
 for purpose in ('current_registration','forecast','scenario'):
  try:require_component_use(full,purpose=purpose)
  except ValueError as e:assert 'Postlock' in str(e)
  else:raise AssertionError(purpose)
 coverage={k:dict(actor_rows=sum(k in row['metrics'] for row in full['actor_game_rows']),exact_rows=sum(k in row['metrics'] and row['metrics'][k].get('exact_within_log_sum',row['metrics'][k].get('exact_within_log_value')) is not None for row in full['actor_game_rows'])) for k in full['definitions']}
 receipt=dict(status='Actual verified-small-block retrospective G03/G06/G08 composition; High pending',full_ref=full_ref,selected_ref=selected_ref,full_actor_games=len(full['actor_game_rows']),selected_actor_games=len(selected['actor_game_rows']),coverage=coverage,source_gaps=full['source_gaps'],input_refs={k:v[1] for k,v in inputs.items()},actual_read_at=actual,actual_publication_at=full['provenance']['actual_publication_at'],elapsed_seconds=time.monotonic()-start,current_uses_rejected=True,fits=0,source_fetches=0,database_writes=0,parent_inflates=0,model_optimizer_consumers='Deferred under features-only priority')
 (directory/'actual_derivation_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))

if __name__=='__main__':main()
