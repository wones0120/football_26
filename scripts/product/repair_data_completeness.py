"""Audit or apply missing-only historical actuals and salary identity repairs.

Plans and applied keys are saved in a content-addressed directory before writes.
Existing actuals, player masters, raw sources and projections are never changed.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sqlalchemy import text, Table, MetaData
from sqlalchemy.dialects.postgresql import insert
from backend.app.product_services.ownership import OwnershipService
from backend.app.product_services.data_completeness import historical_actual_plan, salary_identity_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--through-season', type=int, required=True)
    parser.add_argument('--salary-season', type=int, required=True)
    parser.add_argument('--salary-week', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.through_season >= args.salary_season:
        raise ValueError('Historical backfill must end before the current salary season')
    engine = OwnershipService().engine
    with engine.connect() as c:
        def read(sql, params=None):
            return [dict(r) for r in c.execute(text(sql), params or {}).mappings()]
        aliases = read('SELECT source_system,source_key,player_master_id,alias_name,team,position FROM player_alias ORDER BY alias_id')
        salaries = read('''SELECT curated_salary_id,ingest_run_id,season,week,slate,source_player_key,
            player_name,normalized_name,team,opponent,position FROM curated_salary
            WHERE season=:season AND week=:week AND source_system='draftkings' AND player_master_id IS NULL
            ORDER BY curated_salary_id''', {'season': args.salary_season, 'week': args.salary_week})
        rosters = read('''SELECT raw_nfl_weekly_roster_id,ingest_run_id,season,week,team,position,player_name,gsis_id
            FROM raw_nfl_weekly_roster WHERE season=:season AND week=:week ORDER BY raw_nfl_weekly_roster_id''',
            {'season': args.salary_season, 'week': args.salary_week})
        raw = read('''SELECT raw_nfl_weekly_stat_id,ingest_run_id,season,week,player_id,player_name,team,opponent,
            position,game_id,raw_row_json FROM raw_nfl_weekly_stat
            WHERE source_system='nflreadpy' AND season<=:season AND position IN ('QB','RB','FB','WR','TE','K')
            ORDER BY raw_nfl_weekly_stat_id''', {'season': args.through_season})
        games = read('SELECT season,week,game_id,home_team_id,away_team_id FROM target.dim_game')
        existing = read('SELECT season,week,game_id,player_id FROM target.fact_player_game_actual')
    history = historical_actual_plan(raw, games, aliases, existing)
    salary = salary_identity_plan(salaries, rosters, aliases)
    plan = {'scoring_policy': 'signed_dk_actuals_v1_no_missed_kick_penalty', 'history': history, 'salary': salary}
    encoded = json.dumps(plan, sort_keys=True, default=str).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    destination = args.output / digest
    destination.mkdir(parents=True, exist_ok=True)
    plan_path = destination / 'plan.json'
    if not plan_path.exists(): plan_path.write_bytes(encoded)
    summary = {'plan_sha256': digest, 'history': dict(Counter(r['status'] for r in history)),
               'salary': dict(Counter(r['status'] for r in salary)), 'applied': args.apply}
    if args.apply:
        inserted = []
        repaired = []
        with engine.begin() as c:
            table = Table('fact_player_game_actual', MetaData(), schema='target', autoload_with=c)
            missing = [row for row in history if row['status'] == 'missing']
            raw_by_key = {(r['record']['season'],r['record']['week'],r['record']['game_id'],r['record']['player_id']):r['raw_id'] for r in missing}
            statement = insert(table).on_conflict_do_nothing().returning(table.c.season, table.c.week, table.c.game_id, table.c.player_id)
            for offset in range(0, len(missing), 1000):
                inserted.extend(raw_by_key[tuple(key)] for key in c.execute(statement, [r['record'] for r in missing[offset:offset+1000]]))
            for row in salary:
                if row['status'] != 'resolved': continue
                s = row['salary']
                values = {**s, 'player_master_id': row['player_master_id']}
                known = c.execute(text("SELECT player_master_id FROM player_alias WHERE source_system='draftkings' AND source_key=:source_player_key"), values).scalar()
                if known and known != row['player_master_id']:
                    raise ValueError('DraftKings alias changed since planning; transaction cancelled')
                result = c.execute(text('''UPDATE curated_salary SET player_master_id=:player_master_id
                    WHERE curated_salary_id=:curated_salary_id AND player_master_id IS NULL
                    RETURNING curated_salary_id'''), values).first()
                if result:
                    c.execute(text('''INSERT INTO player_alias (player_master_id,source_system,source_key,
                        alias_name,normalized_alias,team,position,first_seen_season,first_seen_week,last_seen_at,created_at)
                        VALUES (:player_master_id,'draftkings',:source_player_key,:player_name,:normalized_name,
                        :team,:position,:season,:week,now(),now()) ON CONFLICT (source_system,source_key) DO NOTHING'''), values)
                    repaired.append(s['curated_salary_id'])
        application = {'inserted_raw_ids': inserted, 'repaired_salary_ids': repaired}
        application_path = destination / 'applied.json'
        if not application_path.exists(): application_path.write_text(json.dumps(application))
        summary.update(inserted_actuals=len(inserted), repaired_salaries=len(repaired))
    (destination / ('applied_summary.json' if args.apply else 'dry_run_summary.json')).write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    print('Evidence:', destination)


if __name__ == '__main__': main()
