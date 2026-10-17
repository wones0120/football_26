"""Add matrix-value fingerprints and environment evidence without refitting."""
from pathlib import Path
import hashlib
import json
import platform
import joblib
import numpy
import pandas
import sklearn
P=Path(__file__).resolve().parent
artifact=joblib.load(P/'dedicated_dst.joblib')
manifest=artifact['metadata']
manifest.pop('artifact_sha256',None)
for key in ['features','target_features']:
    raw=artifact[key].to_json(orient='split',double_precision=15).encode()
    manifest[f'{key}_values_sha256']=hashlib.sha256(raw).hexdigest()
manifest['environment']=dict(python=platform.python_version(),numpy=numpy.__version__,pandas=pandas.__version__,sklearn=sklearn.__version__)
manifest['code_hashes'][str(Path(__file__))]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
joblib.dump(artifact,P/'dedicated_dst.joblib',compress=3)
manifest['artifact_sha256']=hashlib.sha256((P/'dedicated_dst.joblib').read_bytes()).hexdigest()
(P/'candidate_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Feature values, runtime versions and final artifact checksum recorded')
