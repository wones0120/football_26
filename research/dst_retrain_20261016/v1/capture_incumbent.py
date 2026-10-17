from pathlib import Path
import json
from sqlalchemy import text
from backend.app.product_services.optimizer import OptimizerService,_json_safe
from backend.app.product_services.model_artifacts import load_run_artifact
P=Path(__file__).resolve().parent;s=OptimizerService()
with s.engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 active=[dict(r) for r in c.execute(text("SELECT * FROM target.active_projection_run WHERE season=2026 AND week=6 ORDER BY slate_id")).mappings()]
 (P/'active_baseline.json').write_text(json.dumps(_json_safe(active),indent=2))
 main=next(r for r in active if r['slate_id']=='SUNDAY_MAIN');artifact,meta=load_run_artifact(c,str(main['projection_run_id']))
 import joblib
 joblib.dump(artifact,P/'incumbent.joblib')
 meta.pop('artifact_bytes',None)
 (P/'incumbent_metadata.json').write_text(json.dumps(_json_safe(meta),indent=2,default=str))
 print('active',active); print('train',artifact['train'].shape,'target',artifact['target'].shape,'features',artifact['feature_columns']);print(artifact['train'].groupby(['season','position']).size().to_string());print('model',artifact['model'])
 print('columns',artifact['train'].columns.tolist())
