"""Isolated iteration-budget v2: original objective/inputs/init remain frozen.

This module never mutates either reviewed 500-iteration module or its RECIPE.
It requires a separately authorized invocation; no automatic retry is provided.
"""
from copy import deepcopy
import hashlib
import numpy as np
from scipy.optimize import minimize
from . import joint_rush_conditional_means as rush
from . import joint_target_pass_conditional_means as target

VERSION='joint_mean_iteration_budget_v2'
MAXITER=2500
HARD_CAP_SECONDS=300  # Enforced by the separately reviewed orchestration runner.


def fit(groups,prep,*,channel,optimizer=minimize):
    if channel not in{'rush','target'}:raise ValueError('Explicit reviewed channel required')
    module=rush if channel=='rush'else target
    original=deepcopy(module.RECIPE)
    recipe={**original,'version':original['version']+'_iteration_budget_v2','maxiter':MAXITER}
    for year in(2023,2024,2025):
        module.transform_groups([g for g in groups if g['period']//100==year],prep)
    data=module.transform_groups([g for g in groups if g['period']//100==2023],prep)
    initial=rush.initial_parameters(data['X'].shape[1],original)
    last=initial.copy()
    options={k:recipe[k]for k in('maxiter','ftol','gtol')}
    base=dict(version=VERSION,channel=channel,recipe=recipe,objective_recipe=original,
              preprocessing=deepcopy(prep),retries=0,fresh_original_seed_start=True,
              initial_parameters_sha256=hashlib.sha256(initial.astype('<f8').tobytes()).hexdigest(),
              effective_optimizer_method=recipe['optimizer'],effective_optimizer_options=deepcopy(options),
              hard_cap_seconds=HARD_CAP_SECONDS)
    def checked(theta):
        nonlocal last
        value=module.objective(theta,data,prep)
        last=np.array(theta,copy=True)
        return value
    try:
        result=optimizer(checked,initial.copy(),jac=True,method=recipe['optimizer'],options=options)
    except Exception as exc:
        return {**base,'status':'fit_failed','parameters':last.tolist(),
                'optimizer_success':False,'optimizer_message':str(exc),'error_type':type(exc).__name__}
    success=bool(result.success and np.isfinite(result.fun)and np.isfinite(result.x).all())
    out={**base,'status':'completed'if success else'fit_failed',
         'parameters':(np.asarray(result.x)if np.isfinite(result.x).all()else last).tolist(),
         'optimizer_success':bool(result.success),'optimizer_message':str(result.message),
         'iterations':int(result.nit),'objective':float(result.fun)if np.isfinite(result.fun)else None}
    if success:
        try:module.predict(out,groups)
        except(ValueError,FloatingPointError):
            out['status']='fit_failed';out['optimizer_message']+='; nonfinite output; inference blocked'
    return out
