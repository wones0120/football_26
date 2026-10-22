"""Metadata-only immutable composition, preserving original measured arrays/clocks."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,UTC
import json,hashlib,time
from backend.app.product_services.official_efficiency_features import DEFINITIONS as VARIANT_DEFINITIONS
from backend.app.product_services.evaluation_record import digest

root=Path('research/official_efficiency_catalog_20261020/v1');started=time.monotonic();now=datetime.now(UTC)
receipt=json.loads((root/'actual_derivation_receipt_before_team_definition_binding.json').read_text())
ref=receipt['full_ref'];path=Path(ref['path']).resolve();raw=path.read_bytes()
assert path.parent==Path('artifacts/official_efficiency_catalog').resolve() and path.name==ref['sha256']+'.json'
assert len(raw)==ref['bytes']<=32*1024*1024 and hashlib.sha256(raw).hexdigest()==ref['sha256']
original=json.loads(raw);value=deepcopy(original)
old_code_sha=hashlib.sha256((root/'producer_before_team_definition_binding.py').read_bytes()).hexdigest()
assert original['provenance']['producer_code_sha256']==old_code_sha
new_code_sha=hashlib.sha256(Path('backend/app/product_services/official_efficiency_catalog.py').read_bytes()).hexdigest()
value['full_team_source_measurement_definitions']=deepcopy(VARIANT_DEFINITIONS)
value['full_team_source_measurement_scope']='Preserved v1 all-source channel measurements; keys follow the variant definition map, not corrected actor catalog definitions'
fields=('version','before_period','definitions','actor_game_rows','full_team_source_measurements','full_team_source_measurement_definitions','full_team_source_measurement_scope','full_team_conversion_measurements')
value['semantic_measurements_sha256']=digest({k:value[k] for k in fields})
for field in ('actor_game_rows','full_team_source_measurements','full_team_conversion_measurements','unattributed_events','unattributed_conversion_events','identity_review_requests'):
 assert value[field]==original[field]
value['provenance'].update(previous_catalog_artifact_ref=ref,measurement_derivation_producer_code_sha256=old_code_sha,
                          metadata_binding_producer_code_sha256=new_code_sha,producer_code_sha256=new_code_sha,
                          actual_metadata_binding_at=now.isoformat(),actual_publication_at=now.isoformat())
# Original actual_read_at and actual_derived_at are deliberately retained.
assert value['provenance']['actual_read_at']==original['provenance']['actual_read_at']
assert value['provenance']['actual_derived_at']==original['provenance']['actual_derived_at']

def save(v):
 b=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(b)<=32*1024*1024
 sha=hashlib.sha256(b).hexdigest();p=Path('artifacts/official_efficiency_catalog')/(sha+'.json')
 if p.exists():assert p.read_bytes()==b
 else:
  with p.open('xb') as f:f.write(b)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(b),semantic_measurements_sha256=v.get('selected_semantic_measurements_sha256') or v['semantic_measurements_sha256'],evidence_use=v['evidence_use'],pregame_serving_eligible=False)
full=save(value)
selected={k:v for k,v in value.items() if k not in {'actor_game_rows','full_team_source_measurements','full_team_conversion_measurements','identity_review_requests','unattributed_events','unattributed_conversion_events','provenance','semantic_measurements_sha256'}};selected['teams']=['SF','WAS']
for field in ('actor_game_rows','full_team_source_measurements','full_team_conversion_measurements','identity_review_requests','unattributed_events','unattributed_conversion_events'):
 selected[field]=[r for r in value[field] if r['team'] in selected['teams']]
selected['selected_semantic_measurements_sha256']=digest(selected)
selected['provenance']=value['provenance']|dict(full_ref=full,global_semantic_measurements_sha256=value['semantic_measurements_sha256'])
sel=save(selected)
receipt.update(full_ref=full,selected_ref=sel,previous_measurement_artifact_ref=ref,metadata_binding_at=now.isoformat(),metadata_binding_elapsed_seconds=time.monotonic()-started,
               metadata_only_numeric_arrays_unchanged=True,metadata_parent_inflations=0,actual_publication_at=now.isoformat())
(root/'actual_derivation_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(dict(full_ref=full,selected_ref=sel,metadata_seconds=receipt['metadata_binding_elapsed_seconds'],numeric_arrays_unchanged=True)))
