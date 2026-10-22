"""Offline source-observed target/pass joint means, using the reviewed rush core.

Known outside-target rest and source pass-minus-target remainder are different
cells. The latter is not an identified throwaway, spike or unreported target.
"""
from copy import deepcopy
import numpy as np
from scipy.optimize import minimize
from . import joint_rush_conditional_means as core

VERSION='joint_target_pass_conditional_means_v1'
RECIPE={**core.RECIPE,'version':'shared_tanh8_joint_target_pass_raw_mse_v1','target_budget_loss_weight':1.0}


def validate_groups(groups,columns):
    if not groups:raise ValueError('Nonempty fixed target cohort required')
    seen=set()
    for g in groups:
        key=g['game_id'],g['team']
        if key in seen or g['period']//100 not in(2023,2024,2025):raise ValueError('Unique fixed historical groups required')
        seen.add(key)
        if [c['kind']for c in g['cells'][-2:]]!=['outside_target_rest','source_pass_minus_target_remainder']:raise ValueError('Distinct target rest then source P-T cell required')
        actors=g['cells'][:-2]
        if not actors or any(c['kind']!='candidate'for c in actors):raise ValueError('Explicit prior candidates required')
        for field in('source_player_id','player_master_id'):
            ids=[c[field]for c in actors]
            if None in ids or len(set(ids))!=len(ids):raise ValueError('Unique native/canonical candidate keys required')
        y=np.asarray([c['label']for c in g['cells']],dtype=float)
        if not np.isfinite(y).all()or(y<0).any()or not np.equal(y,np.floor(y)).all():raise ValueError('Known nonnegative integral labels required')
        if y[:-1].sum()!=g['target_budget_label']or y.sum()!=g['pass_budget_label']:raise ValueError('Target and pass source budget identity required')
        for c in g['cells']:
            if list(c['features'])!=list(columns):raise ValueError('Exact prior-only column order required')
            if any(v is not None and(type(v)not in(int,float)or not np.isfinite(v))for v in c['features'].values()):raise ValueError('Finite numeric/unknown features required')


