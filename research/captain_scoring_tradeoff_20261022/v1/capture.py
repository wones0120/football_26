"""Capture imported evidence locally; never access DraftKings or mutate the DB."""
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import text
from backend.app.db import engine

out = Path(__file__).parent
target = out / 'inputs.json.gz'
if target.exists():
    raise SystemExit('Preserve existing capture')
with engine.connect() as c:
    c.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
    c.execute(text("SET LOCAL statement_timeout='60000'"))
    def query(sql):
        return [dict(r) for r in c.execute(text(sql)).mappings()]
    data = {
        'contests': query("SELECT * FROM target.dfs_contest WHERE season=2026 AND contest_format='showdown' ORDER BY week,slate_id,contest_id"),
        'entries': query("SELECT e.contest_id,e.rank,e.entry_points,e.lineup_text,count(*) AS n FROM target.dfs_contest_entry_result e JOIN target.dfs_contest c USING(contest_id) WHERE c.season=2026 AND c.contest_format='showdown' GROUP BY e.contest_id,e.rank,e.entry_points,e.lineup_text"),
        'observations': query("SELECT o.* FROM target.contest_ownership_observation o JOIN target.dfs_contest c USING(contest_id) WHERE c.season=2026 AND c.contest_format='showdown'"),
        'salaries': query("SELECT * FROM curated_salary WHERE season=2026 AND source_system='draftkings'"),
        'raw_salaries': query("SELECT * FROM raw_salary_row WHERE season=2026 AND raw_row_json->>'Roster Position' IN ('CPT','FLEX')"),
        'aliases': query("SELECT * FROM player_alias WHERE source_system='draftkings'"),
        'schedule': query("SELECT * FROM raw_nfl_schedule WHERE season=2026"),
    }
with gzip.open(target, 'wt') as f:
    json.dump(data, f, default=str, sort_keys=True)
(out / 'manifest.json').write_text(json.dumps({
    'captured_at': datetime.now(timezone.utc).isoformat(),
    'transaction': 'REPEATABLE READ READ ONLY',
    'source': 'local imported database; no DraftKings access',
    'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
    'counts': {k: len(v) for k, v in data.items()},
}, indent=2) + '\n')
print({k: len(v) for k, v in data.items()})
