"""Read-only kicker audit and reproducible correction of one frozen experiment."""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import json
from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.kicker_roles import load_kicker_evidence
from scripts.run_showdown_qb_policy_experiment import read, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('artifacts/showdown_qb_policy_controlled/2026w4-monday-2771d4f1'))
    parser.add_argument('--destination', type=Path, default=Path('artifacts/kicker_role_audit/controlled'))
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    frozen = deepcopy(read(args.source / 'input_freeze.json'))
    cutoff = datetime.fromisoformat(frozen['projection_header'][0]['data_cutoff_at'])
    evidence = load_kicker_evidence(engine, season=frozen['season'], week=frozen['week'],
                                    slate=frozen['slate'], cutoff=cutoff)
    frozen.setdefault('pool_attrs', {})['kicker_evidence'] = evidence
    # Keep every archived point estimate unchanged: optimizer gate is an eligibility
    # correction. Fresh production predictions separately zero unsupported roles.
    write(args.destination / 'input_freeze.json', frozen)
    write(args.destination / 'recent-A.json', read(args.source / 'recent-A.json'))
    write(args.destination / 'role_evidence.json', evidence)
    with engine.connect() as connection:
        connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        out = {}
        queries = {
            'duplicate_projection_pools': """SELECT p.season,p.week,p.slate_id,p.projection_run_id,s.team,
                count(DISTINCT p.player_id) AS kickers,
                jsonb_agg(jsonb_build_object('player_id',p.player_id,'name',s.player_name,'mean',p.mean,'p90',p.p90)) AS players
                FROM target.player_projection p JOIN
                  (SELECT DISTINCT season,week,UPPER(slate) AS slate,team,player_master_id,player_name
                   FROM public.curated_salary WHERE position='K') s
                ON p.season=s.season AND p.week=s.week AND UPPER(p.slate_id)=s.slate AND p.player_id=s.player_master_id
                GROUP BY p.season,p.week,p.slate_id,p.projection_run_id,s.team
                HAVING count(DISTINCT p.player_id)>1 ORDER BY p.season DESC,p.week DESC""",
            'selected_multiple_kickers': '''SELECT r.season,r.week,r.slate_id,r.optimizer_run_id,l.lineup_id,
                p.player_json->>'player_team' AS team,
                jsonb_agg(p.player_json->>'name') AS kickers
                FROM target.lineup_player p JOIN target.lineup l USING(lineup_id)
                JOIN target.optimizer_run r USING(optimizer_run_id)
                WHERE p.player_json->>'position'='K'
                GROUP BY r.season,r.week,r.slate_id,r.optimizer_run_id,l.lineup_id,p.player_json->>'player_team'
                HAVING count(DISTINCT p.player_id)>1 ORDER BY r.season DESC,r.week DESC''',
            'selected_smyth': '''SELECT DISTINCT r.season,r.week,r.slate_id,r.optimizer_run_id,l.lineup_id
                FROM target.lineup_player p JOIN target.lineup l USING(lineup_id)
                JOIN target.optimizer_run r USING(optimizer_run_id)
                WHERE p.player_id='0b8b1e2f-997c-46d1-b808-99c0bd130f6d'
                ORDER BY r.season DESC,r.week DESC''',
            'reference_run': "SELECT * FROM target.optimizer_run WHERE optimizer_run_id='c9a9a25c-e31c-4cca-b662-9ee3cd71b1fb'",
            'reference_lineups': '''SELECT l.*, jsonb_agg(p.player_json ORDER BY p.slot_index) AS players
                FROM target.lineup l JOIN target.lineup_player p USING(lineup_id)
                WHERE l.optimizer_run_id='c9a9a25c-e31c-4cca-b662-9ee3cd71b1fb' GROUP BY l.lineup_id ORDER BY l.lineup_number''',
        }
        for name, sql in queries.items():
            out[name] = [dict(row) for row in connection.execute(text(sql)).mappings()]
    write(args.destination.parent / 'historical_audit.json', out)
    print({key: len(value) for key,value in out.items()}, flush=True)

if __name__ == '__main__': main()
