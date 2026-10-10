"""Export read-only contest evidence; never ingest, resolve, or optimize anything.

Run from repo root with PYTHONPATH=. .venv/bin/python scripts/capture_classic_historical_study.py.
The metadata snapshot must already exist. Existing exports are reused, not replaced.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from sqlalchemy import create_engine, text
from Database.config import get_connection_string

OUT = Path('artifacts/classic_historical_study')


def main():
    inventory = json.loads((OUT / 'inventory_snapshot.json').read_text())
    sources = {r['source_file_id']: r for r in inventory['sources']}
    with create_engine(get_connection_string()).connect() as conn:
        conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        for contest in inventory['contests']:
            cid = contest['contest_id']
            output = OUT / 'inputs' / f'{cid}.json.gz'
            if output.exists():
                continue
            # Include mislabeled formats in the inventory; actual slots determine eligibility.
            query = '''SELECT lineup_text, count(*)::int AS n, min(rank) AS best_rank,
                min(entry_points) AS min_points, max(entry_points) AS max_points,
                count(*) FILTER (WHERE rank=1)::int AS winner,
                count(*) FILTER (WHERE rank<=ceil(:n * .001))::int AS top_01,
                count(*) FILTER (WHERE rank<=ceil(:n * .01))::int AS top_1,
                count(*) FILTER (WHERE rank<=ceil(:n * .1))::int AS top_10
                FROM target.dfs_contest_entry_result WHERE contest_id=:cid GROUP BY lineup_text'''
            entries = [dict(r) for r in conn.execute(text(query), {'cid': cid, 'n': contest['field_size']}).mappings()]
            source = sources[contest['source_file_id']]
            observations = [dict(r) for r in conn.execute(text('''SELECT DISTINCT
                player_display_name,roster_position,pct_drafted,fpts
                FROM public.dk_contest_standings_rows WHERE source_file=:path
                AND player_display_name IS NOT NULL AND player_display_name<>'' '''),
                {'path': source['original_path']}).mappings()]
            # Source path may have moved or be a ZIP whereas legacy rows reference another path.
            if not observations:
                observations = [dict(r) for r in conn.execute(text('''SELECT DISTINCT
                    player_display_name,roster_position,pct_drafted,fpts
                    FROM public.dk_contest_standings_rows WHERE contest_id=:cid
                    AND player_display_name IS NOT NULL AND player_display_name<>'' '''), {'cid': cid}).mappings()]
            # Includes the normalized-only Week 1 imports and their decision provenance.
            reviewed = [dict(r) for r in conn.execute(text('''SELECT * FROM target.contest_ownership_observation
                WHERE contest_id=:cid ORDER BY recorded_at,observation_id'''), {'cid': cid}).mappings()]
            winners = [dict(r) for r in conn.execute(text('''SELECT entry_id,rank,entry_points,lineup_text
                FROM target.dfs_contest_entry_result WHERE contest_id=:cid AND rank=1 ORDER BY entry_id'''), {'cid': cid}).mappings()]
            payload = {'contest': contest, 'source': source, 'entries': entries,
                       'observations': observations, 'reviewed': reviewed, 'winners': winners}
            with gzip.open(output, 'wt') as file:
                json.dump(payload, file, default=str, sort_keys=True)
            print(cid, sum(r['n'] for r in entries), len(entries), len(observations), flush=True)
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((OUT/'inputs').glob('*.gz'))}
    (OUT/'input_hashes.json').write_text(json.dumps(hashes, indent=2, sort_keys=True)+'\n')


if __name__ == '__main__':
    main()
