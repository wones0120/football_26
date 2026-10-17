from pathlib import Path
from datetime import datetime,UTC
import json
from sqlalchemy import text
from backend.app.product_services.optimizer import OptimizerService,_json_safe
P=Path(__file__).resolve().parent;s=OptimizerService();q="SELECT * FROM public.player_game_feature_matrix WHERE position IN ('DST','D','DEF') AND season BETWEEN 2024 AND 2026 AND (season<2026 OR week<=5) ORDER BY season,week,team,player_game_feature_matrix_id"
with s.engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'));rows=[dict(r) for r in c.execute(text(q)).mappings()]
(P/'all_dst_matrix_rows.json').write_text(json.dumps(_json_safe(dict(captured_at=datetime.now(UTC).isoformat(),query=q,rows=rows)),indent=2)+'\n');print('physical rows',len(rows))
