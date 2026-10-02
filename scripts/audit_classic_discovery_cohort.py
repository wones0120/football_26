#!/usr/bin/env python3
"""Read-only historical input audit. Reads availability counts, never actual scores.

No generation takes place when original frozen inputs are absent. This command
cannot turn a fixed-pool audit or a current-table reload into a historical replay.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import text

from backend.app.db import engine
from backend.app.product_services.classic_discovery_validation import chronological_split, timestamp
from backend.app.product_services.classic_prospective import digest_payload

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / 'backend/app/product_services'
CODE = ('classic_prospective.py', 'classic_small_field.py', 'gpp_optimizer.py',
        'lineup_correlation_scoring.py', 'rule_library.py')


def load_catalog(connection) -> dict:
    queries = {
        'salaries': """SELECT season,week,upper(slate) slate,count(*) rows,
            count(distinct game_info) stored_game_labels,min(created_at) first_import_at
            FROM public.curated_salary GROUP BY season,week,upper(slate) ORDER BY 1,2,3""",
        'salary_snapshots': """SELECT season,week,upper(slate) slate,count(distinct player_id) players,
            count(distinct game_id) stored_games,min(as_of) first_as_of,max(as_of) latest_as_of
            FROM target.snapshot_salary GROUP BY season,week,upper(slate) ORDER BY 1,2,3""",
        'projections': """SELECT season,week,upper(slate_id) slate,count(*) runs,
            min(created_at) first_created_at,max(created_at) latest_created_at
            FROM target.projection_run GROUP BY season,week,upper(slate_id) ORDER BY 1,2,3""",
        'ownership': """SELECT season,week,upper(slate_id) slate,count(*) rows,
            count(distinct player_id) players,min(created_at) first_created_at,
            min(data_cutoff_at) first_cutoff_at FROM target.ownership_projection
            GROUP BY season,week,upper(slate_id) ORDER BY 1,2,3""",
        'schedules': """SELECT season,week,game_id,
            raw_row_json->>'gameday' gameday,raw_row_json->>'weekday' weekday,
            raw_row_json->>'gametime' gametime,
            bool_or(raw_row_json->>'total_line' IS NOT NULL OR raw_row_json->>'spread_line' IS NOT NULL) market_values_present,
            min(raw_row_json->>'observed_at') first_observed_at
            FROM public.raw_nfl_schedule
            GROUP BY season,week,game_id,raw_row_json->>'gameday',raw_row_json->>'weekday',raw_row_json->>'gametime'
            ORDER BY 1,2,3""",
        'actual_availability': """SELECT season,week,count(distinct player_id) players
            FROM target.fact_player_game_actual GROUP BY season,week ORDER BY 1,2""",
        'contest_actual_availability': """SELECT c.season,c.week,upper(c.slate_id) slate,
            count(distinct o.player_id) players FROM target.contest_ownership_observation o
            JOIN target.dfs_contest c USING(contest_id)
            WHERE lower(c.contest_format)='classic' AND o.actual_points IS NOT NULL
            AND o.player_id IS NOT NULL GROUP BY c.season,c.week,upper(c.slate_id) ORDER BY 1,2,3""",
        'contest_availability': """SELECT c.season,c.week,upper(c.slate_id) slate,
            count(distinct c.contest_id) contests,count(e.entry_id) result_rows,
            count(e.entry_points) scored_result_rows FROM target.dfs_contest c
            LEFT JOIN target.dfs_contest_entry_result e USING(contest_id)
            WHERE lower(c.contest_format)='classic' GROUP BY c.season,c.week,upper(c.slate_id) ORDER BY 1,2,3""",
        'runs': """SELECT optimizer_run_id,projection_run_id,season,week,upper(slate_id) slate,
            strategy,status,created_at,data_cutoff_at,
            constraint_config_json->'strategy_runtime'->'classic_small_field'->'frozen_solver_snapshot'->>'sha256' snapshot_sha256,
            constraint_config_json->'strategy_runtime'->'classic_small_field'->'frozen_generation_inputs'->>'sha256' generation_sha256,
            jsonb_array_length(coalesce(constraint_config_json->'strategy_runtime'->'classic_small_field'->'all_candidates','[]'::jsonb)) candidate_count,
            (SELECT count(*) FROM jsonb_array_elements(coalesce(constraint_config_json->'strategy_runtime'->'player_pool'->'rows','[]'::jsonb)) p WHERE p->>'included'='true') eligible_players,
            constraint_config_json->'strategy_runtime'->'classic_small_field'->'prelock_timing' timing
            FROM target.optimizer_run WHERE lower(contest_format)='classic' AND upper(slate_id)='SUNDAY_MAIN'
            ORDER BY season,week,created_at,optimizer_run_id""",
    }
    return {name: [dict(r) for r in connection.execute(text(sql)).mappings()]
            for name, sql in queries.items()}


def build_cohort(catalog: dict, *, as_of: str) -> dict:
    def index(name):
        return {(r['season'], r['week'], r.get('slate')): r for r in catalog[name]}
    salary, projection, ownership, contests, snapshots = map(index,
        ('salaries', 'projections', 'ownership', 'contest_availability', 'salary_snapshots'))
    actual = {(r['season'], r['week']): r for r in catalog['actual_availability']}
    contest_actual = index('contest_actual_availability')
    schedules, runs = defaultdict(list), defaultdict(list)
    for r in catalog['schedules']:
        if r['weekday'] == 'Sunday' and r['gametime'] and '13:00' <= r['gametime'] < '17:00':
            schedules[r['season'], r['week']].append(r)
    for r in catalog['runs']:
        runs[r['season'], r['week'], r['slate']].append(r)
    keys = set(salary) | set(projection) | set(runs)
    rows, outside = [], []
    for key in sorted(keys):
        season, week, slate = key
        if slate not in {'SUNDAY_MAIN', 'DEFAULT', 'MAIN', 'NORMAL', 'SUNDAY_ALL', 'SUNDAY'}:
            outside.append({'season': season, 'week': week, 'slate': slate,
                            'reason': 'not_Sunday_Main_or_ambiguous_full_slate_alias'})
            continue
        games = schedules[season, week]
        dates = sorted({r['gameday'] for r in games if r['gameday']})
        kickoff = datetime.fromisoformat(f'{dates[0]}T13:00:00').replace(
            tzinfo=ZoneInfo('America/New_York')).isoformat() if dates else None
        # Dates below are catalog diagnostics only. Saved input timing remains
        # mandatory for any replay; this schedule inference cannot certify lock.
        small = [r for r in runs[key] if r['strategy'] == 'classic_small_field_gpp']
        completed = [r for r in small if r['status'] == 'completed']
        future = bool(kickoff and timestamp(kickoff) >= timestamp(as_of))
        reasons = []
        if slate != 'SUNDAY_MAIN':
            reasons.append('Sunday_Main_membership_not_certified')
        if future:
            reasons.append('future_slate_diagnostic_only')
        if not completed:
            reasons.append('no_original_completed_small_field_control')
        if not any(r.get('snapshot_sha256') and r.get('generation_sha256') for r in completed):
            reasons.append('complete_frozen_generation_inputs_absent')
        # A presence-only SQL audit must never accept an unverified snapshot.
        # If an unexpected historical complete snapshot appears, stop for full
        # validation instead of silently dropping or accepting that slate.
        if not future and any(r.get('snapshot_sha256') for r in completed):
            raise ValueError(f'Historical snapshot requires full replay audit: {key}')
        own, market = ownership.get(key, {}), [r for r in games if r['market_values_present']]
        contest = contests.get(key, {})
        rows.append({'slate_key': f'{season}w{week}:{slate}', 'season': season, 'week': week, 'slate': slate,
            'date': dates[0] if dates else None, 'kickoff_at': kickoff,
            'date_basis': 'schedule_inventory_not_certified_slate_membership',
            'stored_games': snapshots.get(key, {}).get('stored_games'),
            'stored_salary_players': snapshots.get(key, {}).get('players'),
            'eligible_players': max((r['eligible_players'] for r in completed), default=None),
            'ownership_players_available': own.get('players', 0),
            'schedule_market_games_available': len({r['game_id'] for r in market}),
            'actual_players_available_weekwide': actual.get((season, week), {}).get('players', 0),
            'contest_actual_players_available': contest_actual.get(key, {}).get('players', 0),
            'contests_available': contest.get('contests', 0), 'field_scored_rows_available': contest.get('scored_result_rows', 0),
            'optimizer_runs': len(runs[key]), 'small_field_runs': len(small),
            'completed_small_field_runs': len(completed),
            'solver_snapshots_present': sum(bool(r['snapshot_sha256']) for r in completed),
            'pregame_comparison_qualified': False, 'postgame_comparison_qualified': False,
            'field_percentile_qualified': False, 'qualified': False, 'exclusion_reasons': reasons,
            'projection_first_created_at': projection.get(key, {}).get('first_created_at'),
            'run_ids': [str(r['optimizer_run_id']) for r in runs[key]]})
    return {'slates': rows, 'outside_scope': outside,
            'holdout': chronological_split(rows),
            'historical_qualified_count': sum(r['qualified'] for r in rows)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/classic_discovery_multi_slate/cohort_audit.json')
    args = parser.parse_args()
    started = datetime.now(UTC)
    with engine.connect() as connection:
        connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        database_time = connection.execute(text('SELECT current_timestamp')).scalar()
        catalog = load_catalog(connection)
    # Normalize all timestamp/UUID values without exposing the connection URL.
    catalog = json.loads(json.dumps(catalog, default=str))
    payload = {'contract': 'classic_discovery_cohort_audit_v1', 'audited_at': database_time.isoformat(),
        'read_only': True, 'actual_score_values_read': False,
        'catalog': catalog, **build_cohort(catalog, as_of=database_time.isoformat()),
        'production_code_sha256': {name: sha256((SERVICE / name).read_bytes()).hexdigest() for name in CODE},
        'audit_runtime_seconds': (datetime.now(UTC) - started).total_seconds()}
    artifact = {'payload': payload, 'sha256': digest_payload(payload)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(artifact, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'sha256': artifact['sha256'],
                      'qualified': payload['historical_qualified_count'],
                      'inventoried_periods': len(payload['slates']), 'outside_scope': len(payload['outside_scope'])}))


if __name__ == '__main__':
    main()
