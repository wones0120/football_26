"""Explicit read-only exports. Outcomes are a separate, post-specification phase."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUNS = [
    '3a41af88-a28c-41b1-888c-462ddcd7d74d',
    'a07b5a67-f041-49e0-ad51-4001ba04fb79',
    '17212766-52eb-40ed-9544-e599d7bfb8bd',
    '442dd04c-7c8c-46f6-80c5-273924e7c655',
    '9c07a5bd-11ac-42b1-a0d0-7e6b3a30fb4f',
    'dc21b3ab-c330-487c-bb88-766f9a71f04c',
]
REPORT = Path('/Users/wones/Downloads/week-learning-2026-w05-wones0120 (2).md')
CLAIMS = Path('/Users/wones/.codex/attachments/2fbc34c0-c599-4924-be22-ddb515a77ba1/Pasted text.txt')
CODE = [
    'backend/app/product_services/optimizer.py',
    'backend/app/product_services/showdown_portfolio_selection.py',
    'backend/app/product_services/showdown_captain_shortlist.py',
    'backend/app/product_services/showdown_captain_preferences.py',
    'backend/app/product_services/optimizer_effectiveness.py',
    'backend/app/product_services/showdown_ownership_policy.py',
    'backend/app/product_services/player_context_scoring.py',
    'backend/app/product_services/showdown_candidate_comparison.py',
    'backend/app/product_services/lineup_correlation_scoring.py',
    'artifacts/showdown_qb_construction/audited_code/optimizer.py.0bbba8146455.txt',
    'artifacts/showdown_qb_construction/audited_code/showdown_portfolio_selection.py.4bdbc82c5f83.txt',
]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, indent=2, sort_keys=True, default=str, allow_nan=False) + '\n'
    if path.exists():
        if path.read_text() != data:
            raise ValueError(f'Refusing to overwrite differing evidence: {path}')
    else:
        path.write_text(data)

def read_report():
    value = REPORT.read_text()
    start = value.index('~~~~json') + 8
    return json.loads(value[start:value.index('~~~~', start)])

def capture(phase):
    from backend.app.db import engine
    from sqlalchemy import text
    if phase == 'outcomes':
        freeze = json.loads((OUT / 'freeze.json').read_text())
        assert sha(OUT / 'SPECIFICATION.md') == freeze['specification_sha256']
        assert sha(OUT / 'prepared.json') == freeze['prepared_sha256']
    with engine.connect() as connection:
        connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
        connection.execute(text('SET TRANSACTION READ ONLY'))
        for run_id in RUNS:
            if phase == 'pregame':
                run = dict(connection.execute(text('SELECT * FROM target.optimizer_run WHERE optimizer_run_id=:id'), {'id':run_id}).mappings().one())
                lineups = [dict(r) for r in connection.execute(text('SELECT * FROM target.lineup WHERE optimizer_run_id=:id ORDER BY lineup_number'), {'id':run_id}).mappings()]
                players = [dict(r) for r in connection.execute(text('SELECT p.* FROM target.lineup_player p JOIN target.lineup l USING(lineup_id) WHERE l.optimizer_run_id=:id ORDER BY l.lineup_number,p.slot_index'), {'id':run_id}).mappings()]
                projection = dict(connection.execute(text('SELECT * FROM target.projection_run WHERE projection_run_id=:id'), {'id':run['projection_run_id']}).mappings().one())
                save(OUT / 'inputs' / f'{run_id}.json', dict(run=run, selected_lineups=lineups, selected_players=players, projection_run=projection))
            else:
                source = json.loads((OUT / 'inputs' / f'{run_id}.json').read_text())['run']
                rows = [dict(r) for r in connection.execute(text('''
                    SELECT o.player_id::text,o.roster_position,o.actual_points,o.resolution_status,
                           o.contest_id::text FROM target.contest_ownership_observation o
                    JOIN target.dfs_contest c USING(contest_id)
                    WHERE c.season=:season AND c.week=:week AND c.slate_id=:slate
                      AND c.contest_format='showdown'
                    ORDER BY o.contest_id,o.player_id,o.roster_position,o.actual_points,o.resolution_status
                '''), dict(season=source['season'],week=source['week'],slate=source['slate_id'])).mappings()]
                save(OUT / 'outcomes' / f'{run_id}.json', rows)
    if phase == 'pregame':
        files = {}
        for relative in CODE:
            src = ROOT / relative
            dst = OUT / 'inputs' / 'code' / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists() and dst.read_bytes() != src.read_bytes():
                raise ValueError('Code snapshot drift: '+relative)
            if not dst.exists():
                dst.write_bytes(src.read_bytes())
            files[relative] = sha(src)
        tracked = subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
        save(OUT / 'workspace_before.json', {p:sha(ROOT/p) for p in tracked if p and (ROOT/p).is_file()})
        save(OUT / 'input_manifest.json', dict(
            git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
            code_sha256=files, source_sha256={r:sha(OUT/'inputs'/f'{r}.json') for r in RUNS},
            report=dict(path=str(REPORT),sha256=sha(REPORT)), claims=dict(path=str(CLAIMS),sha256=sha(CLAIMS)),
            queries='REPEATABLE READ / READ ONLY; exact six optimizer IDs and their projection IDs; no latest-data lookup',
        ))
    else:
        report=read_report()
        save(OUT / 'outcomes' / 'report_evidence.json', dict(
            report_id=report['report_id'], sha256=sha(REPORT),
            slates=[dict(slate=s['slate'],field_benchmarks=s['optimizer_effectiveness']['field_benchmarks'],
                         runs=s['optimizer_effectiveness']['runs'],entries=s['entries'])
                    for s in report['slate_reports'] if any(r['optimizer_run_id'] in RUNS for r in s['optimizer_effectiveness']['runs'])],
            history=[r for r in report['optimizer_effectiveness_history'] if r['optimizer_run_id'] in RUNS],
        ))
    print(json.dumps(dict(phase=phase, read_only=True, runs=len(RUNS))))

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('phase',choices=['pregame','outcomes'])
    capture(parser.parse_args().phase)
