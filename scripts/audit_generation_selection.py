"""Read-only stage audit of a frozen weekly validation report; no policy changes."""
import argparse
from collections import Counter
from pathlib import Path
import json
from sqlalchemy import text
from backend.app.db import engine
from backend.app.product_services.gpp_historical_audit import digest
from backend.app.product_services.optimizer_effectiveness import actual_points_by_player, candidate_signature, score_signature


def coverage(rows):
    unique = {r['candidate_id']: r for r in rows}
    scored = [r for r in unique.values() if r['actual_points'] is not None]
    best = max(scored, key=lambda r: r['actual_points'], default=None)
    return dict(unique=len(unique), scoreable=len(scored), best=best,
                complete=bool(unique) and len(unique) == len(scored))


def paid_above_cutoff(score, cutoff):
    # Boundary ties need the full field; never convert equality into a paid claim.
    if score is None or cutoff is None or abs(score-cutoff) <= .005:
        return None
    return score > cutoff


def diagnose(selected, returned, pool, eligible, complete):
    if selected is True:
        return 'recommended_paid'
    if selected is not False:
        return 'unknown'
    if returned is True:
        return 'final_selection_miss'
    if eligible is True:
        return 'eligible_pool_shortlisting_miss'
    if pool is True:
        return 'quality_or_constraint_screen_or_unrecorded_eligibility'
    if pool is False and complete:
        return 'no_paid_candidate_in_saved_pool'
    return 'incomplete_pool_evidence'


def audit(connection, report):
    connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
    connection.execute(text('SET TRANSACTION READ ONLY'))
    actuals, details = {}, []
    positions = {str(k):v for k,v in connection.execute(text("SELECT player_id,primary_position FROM target.dim_player"))}
    for run in report['runs']:
        if run['eligibility'] != 'exploratory':
            continue
        key = run['week'], run['slate'], run['contest_format']
        fields = [f for f in run['field_outcomes'] if f['paid_finish_evidence']]
        if not fields:
            continue
        pool = run['pool_evidence']
        records, gates = [], {}
        if pool['status'] == 'original_candidate_pool':
            if key not in actuals:
                obs = connection.execute(text('''SELECT o.player_id,o.roster_position,o.actual_points,o.resolution_status
                    FROM target.contest_ownership_observation o JOIN target.dfs_contest c USING(contest_id)
                    WHERE c.season=:season AND c.week=:week AND c.slate_id=:slate AND c.contest_format=:fmt'''),
                    dict(season=report['season'],week=key[0],slate=key[1],fmt=key[2])).mappings()
                actuals[key] = actual_points_by_player(obs,key[2])
            rows = connection.execute(text('SELECT constraint_config_json #> :path FROM target.optimizer_run WHERE optimizer_run_id=:id'),
                dict(path=pool['source_path'].split('.'),id=run['run_id'])).scalar_one()
            if digest(rows) != pool['sha256']:
                raise ValueError('Saved pool changed since weekly audit: '+run['run_id'])
            for row in rows:
                signature = candidate_signature(row,key[2])
                score, missing = score_signature(signature,actuals[key])
                flags = {k:row[k] for k in ('quality_eligible','baseline_constraint_survives') if k in row}
                status = ('rejected' if any(v is False for v in flags.values()) else
                          'recorded_eligible' if flags.get('quality_eligible') is True else 'unknown')
                captain_id = next((pid for pid,cap in signature if cap), None)
                records.append(dict(candidate_id=digest(signature),actual_points=score,missing_actuals=missing,
                    captain_position=positions.get(captain_id),
                    eligibility=status,flags=flags,rank=row.get('rank'),captain=row.get('captain_name') or row.get('captain'),
                    projected_mean=row.get('baseline_mean',row.get('mean'))))
            if 'showdown_portfolio_policy' in pool['source_path']:
                gates = connection.execute(text("""SELECT jsonb_build_object(
                    'quality_fraction',constraint_config_json #> '{strategy_runtime,showdown_portfolio_policy,candidate_selection,quality_fraction}',
                    'quality_basis',constraint_config_json #> '{strategy_runtime,showdown_portfolio_policy,candidate_selection,quality_basis}',
                    'best_mean',constraint_config_json #> '{strategy_runtime,showdown_portfolio_policy,candidate_selection,best_mean}',
                    'best_p90',constraint_config_json #> '{strategy_runtime,showdown_portfolio_policy,candidate_selection,best_p90}')
                    FROM target.optimizer_run WHERE optimizer_run_id=:id"""),dict(id=run['run_id'])).scalar_one()
        groups = {name:coverage(records if name=='all' else [r for r in records if r['eligibility']==name])
                  for name in ('all','recorded_eligible','rejected','unknown')}
        groups['wr_rb_captain_only'] = coverage([r for r in records if r['captain_position'] in {'WR','RB'}])
        groups['wr_rb_captain_recorded_eligible'] = coverage([r for r in records if r['captain_position'] in {'WR','RB'} and r['eligibility']=='recorded_eligible'])
        def best(name):
            return (groups[name]['best'] or {}).get('actual_points')
        outcomes=[]
        for f in fields:
            cutoff=f['paid_cutoff_points']
            outcomes.append(dict(contest_id=f['contest_id'],contest_name=f['contest_name'],cutoff=cutoff,
                selected_paid=f['paid_finish'],top_ten_percent=f['top_ten_percent'],top_one_percent=f['top_one_percent'],
                diagnosis=diagnose(f['paid_finish'],paid_above_cutoff(run['returned_coverage']['best_observed'],cutoff),
                    paid_above_cutoff(best('all'),cutoff),paid_above_cutoff(best('recorded_eligible'),cutoff),groups['all']['complete'])))
        details.append(dict(run_id=run['run_id'],week=key[0],slate=key[1],format=key[2],strategy=run['strategy'],
            optimizer_created_at=run['optimizer_created_at'],selected_actual=run['selected_actual_points'],
            returned=run['returned_coverage'],pool_sha256=pool.get('sha256'),groups=groups,gates=gates,outcomes=outcomes))
    primary_ids={b['primary_run']['run_id'] for b in report['blocks'] if b['primary_run']}
    return dict(source_sha256=digest(report),live_selector_changed=False,promotion_eligible=False,
        primary=[r for r in details if r['run_id'] in primary_ids],runs=details,
        comparisons=dict(Counter(o['diagnosis'] for r in details for o in r['outcomes'])))


