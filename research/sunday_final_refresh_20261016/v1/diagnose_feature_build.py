from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.app.product_services.optimizer import OptimizerService
from backend.app.services.lineup_learning import LineupLearningService
import json,traceback
P=Path(__file__).resolve().parent;s=OptimizerService();e=create_engine(s.connection_string,connect_args={'options':'-c default_transaction_read_only=on'})
with Session(e) as session:
 svc=LineupLearningService(session)
 try:
  print('readonly projection lookup',flush=True);a,b=svc._compute_player_projection_lookup(source_system='draftkings',season=2026,week=6,slate='SUNDAY_MAIN');print('readonly player pool',flush=True);pool=svc._fetch_slate_player_pool(source_system='draftkings',season=2026,week=6,slate='SUNDAY_MAIN',projection_lookup=a,dst_projection_lookup=b);print('rows',len(pool),flush=True)
 except Exception as exc:
  out=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc());(P/'feature_build_diagnostic.json').write_text(json.dumps(out,indent=2)+'\n');print(out['type'],out['message'],flush=True)
