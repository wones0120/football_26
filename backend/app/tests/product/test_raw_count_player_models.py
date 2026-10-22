from copy import deepcopy
import warnings

import numpy as np
import pytest
from sklearn.exceptions import ConvergenceWarning

from backend.app.product_services import raw_count_player_models as m


def prepared():
    columns = list(m.PLAYER_COLUMNS)
    keys = [dict(player_master_id=str(i), team='BUF', game_id=str(i), period=202301+i) for i in range(3)]
    train = dict(keys=keys, x=[[0.] * (2 * len(columns)) for _ in keys],
        labels=[dict(pass_attempts=v, rush_attempts=0, targets=None if i == 2 else i) for i, v in enumerate([0, 10, 20])])
    validation = deepcopy(train)
    for row in validation['labels']:
        row['pass_attempts'] = 999
    out = dict(version=m.WORKLOAD_VERSION, matrix_sha256='source',
        preprocessing=dict(columns=columns), target_columns=list(m.CHANNELS), train_before=202400,
        training_max_period=202303, splits=dict(train=train, validation=validation))
    out['prepared_sha256'] = m.digest(out)
    out['provenance'] = dict(label_contract=dict(version='all_native_source_observed_weekly_counts_v1'))
    return out


class Estimator:
    calls = []
    fail = False
    def __init__(self, **params):
        self.params = params
    def fit(self, x, y):
        self.y = y.copy()
        self.calls.append(self)
        if self.fail:
            warnings.warn('fixed failure', ConvergenceWarning)
        return self
    def predict(self, x):
        return np.full(len(x), -2.)
    def get_params(self):
        return self.params


@pytest.fixture(autouse=True)
def estimators(monkeypatch):
    Estimator.calls = []
    Estimator.fail = False
    monkeypatch.setattr(m, 'HistGradientBoostingRegressor', Estimator)
    monkeypatch.setattr(m, 'MLPRegressor', Estimator)


@pytest.mark.parametrize('family', ['tree', 'neural'])
def test_train_only_affine_raw_mean_known_zeros_and_constant(family):
    data = prepared()
    before = deepcopy(data)
    result = m.fit_raw_player_family(data, family=family, minimum_target_rows=1)
    r = result['receipt']
    assert data == before
    assert r['status'] == 'fit_complete'
    assert r['target_scalers']['pass_attempts']['center'] == 10
    assert r['target_scalers']['rush_attempts'] == dict(center=0., scale=1., known_training_rows=3)
    assert r['training_rows_by_target']['targets'] == 2
    assert Estimator.calls[0].y == pytest.approx(np.array([-10, 0, 10]) / np.std([0, 10, 20]))
    assert r['metrics']['validation']['pass_attempts']['raw']['bias'] < -999
    values = m.predict_arrays(result, data['splits']['train']['x'])
    assert values['pass_attempts']['raw'][0] == pytest.approx(10 - 2 * np.std([0, 10, 20]))
    assert values['pass_attempts']['supported'].tolist() == [0.] * 3
    assert values['pass_attempts']['clipping']['rows'] == 3
    assert r['metrics']['train']['pass_attempts']['raw'] != r['metrics']['train']['pass_attempts']['supported']
    params = Estimator.calls[0].params
    assert params['random_state'] == 17 and params['early_stopping'] is False
    if family == 'neural':
        assert params['solver'] == 'adam' and params['max_iter'] == 500
        assert r['neural_recipe_id'] == 'adam_optimizer_repair_v1'
    else:
        assert params['max_iter'] == 80 and params['max_leaf_nodes'] == 7


def test_failed_head_stops_without_later_fits_and_preserves_partial():
    Estimator.fail = True
    result = m.fit_raw_player_family(prepared(), family='neural', minimum_target_rows=1)
    assert result['receipt']['status'] == 'fit_not_converged'
    assert result['receipt']['stopped_after_target'] == 'pass_attempts'
    assert list(result['estimators']) == ['pass_attempts']
    assert len(Estimator.calls) == 1
    with pytest.raises(ValueError, match='Incomplete'):
        m.predict_raw_player_model(result, [], before_period=202501)


@pytest.mark.parametrize('change', ['hash', 'version', 'order', 'labels', 'alignment', 'future', 'infinite'])
def test_strict_prepared_contract(change):
    data = prepared()
    if change == 'hash':
        data['prepared_sha256'] = 'wrong'
    elif change == 'version':
        data['version'] = 'old'
    elif change == 'order':
        data['preprocessing']['columns'].reverse()
    elif change == 'labels':
        data['splits']['train']['labels'][0]['targets'] = True
    elif change == 'alignment':
        data['splits']['train']['keys'].pop()
    elif change == 'future':
        data['splits']['train']['keys'][0]['period'] = 202401
    else:
        data['splits']['train']['x'][0][0] = float('inf')
    if change not in {'hash', 'infinite'}:
        data['prepared_sha256'] = m.digest({k:v for k,v in data.items() if k not in {'prepared_sha256','provenance'}})
    with pytest.raises(ValueError):
        m.fit_raw_player_family(data, family='tree', minimum_target_rows=1)
    assert not Estimator.calls


def test_unknown_label_and_insufficient_rows_never_zero_filled():
    data = prepared()
    with pytest.raises(ValueError, match='Insufficient'):
        m.fit_raw_player_family(data, family='tree', minimum_target_rows=4)
    assert not Estimator.calls


def test_nonfinite_prediction_rejected():
    class Bad(Estimator):
        def predict(self, x):
            return np.full(len(x), np.nan)
    bundle = dict(receipt=dict(target_scalers=dict(targets=dict(center=0, scale=1))), estimators=dict(targets=Bad()))
    with pytest.raises(ValueError, match='Invalid raw'):
        m.predict_arrays(bundle, [[0]])


def test_later_insufficient_head_preflight_does_not_fit_first_head():
    with pytest.raises(ValueError, match='targets'):
        m.fit_raw_player_family(prepared(), family='tree', minimum_target_rows=3)
    assert not Estimator.calls


def test_nonfinite_first_head_stops_preserving_failed_partial(monkeypatch):
    class Bad(Estimator):
        def predict(self, x):
            return np.full(len(x), np.inf)
    monkeypatch.setattr(m, 'MLPRegressor', Bad)
    result = m.fit_raw_player_family(prepared(), family='neural', minimum_target_rows=1)
    assert len(Estimator.calls) == 1
    assert list(result['estimators']) == ['pass_attempts']
    r = result['receipt']
    assert r['status'] == 'fit_invalid_prediction'
    assert r['stopped_after_target'] == 'pass_attempts'
    assert r['error_type'] == 'ValueError' and r['completed_at']
    assert not r['metrics']['train']
    with pytest.raises(ValueError, match='Incomplete'):
        m.predict_raw_player_model(result, [], before_period=202501)
