"""Explicit offline arithmetic-count recipes; no serving or baseline mutation."""
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import warnings

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.neural_network import MLPRegressor

from .feature_block_model_inputs import WORKLOAD_VERSION, transform
from .offensive_volume_features import digest
from .opportunity_history_evidence import CHANNELS
from .scheduled_workload_efficiency_model_inputs import PLAYER_COLUMNS

VERSION = 'player_raw_count_models_v1'
RECIPE = 'train_affine_raw_count_v1'
NEURAL_RECIPE = 'adam_optimizer_repair_v1'


def count_metrics(actual, predicted):
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if not len(actual):
        return None
    error = predicted - actual
    return dict(rows=len(actual), mae=float(np.abs(error).mean()),
                rmse=float(np.sqrt(np.mean(error ** 2))), bias=float(error.mean()))


def predict_arrays(bundle, x):
    """Keep unconstrained count estimates separate from max-zero support."""
    output = {}
    for target, model in bundle['estimators'].items():
        scaler = bundle['receipt']['target_scalers'][target]
        raw = np.asarray(model.predict(np.asarray(x, dtype=float)), dtype=float) * scaler['scale'] + scaler['center']
        if raw.ndim != 1 or len(raw) != len(x) or not np.isfinite(raw).all():
            raise ValueError('Invalid raw count prediction')
        supported = np.maximum(0., raw)
        magnitude = supported - raw
        output[target] = dict(raw=raw, supported=supported,
            clipping=dict(rows=int((raw < 0).sum()), total_magnitude=float(magnitude.sum()),
                          maximum_magnitude=float(magnitude.max()) if len(raw) else 0.))
    return output


def _validate(prepared):
    basis = {k: v for k, v in prepared.items() if k not in {'prepared_sha256', 'provenance'}}
    if prepared.get('version') != WORKLOAD_VERSION or digest(basis) != prepared.get('prepared_sha256'):
        raise ValueError('Unsupported or changed raw-count prepared matrix')
    if prepared['preprocessing']['columns'] != list(PLAYER_COLUMNS) or prepared['target_columns'] != list(CHANNELS):
        raise ValueError('Raw-count ordered schema differs')
    if prepared.get('provenance', {}).get('label_contract', {}).get('version') != 'all_native_source_observed_weekly_counts_v1':
        raise ValueError('Missing source-observed label contract')
    width = 2 * len(PLAYER_COLUMNS)
    for part in prepared['splits'].values():
        if len(part['keys']) != len(part['labels']) or len(part['x']) != len(part['labels']):
            raise ValueError('Raw-count row alignment differs')
        x = np.asarray(part['x'], dtype=float)
        if len(x) and (x.shape != (len(part['keys']), width) or not np.isfinite(x).all()):
            raise ValueError('Invalid transformed input array')
        for labels in part['labels']:
            if set(labels) != set(CHANNELS) or any(v is not None and (isinstance(v, bool) or not np.isfinite(v) or v < 0) for v in labels.values()):
                raise ValueError('Invalid source-observed count label')
    if any(k['period'] >= prepared['train_before'] for k in prepared['splits']['train']['keys']):
        raise ValueError('Training scope crosses chronological boundary')


