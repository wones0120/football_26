"""Read-only 2026 W1–4 projection and GPP replay audit across Classic and Captain."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import argparse
import json
import math
from Database.dst import normalize_team

from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.entry_history import load_history, enrich_contests
from backend.app.product_services.gpp_historical_audit import evaluate_run, freeze_choice, field_outcome, digest
from backend.app.product_services.optimizer_effectiveness import actual_points_by_player
from scripts.audit_gpp_recommendation_history import PLAYER_KEYS

AUDIT_PLAYER_KEYS = list(dict.fromkeys(PLAYER_KEYS + ['dk_captain_id', 'player_team', 'base_salary']))


def game_key(game_id):
    parts = str(game_id).split('_')
    if len(parts) != 4:
        return None
    try:
        teams = tuple(sorted({normalize_team(parts[2]), normalize_team(parts[3])}))
        return (int(parts[0]), int(parts[1]), teams) if len(teams) == 2 else None
    except ValueError:
        return None


def resolve_kickoff(game_id, kicks):
    if game_id in kicks:
        values = kicks[game_id]
        return (next(iter(values)), game_id, 'native_game_id') if len(values) == 1 else (None, None, 'conflicting_kickoff')
    key = game_key(game_id)
    matches = [g for g in kicks if key is not None and game_key(g) == key]
    if len(matches) == 1 and len(kicks[matches[0]]) == 1:
        native = matches[0]
        return next(iter(kicks[native])), native, 'unique_season_week_team_pair_alias'
    return None, None, 'missing_or_ambiguous_game'


def metrics(rows):
    valid = [r for r in rows if r.get('actual') is not None and r.get('mean') is not None
             and math.isfinite(r['mean']) and math.isfinite(r['actual'])]
    errors = [r['mean'] - r['actual'] for r in valid]
    intervals = [r for r in valid if r.get('p10') is not None and r.get('p90') is not None
                 and math.isfinite(r['p10']) and math.isfinite(r['p90']) and r['p10'] <= r['p90']]
    return dict(rows=len(rows), matched=len(valid), missing=len(rows)-len(valid),
        mae=sum(map(abs, errors))/len(errors) if errors else None,
        rmse=math.sqrt(sum(e*e for e in errors)/len(errors)) if errors else None,
        bias=sum(errors)/len(errors) if errors else None,
        interval_rows=len(intervals), interval_coverage=sum(r['p10'] <= r['actual'] <= r['p90'] for r in intervals)/len(intervals) if intervals else None)


def projection_exclusions(rows):
    if not rows or any(not r.get('kickoff') for r in rows):
        return ['missing_or_conflicting_kickoff']
    lock = min(r['kickoff'] for r in rows)
    reasons = []
    for key in ('created_at', 'run_created_at', 'model_created_at', 'data_cutoff_at', 'run_cutoff_at'):
        if any(r.get(key) is None or not r[key].tzinfo or r[key] >= lock for r in rows):
            reasons.append(key + '_missing_or_not_prelock')
    if not reasons and any(r['data_cutoff_at'] > r['created_at'] or r['run_cutoff_at'] > r['run_created_at'] for r in rows):
        reasons.append('cutoff_after_creation')
    return reasons


def pregame(rows):
    return not projection_exclusions(rows)


def primary_run(rows):
    # Choose by time before asking whether its selected lineup has complete actuals.
    valid = [r for r in rows if r['eligibility'] == 'exploratory']
    return max(valid, key=lambda r: (datetime.fromisoformat(r['optimizer_created_at']), r['run_id']), default=None)


def load(c):
    c.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
    c.execute(text('SET TRANSACTION READ ONLY'))
    contests = [dict(r) for r in c.execute(text('''SELECT c.contest_id,c.season,c.week,c.slate_id,c.contest_format,c.contest_name,
        c.contest_type,c.entry_fee,c.field_size,c.prize_pool,c.source_file_id,s.content_sha256
        FROM target.dfs_contest c LEFT JOIN target.source_file_import s USING(source_file_id)
        WHERE c.season=2026 AND c.week BETWEEN 1 AND 4''')).mappings()]
    history, conflicts, sources = load_history(c)
    contests = enrich_contests(contests, history)
    groups, observations, histograms, tiers = (defaultdict(list) for _ in range(4))
    for contest in contests:
        cid = str(contest['contest_id'])
        key = (contest['week'], contest['slate_id'], contest['contest_format'])
        groups[key].append(contest)
        histograms[cid] = [dict(r) for r in c.execute(text('SELECT entry_points,count(*) AS entries FROM target.dfs_contest_entry_result WHERE contest_id=:id GROUP BY entry_points'), {'id':cid}).mappings()]
        tiers[cid] = [dict(r) for r in c.execute(text('SELECT min_rank,max_rank,payout FROM target.dfs_contest_payout_tier WHERE contest_id=:id'), {'id':cid}).mappings()]
        observations[key].extend(dict(r) for r in c.execute(text('SELECT player_id,roster_position,actual_points,resolution_status,source_file_id FROM target.contest_ownership_observation WHERE contest_id=:id'), {'id':cid}).mappings())
    actuals = {key:actual_points_by_player(obs,key[2]) for key,obs in observations.items()}
    runs = [dict(r) for r in c.execute(text('''SELECT optimizer_run_id,projection_run_id,season,week,slate_id,contest_format,strategy,
        data_cutoff_at,created_at AS optimizer_created_at,updated_at,status,objective
        FROM target.optimizer_run WHERE season=2026 AND week BETWEEN 1 AND 4 ORDER BY created_at,optimizer_run_id''')).mappings()]
    results = []
    for run in runs:
        if run['status'] != 'completed' or run['objective'] != 'gpp':
            continue
        rid = str(run['optimizer_run_id'])
        # Fetch only known pool branches, not multi-megabyte repeated input snapshots.
        config = {'strategy_runtime':{}}
        for branch in ('classic_small_field','single_lineup','showdown_portfolio_policy','single_entry','three_max','small_max'):
            path = ['strategy_runtime', branch] + (['candidate_selection','ranked_metrics'] if branch=='showdown_portfolio_policy' else ['all_candidates'])
            value = c.execute(text('SELECT constraint_config_json #> :path FROM target.optimizer_run WHERE optimizer_run_id=:id'), {'path':path,'id':rid}).scalar_one()
            if value:
                config['strategy_runtime'][branch] = {'candidate_selection':{'ranked_metrics':value}} if branch=='showdown_portfolio_policy' else {'all_candidates':value}
        config['strategy_runtime']['candidate_pool_manifest'] = c.execute(text("SELECT constraint_config_json->'strategy_runtime'->'candidate_pool_manifest' FROM target.optimizer_run WHERE optimizer_run_id=:id"), {'id':rid}).scalar_one()
        run['constraint_config_json'] = config
        lineups = []
        for lid in c.execute(text('SELECT lineup_id FROM target.lineup WHERE optimizer_run_id=:id ORDER BY lineup_number'), {'id':rid}).scalars():
            lineups.append(list(c.execute(text('SELECT (SELECT jsonb_object_agg(key,value) FROM jsonb_each(player_json) WHERE key=ANY(:keys)) FROM target.lineup_player WHERE lineup_id=:id ORDER BY slot_index'), {'id':lid,'keys':AUDIT_PLAYER_KEYS}).scalars()))
        choice = freeze_choice(run,lineups)
        key = (run['week'],run['slate_id'],run['contest_format'])
        result = evaluate_run(run,lineups,choice,observations[key],groups[key],histograms,tiers)
        result['contest_format'] = run['contest_format']
        result['selected_projection_error'] = (result['selected']['projected_points'] - result['selected_actual_points']
            if result.get('selected_actual_points') is not None else None)
        results.append(result)
    kicks = defaultdict(set)
    for r in c.execute(text("SELECT DISTINCT game_id,raw_row_json->>'gameday' AS day,raw_row_json->>'gametime' AS time FROM raw_nfl_schedule WHERE season=2026 AND week BETWEEN 1 AND 4")).mappings():
        try:
            kicks[r['game_id']].add(datetime.fromisoformat(f"{r['day']}T{r['time']}").replace(tzinfo=ZoneInfo('America/New_York')))
        except (ValueError,TypeError):
            pass
    projections = defaultdict(list)
    for r in c.execute(text('''SELECT p.projection_run_id,p.player_id,p.game_id,p.mean,p.p10,p.p90,p.created_at,p.data_cutoff_at,
        pr.week,pr.slate_id,pr.created_at AS run_created_at,pr.data_cutoff_at AS run_cutoff_at,m.created_at AS model_created_at,
        d.primary_position AS position FROM target.player_projection p JOIN target.projection_run pr USING(projection_run_id)
        JOIN target.model_run m ON m.model_run_id=pr.model_run_id LEFT JOIN target.dim_player d ON d.player_id=p.player_id
        WHERE pr.season=2026 AND pr.week BETWEEN 1 AND 4 AND pr.status='completed' ''')).mappings():
        row = dict(r)
        row['kickoff'], row['resolved_game_id'], row['game_match_basis'] = resolve_kickoff(row['game_id'], kicks)
        projections[row['projection_run_id']].append(row)
    scopes = set(groups) | {(r['week'],r['slate_id'],r['contest_format']) for r in runs}
    # Show absent expected slates too; do not invent a result for them.
    for week in range(1,5):
        scopes.update((week,s,'classic') for s in ('SUNDAY_MAIN','SUNDAY_EARLY','SUNDAY_LATE'))
        scopes.update((week,s,'showdown') for s in ('THURSDAY_NIGHT','SUNDAY_NIGHT','MONDAY_NIGHT'))
    blocks=[]
    for key in sorted(scopes):
        week,slate,fmt=key
        related=[r for r in results if (r['week'],r['slate'],r['contest_format'])==key]
        available=[rows for rows in projections.values() if rows[0]['week']==week and rows[0]['slate_id']==slate]
        eligible=[rows for rows in available if pregame(rows)]
        chosen=max(eligible,key=lambda rows:(rows[0]['run_created_at'],rows[0]['projection_run_id']),default=[])
        scored=[dict(player_id=r['player_id'],game_id=r['game_id'],position=r['position'],mean=r['mean'],p10=r['p10'],p90=r['p90'],actual=actuals.get(key,{}).get(r['player_id'])) for r in chosen]
        # Ambiguous repeated player/game scope cannot use a player-only contest label.
        counts=Counter(r['player_id'] for r in scored)
        for r in scored:
            if counts[r['player_id']]>1: r['actual']=None
        fields=[field_outcome(None,ct,histograms[str(ct['contest_id'])],tiers[str(ct['contest_id'])]) for ct in groups[key]]
        primary=primary_run(related)
        gaps=[]
        if not groups[key]: gaps.append('no_imported_standings')
        if not eligible: gaps.append('no_clock_eligible_projection_snapshot')
        if not primary: gaps.append('no_clock_eligible_gpp_replay')
        if scored and any(r['actual'] is None for r in scored): gaps.append('incomplete_projection_actuals')
        if not any(f['paid_finish_evidence'] for f in fields): gaps.append('no_verified_gpp_paid_cutoff')
        if not any(f['payout_evidence_reason'] is None for f in fields): gaps.append('no_complete_gpp_payout_ladder')
        blocks.append(dict(week=week,slate=slate,contest_format=fmt,contests=len(fields),paid_ready=sum(f['paid_finish_evidence'] for f in fields),
            actual_player_count=len(actuals.get(key,{})),projection_runs=len(available),pregame_projection_runs=len(eligible),
            projection_run_id=chosen[0]['projection_run_id'] if chosen else None,projection_metrics=metrics(scored),
            game_resolution=[dict(game_id=g, resolved_game_id=next(r['resolved_game_id'] for r in chosen if r['game_id']==g),
                basis=next(r['game_match_basis'] for r in chosen if r['game_id']==g)) for g in sorted({r['game_id'] for r in chosen})],
            projected_10_plus_metrics=metrics([r for r in scored if r['mean'] is not None and r['mean'] >= 10]),
            projection_exclusions=[dict(projection_run_id=rr[0]['projection_run_id'], reasons=projection_exclusions(rr)) for rr in available if not pregame(rr)],
            position_metrics={pos:metrics([r for r in scored if r['position']==pos]) for pos in sorted({r['position'] or 'UNKNOWN' for r in scored})},
            projection_players=scored,projection_snapshot_sha256=digest(chosen),gpp_runs=len(related),
            eligible_gpp_runs=sum(r['eligibility']=='exploratory' for r in related),
            excluded_reasons=dict(Counter(reason for r in related for reason in r['excluded_reasons'])),
            primary_run=primary,fields=fields,gaps=gaps))
    return dict(created_at=datetime.now(timezone.utc).isoformat(),season=2026,weeks=[1,2,3,4],
        contract='weekly_validation_v1',history_conflicts=conflicts,history_source_hashes=[s['content_sha256'] for s in sources],
        blocks=blocks,runs=results,limitations=[
        'Exploratory retrospective audit; database clocks do not prove immutable prelock capture.',
        'Latest eligible snapshot/replay per slate chosen by time, never actual performance; related runs are not independent trials.',
        'Projection means use base points; Captain actuals normalize CPT observations to base points and lineup scores multiply once.',
        'Actual labels come from imported contest observations; absent/conflicting scores are unknown, not zero. No cross-slate label substitution.',
        'Schedule dates are imported NFL schedule evidence interpreted in America/New_York, not independently archived kickoff certification.',
        'Recommendation is a current-policy historical replay, not proof of the historical entry. Best candidate scores are hindsight diagnostics.',
        'Primary replay may use a different projection snapshot than the separately selected latest eligible projection audit.',
        'No training, model promotion, active projection changes, or expected-return estimates.'])


def markdown(report):
    lines=['# 2026 Weeks 1–4 validation','',*['- '+s for s in report['limitations']],'',
           '| Week | Slate / format | Projection matched / rows | MAE | Bias | GPP eligible / runs | Primary actual | Paid / known |',
           '|---|---|---:|---:|---:|---:|---:|---:|']
    for b in report['blocks']:
        m=b['projection_metrics'];p=b['primary_run'] or {};fs=p.get('field_outcomes',[])
        known=[f['paid_finish'] for f in fs if f['paid_finish'] is not None]
        num=lambda v:'—' if v is None else f'{v:.2f}'
        lines.append(f"| {b['week']} | {b['slate']} / {b['contest_format']} | {m['matched']}/{m['rows']} | {num(m['mae'])} | {num(m['bias'])} | {b['eligible_gpp_runs']}/{b['gpp_runs']} | {num(p.get('selected_actual_points'))} | {sum(known)}/{len(known)} |")
    lines+=['','## Missing evidence by slate','']
    for b in report['blocks']:
        lines.append(f"- W{b['week']} {b['slate']} ({b['contest_format']}): {', '.join(b['gaps']) or 'none'}.")
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    if args.output_dir.exists(): raise SystemExit('Use a new output directory to preserve prior audits')
    with engine.connect() as c: report=load(c)
    args.output_dir.mkdir(parents=True)
    (args.output_dir/'report.json').write_text(json.dumps(report,indent=2,default=str,allow_nan=False)+'\n')
    (args.output_dir/'report.md').write_text(markdown(report))
    print(markdown(report))

if __name__=='__main__': main()
