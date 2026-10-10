"""Replay a captured Captain shortlist audit offline; never change live selections."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from backend.app.product_services.gpp_recommendation import candidate_id, evaluate_candidates


def audit(baseline, selection, salaries):
    control = baseline['arms']['control']['roster']
    players = {p['player_id']: p for p in control}
    native = {(p['player_id'], p['roster_position']): p for p in salaries}
    rows = selection['ranked_metrics']
    eligible = [r for r in rows if r['quality_eligible'] and r['baseline_constraint_survives']]
    # Freeze the existing recommendation ordering; change only shortlist coverage.
    def identity(row):
        return candidate_id([dict(p, roster_position=p['slot']) for p in row['players']])
    best = min(eligible, key=lambda r: (-r['baseline_mean'], -r['baseline_p90'], identity(r)))
    challenger = []
    for p in best['players']:
        # This bounded audit reconstructs only players already in the frozen control.
        # Fail closed if a future experiment needs additional projection evidence.
        row = deepcopy(players[p['player_id']])
        slot = p['slot']
        salary = native[(p['player_id'], slot)]
        multiplier = 1.5 if slot == 'CPT' else 1.0
        old_multiplier = 1.5 if row['roster_position'] == 'CPT' else 1.0
        mean = row['baseline_projection'] / old_multiplier * multiplier
        p90 = row['baseline_p90'] / old_multiplier * multiplier
        row.update(roster_position=slot, salary=float(salary['salary']),
                   projection=mean, baseline_projection=mean, p90=p90, baseline_p90=p90,
                   dk_player_id=native[(p['player_id'], 'FLEX')]['source_player_key'],
                   dk_captain_id=native[(p['player_id'], 'CPT')]['source_player_key'])
        row.pop('scenario_projection', None)
        challenger.append(row)
    assert len(challenger) == len({r['player_id'] for r in challenger}) == 6
    assert sum(r['roster_position'] == 'CPT' for r in challenger) == 1
    assert len({r['player_team'] for r in challenger}) == 2
    assert math.isclose(sum(r['projection'] for r in challenger), best['baseline_mean'])
    assert math.isclose(sum(r['p90'] for r in challenger), best['baseline_p90'])
    assert math.isclose(sum(r['salary'] for r in challenger), best['salary'])
    report = evaluate_candidates([control, challenger], run_id=baseline['source_run_id'],
        season=baseline['season'], week=baseline['week'], slate=baseline['slate'],
        contest_format='showdown', projection_run_id=None, data_cutoff_at=None)
    assert len(report['candidates']) == 2 and not report['exceptions']
    assert report['recommended']['candidate_id'] == identity(best)
    return dict(source_run_id=baseline['source_run_id'], policy='expanded_shortlist_same_projection_order_v1',
        candidate_count=len(rows), eligible_count=len(eligible),
        challenger_original_rank=best['rank'], challenger_was_returned=best['rank'] in selection['selected_ranks'],
        portfolio_selector_opportunity_cost=best['forced_baseline_portfolio_opportunity_cost'],
        forecast_gain=best['baseline_mean'] - sum(p['projection'] for p in control),
        challenger_roster=challenger, comparison=report,
        status='offline_shadow_only', paid_finish_improvement=None,
        next_gate='Register before kickoff and evaluate imported outcomes; no live promotion from projection gain alone.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--capture-dir', type=Path, required=True)
    args = parser.parse_args()
    paths = [args.baseline, args.capture_dir / 'candidate_selection.json', args.capture_dir / 'native_salaries.json']
    result = audit(*(json.loads(p.read_text()) for p in paths))
    result['input_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (args.capture_dir / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('candidate_count', 'eligible_count', 'forecast_gain', 'challenger_original_rank', 'status')}))


if __name__ == '__main__':
    main()