def markdown(result):
    lines=['# Generation versus selection: Classic and Captain','',
        'Read-only 2026 Weeks 1–4 audit. Paid finishes take priority; no live policy changes or promotion.',
        'Primary run per slate is the latest clock-eligible run, chosen before inspecting results.',
        'Recommendations replay today’s policy on historical returned candidates; they are not actual submitted entries.',
        'Pool maxima are hindsight diagnostics, not a strategy or attainable forecast.', '',
        '| Week / slate | Selected actual | Best returned | Best saved pool | Best recorded eligible pool | Paid / known GPPs | Diagnosis |',
        '|---|---:|---:|---:|---:|---:|---|']
    num=lambda x:'—' if x is None else f'{x:.2f}'
    for r in sorted(result['primary'],key=lambda r:(r['format']!='classic',r['week'],r['slate'])):
        best=lambda k:(r['groups'][k]['best'] or {}).get('actual_points')
        known=[o['selected_paid'] for o in r['outcomes'] if o['selected_paid'] is not None]
        lines.append(f"| W{r['week']} {r['slate']} | {num(r['selected_actual'])} | {num(r['returned']['best_observed'])} | {num(best('all'))} | {num(best('recorded_eligible'))} | {sum(known)}/{len(known)} | {', '.join(sorted({o['diagnosis'] for o in r['outcomes']}))} |")
    lines+=['','## Interpretation and limits','',
        '- A saved pool with no paid candidate is a failure of that particular generated set, not proof no legal paid lineup existed.',
        '- WR/RB subsets check Captain position only (canonical player dimension); they do not replay all current salary, team-leader, stack or team-split rules.',
        '- Missing eligibility flags stay unknown; an excluded quality-gate candidate is not automatically a selectable alternative.',
        '- Recorded quality eligibility does not certify undocumented constraints or current user preferences. Older pools predate current defaults.',
        '- Scenario variants are deduplicated by canonical roster and Captain assignment within each group; group counts can overlap.',
        '- Missing actuals are unknown, not zero. Ties at the paid boundary remain unknown in the extra stage comparison.',
        '- Related runs and contests are not independent trials. Do not interpret the comparison counts as a win rate.',
        '- Database clocks screen out post-lock runs but do not prove immutable prelock provenance.',
        '- Full payout ladders are absent; expected return, duplication-adjusted winnings, and ROI improvement remain unvalidated.',
        '- See report.json/report.md for all missing slate evidence and excluded runs.', '',
        '## Related run/contest diagnostic counts (not independent trials)','',
        *[f'- {k}: {v}' for k,v in sorted(result['comparisons'].items())]]
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    args=parser.parse_args()
    target=args.source.parent/'stage_audit.json'
    if target.exists():raise SystemExit('Use a fresh report directory')
    report=json.loads(args.source.read_text())
    with engine.connect() as c: result=audit(c,report)
    target.write_text(json.dumps(result,indent=2,default=str)+'\n')
    target.with_suffix('.md').write_text(markdown(result))
    print(markdown(result))

if __name__=='__main__':main()
