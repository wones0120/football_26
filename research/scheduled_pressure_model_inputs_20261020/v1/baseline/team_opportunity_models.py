"""Matched fixed tree/NN team-count families on one frozen ordered matrix.

Fitting is explicit, never an inference side effect. Point means are conditional
count budgets; no calibrated probability/interval or lineup success claim.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
from pathlib import Path
import warnings
from datetime import datetime, timezone
from io import BytesIO
import re

from ..services.source_capture import _write_new_bytes
from .factual_designation import clock

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.exceptions import ConvergenceWarning

from .team_opportunity_matrix import VERSION as MATRIX_VERSION, FEATURES
from .defense_context_evidence import _hash

VERSION='team_opportunity_models_v1'
FAMILIES=('tree','neural')


def _array(rows,columns):
    return np.asarray([[np.nan if r['features'][k] is None else r['features'][k] for k in columns] for r in rows],dtype=float)


def prepare_model_inputs(matrix, *, train_before, validation_before=None):
    """Freeze train-only preprocessing for the SAME tree/NN transformed rows."""
    check=deepcopy(matrix);supplied=check.pop('matrix_sha256',None);check.pop('provenance',None)
    if supplied!=_hash(check):raise ValueError('Team matrix checksum mismatch')
    if matrix['target_columns']!=['pass_attempts','rush_attempts'] or matrix['feature_columns']!=list(FEATURES):raise ValueError('Unsupported ordered count matrix')
    final_refit=validation_before is None
    if matrix['version']!=MATRIX_VERSION or (not 0<train_before<=matrix['before_period']) or (not final_refit and not train_before<validation_before<=matrix['before_period']):
        raise ValueError('Invalid chronological matrix boundaries')
    for row in matrix['rows']:
        labels=row.get('labels',{})
        if set(labels)!=set(matrix['target_columns']):raise ValueError('Complete official label keys required')
        if any(v is not None and (isinstance(v,(bool,np.bool_)) or not isinstance(v,(int,float,np.integer,np.floating)) or not np.isfinite(v) or v<0) for v in labels.values()):
            raise ValueError('Invalid official label in scoreable split')
        if any(p>=row['period'] for p in row.get('context_periods',[])+row.get('legacy_periods',[])):
            raise ValueError('Matrix contributing period leaks into target')
    ordered=matrix['feature_columns'];eligible=[r for r in matrix['rows'] if r['legacy_feature_ready'] and all(v is not None for v in r['labels'].values())]
    train=[r for r in eligible if r['period']<train_before]
    if not train:raise ValueError('No scoreable chronological training rows')
    x=_array(train,ordered)
    if np.isinf(x).any():raise ValueError('Infinite matrix feature')
    # An entirely absent train column gets a declared neutral preprocessing
    # constant plus a missingness mask, never a source-observed zero.
    medians=np.asarray([np.median(c[~np.isnan(c)]) if (~np.isnan(c)).any() else 0. for c in x.T])
    filled=np.where(np.isnan(x),medians,x);center=filled.mean(axis=0);scale=filled.std(axis=0);scale[scale==0]=1
    y=np.asarray([[r['labels'][k] for k in matrix['target_columns']] for r in train],dtype=float)
    if not np.isfinite(y).all() or (y<0).any():raise ValueError('Invalid official count labels')
    ycenter=y.mean(axis=0);yscale=y.std(axis=0);yscale[yscale==0]=1
    prep=dict(columns=ordered,medians=medians.tolist(),center=center.tolist(),scale=scale.tolist(),
        target_center=ycenter.tolist(),target_scale=yscale.tolist(),
        entirely_missing_train_columns=[k for k,c in zip(ordered,x.T) if np.isnan(c).all()],
        missingness='Train-median imputation plus explicit per-column missing indicators; preprocessing constants are not source facts')
    result=dict(version=VERSION,matrix_sha256=matrix['matrix_sha256'],target_columns=matrix['target_columns'],
        preprocessing=prep,train_before=train_before,validation_before=validation_before,final_refit=final_refit,
        training_max_period=max(r['period'] for r in train),splits={})
    for name,rows in [('train',train),('validation',[] if final_refit else [r for r in eligible if train_before<=r['period']<validation_before]),
                      ('retrospective_test',[] if final_refit else [r for r in eligible if validation_before<=r['period']<matrix['before_period']])]:
        result['splits'][name]=dict(keys=[dict(game_id=r['game_id'],team=r['team'],period=r['period']) for r in rows],
            x=transform_rows(rows,prep).tolist(),y=[[r['labels'][k] for k in matrix['target_columns']] for r in rows])
    result['prepared_sha256']=_hash(result)
    result['matrix_provenance']=deepcopy(matrix.get('provenance',{}))
    return result


def transform_rows(rows,preprocessing):
    p=preprocessing;raw=_array(rows,p['columns'])
    if not rows:return np.empty((0,len(p['columns'])*2))
    if np.isinf(raw).any():raise ValueError('Infinite inference feature')
    # No numerical response was learned for a never-observed training column.
    # Keep its value/mask at the fitted unknown state until an explicit refit.
    for field in p.get('entirely_missing_train_columns',[]):
        raw[:,p['columns'].index(field)]=np.nan
    missing=np.isnan(raw);filled=np.where(missing,p['medians'],raw)
    return np.concatenate(((filled-p['center'])/np.asarray(p['scale']),missing.astype(float)),axis=1)


def fit_team_family(prepared, *, family):
    """One explicit family fit call; orchestrator serializes all fit jobs."""
    started_at=datetime.now(timezone.utc).isoformat()
    if family not in FAMILIES:raise ValueError('Unknown count model family')
    basis=deepcopy(prepared);supplied=basis.pop('prepared_sha256',None);basis.pop('matrix_provenance',None)
    if supplied!=_hash(basis):raise ValueError('Prepared matrix checksum mismatch')
    train=prepared['splits']['train'];x=np.asarray(train['x']);y=np.asarray(train['y'],dtype=float)
    if len(x)<100:raise ValueError('Team model requires100 complete chronological training examples')
    p=prepared['preprocessing'];z=(y-p['target_center'])/np.asarray(p['target_scale'])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always',ConvergenceWarning)
        if family=='tree':
            estimators=[HistGradientBoostingRegressor(max_iter=100,learning_rate=.06,max_leaf_nodes=7,min_samples_leaf=15,l2_regularization=3,early_stopping=False,random_state=17).fit(x,z[:,i]) for i in range(z.shape[1])]
        else:
            estimators=MLPRegressor(hidden_layer_sizes=(16,),activation='relu',solver='lbfgs',alpha=10,max_iter=500,early_stopping=False,random_state=17).fit(x,z)
    converged=not any(issubclass(w.category,ConvergenceWarning) for w in caught)
    receipt=dict(version=VERSION,family=family,status='fit_complete' if converged else 'fit_not_converged',
        matrix_sha256=prepared['matrix_sha256'],prepared_sha256=prepared['prepared_sha256'],preprocessing=deepcopy(p),
        target_columns=prepared['target_columns'],feature_columns=list(p['columns']),source_provenance=deepcopy(prepared.get('matrix_provenance',{})),training_rows=len(x),training_max_period=prepared['training_max_period'],
        trained_started_at=started_at,trained_completed_at=datetime.now(timezone.utc).isoformat(),
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        quality='Revised-history point-count model; no calibrated probability/interval or tournament superiority',
        metrics={})
    bundle=dict(receipt=receipt,estimators=estimators)
    for split,part in prepared['splits'].items():
        if not part['x']:continue
        prediction=_predict(bundle,np.asarray(part['x']));actual=np.asarray(part['y'])
        receipt['metrics'][split]=dict(rows=len(actual),mae_by_target=dict(zip(receipt['target_columns'],np.mean(abs(prediction-actual),axis=0).tolist())),
            bias_by_target=dict(zip(receipt['target_columns'],np.mean(prediction-actual,axis=0).tolist())))
    return bundle


def _predict(bundle,x):
    r=bundle['receipt'];models=bundle['estimators']
    z=np.column_stack([m.predict(x) for m in models]) if r['family']=='tree' else models.predict(x)
    values=np.asarray(z)*r['preprocessing']['target_scale']+r['preprocessing']['target_center']
    if not np.isfinite(values).all():raise ValueError('Nonfinite count model prediction')
    return np.maximum(0,values)


def predict_team_family(bundle, rows, *, before_period):
    receipt=bundle['receipt']
    if receipt['status']!='fit_complete' or receipt['training_max_period']>=before_period:
        raise ValueError('Unusable or future-trained count model')
    if any(p>=before_period for r in rows for p in r.get('context_periods',[])+r.get('legacy_periods',[])):
        raise ValueError('Inference contributing period leaks into decision')
    if any(r['period']!=before_period or not r['legacy_feature_ready'] for r in rows):
        raise ValueError('Inference row scope or legacy history incomplete')
    values=_predict(bundle,transform_rows(rows,receipt['preprocessing']))
    return [dict(game_id=r['game_id'],team=r['team'],period=r['period'],family=receipt['family'],
        counts=dict(zip(receipt['target_columns'],v.tolist())),matrix_sha256=receipt['matrix_sha256'],
        prepared_sha256=receipt['prepared_sha256'],uncertainty='unavailable; conditional point budgets only') for r,v in zip(rows,values)]


def predict_team_families(tree_bundle, neural_bundle, rows, *, before_period):
    """Declared arithmetic mean of SAME targets; preserve both components."""
    a=tree_bundle['receipt'];b=neural_bundle['receipt']
    if (a['family'],b['family'])!=('tree','neural') or any(a[k]!=b[k] for k in ('matrix_sha256','prepared_sha256','target_columns','preprocessing')):
        raise ValueError('Count families do not share the same frozen prepared matrix')
    tree=predict_team_family(tree_bundle,rows,before_period=before_period)
    neural=predict_team_family(neural_bundle,rows,before_period=before_period)
    return [dict(game_id=t['game_id'],team=t['team'],period=before_period,
        counts={k:(t['counts'][k]+n['counts'][k])/2 for k in a['target_columns']},
        components=dict(tree=t['counts'],neural=n['counts']),
        disagreement={k:abs(t['counts'][k]-n['counts'][k]) for k in a['target_columns']},
        pooling='fixed arithmetic mean of same official count targets; not additive votes or FP bonus',
        matrix_sha256=a['matrix_sha256'],prepared_sha256=a['prepared_sha256'],
        uncertainty='unavailable; model disagreement is not a calibrated interval') for t,n in zip(tree,neural)]


MODEL_DIRECTORY=Path(__file__).resolve().parents[3]/'artifacts/opportunity_models'


def _model_metadata(bundle):
    r=bundle['receipt']
    return dict(version=r['version'],family=r['family'],matrix_sha256=r['matrix_sha256'],prepared_sha256=r['prepared_sha256'],
        code_sha256=r['code_sha256'],training_max_period=r['training_max_period'],receipt_sha256=_hash(r))


def freeze_team_family(bundle, *, directory=None, producer_clock=None):
    """Publish server-produced models only; callers cannot provide model bytes."""
    import joblib
    if bundle['receipt']['status']!='fit_complete' or bundle['receipt']['version']!=VERSION:
        raise ValueError('Only completed supported model fits can publish')
    published=clock(producer_clock() if producer_clock else datetime.now(timezone.utc))
    if bundle['receipt'].get('trained_completed_at') and clock(bundle['receipt']['trained_completed_at'])>published:
        raise ValueError('Publication before actual model completion')
    value=dict(bundle=bundle,published_at=published.isoformat(),contract='team_opportunity_model_artifact_v1')
    stream=BytesIO();joblib.dump(value,stream,compress=3);payload=stream.getvalue();sha=hashlib.sha256(payload).hexdigest()
    root=Path(directory or MODEL_DIRECTORY).resolve();root.mkdir(parents=True,exist_ok=True);path=root/(sha+'.joblib')
    _write_new_bytes(path,payload)
    return dict(contract=value['contract'],path=str(path),sha256=sha,bytes=len(payload),published_at=value['published_at'],**_model_metadata(bundle))


def load_team_family(ref, *, before_period, cutoff, directory=None,max_bytes=32*1024*1024):
    """Trusted server ledger ref only. Hash/metadata checks precede/after loading.

    Joblib is executable serialization: never route caller-supplied bytes, paths
    or unregistered references here. The root is server configured or test-owned.
    """
    import joblib
    sha=ref.get('sha256','')
    if not re.fullmatch(r'[0-9a-f]{64}',sha):raise ValueError('Invalid managed model SHA')
    root=Path(directory or MODEL_DIRECTORY).resolve();path=root/(sha+'.joblib')
    if Path(ref['path']).resolve()!=path or path.resolve().parent!=root:raise ValueError('Model path is outside managed root')
    if path.stat().st_size>max_bytes or path.stat().st_size!=ref['bytes']:raise ValueError('Model byte bound/size mismatch')
    payload=path.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=sha:raise ValueError('Managed model byte hash mismatch')
    value=joblib.load(BytesIO(payload))
    if value.get('contract')!='team_opportunity_model_artifact_v1' or ref.get('contract')!=value['contract']:
        raise ValueError('Unsupported managed model contract')
    bundle=value['bundle']
    if bundle['receipt']['status']!='fit_complete' or bundle['receipt']['version']!=VERSION:raise ValueError('Unusable managed model')
    for k,v in _model_metadata(bundle).items():
        if ref.get(k)!=v:raise ValueError('Managed model metadata mismatch')
    if value['published_at']!=ref['published_at'] or clock(value['published_at'])>clock(cutoff):raise ValueError('Model publication unavailable at decision')
    if bundle['receipt']['training_max_period']>=before_period:raise ValueError('Model trained on forecast/future period')
    return bundle
