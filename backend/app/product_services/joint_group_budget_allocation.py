"""V4 jointly learned group count means and normalized mean allocations.

The group head cannot change with candidate arity or score parameters. Fractions
allocate CONDITIONAL MEANS; they are not separately fitted expected shares.
"""
from copy import deepcopy
import hashlib
import numpy as np
from scipy.optimize import least_squares
from scipy.sparse.linalg import LinearOperator
from scipy.special import expit
from . import joint_rush_conditional_means as rush
from . import joint_target_pass_conditional_means as target
from .joint_mean_exact_residual_solver import SOLVER_OPTIONS,HARD_CAP_SECONDS
from .scheduled_workload_efficiency_model_inputs import TEAM_ADDED

VERSION='joint_group_budget_allocation_v4'
HIDDEN=8
L2=.001
INIT_ZERO_MEAN_FLOOR=1e-8


def _module(channel):
    if channel not in{'rush','target'}:raise ValueError('Explicit reviewed channel required')
    return rush if channel=='rush'else target


def raw_group_inputs(groups):
    rows=[]
    for g in groups:
        values=np.asarray([np.nan if g['cells'][0]['features'][k]is None else g['cells'][0]['features'][k]for k in TEAM_ADDED],dtype=float)
        for c in g['cells']:
            other=np.asarray([np.nan if c['features'][k]is None else c['features'][k]for k in TEAM_ADDED],dtype=float)
            if not np.array_equal(values,other,equal_nan=True):raise ValueError('All38 prior group fields must agree across every cell')
        rows.append(values)
    return np.asarray(rows,dtype=float)


