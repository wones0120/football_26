#!/usr/bin/env python3
"""Read-only Sunday Main GPP audit. Writes separate artifacts, never optimizer rows."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.entry_history import load_history, enrich_contests
from backend.app.product_services.gpp_historical_audit import (
    evaluate_run, field_outcome, freeze_choice, summarize,
)

PLAYER_KEYS = ['player_id', 'roster_position', 'position', 'salary', 'dk_player_id',
               'projection', 'baseline_projection', 'p90', 'baseline_p90', 'game_id',
               'postgame', 'actual_points', 'actual_score', 'actual_rank',
               'name', 'player_name', 'team', 'official_availability_status', 'availability_status', 'injury_status']


def load_and_audit(connection):
    connection.execute(text('SET TRANSACTION READ ONLY'))
    connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
    contests = [dict(r) for r in connection.execute(text("""
        SELECT c.contest_id,c.season,c.week,c.slate_id,c.contest_format,c.contest_name,
               c.contest_type,c.entry_fee,c.field_size,c.prize_pool,c.source_file_id,s.content_sha256
        FROM target.dfs_contest c LEFT JOIN target.source_file_import s USING(source_file_id)
        WHERE upper(c.slate_id)='SUNDAY_MAIN' AND c.contest_format='classic'
        ORDER BY c.season,c.week,c.contest_id
    """)).mappings()]
    history, history_conflicts, history_sources = load_history(connection)
    contests = enrich_contests(contests, history)
    histograms, tiers, actuals, contest_groups = (defaultdict(list) for _ in range(4))
    for c in contests:
        cid = str(c['contest_id'])
        key = (c['season'], c['week'])
        contest_groups[key].append(c)
        histograms[cid] = [dict(r) for r in connection.execute(text('''
            SELECT entry_points,count(*) AS entries FROM target.dfs_contest_entry_result
            WHERE contest_id=:id GROUP BY entry_points ORDER BY entry_points
        '''), {'id':cid}).mappings()]
        tiers[cid] = [dict(r) for r in connection.execute(text('''
            SELECT min_rank,max_rank,payout FROM target.dfs_contest_payout_tier
            WHERE contest_id=:id ORDER BY min_rank
        '''), {'id':cid}).mappings()]
        actuals[key].extend(dict(r) for r in connection.execute(text('''
            SELECT player_id,roster_position,actual_points,resolution_status
            FROM target.contest_ownership_observation WHERE contest_id=:id
        '''), {'id':cid}).mappings())
    runs = [dict(r) for r in connection.execute(text('''
        SELECT optimizer_run_id,projection_run_id,season,week,slate_id,contest_format,strategy,
               data_cutoff_at,created_at AS optimizer_created_at,updated_at
        FROM target.optimizer_run WHERE status='completed' AND objective='gpp'
          AND contest_format='classic' AND upper(slate_id)='SUNDAY_MAIN'
        ORDER BY season,week,created_at,optimizer_run_id
    ''')).mappings()]
    results = []
    for run in runs:
        rid = str(run['optimizer_run_id'])
        run['constraint_config_json'] = connection.execute(text('''
            SELECT jsonb_build_object('strategy_runtime',jsonb_build_object(
                'candidate_pool_manifest',constraint_config_json->'strategy_runtime'->'candidate_pool_manifest',
                'classic_small_field',jsonb_build_object('all_candidates',
                    constraint_config_json->'strategy_runtime'->'classic_small_field'->'all_candidates'),
                'single_lineup',jsonb_build_object('all_candidates',
                    constraint_config_json->'strategy_runtime'->'single_lineup'->'all_candidates')))
            FROM target.optimizer_run WHERE optimizer_run_id=:id
        '''), {'id':rid}).scalar_one()
        lineups = []
        lineup_ids = connection.execute(text('''
            SELECT lineup_id FROM target.lineup WHERE optimizer_run_id=:id ORDER BY lineup_number
        '''), {'id':rid}).scalars().all()
        for lid in lineup_ids:
            # Avoid repeated megabyte-sized embedded runtime reports in player_json.
            lineups.append(list(connection.execute(text('''
                SELECT (SELECT jsonb_object_agg(key,value) FROM jsonb_each(player_json)
                        WHERE key=ANY(:keys)) FROM target.lineup_player
                WHERE lineup_id=:id ORDER BY slot_index
            '''), {'id':lid,'keys':PLAYER_KEYS}).scalars()))
        choice = freeze_choice(run, lineups)
        key = (run['season'],run['week'])
        results.append(evaluate_run(run,lineups,choice,actuals[key],contest_groups[key],histograms,tiers))
    fields = [field_outcome(None,c,histograms[str(c['contest_id'])],tiers[str(c['contest_id'])]) for c in contests]
    return dict(contract='gpp_historical_audit_v2', entry_history_sources=[s['content_sha256'] for s in history_sources],
                entry_history_conflicts=history_conflicts, created_at=datetime.now(timezone.utc).isoformat(),
                summary=summarize(results,fields), contests=fields, runs=results)


def markdown(report):
    s = report['summary']
    lines = ['# Sunday Main GPP historical baseline', '',
        f"Audited {s['run_count']} saved GPP runs and {s['contest_count']} imported contests.",
        f"{s['exploratory_runs']} runs pass recorded-clock screening; {s['excluded_runs']} are excluded.",
        f"Paid-finish-ready GPP contests: {s['paid_finish_ready_contests']}. Full payout-ready contests: {s['payout_ready_contests']}. Paid-finish comparisons: {s['verified_paid_finish_evaluations']}.", '',
        '**Research only. No policy promotion or live settings changes.**', '',
        'The deployed projection-first selector is replayed on saved returned candidates before outcomes are joined. '
        'This is a retrospective policy comparison, not proof that the policy was used for historical entries. '
        'Recorded creation/update/cutoff clocks must precede saved kickoff. Database clocks do not independently '
        'prove immutable prelock capture. Missing selected-player actuals remain missing; no hindsight reselection.', '',
        'Paid finishes require GPP classification and complete standings plus verified exported Places_Paid. Exact returns require a contiguous payout ladder '
        'reconciled to the prize pool, and resolved canonical player results. Net return also requires the entry fee. '
        'Historical placement uses synthetic insertion into the unchanged field, with conservative tie bounds. '
        'This is counterfactual performance, not realized winnings or an expected-return estimate.', '',
        '## Slate blocks', '', '| Slate | Related runs | Scoreable selections |', '|---|---:|---:|']
    for b in s['slate_blocks']:
        lines.append(f"| {b['slate']} | {b['runs']} | {b['scoreable_selections']} |")
    lines += ['', s['note'], '', '## Candidate selection diagnostics', '',
        '| Run | Week | Selected points | First returned points | Best returned points | Best saved search pool points |',
        '|---|---:|---:|---:|---:|---:|']
    for r in report['runs']:
        if r['eligibility'] == 'exploratory':
            lines.append(f"| {r['run_id'][:8]} | {r['week']} | {r['selected_actual_points']} | {r['first_returned_actual_points']} | {r['returned_coverage']['best_observed']} | {r['search_pool_coverage']['best_observed']} |")
    lines += ['', '## Paid-finish diagnosis by slate and strategy', '',
        'Counts below are related run/contest comparisons, not independent trials or estimated win rates.', '',
        '| Week | Strategy | Runs | Recommendation paid | Final selection miss | Shortlist miss | Complete-pool generation miss | Incomplete evidence miss |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    from collections import Counter
    groups = defaultdict(list)
    for row in report['runs']:
        if row['eligibility'] == 'exploratory':
            groups[(row['season'], row['week'], row['strategy'])].append(row)
    for (season, week, strategy), rows in sorted(groups.items()):
        counts = Counter(d['diagnosis'] for row in rows for d in row['stage_diagnostics'] if d['paid_cutoff_points'] is not None)
        lines.append(f"| {season} W{week} | {strategy} | {len(rows)} | {counts['recommended_paid']} | {counts['final_selection_miss']} | {counts['candidate_shortlisting_miss']} | {counts['generation_miss']} | {counts['no_observed_paid_candidate_incomplete_pool']} |")
    lines += ['', '## Exported GPP paid cutoffs', '', '| Contest | Paid cutoff points |', '|---|---:|']
    for contest in report['contests']:
        if contest['paid_finish_evidence']:
            lines.append(f"| {contest['contest_id']} — {contest['contest_name']} | {contest['paid_cutoff_points']:.2f} |")
    lines += ['', 'Best observed scores are hindsight diagnostics. Incomplete coverage makes these lower bounds on '
              'candidate quality; missing full search pools prevent generation-ceiling conclusions. '
              'Each JSON run includes coverage, missing identities, field placement, hashes and exclusion reasons.', '',
              '## Next evidence required', '',
              '- Import historical contest classification, entry fees and complete payout ladders/prize totals.',
              '- Resolve missing or conflicting canonical actual scores without changing the frozen candidate choice.',
              '- Accumulate independently captured prelock candidate/selection snapshots across additional slates.',
              '- Validate paid-finish performance first, then net return and top-finish outcomes on held-out slate blocks.']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', default='artifacts/gpp_historical_baseline')
    args = parser.parse_args()
    with engine.connect() as connection:
        report = load_and_audit(connection)
    output = Path(args.output_dir)
    output.mkdir(parents=True,exist_ok=True)
    (output/'report.json').write_text(json.dumps(report,indent=2,default=str,allow_nan=False)+'\n')
    (output/'report.md').write_text(markdown(report))
    print(json.dumps(report['summary'],indent=2))


if __name__ == '__main__':
    main()
