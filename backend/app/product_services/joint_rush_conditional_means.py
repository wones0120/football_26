"""Offline joint source-observed rush means; no live consumer registration.

Candidate eligibility and complete labels are frozen upstream. Each candidate and
known outside rest has one jointly trained nonnegative mean. Their sum IS the
budget mean; no independent budget/share product or post-hoc rescaling is used.
"""
from copy import deepcopy
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

VERSION = 'joint_rush_conditional_means_v1'
RECIPE = dict(version='shared_tanh8_softplus_joint_raw_mse_v1', hidden_units=8,
              seed=17, optimizer='L-BFGS-B', maxiter=500, ftol=1e-9,
              gtol=1e-5, l2=0.001, cell_loss_weight=1.0,
              budget_loss_weight=1.0, retries=0)


def validate_groups(groups, columns):
    seen = set()
    for group in groups:
        key = group['game_id'], group['team']
        if key in seen:
            raise ValueError('Duplicate group')
        seen.add(key)
        if group['period']//100 not in (2023, 2024, 2025):
            raise ValueError('Frozen historical years only')
        cells = group['cells']
        if any(c['kind'] not in {'candidate', 'outside_rest'} for c in cells):
            raise ValueError('Only explicit candidates and known outside rest allowed')
        if len(cells) < 2 or sum(c['kind'] == 'outside_rest' for c in cells) != 1:
            raise ValueError('Candidates and exactly one known outside rest required')
        native = [c['source_player_id'] for c in cells if c['kind'] == 'candidate']
        canonical = [c['player_master_id'] for c in cells if c['kind'] == 'candidate']
        if None in native or None in canonical or len(set(native)) != len(native) or len(set(canonical)) != len(canonical):
            raise ValueError('Unique native/canonical candidates required')
        labels = np.asarray([c['label'] for c in cells], dtype=float)
        if not np.isfinite(labels).all() or (labels < 0).any() or not np.equal(labels, np.floor(labels)).all():
            raise ValueError('Known nonnegative integral observed labels required')
        if not np.isfinite(group['budget_label']) or sum(labels) != group['budget_label']:
            raise ValueError('Candidate plus disjoint rest must conserve observed budget')
        for c in cells:
            if list(c['features']) != list(columns):
                raise ValueError('Exact ordered prior-only feature schema required')
            if any(v is not None and (type(v) not in (int, float) or not np.isfinite(v)) for v in c['features'].values()):
                raise ValueError('Finite numeric or explicit unknown features required')
    if not groups:
        raise ValueError('Nonempty group cohort required')


