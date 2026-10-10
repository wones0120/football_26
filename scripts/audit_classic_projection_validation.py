"""Reproduce provenance failures and paired diagnostics without changing archives.

Outputs are RESEARCH_ONLY: archived alias receipts and historical per-game
features are not certified. No Week 5 outcomes are read. No database writes.
"""
from __future__ import annotations
import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.product_services.model_artifacts import deserialize_artifact
from backend.app.product_services.canonical_projection_inputs import attach_lagged_opportunity_features
from scripts.classic_projection_validation import build_opportunity_pair, paired_metrics, calibration_metrics, POLICIES
from scripts.validate_classic_opportunity_repair import forecasts

SOURCE = ROOT / 'artifacts/classic_opportunity_repair'
OUT = ROOT / 'artifacts/classic_projection_validation'
COUNTS = ('carries_mean_3', 'targets_mean_3', 'carry_share_mean_3', 'target_share_mean_3')


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, default=str, allow_nan=False) + '\n')


def differences(rebuilt, frozen):
    return {col: {'mismatches': int((rebuilt[col] - frozen['pregame_base_' + col]).abs().gt(1e-8).sum()),
                  'max_error': float((rebuilt[col] - frozen['pregame_base_' + col]).abs().max())} for col in COUNTS}


def input_context(artifact, run):
    target = artifact['target'].copy().reset_index(drop=True)
    meta = run['params_json']['pregame_context']
    known = set(target.player_id.astype(str))
    roles = {x['player_id']: x for x in meta.get('role_availability_audit', {}).get('players', [])}
    extras = {}
    for allocation in meta['allocations']:
        for player in allocation.get('players', []):
            pid = player['player_id']
            if pid in known:
                continue
            extra = extras.setdefault(pid, {'player_id': pid, 'player_master_id': pid,
                'recent_team': allocation['team'], 'team': allocation['team'],
                'position': roles.get(pid, {}).get('position', 'RB' if allocation['opportunity'] == 'carry' else 'WR'),
                'season': run['season'], 'week': run['week'], 'availability_probability': 1.})
            if player['prior_volume'] > 0:
                extra['availability_probability'] = min(extra['availability_probability'], 1-player['vacated_volume']/player['prior_volume'])
    neutral = pd.concat([target, pd.DataFrame(extras.values())], ignore_index=True) if extras else target.copy()
    contexts = []
    for _, row in neutral.iterrows():
        item = {'player_id': str(row.player_id)}
        for field in ('availability_probability', 'start_probability', 'carry_share', 'target_share', 'role_label',
                      'injury_status', 'expected_snaps', 'expected_routes', 'expected_carries', 'expected_targets',
                      'red_zone_share', 'goal_line_share'):
            value = row.get('pregame_' + field)
            if pd.isna(value):
                value = row.get(field)
            if pd.notna(value):
                item[field] = value
        contexts.append(item)
    starters = target[['recent_team', 'team_starting_qb_player_id']].dropna().drop_duplicates('recent_team').rename(
        columns={'recent_team': 'team', 'team_starting_qb_player_id': 'player_master_id'})
    return target, neutral, pd.DataFrame(contexts), starters


def recover_prelock_sources(weekly, cutoff):
    database = json.loads((OUT / 'database_inventory.json').read_text())
    frames, receipts = [], []
    mapping = weekly[['source_player_id', 'player_master_id']].dropna().drop_duplicates()
    if mapping.source_player_id.duplicated().any():
        raise ValueError('Ambiguous native ID mapping in frozen archive')
    lookup = mapping.set_index('source_player_id').player_master_id
    for receipt in database['source_snapshots']:
        if receipt['dataset'] != 'weekly_stats' or max(pd.Timestamp(receipt['observed_at']), pd.Timestamp(receipt['captured_at'])) > cutoff:
            continue
        path = Path(receipt['artifact_path'])
        if not path.exists():
            receipts.append({**receipt, 'available': False})
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != receipt['content_sha256']:
            raise ValueError('Immutable snapshot checksum mismatch')
        raw = pd.read_csv(path)
        frame = raw[['season', 'week', 'player_id', 'team', 'position', 'carries', 'targets']].rename(columns={'player_id': 'source_player_id'}).copy()
        frame['player_master_id'] = frame.source_player_id.map(lookup)
        frame['created_at'] = receipt['captured_at']
        frame['raw_nfl_weekly_stat_id'] = np.arange(len(frame))
        frames.append(frame)
        receipts.append({**receipt, 'available': True, 'hash_verified': True, 'raw_rows': len(frame),
                         'periods': frame[['season', 'week']].drop_duplicates().to_dict('records'),
                         'unresolved_native_ids': int(frame.player_master_id.isna().sum())})
    # Prior-season versions are demonstrably received before this 2026 cutoff;
    # their within-2024/2025 availability is NOT certified.
    older = weekly.loc[weekly.season < 2026].drop(columns='raw_row_json')
    combined = pd.concat([older, *frames], ignore_index=True)
    combined['created_at'] = pd.to_datetime(combined.created_at, utc=True, format='mixed')
    return combined, receipts


