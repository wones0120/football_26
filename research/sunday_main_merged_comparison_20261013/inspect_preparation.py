"""Read only saved preparation checkpoint and current canonical context."""
from collections import Counter
from datetime import datetime, UTC
import json
from pathlib import Path
from sqlalchemy import create_engine, text
from Database.config import get_connection_string
from backend.app.product_services.pregame_context import load_current_pregame_context
from backend.app.product_services.optimizer import _json_safe

engine=create_engine(get_connection_string())
with engine.connect() as connection:
 job=dict(connection.execute(text('SELECT job_id,status,stage,progress_message,error_message,checkpoint_json,result_json FROM public.operational_job WHERE job_id=:id'),{'id':'e7227a48-88a1-42b2-83c2-27e988481f00'}).mappings().one())
 contexts=load_current_pregame_context(connection,season=2026,week=6,slate='SUNDAY_MAIN',cutoff=datetime.now(UTC))
 salary=[dict(r) for r in connection.execute(text("SELECT player_master_id,player_name,team,position FROM public.curated_salary WHERE season=2026 AND week=6 AND slate='SUNDAY_MAIN' AND source_system='draftkings'")).mappings()]
by_id={str(c['player_master_id']):c for c in contexts}
issues=[]
for row in salary:
 context=by_id.get(str(row['player_master_id']),{});e=context.get('evidence_json') or {}
 if e.get('availability_state')=='UNKNOWN' or not e.get('canonical_role'):
  issues.append({**row,'availability_state':e.get('availability_state'),'role':e.get('canonical_role'),'source':context.get('source'),'observed_at':context.get('observed_at'),'issues':e.get('issues')})
result=_json_safe(dict(checked_at=datetime.now(UTC),job=job,context_count=len(contexts),availability_counts=dict(Counter((c.get('evidence_json') or {}).get('availability_state') for c in contexts)),issues=issues))
path=Path('research/sunday_main_merged_comparison_20261013/readiness_inspection_after_build.json');path.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in {'issues','job'}}));print({k:v for k,v in result['job'].items() if k not in {'checkpoint_json','result_json'}});print('issues',len(issues),[(r['player_name'],r['team'],r['availability_state'],r['role']) for r in issues][:25])
