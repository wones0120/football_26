"""Read-only research snapshot; no ingest, optimizer execution, or database writes.

PYTHONPATH=. .venv/bin/python scripts/capture_showdown_qb_construction.py
Existing snapshots are never overwritten. Remove nothing to refresh: use --output.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from Database.config import get_connection_string


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/showdown_qb_construction/inputs'))
    out = parser.parse_args().output
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'manifest.json').exists():
        raise SystemExit('Snapshot already exists; use a new --output directory.')
    with create_engine(get_connection_string()).connect() as conn:
        conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        def query(sql, params=None):
            return [dict(r) for r in conn.execute(text(sql), params or {}).mappings()]
        contests = query('''SELECT c.*, count(e.entry_id)::int AS loaded_entries,
            count(*) FILTER (WHERE e.lineup_text LIKE 'CPT %')::int AS cpt_entries
            FROM target.dfs_contest c LEFT JOIN target.dfs_contest_entry_result e USING(contest_id)
            GROUP BY c.contest_id ORDER BY season,week,slate_id,contest_id''')
        support = {
            'contests': contests,
            'sources': query('SELECT * FROM target.source_file_import'),
            'salaries': query("SELECT * FROM public.curated_salary WHERE source_system='draftkings' AND season>=2024"),
            'starters': query('SELECT * FROM public.starting_qb_evidence'),
            'schedule': query('SELECT * FROM public.raw_nfl_schedule WHERE season>=2024'),
            'snapshots': query("SELECT * FROM public.source_snapshot WHERE dataset ILIKE '%market%' OR dataset ILIKE '%depth%' OR dataset ILIKE '%starter%' OR dataset='salary'"),
            'payout_tiers': query('SELECT * FROM target.dfs_contest_payout_tier'),
            'saved_observations': query('SELECT * FROM target.saved_dk_contest_observation'),
            'legacy_inventory': query('''SELECT season,week,slate,source_file,count(*)::int AS rows,
                count(entry_id)::int AS entries,count(*) FILTER(WHERE lineup_text LIKE 'CPT %')::int AS cpt_entries
                FROM public.dk_contest_standings_rows GROUP BY season,week,slate,source_file'''),
            'optimizer_runs': query("SELECT * FROM target.optimizer_run WHERE contest_format='showdown' ORDER BY created_at"),
        }
        support['optimizer_lineups'] = query('''SELECT l.*,r.season,r.week,r.slate_id,r.strategy,
            jsonb_agg(jsonb_build_object('player_id',p.player_id,'roster_position',p.roster_position,
                'salary',p.salary,'player_json',p.player_json) ORDER BY p.slot_index) AS players
            FROM target.lineup l JOIN target.optimizer_run r USING(optimizer_run_id)
            JOIN target.lineup_player p USING(lineup_id) WHERE r.contest_format='showdown'
            GROUP BY l.lineup_id,r.season,r.week,r.slate_id,r.strategy ORDER BY l.created_at''')
        (out / 'support.json').write_text(json.dumps(support, default=str, sort_keys=True)+'\n')
        raw_query='''SELECT r.*,i.source_path,i.source_checksum,i.started_at,i.completed_at
            FROM public.raw_salary_row r JOIN public.ingest_run i USING(ingest_run_id)
            WHERE r.raw_row_json->>'Roster Position' IN ('CPT','FLEX')'''
        recovered={'raw_salaries':query(raw_query+" AND r.season=2026 AND r.week=3 AND r.slate='THURSDAY_NIGHT'"),
            'aliases':query("SELECT * FROM public.player_alias WHERE source_system='draftkings'"),
            'qb_stats':query('''SELECT s.season,s.week,s.player_id AS native_id,s.team,s.raw_row_json,a.player_master_id
                FROM public.raw_nfl_weekly_stat s JOIN public.player_alias a
                ON a.source_key=s.player_id AND a.source_system='nflreadpy'
                WHERE s.position='QB' AND s.season BETWEEN 2023 AND 2026
                ORDER BY s.raw_nfl_weekly_stat_id DESC''')}
        (out/'recovered_salary.json').write_text(json.dumps(recovered,default=str,sort_keys=True)+'\n')
        historical=query(raw_query+' AND r.season=2025 AND r.week IN (5,6,8,9,13)')
        (out/'raw_historical_salaries.json').write_text(json.dumps(historical,default=str,sort_keys=True)+'\n')
        for contest in contests:
            if not contest['cpt_entries'] and contest['contest_format'] != 'showdown':
                continue
            cid = contest['contest_id']
            rows = query('''SELECT lineup_text,rank,entry_points,count(*)::int AS n
                FROM target.dfs_contest_entry_result WHERE contest_id=:cid
                GROUP BY lineup_text,rank,entry_points ORDER BY rank,lineup_text''', {'cid':cid})
            with gzip.open(out / (cid+'.json.gz'), 'wt') as f:
                json.dump({'contest':contest,'entries':rows}, f, default=str, sort_keys=True)
            print(contest['season'],contest['week'],contest['slate_id'],cid,sum(r['n'] for r in rows),flush=True)
    paths = sorted(p for p in out.iterdir() if p.is_file())
    manifest = {'captured_at':datetime.now(timezone.utc).isoformat(),
        'transaction':'REPEATABLE READ READ ONLY',
        'git_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    (out / 'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')


if __name__ == '__main__':
    main()
