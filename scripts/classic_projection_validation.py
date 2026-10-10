"""Offline validation primitives. No database writes or production settings changes.

Forecast tables must be joined by canonical ID/team/week, never display names.
One Sunday Main slate per season/week is one independent observation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

POLICIES = ('legacy_v1', 'team_window_v2')


def validate_windows(windows):
    """Reject unverifiable windows before fitting, tuning, or reading test labels.

    Each receipt is an immutable source version, including identity, roster,
    non-opportunity features, context and raw workload. Timestamps alone are not
    proof: hashes must have been checked against the frozen bytes by the loader.
    """
    seen = set()
    for window in windows:
        key = (int(window['season']), int(window['week']))
        if key in seen:
            raise ValueError('Multiple snapshots of one week are not independent folds')
        seen.add(key)
        if window['slate'] != 'SUNDAY_MAIN':
            raise ValueError('Only Sunday Main slates are eligible')
        cutoff = pd.Timestamp(window['cutoff'])
        kickoff = pd.Timestamp(window['earliest_kickoff'])
        if cutoff.tzinfo is None or kickoff.tzinfo is None or cutoff >= kickoff:
            raise ValueError('A timezone-aware prelock cutoff is required')
        required = {'weekly_stats', 'identity', 'roster', 'features', 'context'}
        receipts = window['receipts']
        if not required.issubset({r['kind'] for r in receipts}):
            raise ValueError('Missing point-in-time source domain')
        for receipt in receipts:
            if not receipt.get('hash_verified') or not receipt.get('sha256'):
                raise ValueError('Unverified source bytes')
            for field in ('received_at', 'observed_at'):
                stamp = pd.Timestamp(receipt[field])
                if stamp.tzinfo is None or stamp > cutoff:
                    raise ValueError('Source received/observed after cutoff')
        if not window.get('historical_features_as_of_each_game'):
            raise ValueError('Training features lack per-game point-in-time evidence')


def error_metrics(predicted, actual):
    p, a = np.asarray(predicted, dtype=float), np.asarray(actual, dtype=float)
    valid = np.isfinite(p) & np.isfinite(a)
    error = p[valid] - a[valid]
    return {'n': int(valid.sum()), 'missing_forecast_n': int((~np.isfinite(p) & np.isfinite(a)).sum()),
            'mae': float(np.abs(error).mean()) if len(error) else None,
            'rmse': float(np.sqrt(np.mean(error ** 2))) if len(error) else None,
            'bias': float(error.mean()) if len(error) else None}


def paired_metrics(frame, outcome, prediction, *, bootstrap_samples=2000, seed=42):
    """Equal-week paired differences; bootstrap weeks, never individual players."""
    before, after = (frame[p + '_' + prediction] for p in POLICIES)
    actual = frame[outcome]
    paired = np.isfinite(before) & np.isfinite(after) & np.isfinite(actual)
    g = frame.loc[paired].copy()
    result = {p: error_metrics(g[p + '_' + prediction], g[outcome]) for p in POLICIES}
    result['paired_n'] = len(g)
    result['unpaired'] = {p: error_metrics(frame[p + '_' + prediction], actual) for p in POLICIES}
    week_deltas = []
    result['by_week'] = {}
    for key, rows in g.groupby(['season', 'week']):
        metrics = {p: error_metrics(rows[p + '_' + prediction], rows[outcome]) for p in POLICIES}
        delta = {m: metrics[POLICIES[1]][m] - metrics[POLICIES[0]][m] for m in ('mae', 'rmse', 'bias')}
        result['by_week'][f'{key[0]}-W{key[1]}'] = {**metrics, 'delta': delta}
        week_deltas.append([delta[m] for m in ('mae', 'rmse', 'bias')])
    result['independent_weeks'] = len(week_deltas)
    result['equal_week_delta'] = None
    result['week_cluster_95_ci'] = None
    if week_deltas:
        values = np.asarray(week_deltas)
        result['equal_week_delta'] = dict(zip(('mae', 'rmse', 'bias'), values.mean(axis=0).tolist()))
        if len(values) >= 2:
            rng = np.random.default_rng(seed)
            draws = values[rng.integers(0, len(values), (bootstrap_samples, len(values)))].mean(axis=1)
            bounds = np.quantile(draws, [.025, .975], axis=0)
            result['week_cluster_95_ci'] = {m: bounds[:, i].tolist() for i, m in enumerate(('mae', 'rmse', 'bias'))}
    return result


def calibration_metrics(frame, policy):
    cols = [policy + '_p10', policy + '_p90', 'actual_points']
    g = frame.loc[np.isfinite(frame[cols]).all(axis=1)]
    if (g[cols[0]] > g[cols[1]]).any():
        raise ValueError('Crossed prediction intervals')
    if g.empty:
        return {'n': 0}
    actual, lo, hi = g.actual_points, g[cols[0]], g[cols[1]]
    return {'n': len(g), 'below_p10': float((actual < lo).mean()),
            'above_p90': float((actual > hi).mean()),
            'coverage': float(((actual >= lo) & (actual <= hi)).mean()),
            'width': float((hi - lo).mean()),
            'interval_score_80': float((hi-lo + 10*(lo-actual).clip(lower=0) + 10*(actual-hi).clip(lower=0)).mean())}


def select_anchor_weights(validation, *, test_start, candidates=((.55, .70), (.25, .40), (.40, .55), (.70, .85), (0., 0.), (1., 1.))):
    """Tune only prior validation OOF rows; leave the chronological test untouched.

    base/anchor must come from independently refitted prior-only models; inactive
    anchors remain inactive. Score equal-week MAE, break ties in favor of defaults.
    """
    period = validation.season * 100 + validation.week
    if validation.empty or period.ge(test_start).any():
        raise ValueError('Validation must be nonempty and strictly before untouched test')
    if validation[['season', 'week']].drop_duplicates().shape[0] < 3:
        raise ValueError('At least three independent validation weeks required')
    if not validation['prior_only_fit'].eq(True).all():
        raise ValueError('Weight tuning requires prior-only out-of-fold forecasts')
    if not (validation.training_through < period).all():
        raise ValueError('Training overlaps validation outcomes')
    scores = []
    for veteran, low_history in candidates:
        weight = np.where(validation.player_games_history < 3, low_history, veteran)
        weight = np.where(validation.anchor_active & validation.anchor.notna(), weight, 0.)
        prediction = (1-weight)*validation.base + weight*validation.anchor.fillna(0.)
        error = (prediction - validation.actual_points).abs()
        score = error.groupby([validation.season, validation.week]).mean().mean()
        scores.append({'veteran': veteran, 'low_history': low_history, 'mae': float(score)})
    return min(scores, key=lambda r: r['mae']), scores


def build_opportunity_pair(neutral, weekly, *, cutoff, context=None, starters=None):
    """Build both allocation methods from the exact same frozen input objects.

    neutral contains the full prelock roster including unavailable players;
    caller must supply point-in-time receipts via validate_windows first.
    """
    from backend.app.product_services.canonical_projection_inputs import (
        attach_lagged_opportunity_features, apply_pregame_projection_context,
    )
    from backend.app.product_services.offensive_role import attach_offensive_role
    pair, audits = {}, {}
    for policy in POLICIES:
        rows, source = attach_lagged_opportunity_features(neutral, weekly, cutoff=cutoff, policy=policy)
        rows, audit = apply_pregame_projection_context(rows, pregame_context=context, starting_qbs=starters)
        role_rows = rows.copy()
        for kind in ('carry', 'target'):
            col = kind + '_share_mean_3'
            explicit = rows['pregame_effective_' + kind + '_share']
            role_rows[col] = explicit.where(explicit.notna(), rows['pregame_base_' + col])
            role_rows[col + '_available'] = rows[col + '_available'] | explicit.notna()
        refreshed = attach_offensive_role(role_rows)
        for col in refreshed:
            if col.startswith('offensive_role_'):
                rows[col] = refreshed[col]
        pair[policy], audits[policy] = rows, {'source': source, 'allocation': audit}
    return pair, audits


def refit_forecast_pair(train_pair, target_pair, *, target_period, feature_columns, windows):
    """Independently refit comparable models and prior OOF calibration.

    No target outcomes are accepted. Requires caller-certified per-game source
    snapshots, not historically lagged features rebuilt from today's sources.
    """
    from sklearn.ensemble import GradientBoostingRegressor
    from backend.app.product_services.predictions import (
        TARGET_COL, blend_point_predictions, apply_opportunity_point_adjustment,
        derive_calibration_roles, build_position_calibration, apply_residual_calibration,
    )
    validate_windows(windows)
    if target_period not in {int(w['season'])*100+int(w['week']) for w in windows}:
        raise ValueError('Missing evaluation window provenance')
    opportunity_features = {'offensive_role_importance', 'offensive_role_completeness'}
    for frames in (train_pair, target_pair):
        for column in feature_columns:
            if column not in opportunity_features:
                pd.testing.assert_series_equal(frames[POLICIES[0]][column].reset_index(drop=True), frames[POLICIES[1]][column].reset_index(drop=True))
        for column in ('player_master_id', 'season', 'week', 'position'):
            pd.testing.assert_series_equal(frames[POLICIES[0]][column].reset_index(drop=True), frames[POLICIES[1]][column].reset_index(drop=True))
    predictions = {}
    for policy in POLICIES:
        train, target = train_pair[policy].copy(), target_pair[policy].copy()
        if TARGET_COL in target and target[TARGET_COL].notna().any():
            raise ValueError('Evaluation labels must not enter forecasting')
        if 'market_team_point_adjustment' in target and target.market_team_point_adjustment.fillna(0).ne(0).any():
            raise ValueError('Refit requires recomputed market reconciliation; frozen fitted adjustments cannot be reused')
        period = train.season * 100 + train.week
        if train.empty or period.ge(target_period).any():
            raise ValueError('Training must be strictly prior to evaluation week')
        if (target.season * 100 + target.week).ne(target_period).any():
            raise ValueError('Target rows must belong to the evaluation week')
        residual_frames = []

        def predict(prior, scoring):
            model = GradientBoostingRegressor(random_state=42)
            model.fit(prior[feature_columns].apply(pd.to_numeric, errors='coerce').fillna(0), prior[TARGET_COL])
            raw = model.predict(scoring[feature_columns].apply(pd.to_numeric, errors='coerce').fillna(0))
            mean = blend_point_predictions(raw, prior, scoring)
            mean, _ = apply_opportunity_point_adjustment(mean, prior, scoring)
            availability = scoring.get('pregame_availability_probability', pd.Series(1., index=scoring.index)).fillna(1.).to_numpy()
            starter = scoring.get('pregame_start_probability', pd.Series(1., index=scoring.index)).fillna(1.).to_numpy()
            availability *= np.where(scoring.position.eq('QB'), starter, 1.)
            return np.maximum(0., mean), availability

        for calibration_period in sorted(period.unique()):
            prior, scoring = train.loc[period < calibration_period], train.loc[period == calibration_period]
            if len(prior) < 200:
                continue
            mean, availability = predict(prior, scoring)
            residual = scoring[['season', 'week', 'position']].copy()
            residual['calibration_role'] = derive_calibration_roles(scoring).to_numpy()
            # Calibrate the conditional prediction; zero-probability rows cannot
            # identify its residual. Evaluation intervals retain production scaling.
            valid = availability > 0
            residual['residual'] = scoring[TARGET_COL].to_numpy() / np.where(valid, availability, 1.) - mean
            if 'offensive_role_importance' in scoring:
                residual['offensive_role_importance'] = scoring.offensive_role_importance.to_numpy()
            residual_frames.append(residual.loc[valid])
        if not residual_frames:
            raise ValueError('Insufficient prior OOF calibration evidence; no dispersion substitute')
        profiles, calibration = build_position_calibration(pd.concat(residual_frames), train)
        mean, availability = predict(train, target)
        roles = derive_calibration_roles(target).reset_index(drop=True)
        result = target[['player_master_id', 'recent_team', 'position', 'season', 'week']].reset_index(drop=True)
        result['mean'] = mean * availability
        lower, upper = [], []
        for i, row in target.reset_index(drop=True).iterrows():
            role = row.get('pregame_role_label')
            role = role if role in {'LEAD', 'COMMITTEE', 'PRIMARY', 'SECONDARY', 'ROTATION'} else roles.iloc[i]
            key = f'{row.position}|{role}'
            split = calibration.get('importance_splits_by_role', {}).get(key)
            importance = row.get('offensive_role_importance', np.nan)
            if split is not None and pd.notna(importance):
                key += '|importance_' + ('high' if importance >= split else 'low')
            profile = profiles.get(key, profiles.get(f'{row.position}|{role}', profiles.get(row.position, profiles['__ALL__'])))
            quantiles = apply_residual_calibration(float(mean[i]), profile)
            lower.append(quantiles['p10'] * availability[i])
            upper.append(quantiles['p90'] * availability[i])
        result['p10'], result['p90'] = lower, upper
        predictions[policy] = result
    return predictions
