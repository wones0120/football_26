"""Offline current-team workload evidence and frozen-model Sunday Main experiment.

Does not fetch news, alter source evidence, or write live projections/selections.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from backend.app.product_services.canonical_projection_inputs import attach_lagged_opportunity_features
from backend.app.product_services.classic_strategy_contract import digest, execute_strategy_contract, portfolio_audit, validate_strategy_contract
from backend.app.product_services.model_artifacts import deserialize_artifact
from backend.app.product_services.optimizer_effectiveness import chronological_validation
from scripts.audit_sunday_projection_generation import recommend
from scripts.validate_classic_opportunity_repair import corrected, forecasts


def workload_contract(source, predictions):
    """Keep eligibility, preferences and scoring policy fixed; replace forecasts only."""
    result = deepcopy(source)
    result.pop('sha256')
    result['execution_mode'] = 'RESEARCH_SHADOW'
    result['strategy_label'] = source['strategy_id'] + ' + same-team workload shadow'
    result['deviations'] = ['Replace mean and marginal P90 from frozen-model team_window_v2 workload replay; preserve eligible IDs, salaries, ownership, tags, scoring weights and all user constraints. Pool pruning is frozen, not rerun.']
    for player in result['effective']['players']:
        values = predictions.loc[player['player_id']]
        mean, ceiling = float(values['mean']), float(values['p90'])
        if not np.isfinite([mean, ceiling]).all() or mean < 0 or ceiling < mean:
            raise ValueError('Invalid shadow prediction for ' + player['player_id'])
        player.update(projection=mean, ceiling=ceiling)
    result['effective_sha256'] = digest(result['effective'])
    result['sha256'] = digest(result)
    return result


def evidence_rows(features):
    """Derived forecasts remain distinct from absent explicit pregame measurements."""
    output = []
    for row in features.to_dict('records'):
        fields = ['player_id', 'player_display_name', 'position', 'recent_team',
                  'projected_carries', 'projected_targets', 'projected_opportunity_source',
                  'opportunity_history_status', 'opportunity_history_observed_games',
                  'opportunity_history_window', 'expected_depth_role']
        record = {k:row.get(k) for k in fields}
        record['missing_explicit_fields'] = [k for k in ('expected_snaps', 'expected_routes', 'expected_carries', 'expected_targets', 'red_zone_share', 'goal_line_share')
                                             if pd.isna(row.get('pregame_' + k))]
        window = row.get('opportunity_history_window', [])
        record['review_reasons'] = []
        if row.get('position') in {'RB', 'WR', 'TE'}:
            if row.get('opportunity_history_status') == 'no_same_team_window_history':
                record['review_reasons'].append('missing_current_team_history')
            elif row.get('opportunity_history_observed_games', 0) < len(window):
                record['review_reasons'].append('partial_current_team_window')
            if any(g['season'] < row['season'] for g in window):
                record['review_reasons'].append('prior_season_window')
        output.append(record)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, default=Path('artifacts/sunday_workload_shadow'))
    parser.add_argument('--source', type=Path, default=Path('artifacts/sunday_projection_generation/replay_source.json'))
    parser.add_argument('--output', type=Path, default=Path('artifacts/sunday_workload_shadow/results'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    def save(name, data):
        # Pandas normalizes NaN to JSON null; never present missing evidence as zero.
        clean = json.loads(pd.Series([data]).to_json(orient='values', date_format='iso'))[0]
        (args.output / name).write_text(json.dumps(clean, indent=2, allow_nan=False) + '\n')
    source = json.loads(args.source.read_text())
    config = source['constraint_config_json']
    contract = config['effective_strategy_contract']
    validate_strategy_contract(contract)
    run = json.loads((args.inputs / 'inventory.json').read_text())
    if (run['season'], run['week'], run['slate_id'], str(run['projection_run_id'])) != (2026, 5, 'SUNDAY_MAIN', source['projection_run_id']):
        raise ValueError('Frozen scope mismatch')
    artifact = deserialize_artifact((args.inputs / 'model.joblib').read_bytes(), run['artifact_sha256'])
    target = artifact['target'].reset_index(drop=True)
    training_period = artifact['train'].season * 100 + artifact['train'].week
    assert training_period.max() < run['season'] * 100 + run['week'], 'Training leaks target outcomes'
    weekly = pd.DataFrame(json.load(gzip.open(args.inputs / 'weekly_stats.json.gz', 'rt')))
    cutoff = pd.Timestamp(run['data_cutoff_at']).tz_convert('UTC')
    assert (pd.to_datetime(weekly.created_at, utc=True) <= cutoff).all()
    assert (weekly.season * 100 + weekly.week < run['season'] * 100 + run['week']).all()
    before = forecasts(artifact, target).set_index('player_id')
    stored = pd.DataFrame(json.loads((args.inputs / 'original_projections.json').read_text())).set_index('player_id')
    assert set(before.index) == set(stored.index)
    baseline_error = max(float((before[k] - stored[k]).abs().max()) for k in ('mean', 'p10', 'p90'))
    assert baseline_error < 1e-7, ('Prediction replay failed', baseline_error)
    legacy, _ = attach_lagged_opportunity_features(target, weekly, cutoff=cutoff)
    source_errors = {}
    for field in ('carries_mean_3', 'targets_mean_3', 'carry_share_mean_3', 'target_share_mean_3'):
        expected = target['pregame_base_' + field]
        pd.testing.assert_series_equal(legacy[field], expected, check_names=False, atol=1e-8, rtol=0)
        source_errors[field] = float((legacy[field] - expected).abs().max())
    print('Frozen projection and raw-source parity verified', flush=True)
    changed, allocation, excluded, lineage = corrected(artifact, run, weekly)
    after = forecasts(artifact, changed).set_index('player_id')
    save('workload_evidence.json', evidence_rows(changed))
    save('allocation.json', allocation)
    comparison = target[['player_id', 'player_display_name', 'recent_team', 'position']].set_index('player_id')
    for field in ('mean', 'p10', 'p90'):
        comparison['before_' + field] = before[field]
        comparison['after_' + field] = after[field]
        comparison['delta_' + field] = after[field] - before[field]
    for field, legacy_field in [('projected_carries', 'carries_mean_3'), ('projected_targets', 'targets_mean_3')]:
        comparison['before_' + field] = target.set_index('player_id')[legacy_field]
        comparison['after_' + field] = changed.set_index('player_id')[field]
    comparison.to_csv(args.output / 'player_comparison.csv')
    solver_rows = config['strategy_runtime']['classic_run_input_snapshot']['payload']['final_solver_rows']
    for player in contract['effective']['players']:
        assert abs(player['projection'] - before.loc[player['player_id'], 'mean']) < 1e-7
        assert abs(player['ceiling'] - before.loc[player['player_id'], 'p90']) < 1e-7
    saved = config['portfolio_controls_report']['candidate_rosters']
    report = dict(source_run_id=source['optimizer_run_id'], projection_run_id=source['projection_run_id'],
                  baseline_max_error=baseline_error, source_parity=source_errors,
                  training_latest_period=int(training_period.max()), lineage=lineage,
                  started_at=datetime.now(timezone.utc).isoformat(), live_changes=False,
                  promotion='NOT_VALIDATED', paid_finish_probability=None, expected_return=None,
                  limitations=['No fresh snaps/routes/red-zone source was added; estimates are derived from archived usage.',
                               'Canonical aliases reflect capture-time mapping, not a historical alias snapshot.',
                               'Same fixed final solver pool; this does not test projection-driven upstream pruning.',
                               'Current outcomes unavailable; prior exploratory repair validation did not establish promotion.'], arms={})
    for arm in ('control', 'workload_shadow'):
        current = contract if arm == 'control' else workload_contract(contract, after)
        # Use exact JSON precision for hashed contracts; do not pass through Pandas.
        (args.output / (arm + '_contract.json')).write_text(json.dumps(current, indent=2, allow_nan=False) + '\n')
        result = execute_strategy_contract(current)
        proof = portfolio_audit(current, result.lineups, trace=result.selection_trace)
        assert result.status == 'completed' and proof['validation']['status'] == 'verified'
        rec, rosters = recommend(result, source, solver_rows)
        if arm == 'control':
            assert [sorted(p['player_id'] for p in r) for r in rosters] == [sorted(r['player_ids']) for r in saved]
            assert rec['recommended']['candidate_id'] == config['gpp_recommendation']['recommended']['candidate_id']
        completed = datetime.now(timezone.utc).isoformat()
        cross_scores = []
        for roster in rosters:
            ids = [p['player_id'] for p in roster]
            cross_scores.append(dict(baseline_mean=float(before.loc[ids, 'mean'].sum()), shadow_mean=float(after.loc[ids, 'mean'].sum())))
        report['arms'][arm] = dict(recommendation=rec, rosters=rosters, portfolio=proof,
                                  scores_under_both_models=cross_scores, completed_at=completed,
                                  timing=chronological_validation(dict(data_cutoff_at=source['data_cutoff_at'], optimizer_created_at=completed),dict(status='slate_source_pool', candidates=saved)))
        save('experiment.json', report)
        print(arm, rec['recommended'], flush=True)
    manifest = {str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [args.source, *args.inputs.glob('*.json'), args.inputs/'model.joblib', args.inputs/'weekly_stats.json.gz', Path(__file__), Path('scripts/validate_classic_opportunity_repair.py')]}
    save('input_manifest.json', manifest)


if __name__ == '__main__':
    main()