def fit_raw_player_family(prepared, *, family, minimum_target_rows=100):
    """Fixed squared-error recipes on train-only affine counts, stop on failure."""
    if family not in ('tree', 'neural'):
        raise ValueError('Unknown raw-count family')
    _validate(prepared)
    for target in CHANNELS:
        if sum(row[target] is not None for row in prepared['splits']['train']['labels']) < minimum_target_rows:
            raise ValueError(f'Insufficient known raw-count labels for {target}')
    started = datetime.now(UTC).isoformat()
    train = prepared['splits']['train']
    x = np.asarray(train['x'], dtype=float)
    receipt = dict(version=VERSION, recipe_id=RECIPE, family=family,
        neural_recipe_id=NEURAL_RECIPE if family == 'neural' else None,
        prepared_version=prepared['version'], prepared_sha256=prepared['prepared_sha256'],
        matrix_sha256=prepared['matrix_sha256'], preprocessing=deepcopy(prepared['preprocessing']),
        target_columns=list(CHANNELS), target_scalers={}, training_keys_by_target={},
        training_rows_by_target={}, convergence_by_target={}, head_optimization={}, metrics={},
        target_transform='Per-head TRAIN mean/std affine raw counts; constant scale 1; linear inverse then explicit max0',
        estimand='Squared-error arithmetic conditional count mean on source-observed scored cohort; no full-roster or calibration claim',
        training_max_period=prepared['training_max_period'], started_at=started,
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), status='fit_in_progress')
    bundle = dict(receipt=receipt, estimators={})
    for target in CHANNELS:
        indices = [i for i, labels in enumerate(train['labels']) if labels[target] is not None]
        if len(indices) < minimum_target_rows:
            raise ValueError(f'Insufficient known raw-count labels for {target}')
        y = np.asarray([train['labels'][i][target] for i in indices], dtype=float)
        center, scale = float(y.mean()), float(y.std())
        scale = scale if scale > 0 else 1.
        receipt['target_scalers'][target] = dict(center=center, scale=scale, known_training_rows=len(indices))
        receipt['training_keys_by_target'][target] = [deepcopy(train['keys'][i]) for i in indices]
        receipt['training_rows_by_target'][target] = len(indices)
        if family == 'tree':
            model = HistGradientBoostingRegressor(max_iter=80, learning_rate=.06, max_leaf_nodes=7,
                min_samples_leaf=15, l2_regularization=3, early_stopping=False, random_state=17)
        else:
            model = MLPRegressor(hidden_layer_sizes=(16,), solver='adam', alpha=10, max_iter=500,
                early_stopping=False, random_state=17, learning_rate_init=.001, n_iter_no_change=20, tol=1e-4)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always', ConvergenceWarning)
            model.fit(x[indices], (y - center) / scale)
        bundle['estimators'][target] = model
        converged = not any(issubclass(w.category, ConvergenceWarning) for w in caught)
        receipt['convergence_by_target'][target] = converged
        receipt['head_optimization'][target] = dict(params=model.get_params(),
            n_iter=int(model.n_iter_) if hasattr(model, 'n_iter_') else None,
            loss=float(model.loss_) if hasattr(model, 'loss_') else None,
            warnings=[str(w.message) for w in caught],
            stopping_basis='Fixed training criterion; not proof of calibrated accuracy')
        try:
            for part in prepared['splits'].values():
                if part['x']:
                    predict_arrays(dict(receipt=receipt, estimators={target: model}), part['x'])
        except ValueError as error:
            receipt.update(status='fit_invalid_prediction', stopped_after_target=target,
                           error_type=type(error).__name__, error=str(error))
            break
        if not converged:
            receipt['status'] = 'fit_not_converged'
            receipt['stopped_after_target'] = target
            break
    else:
        receipt['status'] = 'fit_complete'
    for split, part in prepared['splits'].items():
        if not part['x']:
            continue
        valid_models = {k: v for k, v in bundle['estimators'].items()
                        if not (receipt['status'] == 'fit_invalid_prediction' and k == receipt['stopped_after_target'])}
        predictions = predict_arrays(dict(receipt=receipt, estimators=valid_models), part['x'])
        receipt['metrics'][split] = {}
        for target, values in predictions.items():
            indices = [i for i, labels in enumerate(part['labels']) if labels[target] is not None]
            actual = [part['labels'][i][target] for i in indices]
            receipt['metrics'][split][target] = dict(
                raw=count_metrics(actual, values['raw'][indices]),
                supported=count_metrics(actual, values['supported'][indices]),
                clipping_all_rows=values['clipping'])
    receipt['completed_at'] = datetime.now(UTC).isoformat()
    return bundle


def predict_raw_player_model(bundle, rows, *, before_period):
    receipt = bundle['receipt']
    if receipt['version'] != VERSION or receipt['status'] != 'fit_complete' or receipt['training_max_period'] >= before_period:
        raise ValueError('Incomplete or future-trained raw-count model')
    if any(r['period'] != before_period or any(p >= before_period for p in r['history_periods'] + r.get('context_periods', [])) for r in rows):
        raise ValueError('Raw-count inference leaks target period')
    if len({r['player_master_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate raw-count inference actor')
    if not rows:
        return []
    predictions = predict_arrays(bundle, transform(rows, receipt['preprocessing']))
    return [dict(player_master_id=row['player_master_id'], team=row['team'], period=before_period,
        raw_counts={c: float(predictions[c]['raw'][i]) for c in CHANNELS},
        counts={c: float(predictions[c]['supported'][i]) for c in CHANNELS},
        support_projection='max0 only; no team budget rescaling',
        prepared_sha256=receipt['prepared_sha256']) for i, row in enumerate(rows)]
