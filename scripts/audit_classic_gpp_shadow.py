#!/usr/bin/env python3
"""Read-only current-strategy audit; no solver calls or live recommendation writes."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.classic_gpp_shadow import freeze_shadow, POLICY
from backend.app.product_services.gpp_historical_audit import evaluate_run,digest
from backend.app.product_services.gpp_recommendation import evaluate_candidates
from backend.app.product_services.optimizer_effectiveness import chronological_validation
from backend.app.product_services.entry_history import load_history,enrich_contests
from scripts.audit_gpp_recommendation_history import PLAYER_KEYS


def run_audit(connection):
    connection.execute(text('SET TRANSACTION READ ONLY'))
    connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
    rows=[dict(r) for r in connection.execute(text('''
        SELECT optimizer_run_id,projection_run_id,season,week,slate_id,contest_format,strategy,
          created_at AS optimizer_created_at,updated_at,data_cutoff_at,
          constraint_config_json->'effective_strategy_contract'->>'sha256' AS effective_contract_sha256,
          constraint_config_json->'strategy_runtime'->'config' AS effective_config,
          constraint_config_json->'gpp_recommendation' AS saved_recommendation,
          constraint_config_json->'strategy_runtime'->'strategy_contract_audit' AS trace
        FROM target.optimizer_run WHERE status='completed' AND objective='gpp'
          AND strategy='classic_large_gpp_v1' AND contest_format='classic' AND upper(slate_id)='SUNDAY_MAIN'
        ORDER BY season,week,created_at,optimizer_run_id
    ''')).mappings()]
    frozen=[]
    # Stage 1 freezes all forecast-only choices before loading any outcomes.
    for run in rows:
        lineups=[]
        ids=connection.execute(text('SELECT lineup_id FROM target.lineup WHERE optimizer_run_id=:id ORDER BY lineup_number'),{'id':run['optimizer_run_id']}).scalars().all()
        for lid in ids:
            lineups.append(list(connection.execute(text('''
                SELECT (SELECT jsonb_object_agg(key,value) FROM jsonb_each(player_json) WHERE key=ANY(:keys))
                FROM target.lineup_player WHERE lineup_id=:id ORDER BY slot_index
            '''),{'id':lid,'keys':PLAYER_KEYS}).scalars()))
        scope=dict(run_id=str(run['optimizer_run_id']),season=run['season'],week=run['week'],
                   slate=run['slate_id'],contest_format='classic',projection_run_id=str(run['projection_run_id']),
                   data_cutoff_at=run['data_cutoff_at'])
        frozen.append((run,lineups,freeze_shadow(lineups,**scope),evaluate_candidates(lineups,**scope)))
    freeze_time=datetime.now(timezone.utc)
    frozen_sha=digest([f[2] for f in frozen])
    history,conflicts,sources=load_history(connection)
    contests=enrich_contests([dict(r) for r in connection.execute(text('''
        SELECT c.* FROM target.dfs_contest c WHERE contest_format='classic' AND upper(slate_id)='SUNDAY_MAIN'
    ''')).mappings()],history)
    histograms,tiers,observations,by_slate=(defaultdict(list) for _ in range(4))
    for contest in contests:
        cid=str(contest['contest_id']);key=(contest['season'],contest['week'])
        by_slate[key].append(contest)
        histograms[cid]=[dict(r) for r in connection.execute(text('SELECT entry_points,count(*) entries FROM target.dfs_contest_entry_result WHERE contest_id=:id GROUP BY entry_points'),{'id':cid}).mappings()]
        tiers[cid]=[dict(r) for r in connection.execute(text('SELECT min_rank,max_rank,payout FROM target.dfs_contest_payout_tier WHERE contest_id=:id ORDER BY min_rank'),{'id':cid}).mappings()]
        observations[key].extend(dict(r) for r in connection.execute(text('SELECT player_id,roster_position,actual_points,resolution_status FROM target.contest_ownership_observation WHERE contest_id=:id'),{'id':cid}).mappings())
    output=[]
    for run,lineups,shadow,baseline in frozen:
        key=(run['season'],run['week']);run['constraint_config_json']={}
        a=evaluate_run(run,lineups,baseline,observations[key],by_slate[key],histograms,tiers)
        b=evaluate_run(run,lineups,dict(baseline,recommended=shadow['challenger']),observations[key],by_slate[key],histograms,tiers)
        kickoff_pool=dict(status='slate_source_pool',candidates=[dict(games_represented=[p.get('game_id') for p in lineup]) for lineup in lineups])
        timing=chronological_validation(dict(run,optimizer_created_at=freeze_time),kickoff_pool)
        output.append(dict(run_id=str(run['optimizer_run_id']),season=run['season'],week=run['week'],
            created_at=run['optimizer_created_at'],effective_contract_sha256=run['effective_contract_sha256'],
            effective_config=run['effective_config'],selection_trace_sha256=digest(run['trace']),
            saved_recommendation_sha256=digest(run['saved_recommendation']),shadow=shadow,
            baseline_evaluation=a,challenger_evaluation=b,
            prospective=timing['status']=='predecision' and not by_slate[key]
                and a['excluded_reasons']==['historical_results_not_imported'] and shadow['status']=='shadow_only',
            prospective_timing=timing,
            snapshot_lineups=lineups if timing['status']=='predecision' else None))
    # Most recent eligible run per slate is a fixed recency rule, never best by outcome.
    latest={}
    for r in output:
        if r['baseline_evaluation']['eligibility']=='exploratory' and r['challenger_evaluation']['eligibility']=='exploratory':
            latest[(r['season'],r['week'])]=r['run_id']
    return dict(policy=POLICY,created_at=freeze_time,forecast_choices_sha256=frozen_sha,
                entry_history_sources=[s['content_sha256'] for s in sources],entry_history_conflicts=conflicts,
                primary_latest_run_per_slate=list(latest.values()),runs=output,
                limitations=['Previously inspected historical slates: retrospective diagnostic, not an untouched holdout.',
                    'Only returned candidates are compared; no hidden pool, new generation or portfolio-constraint change.',
                    'Player P90 sums are not lineup quantiles; the 2% band is an uncalibrated hypothesis.',
                    'Related runs and contests are not independent trials; unknown outcomes stay unavailable.',
                    'No payout ladder: no counterfactual monetary-return or expected-return claim.'],
                live_changes=False)


def markdown(report):
    lines=['# Current Classic GPP shadow result', '',
        'Decision: do not deploy the mean-guarded upside challenger. Keep live selections unchanged.', '',
        'The primary comparison uses the most recent eligible run per Sunday Main slate. '
        'Previously inspected historical slates are diagnostic, not an untouched holdout.', '',
        '| Week | Current-policy points | Challenger points | Current paid / GPPs | Challenger paid / GPPs |',
        '|---|---:|---:|---:|---:|']
    for row in report['runs']:
        if row['run_id'] not in report['primary_latest_run_per_slate']:
            continue
        a,b=row['baseline_evaluation'],row['challenger_evaluation']
        def paid(e):
            fields=[o for o in e['field_outcomes'] if o['classification']['contest_type']=='gpp']
            return f"{sum(o['paid_finish'] is True for o in fields)} / {len(fields)}"
        lines.append(f"| {row['week']} | {a['selected_actual_points']:.2f} | {b['selected_actual_points']:.2f} | {paid(a)} | {paid(b)} |")
    eligible=[r for r in report['runs'] if r['baseline_evaluation']['eligibility']=='exploratory' and r['challenger_evaluation']['eligibility']=='exploratory']
    changed=[r for r in eligible if r['shadow']['changed']]
    lines += ['',f"Sensitivity: {len(eligible)} eligible historical runs; {len(changed)} changed choices. These are dependent runs across two weeks, not independent trials.", '',
        '## Upcoming Sunday Main', '']
    prospective=[r for r in report['runs'] if r['prospective']]
    if prospective:
        r=prospective[-1]
        lines.append(f"Latest frozen run: {r['run_id']}. Current policy: lineup #{r['shadow']['baseline']['lineup_number']}; challenger: lineup #{r['shadow']['challenger']['lineup_number']}. Outcomes pending.")
        lines.append(f"Frozen at {report['created_at']}; forecast-choice SHA256: {report['forecast_choices_sha256']}.")
    lines += ['', '## Limits', '', *['- '+s for s in report['limitations']], '',
        'The runner opens a read-only database transaction, never invokes a solver, and is not imported by the live recommendation path.']
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',default='artifacts/classic_gpp_shadow')
    args=parser.parse_args()
    path=Path(args.output_dir)
    if (path/'report.json').exists():
        raise ValueError('Keep the prior shadow snapshot; choose a new --output-dir')
    with engine.connect() as c:report=run_audit(c)
    path=Path(args.output_dir);path.mkdir(parents=True,exist_ok=True)
    (path/'report.json').write_text(json.dumps(report,indent=2,default=str,allow_nan=False)+'\n')
    (path/'report.md').write_text(markdown(report))
    print(json.dumps(dict(runs=len(report['runs']),primary=report['primary_latest_run_per_slate'],
        changes=sum(r['shadow'].get('changed',False) for r in report['runs']),
        prospective=sum(r['prospective'] for r in report['runs'])),indent=2))


if __name__=='__main__': main()
