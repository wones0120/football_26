"""Matched tree/neural player-count contracts on the same prior-only matrix.

Explicit fits only; serving never trains. Independent count targets retain their
own known-label cohorts, including measured zeros. No FP/P90/ownership inputs.
"""
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import warnings
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.exceptions import ConvergenceWarning

from .offensive_volume_features import VERSION as MATRIX_VERSION, ACTIVE_VERSION as ACTIVE_MATRIX_VERSION, FEATURES, digest
from .team_opportunity_matrix import FEATURES as TEAM_FEATURES
from .opportunity_history_evidence import CHANNELS

VERSION='player_opportunity_models_v1'
ACTIVE_VERSION='player_opportunity_models_active_games_v2'
RB_RUSH_MEAN_VERSION='player_opportunity_models_rb_rush_mean_v3'
SPARSE_WR_VERSION='player_opportunity_models_sparse_wr_return_v4'
ACTIVE_MODEL_VERSIONS={ACTIVE_VERSION,RB_RUSH_MEAN_VERSION,SPARSE_WR_VERSION}
PRESSURE_VERSION='player_opportunity_models_pressure3_v1'
COVERAGE_VERSION='player_opportunity_models_pressure_coverage3_v1'
WORKLOAD_VERSION='player_opportunity_models_workload_efficiency_v1'
from .scheduled_workload_efficiency_model_inputs import PLAYER_VERSION as WORKLOAD_MATRIX_VERSION,PLAYER_COLUMNS as WORKLOAD_COLUMNS
from .scheduled_coverage_model_inputs import PLAYER_VERSION as COVERAGE_MATRIX_VERSION,PLAYER_COLUMNS as COVERAGE_COLUMNS
from .scheduled_pressure_model_inputs import PLAYER_VERSION as PRESSURE_MATRIX_VERSION,PLAYER_COLUMNS as PRESSURE_COLUMNS
FAMILIES=('tree','neural')


def _matrix_values(rows,columns):
    return np.asarray([[np.nan if r['features'][k] is None else r['features'][k] for k in columns] for r in rows],dtype=float)


def transform(rows,preprocessing):
    if not rows:return np.empty((0,len(preprocessing['columns'])*2))
    columns=preprocessing['columns']
    if any(set(r['features'])!=set(columns) for r in rows):raise ValueError('Player inference feature order differs')
    values=_matrix_values(rows,columns)
    if np.isinf(values).any():raise ValueError('Infinite player model input')
    # A field never observed in training has no learned numerical response.
    # Preserve its raw measurement in the matrix, but keep its fitted channel
    # and mask at the training unknown state until an explicit new fit.
    for field in preprocessing.get('entirely_missing_train_columns',[]):
        values[:,columns.index(field)]=np.nan
    mask=np.isnan(values);filled=np.where(mask,preprocessing['medians'],values)
    return np.concatenate(((filled-preprocessing['center'])/np.asarray(preprocessing['scale']),mask.astype(float)),axis=1)


