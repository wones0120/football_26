"""Version3 numerical solver for the unchanged source-observed joint means.

F(theta)=.5*||r(theta)||² uses original parameters and exactly one original
weight-only L2 term. LinearOperator products avoid a dense Jacobian/Hessian.
"""
from copy import deepcopy
import hashlib
import numpy as np
from scipy.optimize import least_squares
from scipy.sparse.linalg import LinearOperator
from scipy.special import expit
from . import joint_rush_conditional_means as rush
from . import joint_target_pass_conditional_means as target

VERSION='joint_mean_exact_residual_solver_v3'
SOLVER_OPTIONS=dict(method='trf',tr_solver='lsmr',loss='linear',x_scale=1.0,
                    gtol=1e-5,ftol=None,xtol=None,max_nfev=2500,
                    tr_options=dict(regularize=True,atol=1e-6,btol=1e-6,conlim=1e8,maxiter=200))
HARD_CAP_SECONDS=300  # Enforced by the separately gated orchestration runner.


def residual_system(theta,data,prep,*,channel,counters=None):
    if channel not in{'rush','target'}:raise ValueError('Explicit channel required')
    theta=np.asarray(theta,dtype=float).reshape(-1).copy();X=data['X'];off=np.asarray(data['offsets']);ng=len(data['budgets']);nc=len(X)
    if ng==0 or len(off)!=ng+1 or off[0]!=0 or off[-1]!=nc or np.any(np.diff(off)<=0):raise ValueError('Nonempty ordered groups required')
    W,b,v,a=rush._unpack(theta,X.shape[1],8)
    mu,H,z=rush.forward(theta,X,8);s=expit(z);sizes=np.diff(off)
    ri=np.r_[np.arange(W.size),np.arange(W.size+8,W.size+16)]
    cellscale=np.repeat(np.sqrt(2/(ng*sizes))/prep['cell_label_scale'],sizes)
    Bscale=np.sqrt(2/ng)/prep['budget_label_scale']
    Tscale=np.sqrt(2/ng)/prep['target_budget_label_scale']if channel=='target'else None
    ridge=np.sqrt(.001)
    def grouped(values,targets=False):
        values=np.asarray(values).reshape(-1)
        if targets:
            values=values.copy();values[off[1:]-1]=0.
        return np.add.reduceat(values,off[:-1])
    residual=np.r_[cellscale*(mu-data['labels']),Bscale*(grouped(mu)-data['budgets']),
                   *([Tscale*(grouped(mu,True)-data['target_budgets'])]if channel=='target'else[]),ridge*theta[ri]]
    if not np.isfinite(residual).all():raise FloatingPointError('Nonfinite residual')
    def vector(q,length):
        q=np.asarray(q,dtype=float).reshape(-1)
        if q.size!=length or not np.isfinite(q).all():raise ValueError('Finite operator vector with exact dimension required')
        return q
    def matvec(q):
        if counters is not None:counters['matvec']+=1
        q=vector(q,len(theta));qW,qb,qv,qa=rush._unpack(q,X.shape[1],8)
        delta=s*(((1-H**2)*(X@qW+qb))@v+H@qv+qa)
        answer=np.r_[cellscale*delta,Bscale*grouped(delta),*([Tscale*grouped(delta,True)]if channel=='target'else[]),ridge*q[ri]]
        if not np.isfinite(answer).all():raise FloatingPointError('Nonfinite JVP')
        return answer
    def rmatvec(q):
        if counters is not None:counters['rmatvec']+=1
        q=vector(q,len(residual));qm=cellscale*q[:nc]+np.repeat(Bscale*q[nc:nc+ng],sizes);position=nc+ng
        if channel=='target':
            tv=np.repeat(Tscale*q[position:position+ng],sizes);tv[off[1:]-1]=0.;qm+=tv;position+=ng
        dz=qm*s;dh=dz[:,None]*v*(1-H**2)
        answer=np.r_[(X.T@dh).ravel(),dh.sum(0),H.T@dz,dz.sum()];answer[ri]+=ridge*q[position:]
        if not np.isfinite(answer).all():raise FloatingPointError('Nonfinite adjoint')
        return answer
    return residual,LinearOperator((len(residual),len(theta)),matvec=matvec,rmatvec=rmatvec,dtype=np.float64)