def fit_preprocessing(groups,columns):
    validate_groups(groups,columns)
    train=[g for g in groups if g['period']//100==2023]
    if not train:raise ValueError('TRAIN groups required')
    raw=np.asarray([[np.nan if c['features'][k]is None else c['features'][k]for k in columns]for g in train for c in g['cells']],dtype=float)
    missing=np.isnan(raw).all(0)
    med=np.asarray([0. if missing[j]else np.nanmedian(raw[:,j])for j in range(raw.shape[1])])
    filled=np.where(np.isnan(raw),med,raw);center=filled.mean(0);scale=filled.std(0);scale[scale==0]=1.
    std=lambda values:max(1.,float(np.std(values)))
    return dict(version=VERSION,columns=list(columns),medians=med.tolist(),centers=center.tolist(),scales=scale.tolist(),
                entirely_missing_train_columns=[columns[j]for j in np.flatnonzero(missing)],train_year=2023,
                cell_label_scale=std([c['label']for g in train for c in g['cells']]),
                budget_label_scale=std([g['pass_budget_label']for g in train]),
                target_budget_label_scale=std([g['target_budget_label']for g in train]),target_transform='NONE; TRAIN loss scales only')


def transform_groups(groups,prep):
    validate_groups(groups,prep['columns'])
    raw=np.asarray([[np.nan if c['features'][k]is None else c['features'][k]for k in prep['columns']]for g in groups for c in g['cells']],dtype=float)
    for k in prep['entirely_missing_train_columns']:raw[:,prep['columns'].index(k)]=np.nan
    missing=np.isnan(raw);filled=np.where(missing,np.asarray(prep['medians']),raw)
    X=np.concatenate(((filled-prep['centers'])/prep['scales'],missing.astype(float)),axis=1)
    offsets=np.cumsum([0]+[len(g['cells'])for g in groups]).tolist()
    return dict(X=X,offsets=offsets,labels=np.asarray([c['label']for g in groups for c in g['cells']],dtype=float),
                budgets=np.asarray([g['pass_budget_label']for g in groups],dtype=float),
                target_budgets=np.asarray([g['target_budget_label']for g in groups],dtype=float))


def objective(theta,data,prep):
    # Reviewed shared cell/P-budget objective and derivatives; one additional
    # T-budget objective uses the SAME theta/X excluding only the P-T cell.
    loss,grad=core.objective(theta,data,prep,RECIPE)
    keep=np.concatenate([np.arange(lo,hi-1)for lo,hi in zip(data['offsets'][:-1],data['offsets'][1:])])
    tdata=dict(X=data['X'][keep],labels=data['labels'][keep],budgets=data['target_budgets'],
               offsets=np.cumsum([0]+[hi-lo-1 for lo,hi in zip(data['offsets'][:-1],data['offsets'][1:])]).tolist())
    trecipe={**RECIPE,'cell_loss_weight':0.,'budget_loss_weight':RECIPE['target_budget_loss_weight'],'l2':0.}
    tprep={**prep,'budget_label_scale':prep['target_budget_label_scale']}
    tloss,tgrad=core.objective(theta,tdata,tprep,trecipe)
    combined_loss,combined_grad=loss+tloss,grad+tgrad
    if not np.isfinite(combined_loss)or not np.isfinite(combined_grad).all():
        raise FloatingPointError('Nonfinite combined target/pass objective')
    return combined_loss,combined_grad


def predict(model,groups):
    if model['status']!='completed':raise ValueError('Failed/unfitted recipe cannot infer')
    d=transform_groups(groups,model['preprocessing']);mu,_,_=core.forward(np.asarray(model['parameters']),d['X'],RECIPE['hidden_units'])
    if not np.isfinite(mu).all():raise FloatingPointError('Nonfinite output')
    rows=[]
    for g,lo,hi in zip(groups,d['offsets'][:-1],d['offsets'][1:]):
        cells=mu[lo:hi];T=float(cells[:-1].sum());P=T+float(cells[-1])
        rows.append(dict(game_id=g['game_id'],team=g['team'],cell_means=cells.tolist(),target_mean=T,pass_mean=P,
                         known_outside_target_mean=float(cells[-2]),source_pass_minus_target_mean=float(cells[-1])))
    return rows


def fit(groups,prep,*,optimizer=minimize):
    for year in(2023,2024,2025):transform_groups([g for g in groups if g['period']//100==year],prep)
    data=transform_groups([g for g in groups if g['period']//100==2023],prep)
    last=core.initial_parameters(data['X'].shape[1],RECIPE)
    def checked(theta):
        nonlocal last
        result=objective(theta,data,prep);last=np.array(theta,copy=True);return result
    base=dict(version=VERSION,recipe=deepcopy(RECIPE),preprocessing=deepcopy(prep),retries=0)
    try:
        result=optimizer(checked,last.copy(),jac=True,method=RECIPE['optimizer'],options={k:RECIPE[k]for k in('maxiter','ftol','gtol')})
    except Exception as exc:
        return {**base,'status':'fit_failed','parameters':last.tolist(),'error_type':type(exc).__name__,'optimizer_message':str(exc)}
    success=bool(result.success and np.isfinite(result.fun)and np.isfinite(result.x).all())
    out={**base,'status':'completed'if success else'fit_failed','parameters':(result.x if np.isfinite(result.x).all()else last).tolist(),
         'optimizer_success':bool(result.success),'optimizer_message':str(result.message),'iterations':int(result.nit),
         'objective':float(result.fun)if np.isfinite(result.fun)else None}
    if success:
        try:predict(out,groups)
        except(ValueError,FloatingPointError):out['status']='fit_failed';out['optimizer_message']+='; nonfinite output'
    return out