def prepare_player_inputs(matrix, *, train_before, validation_before, minimum_history_games=3):
    material={k:v for k,v in matrix.items() if k not in {'matrix_sha256','provenance'}}
    if digest(material)!=matrix.get('matrix_sha256') or matrix.get('version') not in (MATRIX_VERSION,ACTIVE_MATRIX_VERSION,PRESSURE_MATRIX_VERSION,COVERAGE_MATRIX_VERSION,WORKLOAD_MATRIX_VERSION):
        raise ValueError('Unsupported or changed player matrix')
    if matrix['target_columns']!=list(CHANNELS) or not 0<train_before<validation_before<=matrix['before_period']:
        raise ValueError('Invalid player target/split contract')
    rows=matrix['rows'];columns=matrix['feature_columns'];seen=set()
    workload=matrix.get('version')==WORKLOAD_MATRIX_VERSION
    coverage=workload or matrix.get('version')==COVERAGE_MATRIX_VERSION
    pressure=coverage or matrix.get('version')==PRESSURE_MATRIX_VERSION
    if workload and (matrix.get('weekly_workload_adapter',{}).get('version')!='scheduled_workload_efficiency_model_inputs_v1'or matrix.get('label_contract',{}).get('version')!='all_native_source_observed_weekly_counts_v1'):raise ValueError('Missing workload/source-label contract')
    if coverage and matrix.get('coverage_adapter',{}).get('version')!='scheduled_coverage_model_inputs_v1':raise ValueError('Missing coverage adapter contract')
    if pressure and matrix.get('pressure_adapter',{}).get('version')!='scheduled_pressure_model_inputs_v1':raise ValueError('Missing pressure adapter contract')
    accepted=[list(WORKLOAD_COLUMNS)]if workload else [list(COVERAGE_COLUMNS)] if coverage else [list(PRESSURE_COLUMNS)] if pressure else [list(FEATURES),[*FEATURES,*(f'team_{k}' for k in TEAM_FEATURES)]]
    if columns not in accepted:
        raise ValueError('Unsupported player feature columns; no FP/label objective inputs')
    eligible=[];excluded=[]
    for r in rows:
        key=(r['player_master_id'],r['period'])
        if key in seen:raise ValueError('Duplicate player-game model row')
        seen.add(key)
        if set(r['features'])!=set(columns):raise ValueError('Player feature order differs')
        if any(p>=r['period'] for p in r['history_periods']+r.get('context_periods',[])):
            raise ValueError('Player input leaks target period')
        labels=r['labels']
        if set(labels)!=set(CHANNELS) or any(v is not None and (isinstance(v,bool) or not np.isfinite(v) or v<0) for v in labels.values()):
            raise ValueError('Invalid official player count labels')
        history=max(r['features'][f'{c}_known3'] for c in CHANNELS)
        if r['period']<matrix['before_period'] and history>=minimum_history_games:eligible.append(r)
        else:excluded.append(dict(player_master_id=r['player_master_id'],period=r['period'],reason='forward_row' if r['current_inference'] else 'insufficient_prior_source_games'))
    training=[r for r in eligible if r['period']<train_before]
    if not training:raise ValueError('No chronological player training rows')
    x=_matrix_values(training,columns)
    if np.isinf(x).any():raise ValueError('Infinite training feature')
    medians=np.array([np.median(c[~np.isnan(c)]) if (~np.isnan(c)).any() else 0. for c in x.T])
    filled=np.where(np.isnan(x),medians,x);center=filled.mean(axis=0);scale=filled.std(axis=0);scale[scale==0]=1.
    prep=dict(columns=columns,medians=medians.tolist(),center=center.tolist(),scale=scale.tolist(),
        entirely_missing_train_columns=[k for k,c in zip(columns,x.T) if np.isnan(c).all()],
        meaning='Training-median numerical preprocessing plus missingness masks, not observed zero; no target imputation')
    splits={}
    for split,subset in [('train',training),('validation',[r for r in eligible if train_before<=r['period']<validation_before]),
                         ('retrospective_test',[r for r in eligible if validation_before<=r['period']<min((validation_before//100+1)*100+1,matrix['before_period'])]),
                         ('inspected_later_diagnostic',[r for r in eligible if (validation_before//100+1)*100+1<=r['period']<matrix['before_period']])]:
        splits[split]=dict(keys=[{k:r[k] for k in ('player_master_id','game_id','team','position','period')} for r in subset],
            x=transform(subset,prep).tolist(),labels=[r['labels'] for r in subset])
    result=dict(version=ACTIVE_VERSION if matrix['version']==ACTIVE_MATRIX_VERSION else WORKLOAD_VERSION if workload else COVERAGE_VERSION if coverage else PRESSURE_VERSION if pressure else VERSION,matrix_sha256=matrix['matrix_sha256'],preprocessing=prep,target_columns=list(CHANNELS),
        train_before=train_before,validation_before=validation_before,minimum_history_games=minimum_history_games,
        training_max_period=max(r['period'] for r in training),splits=splits,excluded=excluded,
        cohort='All canonical official weekly actors after fixed prior-history warmup; missing target labels omitted per head, known zeros retained',
        matrix_usage=matrix['usage'])
    result['prepared_sha256']=digest(result);result['provenance']=deepcopy(matrix['provenance'])
    if pressure:result['provenance']['pressure_adapter']=deepcopy(matrix['pressure_adapter'])
    if coverage:result['provenance']['coverage_adapter']=deepcopy(matrix['coverage_adapter'])
    if workload:result['provenance'].update(weekly_workload_adapter=deepcopy(matrix['weekly_workload_adapter']),label_contract=deepcopy(matrix['label_contract']))
    return result


def fit_player_family(prepared, *, family, minimum_target_rows=100, neural_recipe="lbfgs_v1"):
    """One bounded explicit family fit, three sequential known-label heads."""
    if family not in FAMILIES:raise ValueError('Unknown player count family')
    if neural_recipe not in {'lbfgs_v1','adam_optimizer_repair_v1'} or (family=='tree' and neural_recipe!='lbfgs_v1'):raise ValueError('Unsupported explicit neural recipe')
    basis={k:v for k,v in prepared.items() if k not in {'prepared_sha256','provenance'}}
    if digest(basis)!=prepared.get('prepared_sha256'):raise ValueError('Player prepared matrix checksum mismatch')
    started=datetime.now(UTC).isoformat();train=prepared['splits']['train'];x=np.asarray(train['x']);models={};cohorts={};convergence={};head_optimization={}
    for target in CHANNELS:
        indices=[i for i,r in enumerate(train['labels']) if r[target] is not None]
        if len(indices)<minimum_target_rows:raise ValueError(f'Insufficient known player labels for {target}')
        y=np.log1p(np.asarray([train['labels'][i][target] for i in indices],dtype=float))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always',ConvergenceWarning)
            if family=='tree':model=HistGradientBoostingRegressor(max_iter=80,learning_rate=.06,max_leaf_nodes=7,min_samples_leaf=15,l2_regularization=3,early_stopping=False,random_state=17)
            elif neural_recipe=='lbfgs_v1':model=MLPRegressor(hidden_layer_sizes=(16,),solver='lbfgs',alpha=10,max_iter=500,early_stopping=False,random_state=17)
            else:model=MLPRegressor(hidden_layer_sizes=(16,),solver='adam',alpha=10,max_iter=500,early_stopping=False,random_state=17,learning_rate_init=.001,n_iter_no_change=20,tol=1e-4)
            model.fit(x[indices],y)
        models[target]=model;cohorts[target]=[train['keys'][i] for i in indices]
        convergence[target]=not any(issubclass(w.category,ConvergenceWarning) for w in caught)
        head_optimization[target]=dict(params=model.get_params() if hasattr(model,'get_params') else {},n_iter=int(model.n_iter_) if hasattr(model,'n_iter_') else None,loss=float(model.loss_) if hasattr(model,'loss_') else None,warnings=[str(w.message) for w in caught],stopping_basis='Training loss plateau; not gradient optimum or calibrated accuracy' if neural_recipe=='adam_optimizer_repair_v1' else 'Estimator convergence criterion')
    receipt=dict(version=prepared['version'],family=family,neural_recipe_id=neural_recipe if family=='neural' else None,head_optimization=head_optimization,status='fit_complete' if all(convergence.values()) else 'fit_not_converged',
        convergence_by_target=convergence,matrix_sha256=prepared['matrix_sha256'],prepared_sha256=prepared['prepared_sha256'],
        preprocessing=deepcopy(prepared['preprocessing']),target_columns=list(CHANNELS),training_max_period=prepared['training_max_period'],
        training_rows_by_target={k:len(v) for k,v in cohorts.items()},training_keys_by_target=cohorts,
        target_transform='log1p official counts; inverse expm1 followed by explicit nonnegative physical support projection',
        estimand='Transformed-scale conditional point approximation, not an unbiased arithmetic expected-count estimate',
        unsupported_numeric_fields=prepared['preprocessing']['entirely_missing_train_columns'],
        started_at=started,completed_at=datetime.now(UTC).isoformat(),code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        metrics={},quality='Conditional point counts on recorded weekly-actor cohort; revised historical availability, missing participants and intervals unproven')
    bundle=dict(receipt=receipt,estimators=models)
    for split,part in prepared['splits'].items():
        if not part['x']:continue
        predicted=_predict(bundle,np.asarray(part['x']));metrics={}
        for k in CHANNELS:
            ids=[i for i,r in enumerate(part['labels']) if r[k] is not None]
            if ids:
                actual=np.asarray([part['labels'][i][k] for i in ids]);p=predicted[k][ids]
                metrics[k]=dict(rows=len(ids),mae=float(np.mean(abs(p-actual))),bias=float(np.mean(p-actual)),rmse=float(np.sqrt(np.mean((p-actual)**2))))
        receipt['metrics'][split]=metrics
    return bundle


def _predict(bundle,x,*,positions=None):
    result={}
    for k in CHANNELS:
        z=np.asarray(bundle['estimators'][k].predict(x),dtype=float)
        if not np.isfinite(z).all() or (z>50).any():raise ValueError('Invalid player count log prediction')
        result[k]=np.maximum(0,np.expm1(z))
    if 'rb_rush_attempts' in bundle['estimators']:
        if positions is None or len(positions)!=len(x):raise ValueError('RB rush mean head requires explicit canonical positions')
        scaler=bundle['receipt']['rb_rush_mean_head']['target_scaler']
        if not np.isfinite([scaler['center'],scaler['scale']]).all() or scaler['scale']<=0:raise ValueError('Invalid RB rush target scaler')
        indices=[i for i,p in enumerate(positions) if p=='RB']
        if indices:
            raw=np.asarray(bundle['estimators']['rb_rush_attempts'].predict(x[indices]),dtype=float)*scaler['scale']+scaler['center']
            if not np.isfinite(raw).all():raise ValueError('Invalid RB rush mean prediction')
            result['rush_attempts'][indices]=np.maximum(0,raw)
    if bundle['receipt'].get('sparse_wr_count_heads'):
        if positions is None or len(positions)!=len(x):raise ValueError('Sparse WR heads require explicit canonical positions')
        prep=bundle['receipt']['preprocessing'];cols=prep['columns']
        known=np.asarray([x[:,cols.index(f'{c}_known3')]*prep['scale'][cols.index(f'{c}_known3')]+prep['center'][cols.index(f'{c}_known3')] for c in CHANNELS]).T
        indices=[i for i,p in enumerate(positions) if p=='WR' and np.isclose(known[i],2).all()]
        for channel,spec in bundle['receipt']['sparse_wr_count_heads']['heads'].items():
            scaler=spec['target_scaler']
            if not np.isfinite([scaler['center'],scaler['scale']]).all() or scaler['scale']<=0:raise ValueError('Invalid sparse WR target scaler')
            if indices:
                raw=np.asarray(bundle['estimators']['sparse_wr_'+channel].predict(x[indices]),dtype=float)*scaler['scale']+scaler['center']
                if not np.isfinite(raw).all():raise ValueError('Invalid sparse WR count prediction')
                result[channel][indices]=np.maximum(0,raw)
    return result


def predict_player_families(tree,neural,rows,*,before_period):
    a,b=tree['receipt'],neural['receipt']
    if (a['family'],b['family'])!=FAMILIES or any(a[k]!=b[k] for k in ('version','matrix_sha256','prepared_sha256','preprocessing','target_columns')):
        raise ValueError('Player families must share exactly the same feature and target contract')
    if a.get('rb_rush_mean_head')!=b.get('rb_rush_mean_head'):raise ValueError('Player family RB rush contracts differ')
    if a.get('sparse_wr_count_heads')!=b.get('sparse_wr_count_heads'):raise ValueError('Player family sparse WR contracts differ')
    if any(r['status']!='fit_complete' or r['training_max_period']>=before_period for r in (a,b)):
        raise ValueError('Incomplete or future-trained player model')
    if any(r['period']!=before_period or any(p>=before_period for p in r['history_periods']+r.get('context_periods',[])) for r in rows):
        raise ValueError('Player inference scope/history leaks')
    if len({r['player_master_id'] for r in rows})!=len(rows):raise ValueError('Duplicate player inference identity')
    if not rows:return []
    x=transform(rows,a['preprocessing']);positions=[r['position'] for r in rows]
    t=_predict(tree,x,positions=positions);n=_predict(neural,x,positions=positions)
    return [dict(player_master_id=r['player_master_id'],team=r['team'],period=before_period,
        history_supported=max(r['features'][f'{c}_known3'] for c in CHANNELS)>=3 or bool(r['position']=='WR' and a.get('sparse_wr_count_heads') and all(r['features'][f'{c}_known3']==2 for c in CHANNELS)),
        counts={k:float((t[k][i]+n[k][i])/2) for k in CHANNELS},
        components={f:{k:float(v[k][i]) for k in CHANNELS} for f,v in [('tree',t),('neural',n)]},
        disagreement={k:float(abs(t[k][i]-n[k][i])) for k in CHANNELS},
        pooling='Fixed equal arithmetic mean of SAME count estimands; no FP/count vote or calibrated probability',
        estimand='Sparse WR two-observation rush/target heads fit raw-count MSE; conditional role persistence and calibration unproven' if r['position']=='WR' and a.get('sparse_wr_count_heads') and all(r['features'][f'{c}_known3']==2 for c in CHANNELS) else 'RB rush uses raw-count conditional mean heads; other channels retain transformed-scale point approximations; arithmetic expected-count calibration unproven' if r['position']=='RB' and 'rb_rush_mean_head' in a else 'Transformed-scale conditional point approximation; arithmetic expected-count calibration unproven',
        unsupported_numeric_fields=a['preprocessing']['entirely_missing_train_columns'],
        inference_features_sha256=digest(r['features']),model_matrix_sha256=a['matrix_sha256'],prepared_sha256=a['prepared_sha256'])
        for i,r in enumerate(rows)]


def apply_player_count_predictions(receipt,predictions):
    """Actual numerical count consumer, before preferences; downward-only budgets.

    Current role/missing-history gates stay authoritative: an unknown reference
    channel does not become known merely because a regressor can emit a value.
    """
    out=deepcopy(receipt);by_id={r['player_master_id']:r for r in predictions}
    original_known={(t,c):sum(a['counts'][c] for a in receipt['players'] if a['team']==t and a['counts'][c] is not None) for t in receipt['teams'] for c in CHANNELS}
    if len(by_id)!=len(predictions):raise ValueError('Duplicate player count predictions')
    known={r['player_master_id'] for r in out['players']}
    if set(by_id)-known:raise ValueError('Prediction actor outside full count source universe')
    for actor in out['players']:
        p=by_id.get(actor['player_master_id'])
        if p is None:continue
        if p['period']!=out['before_period'] or p['team']!=actor['team']:raise ValueError('Player count forecast scope differs')
        actor['player_model_components']=deepcopy(p)
        # Nonparticipation was established upstream from scoped factual proof.
        # Missing history cannot undo that current condition or create workload.
        if actor.get('world_activity') is False:
            if any(isinstance(p['counts'][c],bool) or not np.isfinite(p['counts'][c]) or p['counts'][c]<0 for c in CHANNELS):
                raise ValueError('Invalid physical player prediction')
            actor['counts']=dict.fromkeys(CHANNELS,0.)
            actor['player_model_application']='not_applied_factual_nonparticipation'
            continue
        if p.get('history_supported') is False:
            actor['counts']=dict.fromkeys(CHANNELS)
            actor.setdefault('reasons',[]).append('Registered count heads do not support this sparse same-team observation cohort')
            continue
        for channel in CHANNELS:
            value=p['counts'][channel]
            if isinstance(value,bool) or not np.isfinite(value) or value<0:raise ValueError('Invalid physical player prediction')
            if actor.get('world_activity') is False:actor['counts'][channel]=0.
            elif actor['counts'][channel] is not None:actor['counts'][channel]=float(value)
    for team,budget in out['teams'].items():
        if budget is None:continue
        if budget.get('targets') is not None and (budget.get('pass_attempts') is None or budget['targets']>budget['pass_attempts']):
            raise ValueError('Team target budget exceeds physical passing attempts')
        budget.setdefault('reconciliation',{})
        for channel in CHANNELS:
            members=[a for a in out['players'] if a['team']==team and a['counts'][channel] is not None]
            total=sum(a['counts'][channel] for a in members);available=budget[channel]
            if available is not None and (not np.isfinite(available) or available<0):raise ValueError('Invalid full-team count budget')
            if available is None and total>0:raise ValueError('Known player forecast lacks physical team budget')
            applicable=lambda a: a.get('position')=='QB' if channel=='pass_attempts' else a.get('position') in ({'QB','RB','WR','TE'} if channel=='rush_attempts' else {'RB','WR','TE'})
            has_unknown=any(a['team']==team and applicable(a) and a['counts'][channel] is None for a in out['players'])
            # Do not donate the reference producer's unallocated forecast to
            # known actors merely because another actor cannot be modeled.
            reserved=max(0.,available-original_known[team,channel]) if has_unknown and available is not None else 0.
            envelope=available-reserved if available is not None else None
            factor=min(1.,envelope/total) if envelope is not None and total>0 else 1.
            for a in members:
                a.setdefault('unreconciled_player_model_counts',{})[channel]=a['counts'][channel]
                a['counts'][channel]*=factor
            budget['reconciliation'][channel]=dict(raw_sum=total,downward_factor=factor,reserved_reference_unallocated=reserved,
                reservation_meaning='Conditional reference residual retained for applicable unknown actors; not observed volume',
                unallocated=available-total*factor if available is not None else None,
                unknown_actors=sum(a['counts'][channel] is None for a in out['players'] if a['team']==team))
    from .workload_count_forecast import utility
    if out.get('scales'):
        for actor in out['players']:actor['utility']=utility(actor,out['scales'])
    out.pop('sha256',None)
    out['player_model_consumption']=dict(version=VERSION,actors=len(predictions),
        numerical_basis='Known role-supported channels replaced once; full-source downward reconciliation; unknowns/residual retained',
        prediction_semantic_sha256=digest(predictions))
    return out


def repair_neural_convergence(original,prepared,*,additional_max_iter=1500):
    """One explicit warm restart, never an automatic serving retry.

    Fitted weights survive; L-BFGS optimizer history restarts. Original model
    bytes and normal family defaults are untouched. Budget is versioned here.
    """
    basis={k:v for k,v in prepared.items() if k not in {'prepared_sha256','provenance'}}
    if digest(basis)!=prepared.get('prepared_sha256'):raise ValueError('Repair prepared checksum mismatch')
    prior=original['receipt']
    if additional_max_iter!=1500 or prior['family']!='neural' or prior['status']!='fit_not_converged' or prior.get('repair'):
        raise ValueError('Unsupported or repeated convergence repair')
    if any(prior[k]!=prepared[k] for k in ('matrix_sha256','prepared_sha256','preprocessing','training_max_period')):
        raise ValueError('Repair matrix or preprocessing differs')
    train=prepared['splits']['train'];x=np.asarray(train['x']);bundle=deepcopy(original);receipt=bundle['receipt'];details={}
    for target in CHANNELS:
        ids=[i for i,r in enumerate(train['labels']) if r[target] is not None]
        if [train['keys'][i] for i in ids]!=prior['training_keys_by_target'][target]:raise ValueError('Repair known-label cohort differs')
        model=bundle['estimators'][target]
        if not hasattr(model,'coefs_') or model.max_iter!=500 or model.solver!='lbfgs':raise ValueError('Repair requires original fitted500-step weights')
        initial=float(model.loss_);initial_iterations=int(model.n_iter_)
        model.set_params(warm_start=True,max_iter=additional_max_iter)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always',ConvergenceWarning)
            model.fit(x[ids],np.log1p([train['labels'][i][target] for i in ids]))
        converged=not any(issubclass(w.category,ConvergenceWarning) for w in caught)
        details[target]=dict(initial_loss=initial,final_loss=float(model.loss_),original_iterations=initial_iterations,
            restart_iterations=int(model.n_iter_),converged=converged,warnings=[str(w.message) for w in caught],
            params=model.get_params())
    receipt.update(status='fit_complete' if all(v['converged'] for v in details.values()) else 'fit_not_converged',
        convergence_by_target={k:v['converged'] for k,v in details.items()},completed_at=datetime.now(UTC).isoformat(),
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),metrics={},
        repair=dict(version='neural_warm_restart_1500_v1',parent_receipt_sha256=digest(prior),
            mechanism='Deep copied original fitted weights; L-BFGS optimizer history restarted, not exact solver continuation',
            additional_max_iter=additional_max_iter,heads=details))
    for split,part in prepared['splits'].items():
        if not part['x']:continue
        predicted=_predict(bundle,np.asarray(part['x']));metrics={}
        for target in CHANNELS:
            ids=[i for i,r in enumerate(part['labels']) if r[target] is not None]
            if ids:
                actual=np.asarray([part['labels'][i][target] for i in ids]);p=predicted[target][ids]
                metrics[target]=dict(rows=len(ids),mae=float(np.mean(abs(p-actual))),bias=float(np.mean(p-actual)),rmse=float(np.sqrt(np.mean((p-actual)**2))))
        receipt['metrics'][split]=metrics
    return bundle