def fit(groups,prep,*,channel,solver=least_squares):
    if channel not in{'rush','target'}:raise ValueError('Explicit reviewed channel required')
    module=rush if channel=='rush'else target
    for year in(2023,2024,2025):module.transform_groups([g for g in groups if g['period']//100==year],prep)
    data=module.transform_groups([g for g in groups if g['period']//100==2023],prep)
    original=deepcopy(module.RECIPE);initial=rush.initial_parameters(data['X'].shape[1],original);last=initial.copy()
    counters=dict(residual_calls=0,jacobian_calls=0,matvec=0,rmatvec=0);cached_theta=None;cached=None
    options=deepcopy(SOLVER_OPTIONS)
    recipe={**original,'version':VERSION+'_'+channel,'optimizer':'scipy.optimize.least_squares',
            'solver_options':deepcopy(options),'max_nfev':options['max_nfev'],
            'ftol':None,'xtol':None,'gtol':options['gtol']}
    # maxiter belonged to the old solver. Never misreport nfev as iterations.
    recipe.pop('maxiter',None)
    base=dict(version=VERSION,channel=channel,recipe=recipe,objective_recipe=original,preprocessing=deepcopy(prep),
              solver_options=deepcopy(options),effective_optimizer_method='scipy.optimize.least_squares',
              effective_optimizer_options=deepcopy(options),
              initial_parameters_sha256=hashlib.sha256(initial.astype('<f8').tobytes()).hexdigest(),
              fresh_original_seed_start=True,retries=0,hard_cap_seconds=HARD_CAP_SECONDS,
              objective_equivalence='OriginalF=.5rTr;oneoriginalsqrtL2weights-only residual;TRFregularize is step stabilization only')
    def system(theta):
        nonlocal cached_theta,cached,last
        if cached_theta is None or not np.array_equal(theta,cached_theta):
            cached=residual_system(theta,data,prep,channel=channel,counters=counters)
            cached_theta=np.array(theta,copy=True);last=cached_theta.copy()
        return cached
    def fun(theta):
        counters['residual_calls']+=1
        return system(theta)[0]
    def jac(theta):
        counters['jacobian_calls']+=1
        return system(theta)[1]
    try:
        result=solver(fun,initial.copy(),jac=jac,bounds=(-np.inf,np.inf),**options)
    except Exception as exc:
        return {**base,'status':'fit_failed','parameters':last.tolist(),'solver_success':False,
                'solver_message':str(exc),'optimizer_message':str(exc),'error_type':type(exc).__name__,
                'solver_counters':counters,'nfev':None,'njev':None,'native_status':None}
    theta=np.asarray(result.x)
    diagnostic_error=None;F=gnorm=cost=None
    try:
        if not np.isfinite(theta).all():raise FloatingPointError('Nonfinite parameters')
        F,g=module.objective(theta,data,prep);gnorm=float(np.max(abs(g)))
        r,_=residual_system(theta,data,prep,channel=channel);cost=float(.5*(r@r))
        if not np.isfinite([F,gnorm,cost]).all()or not np.isclose(F,cost,rtol=1e-11,atol=1e-12):raise FloatingPointError('Residual/original objective mismatch')
    except(ValueError,FloatingPointError)as exc:diagnostic_error=str(exc)
    native_values_finite=np.isfinite([result.cost,result.optimality]).all()
    if diagnostic_error is None and native_values_finite and not np.isclose(result.cost,cost,rtol=1e-11,atol=1e-12):
        diagnostic_error='Native cost does not match exact residual cost'
    accepted=bool(result.success and int(result.status)==1 and native_values_finite and
                  result.optimality<=options['gtol'] and diagnostic_error is None and gnorm<=options['gtol'])
    out={**base,'status':'completed'if accepted else'fit_failed','parameters':(theta if np.isfinite(theta).all()else last).tolist(),
         'solver_success':bool(result.success),'solver_message':str(result.message),'optimizer_message':str(result.message),
         'native_status':int(result.status),'nfev':int(result.nfev),'njev':int(result.njev)if result.njev is not None else None,
         'native_cost':float(result.cost)if np.isfinite(result.cost)else None,
         'native_optimality':float(result.optimality)if np.isfinite(result.optimality)else None,
         'original_objective':F,'objective':F,'residual_cost':cost,'original_gradient_inf':gnorm,
         'original_gradient_threshold':options['gtol'],'diagnostic_error':diagnostic_error,'solver_counters':counters}
    if accepted:
        try:module.predict(out,groups)
        except(ValueError,FloatingPointError):
            out['status']='fit_failed';out['optimizer_message']+='; nonfinite outputs, inference blocked'
    return out