def fit_preprocessing(groups, columns):
    """Only 2023 TRAIN cell inputs and TRAIN labels inform preprocessing."""
    validate_groups(groups, columns)
    train = [g for g in groups if g['period']//100 == 2023]
    if not train:
        raise ValueError('Training groups required')
    raw = np.asarray([[c['features'][k] if c['features'][k] is not None else np.nan
                       for k in columns] for g in train for c in g['cells']])
    all_missing = np.isnan(raw).all(axis=0)
    medians = np.asarray([0. if all_missing[j] else np.nanmedian(raw[:, j]) for j in range(raw.shape[1])])
    filled = np.where(np.isnan(raw), medians, raw)
    centers = filled.mean(axis=0)
    scales = filled.std(axis=0)
    scales[scales == 0] = 1.
    labels = np.asarray([c['label'] for g in train for c in g['cells']], dtype=float)
    budgets = np.asarray([g['budget_label'] for g in train], dtype=float)
    return dict(version=VERSION, columns=list(columns), medians=medians.tolist(),
                centers=centers.tolist(), scales=scales.tolist(),
                entirely_missing_train_columns=[columns[j] for j in np.flatnonzero(all_missing)],
                cell_label_scale=max(1., float(labels.std())),
                budget_label_scale=max(1., float(budgets.std())),
                target_transform='NONE; loss scales only, softplus outputs count units',
                train_year=2023)


def transform_groups(groups, prep):
    columns = prep['columns']
    validate_groups(groups, columns)
    raw = np.asarray([[c['features'][k] if c['features'][k] is not None else np.nan
                       for k in columns] for g in groups for c in g['cells']], dtype=float)
    # Frozen all-missing training columns stay UNKNOWN even if later observed.
    for k in prep['entirely_missing_train_columns']:
        raw[:, columns.index(k)] = np.nan
    missing = np.isnan(raw)
    filled = np.where(missing, np.asarray(prep['medians']), raw)
    X = np.concatenate(((filled-np.asarray(prep['centers']))/np.asarray(prep['scales']), missing.astype(float)), axis=1)
    offsets = np.cumsum([0]+[len(g['cells']) for g in groups]).tolist()
    return dict(X=X, offsets=offsets,
                labels=np.asarray([c['label'] for g in groups for c in g['cells']], dtype=float),
                budgets=np.asarray([g['budget_label'] for g in groups], dtype=float))


def _unpack(theta, n_features, hidden):
    a = n_features*hidden
    return theta[:a].reshape(n_features, hidden), theta[a:a+hidden], theta[a+hidden:a+2*hidden], theta[-1]


def initial_parameters(n_features, recipe=None):
    recipe = recipe or RECIPE
    rng = np.random.default_rng(recipe['seed'])
    h = recipe['hidden_units']
    return np.r_[rng.normal(0, 0.05, n_features*h), np.zeros(h), rng.normal(0, 0.05, h), -1.]


def forward(theta, X, hidden=8):
    W, b, v, a = _unpack(theta, X.shape[1], hidden)
    H = np.tanh(X@W+b)
    z = H@v+a
    return np.logaddexp(0, z), H, z


def objective(theta, data, prep, recipe=None):
    """Equal weight per group; cell and budget losses jointly optimize means."""
    recipe = recipe or RECIPE
    X, y, offsets = data['X'], data['labels'], data['offsets']
    mu, H, z = forward(theta, X, recipe['hidden_units'])
    n = len(data['budgets'])
    dmu = np.zeros_like(mu)
    loss = 0.
    cs, bs = prep['cell_label_scale']**2, prep['budget_label_scale']**2
    for j, (lo, hi) in enumerate(zip(offsets[:-1], offsets[1:])):
        diff = mu[lo:hi]-y[lo:hi]
        bd = mu[lo:hi].sum()-data['budgets'][j]
        loss += (recipe['cell_loss_weight']*np.mean(diff**2)/cs + recipe['budget_loss_weight']*bd**2/bs)/n
        dmu[lo:hi] = (2*recipe['cell_loss_weight']*diff/((hi-lo)*cs) + 2*recipe['budget_loss_weight']*bd/bs)/n
    W, b, v, a = _unpack(theta, X.shape[1], recipe['hidden_units'])
    dz = dmu*expit(z)
    dh = dz[:, None]*v*(1-H**2)
    grad = np.r_[(X.T@dh).ravel(), dh.sum(axis=0), H.T@dz, dz.sum()]
    # Fixed regularization, excluding biases; no test-selected coefficient.
    mask = np.r_[np.ones(W.size), np.zeros(b.size), np.ones(v.size), 0.]
    loss += recipe['l2']*np.sum((theta*mask)**2)/2
    grad += recipe['l2']*theta*mask
    if not np.isfinite(loss) or not np.isfinite(grad).all():
        raise FloatingPointError('Nonfinite joint objective; stop recipe')
    return float(loss), grad


def predict(model, groups):
    if model['status'] != 'completed':
        raise ValueError('Failed/unfitted recipe cannot infer')
    data = transform_groups(groups, model['preprocessing'])
    mu, _, _ = forward(np.asarray(model['parameters']), data['X'], model['recipe']['hidden_units'])
    if not np.isfinite(mu).all():
        raise FloatingPointError('Nonfinite prediction')
    return [dict(game_id=g['game_id'], team=g['team'],
                 cell_means=mu[lo:hi].tolist(), budget_mean=float(mu[lo:hi].sum()))
            for g, lo, hi in zip(groups, data['offsets'][:-1], data['offsets'][1:])]


def fit(groups, prep, *, optimizer=minimize):
    """Explicit root-dispatched fit only. Never called by prefit packaging."""
    recipe = deepcopy(RECIPE)
    train = [g for g in groups if g['period']//100 == 2023]
    # Preflight every split and labels before the only optimization call.
    for year in (2023, 2024, 2025):
        subset = [g for g in groups if g['period']//100 == year]
        if not subset:
            raise ValueError('Every fixed historical split must be nonempty')
        transform_groups(subset, prep)
    data = transform_groups(train, prep)
    last = initial_parameters(data['X'].shape[1])
    def checked_objective(theta):
        nonlocal last
        value = objective(theta, data, prep)
        last = np.array(theta, copy=True)
        return value
    try:
        result = optimizer(checked_objective, last.copy(), jac=True,
                           method=recipe['optimizer'], options={k: recipe[k] for k in ('maxiter', 'ftol', 'gtol')})
    except Exception as exc:
        return dict(version=VERSION, status='fit_failed', recipe=recipe,
                    preprocessing=deepcopy(prep), parameters=last.tolist(),
                    optimizer_success=False, optimizer_message=str(exc),
                    error_type=type(exc).__name__, retries=0)
    success = bool(result.success and np.isfinite(result.fun) and np.isfinite(result.x).all())
    model = dict(version=VERSION, status='completed' if success else 'fit_failed',
                 recipe=recipe, preprocessing=deepcopy(prep),
                 parameters=(np.asarray(result.x) if np.isfinite(result.x).all() else last).tolist(),
                 optimizer_success=bool(result.success), optimizer_message=str(result.message),
                 iterations=int(result.nit), objective=float(result.fun) if np.isfinite(result.fun) else None, retries=0)
    if success:
        try:
            predict(model, groups)
        except (ValueError, FloatingPointError):
            model['status'] = 'fit_failed'
            model['optimizer_message'] += '; nonfinite output; inference blocked'
    return model
