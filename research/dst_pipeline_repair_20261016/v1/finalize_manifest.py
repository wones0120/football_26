"""Record final reviewed contracts without repeating unchanged model fits."""
from pathlib import Path
import hashlib
import json
import joblib
P=Path(__file__).resolve().parent
artifact=joblib.load(P/'candidate_models.joblib');manifest=artifact['metadata']
manifest.pop('artifact_sha256',None)
manifest['final_reviewed_code_sha256']={path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in manifest['code_sha256']}
manifest['final_reviewed_code_sha256'][str(Path(__file__))]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
manifest['post_fit_contract_tightening']='Canonical candidate loader now requires explicit verified label dataset; experiment already selected those exact corrected labels before fitting. No feature/model/math/criteria changed after results. Original fit code hashes retained.'
manifest['model_parameters']={name:str(model.get_params()) for name,model in artifact['models'].items()}
joblib.dump(artifact,P/'candidate_models.joblib',compress=3)
manifest['artifact_sha256']=hashlib.sha256((P/'candidate_models.joblib').read_bytes()).hexdigest()
(P/'candidate_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