def fit_group_preprocessing(groups):
    train=[g for g in groups if g['period']//100==2023]
    if not train:raise ValueError('TRAIN groups required')
    raw=raw_group_inputs(train);allmissing=np.isnan(raw).all(0)
    med=np.asarray([0. if allmissing[j]else np.nanmedian(raw[:,j])for j in range(len(TEAM_ADDED))])
    filled=np.where(np.isnan(raw),med,raw);center=filled.mean(0);scale=filled.std(0);scale[scale==0]=1.
    return dict(columns=list(TEAM_ADDED),medians=med.tolist(),centers=center.tolist(),scales=scale.tolist(),
                entirely_missing_train_columns=[TEAM_ADDED[j]for j in np.flatnonzero(allmissing)],train_year=2023,
                weighting='ONE row perTRAINgroup; never candidate-count weighted')


def transform_group_inputs(groups,prep):
    if prep['columns']!=list(TEAM_ADDED):raise ValueError('Exact38 group fields/order required')
    raw=raw_group_inputs(groups)
    for k in prep['entirely_missing_train_columns']:raw[:,prep['columns'].index(k)]=np.nan
    missing=np.isnan(raw);filled=np.where(missing,np.asarray(prep['medians']),raw)
    G=np.concatenate(((filled-prep['centers'])/prep['scales'],missing.astype(float)),axis=1)
    if not np.isfinite(G).all():raise ValueError('Nonfinite group input')
    return G


def transform_groups(groups,cell_prep,group_prep,*,channel):
    d=_module(channel).transform_groups(groups,cell_prep)
    d['G']=transform_group_inputs(groups,group_prep)
    return d


def _unpack(theta,p,q,channel):
    k=1 if channel=='rush'else 2;a=p*HIDDEN;s=a+2*HIDDEN
    theta=np.asarray(theta,dtype=float).reshape(-1)
    if len(theta)!=s+q*k+k:raise ValueError('Exact parameter count required; no common score-output bias')
    return theta[:a].reshape(p,HIDDEN),theta[a:a+HIDDEN],theta[a+HIDDEN:s],theta[s:s+q*k].reshape(q,k),theta[-k:]


def weight_indices(p,q,channel):
    k=1 if channel=='rush'else 2;a=p*HIDDEN;s=a+2*HIDDEN
    return np.r_[np.arange(a),np.arange(a+HIDDEN,s),np.arange(s,s+q*k)]


def initial_parameters(data,*,channel):
    p,q=data['X'].shape[1],data['G'].shape[1];k=1 if channel=='rush'else 2
    score=rush.initial_parameters(p)[:-1]  # Same fixedseed17 score W/b/v; remove common outputbias.
    means=np.asarray([data['budgets'].mean()]if channel=='rush'else[data['target_budgets'].mean(),(data['budgets']-data['target_budgets']).mean()])
    if not np.isfinite(means).all()or(means<0).any():raise ValueError('Known nonnegative TRAIN head means required')
    safe=np.maximum(means,INIT_ZERO_MEAN_FLOOR)
    bias=safe+np.log(-np.expm1(-safe))
    return np.r_[score,np.zeros(q*k),bias],means


def forward(theta,data,*,channel):
    _module(channel)
    X,G=data['X'],data['G'];off=np.asarray(data['offsets']);sizes=np.diff(off)
    W,b,v,U,a=_unpack(theta,X.shape[1],G.shape[1],channel)
    H=np.tanh(X@W+b);scores=H@v;logits=G@U+a;heads=np.logaddexp(0,logits)
    values=scores.copy()
    if channel=='target':values[off[1:]-1]=-np.inf
    maximum=np.maximum.reduceat(values,off[:-1]);e=np.exp(values-np.repeat(maximum,sizes));shares=e/np.repeat(np.add.reduceat(e,off[:-1]),sizes)
    mu=np.repeat(heads[:,0],sizes)*shares
    if channel=='target':mu[off[1:]-1]=heads[:,1]
    if not np.isfinite(mu).all()or not np.isfinite(heads).all():raise FloatingPointError('Nonfinite joint means')
    return dict(mu=mu,heads=heads,shares=shares,H=H,logits=logits,sizes=sizes,off=off,W=W,v=v,U=U)


def residual_system(theta,data,prep,*,channel,counters=None):
    state=forward(theta,data,channel=channel);X,G=data['X'],data['G'];p,q=X.shape[1],G.shape[1];off=state['off'];sizes=state['sizes'];ng=len(data['budgets']);nc=len(X)
    mu,heads,s,H=state['mu'],state['heads'],state['shares'],state['H'];ri=weight_indices(p,q,channel)
    cellscale=np.repeat(np.sqrt(2/(ng*sizes))/prep['cell_label_scale'],sizes);Bscale=np.sqrt(2/ng)/prep['budget_label_scale'];Tscale=np.sqrt(2/ng)/prep['target_budget_label_scale']if channel=='target'else None
    B=heads[:,0]if channel=='rush'else heads.sum(1)
    r=np.r_[cellscale*(mu-data['labels']),Bscale*(B-data['budgets']),*([Tscale*(heads[:,0]-data['target_budgets'])]if channel=='target'else[]),np.sqrt(L2)*np.asarray(theta)[ri]]
    if not np.isfinite(r).all():raise FloatingPointError('Nonfinite residual')
    def grouped(values):return np.add.reduceat(values,off[:-1])
    def vector(v,n):
        v=np.asarray(v,dtype=float).reshape(-1)
        if len(v)!=n or not np.isfinite(v).all():raise ValueError('Finite operator vector/exact dimension required')
        return v
    def matvec(direction):
        if counters is not None:counters['matvec']+=1
        direction=vector(direction,len(theta));dW,db,dv,dU,da=_unpack(direction,p,q,channel)
        dz=((1-H**2)*(X@dW+db))@state['v']+H@dv
        ds=s*(dz-np.repeat(grouped(s*dz),sizes))
        dheads=expit(state['logits'])*(G@dU+da)
        dmu=np.repeat(dheads[:,0],sizes)*s+np.repeat(heads[:,0],sizes)*ds
        if channel=='target':dmu[off[1:]-1]=dheads[:,1]
        dB=dheads[:,0]if channel=='rush'else dheads.sum(1)
        answer=np.r_[cellscale*dmu,Bscale*dB,*([Tscale*dheads[:,0]]if channel=='target'else[]),np.sqrt(L2)*direction[ri]]
        if not np.isfinite(answer).all():raise FloatingPointError('Nonfinite JVP')
        return answer
    def rmatvec(vr):
        if counters is not None:counters['rmatvec']+=1
        vr=vector(vr,len(r));qm=cellscale*vr[:nc];position=nc+ng
        adjheads=np.zeros_like(heads);adjheads[:,0]=grouped(qm*s)
        if channel=='target':adjheads[:,1]=qm[off[1:]-1]
        head_budget=Bscale*vr[nc:nc+ng]
        adjheads+=head_budget[:,None]
        if channel=='target':adjheads[:,0]+=Tscale*vr[position:position+ng];position+=ng
        score_adj=np.repeat(heads[:,0],sizes)*s*(qm-np.repeat(grouped(qm*s),sizes))
        hidden_adj=score_adj[:,None]*state['v']*(1-H**2)
        logit_adj=adjheads*expit(state['logits'])
        answer=np.r_[(X.T@hidden_adj).ravel(),hidden_adj.sum(0),H.T@score_adj,(G.T@logit_adj).ravel(),logit_adj.sum(0)]
        answer[ri]+=np.sqrt(L2)*vr[position:]
        if not np.isfinite(answer).all():raise FloatingPointError('Nonfinite adjoint')
        return answer
    return r,LinearOperator((len(r),len(theta)),matvec=matvec,rmatvec=rmatvec,dtype=np.float64)


def objective(theta,data,prep,*,channel):
    state=forward(theta,data,channel=channel);mu,heads=state['mu'],state['heads'];ng=len(data['budgets']);value=0.
    for j,(lo,hi)in enumerate(zip(data['offsets'][:-1],data['offsets'][1:])):
        value+=float(np.mean((mu[lo:hi]-data['labels'][lo:hi])**2))/prep['cell_label_scale']**2/ng
        B=heads[j,0]if channel=='rush'else heads[j].sum()
        value+=float((B-data['budgets'][j])**2)/prep['budget_label_scale']**2/ng
        if channel=='target':value+=float((heads[j,0]-data['target_budgets'][j])**2)/prep['target_budget_label_scale']**2/ng
    ri=weight_indices(data['X'].shape[1],data['G'].shape[1],channel);value+=L2*float(np.sum(np.asarray(theta)[ri]**2))/2
    residual,J=residual_system(theta,data,prep,channel=channel)
    return value,J.rmatvec(residual)


def predict(model,groups):
    if model['status']!='completed':raise ValueError('Failed/unfitted models cannot infer')
    channel=model['channel'];d=transform_groups(groups,model['preprocessing'],model['group_preprocessing'],channel=channel);s=forward(np.asarray(model['parameters']),d,channel=channel);rows=[]
    for j,(g,lo,hi)in enumerate(zip(groups,d['offsets'][:-1],d['offsets'][1:])):
        row=dict(game_id=g['game_id'],team=g['team'],cell_means=s['mu'][lo:hi].tolist())
        if channel=='rush':row['budget_mean']=float(s['heads'][j,0])
        else:row.update(target_mean=float(s['heads'][j,0]),pass_mean=float(s['heads'][j].sum()),known_outside_target_mean=float(s['mu'][hi-2]),source_pass_minus_target_mean=float(s['heads'][j,1]))
        rows.append(row)
    return rows


def fit(groups,prep,group_prep,*,channel,solver=least_squares):
    for year in(2023,2024,2025):transform_groups([g for g in groups if g['period']//100==year],prep,group_prep,channel=channel)
    data=transform_groups([g for g in groups if g['period']//100==2023],prep,group_prep,channel=channel);initial,means=initial_parameters(data,channel=channel);last=initial.copy()
    options=deepcopy(SOLVER_OPTIONS);counters=dict(residual_calls=0,jacobian_calls=0,matvec=0,rmatvec=0);cache_theta=None;cache=None
    recipe=dict(version=VERSION,hidden_units=HIDDEN,seed=17,l2=L2,optimizer='scipy.optimize.least_squares',solver_options=options,group_heads='1rush or2target/PminusT affine',allocation='shared8tanhscore/softmax;no common outputbias',cell_loss_weight=1.,budget_loss_weight=1.,target_budget_loss_weight=1. if channel=='target' else 0.)
    base=dict(version=VERSION,channel=channel,recipe=recipe,preprocessing=deepcopy(prep),group_preprocessing=deepcopy(group_prep),objective_recipe=deepcopy(_module(channel).RECIPE),
              solver_options=deepcopy(options),effective_optimizer_options=deepcopy(options),fresh_original_seed_start=True,retries=0,hard_cap_seconds=HARD_CAP_SECONDS,
              initial_parameters_sha256=hashlib.sha256(initial.astype('<f8').tobytes()).hexdigest(),train_group_head_means=means.tolist(),zero_train_mean_initialization_floor=INIT_ZERO_MEAN_FLOOR,
              objective_scope='Same declared rawcount loss/scales/weights andL2coefficient;newexplicitgroupbudget+allocationarchitecture,not sameoldthetafunction')
    def system(theta):
        nonlocal cache_theta,cache,last
        if cache_theta is None or not np.array_equal(theta,cache_theta):
            cache=residual_system(theta,data,prep,channel=channel,counters=counters);cache_theta=np.array(theta,copy=True);last=cache_theta.copy()
        return cache
    def fun(theta):counters['residual_calls']+=1;return system(theta)[0]
    def jac(theta):counters['jacobian_calls']+=1;return system(theta)[1]
    try:result=solver(fun,initial.copy(),jac=jac,bounds=(-np.inf,np.inf),**options)
    except Exception as exc:return {**base,'status':'fit_failed','parameters':last.tolist(),'solver_success':False,'solver_message':str(exc),'optimizer_message':str(exc),'error_type':type(exc).__name__,'nfev':None,'njev':None,'native_status':None,'solver_counters':counters}
    theta=np.asarray(result.x);error=None;F=norm=cost=None
    try:
        if not np.isfinite(theta).all():raise FloatingPointError('Nonfinite parameters')
        F,grad=objective(theta,data,prep,channel=channel);norm=float(np.max(abs(grad)));residual,_=residual_system(theta,data,prep,channel=channel);cost=float(.5*(residual@residual))
        if not np.isfinite([F,norm,cost,result.cost,result.optimality]).all()or not np.isclose(F,cost,rtol=1e-11,atol=1e-12)or not np.isclose(cost,result.cost,rtol=1e-11,atol=1e-12):raise FloatingPointError('Nonfinite/mismatched native/declarative residual cost')
    except(ValueError,FloatingPointError)as exc:error=str(exc)
    success=bool(result.success and int(result.status)==1 and error is None and norm<=options['gtol']and 0<=result.optimality<=options['gtol'])
    out={**base,'status':'completed'if success else'fit_failed','parameters':(theta if np.isfinite(theta).all()else last).tolist(),'solver_success':bool(result.success),'solver_message':str(result.message),'optimizer_message':str(result.message),
         'native_status':int(result.status),'nfev':int(result.nfev),'njev':int(result.njev)if result.njev is not None else None,'native_cost':float(result.cost)if np.isfinite(result.cost)else None,'native_optimality':float(result.optimality)if np.isfinite(result.optimality)else None,
         'original_objective':F,'objective':F,'residual_cost':cost,'original_gradient_inf':norm,'declared_v4_gradient_inf':norm,'diagnostic_error':error,'solver_counters':counters}
    if success:
        try:predict(out,groups)
        except(ValueError,FloatingPointError):out['status']='fit_failed';out['optimizer_message']+='; nonfinite prediction blocked'
    return out