def main():
    OUT.mkdir(exist_ok=True)
    protected = sorted(SOURCE.rglob('*'))
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected if p.is_file()}
    inventory = json.loads((SOURCE / 'inventory.json').read_text())
    weekly = pd.DataFrame(json.load(gzip.open(SOURCE / 'weekly_stats.json.gz', 'rt')))
    receipts = weekly.groupby(['season', 'week']).agg(n=('team', 'size'), earliest=('created_at', 'min'), latest=('created_at', 'max')).reset_index()
    receipts.to_csv(OUT / 'source_receipts.csv', index=False)
    audit = []
    for run in inventory:
        artifact = deserialize_artifact((SOURCE / (run['projection_run_id'] + '.joblib')).read_bytes(), run['artifact_sha256'])
        target = artifact['target']
        cutoff = pd.Timestamp(run['data_cutoff_at']).tz_convert('UTC')
        strict, _ = attach_lagged_opportunity_features(target, weekly, cutoff=cutoff)
        late, _ = attach_lagged_opportunity_features(target, weekly, cutoff=pd.Timestamp('2026-10-09T21:56:16.351300Z'))
        source_prior = weekly.loc[(weekly.season * 100 + weekly.week < run['season'] * 100 + run['week'])]
        audit.append({'run': run['projection_run_id'], 'season': run['season'], 'week': run['week'], 'cutoff': str(cutoff),
            'strict_parity': differences(strict, target), 'late_receipt_counterfactual_parity': differences(late, target),
            'current_season_pre_cutoff_rows': int((source_prior.season.eq(run['season']) & (pd.to_datetime(source_prior.created_at, utc=True) <= cutoff)).sum()),
            'current_season_post_cutoff_rows': int((source_prior.season.eq(run['season']) & (pd.to_datetime(source_prior.created_at, utc=True) > cutoff)).sum()),
            'train_rows_created_after_cutoff': int((pd.to_datetime(artifact['train'].created_at, utc=True) > cutoff).sum()),
            'target_rows_created_after_cutoff': int((pd.to_datetime(target.created_at, utc=True) > cutoff).sum()),
            'alias_as_of_certified': False,
            'historical_training_opportunity_as_of_each_game_certified': False})
    save('source_integrity.json', audit)
    # Exactly ONE Week 4 snapshot: latest saved prelock forecast, chosen without labels.
    run = max((r for r in inventory if r['week'] == 4), key=lambda r: pd.Timestamp(r['data_cutoff_at']))
    artifact = deserialize_artifact((SOURCE / (run['projection_run_id'] + '.joblib')).read_bytes(), run['artifact_sha256'])
    target, neutral, context, starters = input_context(artifact, run)
    recovered, recovery_receipts = recover_prelock_sources(weekly, pd.Timestamp(run['data_cutoff_at']))
    save('recovered_source_receipts.json', recovery_receipts)
    parity, _ = attach_lagged_opportunity_features(target, recovered, cutoff=pd.Timestamp(run['data_cutoff_at']))
    save('recovered_week4_parity.json', differences(parity, target))
    pair, allocations = build_opportunity_pair(neutral, recovered, cutoff=pd.Timestamp(run['data_cutoff_at']), context=context, starters=starters)
    target['expected_depth_role'] = target.get('expected_depth_role', pd.Series('NOT_ESTABLISHED', index=target.index))
    comparison = target[['player_master_id', 'player_display_name', 'recent_team', 'position', 'salary', 'season', 'week', 'expected_depth_role']].copy()
    for policy, rows in pair.items():
        scoring = target.copy()
        rows = rows.iloc[:len(target)].copy()
        # Reuse the frozen non-opportunity inputs, fitted model, market correction,
        # and profiles for this diagnostic ONLY; this is not walk-forward refitting.
        opportunity_columns = [c for c in rows if c.startswith(('opportunity_', 'pregame_base_', 'pregame_effective_', 'offensive_role_'))
            or c in {'pregame_opportunity_context_applied', *COUNTS, 'team_carries_mean_3', 'team_targets_mean_3'}
            or c.endswith('_mean_3_available') and c != 'snap_share_mean_3_available']
        for column in opportunity_columns:
            scoring[column] = rows[column].to_numpy()
        predictions = forecasts(artifact, scoring)
        for col in ('mean', 'p10', 'p90'):
            comparison[policy + '_' + col] = predictions[col].to_numpy()
        for count, eligible in [('carries', {'RB'}), ('targets', {'RB', 'WR', 'TE'})]:
            supported = scoring[count + '_mean_3_available'].fillna(False)
            kind = 'carry' if count == 'carries' else 'target'
            supported |= scoring['pregame_effective_' + kind + '_share'].notna()
            comparison[policy + '_' + count] = scoring[count + '_mean_3'].where(scoring.position.isin(eligible) & supported).to_numpy()
        comparison[policy + '_history'] = rows.get('opportunity_history_status', pd.Series('legacy_player_window', index=rows.index)).to_numpy()
    # Forecasts are written before labels are loaded or joined.
    comparison.to_csv(OUT / 'paired_week4_forecasts.csv', index=False)
    save('paired_week4_allocations.json', allocations)
    from Database.scoring import compute_dk_scoring
    actual_rows = weekly.loc[weekly.season.eq(2026) & weekly.week.eq(4) & weekly.player_master_id.notna()].sort_values(['created_at', 'raw_nfl_weekly_stat_id']).drop_duplicates(['player_master_id', 'team'], keep='last').copy()
    actual_rows['actual_points'] = compute_dk_scoring(pd.DataFrame(actual_rows.raw_row_json.tolist())).dk_total_points.to_numpy()
    labels = actual_rows[['player_master_id', 'team', 'actual_points', 'carries', 'targets']].rename(columns={'team': 'recent_team', 'carries': 'actual_carries', 'targets': 'actual_targets'})
    if labels.duplicated(['player_master_id', 'recent_team']).any():
        raise ValueError('Ambiguous canonical outcome keys')
    comparison = comparison.merge(labels, on=['player_master_id', 'recent_team'], how='left', validate='one_to_one')
    comparison['price_band'] = np.where(comparison.salary >= 7000, 'expensive', np.where(comparison.salary <= 4500, 'inexpensive', 'middle'))
    # All cohort definitions come from prelock inputs, never actual workloads.
    comparison['volume_band'] = np.where(target.targets_mean_3.ge(6) | (target.position.eq('RB') & target.carries_mean_3.ge(14)), 'high', 'low')
    comparison['injury_status'] = target.get('pregame_injury_status', pd.Series('NOT_ESTABLISHED', index=target.index)).fillna('NOT_ESTABLISHED')
    comparison['role_change'] = target.get('pregame_newly_assigned_role', pd.Series('NOT_ESTABLISHED', index=target.index))
    observed = recovered.loc[pd.to_datetime(recovered.created_at, utc=True) <= pd.Timestamp(run['data_cutoff_at'])]
    latest = observed.sort_values(['season', 'week', 'created_at', 'raw_nfl_weekly_stat_id']).dropna(subset=['player_master_id']).drop_duplicates('player_master_id', keep='last').set_index('player_master_id')
    prior_teams = comparison.player_master_id.map(latest.team)
    comparison['team_change_proxy'] = np.where(prior_teams.isna(), 'unknown', np.where(prior_teams.ne(comparison.recent_team), 'prior_team_differs', 'same_latest_team'))
    groups = {'overall': comparison}
    for col in ('position', 'price_band', 'expected_depth_role', 'volume_band', 'team_window_v2_history', 'injury_status', 'role_change', 'team_change_proxy'):
        groups.update({col + ':' + str(k): g for k, g in comparison.groupby(col, dropna=False)})
    metrics = {}
    for name, group in groups.items():
        metrics[name] = {'fantasy': paired_metrics(group, 'actual_points', 'mean'),
                        'calibration': {p: calibration_metrics(group, p) for p in POLICIES}}
        for position, stat in [('RB', 'carries'), ('RB', 'targets'), ('WR', 'targets'), ('TE', 'targets')]:
            metrics[name][position + '_' + stat] = paired_metrics(group.loc[group.position.eq(position)], 'actual_' + stat, stat)
    teams = {}
    for policy, audits in allocations.items():
        for allocation in audits['allocation']['allocations']:
            team, kind = allocation['team'], allocation['opportunity']
            stat = 'carries' if kind == 'carry' else 'targets'
            actual = actual_rows.loc[actual_rows.team.eq(team) & actual_rows.position.isin({'RB', 'FB'} if kind == 'carry' else {'RB', 'WR', 'TE'})]
            if actual.empty:
                continue
            included_ids = {p['player_id'] for p in allocation['players']}
            actual_unrepresented = float(actual.loc[~actual.player_master_id.isin(included_ids), stat].sum())
            entry = teams.setdefault((team, stat), {'team': team, 'season': 2026, 'week': 4, 'opportunity': stat,
                'actual_team': float(actual[stat].sum()), 'actual_unrepresented': actual_unrepresented})
            entry[policy + '_team'] = float(allocation['team_volume'])
            entry[policy + '_unrepresented'] = float(allocation['unallocated_volume'])
            entry[policy + '_allocated'] = float(allocation['player_projected_volume_sum'])
    team_rows = pd.DataFrame(teams.values())
    team_rows.to_csv(OUT / 'paired_week4_team_allocation.csv', index=False)
    metrics['team_allocation'] = {kind: {measure: paired_metrics(g, 'actual_' + measure, measure)
        for measure in ('team', 'unrepresented')} for kind, g in team_rows.groupby('opportunity')}
    comparison['delta_absolute_point_error'] = (comparison.team_window_v2_mean-comparison.actual_points).abs() - (comparison.legacy_v1_mean-comparison.actual_points).abs()
    comparison.to_csv(OUT / 'paired_week4_diagnostic.csv', index=False)
    save('paired_week4_metrics.json', {'classification': 'RESEARCH_ONLY_NOT_VALIDATION',
        'run': run['projection_run_id'], 'independent_weeks': 1, 'promotable_weeks': 0,
        'source_limit': 'Same recovered checksum-verified prelock raw statistics for both policies; alias/context/per-game training provenance uncertified; frozen legacy models and calibration reused.', 'metrics': metrics})
    # Week 5 evidence only: no labels, actuals or future outcomes.
    run5 = next(r for r in inventory if r['week'] == 5)
    artifact5 = deserialize_artifact((SOURCE / (run5['projection_run_id'] + '.joblib')).read_bytes(), run5['artifact_sha256'])
    repaired = pd.read_pickle(SOURCE / (run5['projection_run_id'] + '_corrected_features.pkl'))
    changes = pd.read_csv(SOURCE / (run5['projection_run_id'] + '_comparison.csv'))
    names = {'Jahmyr Gibbs', 'Garrett Wilson', 'Sam LaPorta', 'Christian McCaffrey', 'Darius Slayton', 'Nico Collins', 'Justin Jefferson'}
    selected = []
    for _, row in changes.loc[changes.player_display_name.isin(names)].iterrows():
        f = repaired.loc[repaired.player_id.eq(row.player_id)].iloc[0]
        window = f.opportunity_history_window
        eligible = weekly.loc[weekly.player_master_id.eq(row.player_id) & weekly.team.eq(row.recent_team)
            & (pd.to_datetime(weekly.created_at, utc=True) <= pd.Timestamp(run5['data_cutoff_at']))]
        periods = {int(w['season']) * 100 + int(w['week']) for w in window}
        eligible = eligible.loc[(eligible.season * 100 + eligible.week).isin(periods)].sort_values(['created_at', 'raw_nfl_weekly_stat_id']).drop_duplicates(['season', 'week', 'player_master_id'], keep='last')
        item = {c: (None if pd.isna(v) else v) for c, v in row.to_dict().items() if c != 'history_window'}
        item.update(window=window, observed_games=int(f.opportunity_history_observed_games),
                    evidence=eligible[['season', 'week', 'team', 'carries', 'targets', 'created_at']].to_dict('records'),
                    opportunity_anchor_weight=float(forecasts(artifact5, repaired.loc[repaired.player_id.eq(row.player_id)].reset_index(drop=True)).pregame_opportunity_point_weight.iloc[0]))
        selected.append(item)
    save('week5_player_evidence.json', selected)
    for receipt in recovery_receipts:
        if receipt.get('hash_verified'):
            assert hashlib.sha256(Path(receipt['artifact_path']).read_bytes()).hexdigest() == receipt['content_sha256']
    assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == digest for p, digest in hashes.items()), 'Original frozen artifact changed'
    save('manifest.json', {'original_inputs_sha256': hashes, 'original_artifacts_preserved': True,
        'code_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__), ROOT/'scripts/classic_projection_validation.py']},
        'outputs_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name != 'manifest.json'}})
    print('Saved source-integrity audit, one-week paired diagnostic and Week 5 evidence; promotion remains blocked.')


if __name__ == '__main__':
    main()
