from pathlib import Path
import json,joblib
from sqlalchemy import text
from backend.app.product_services.optimizer import OptimizerService,_json_safe
from backend.app.product_services.model_artifacts import load_run_artifact
P=Path(__file__).resolve().parent;s=OptimizerService()
with s.engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 a,m=load_run_artifact(c,'b2ae485d-f436-470b-a52c-fa53095bbd4d');joblib.dump(a,P/'prepared_incumbent.joblib');m.pop('artifact_bytes',None);(P/'prepared_metadata.json').write_text(json.dumps(_json_safe(m),indent=2,default=str));print('prepared',len(a['train']),len(a['target']),len(a['feature_columns']))
