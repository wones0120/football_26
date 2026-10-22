from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from backend.app.product_services import joint_mean_exact_residual_solver as m
from backend.app.tests.product.test_joint_rush_conditional_means import groups as rush_groups
from backend.app.tests.product.test_joint_target_pass_conditional_means import groups as target_groups


def variable_groups(fixture):
    g=fixture();c=deepcopy(g[0]['cells'][0]);c['source_player_id']='native2';c['player_master_id']='uuid2';c['label']=0
    g[0]['cells'].insert(1,c)
    return g


@pytest.mark.parametrize('channel,fixture',[('rush',rush_groups),('target',target_groups)])
def test_exact_residual_jacobian_gradient_adjoint_and_column_vectors(channel,fixture):
    module=m.rush if channel=='rush'else m.target;g=variable_groups(fixture);p=module.fit_preprocessing(g,list(g[0]['cells'][0]['features']));d=module.transform_groups(g,p)
    initial=m.rush.initial_parameters(d['X'].shape[1]);rng=np.random.default_rng(17)
    for theta in(initial,initial+rng.normal(0,.1,len(initial))):
        r,J=m.residual_system(theta,d,p,channel=channel);F,grad=module.objective(theta,d,p)
        assert .5*(r@r)==pytest.approx(F,abs=1e-12)
        assert J.rmatvec(r)==pytest.approx(grad,abs=1e-12)
        q=rng.normal(size=len(theta));q/=np.linalg.norm(q);u=rng.normal(size=len(r))
        assert J.matvec(q)@u==pytest.approx(q@J.rmatvec(u),abs=1e-12)
        assert J.matvec(q[:,None]).shape==(len(r),1)
        assert J.rmatvec(u[:,None]).shape==(len(theta),1)
        finite=(m.residual_system(theta+1e-5*q,d,p,channel=channel)[0]-m.residual_system(theta-1e-5*q,d,p,channel=channel)[0])/2e-5
        assert J.matvec(q)==pytest.approx(finite,abs=1e-9)
        assert J.matmat(np.column_stack((q,q)))==pytest.approx(np.column_stack((J.matvec(q),J.matvec(q))),abs=1e-12)


@pytest.mark.parametrize('channel,fixture',[('rush',rush_groups),('target',target_groups)])
def test_native_success_with_bad_original_gradient_still_failed(channel,fixture):
    module=m.rush if channel=='rush'else m.target;original=deepcopy(module.RECIPE);g=fixture();p=module.fit_preprocessing(g,list(g[0]['cells'][0]['features']));calls=[]
    def fake(fun,x,**kw):
        calls.append(kw);assert np.array_equal(x,m.rush.initial_parameters(len(p['columns'])*2))
        assert kw['method']=='trf'and kw['tr_solver']=='lsmr'and kw['loss']=='linear'and kw['x_scale']==1.
        assert kw['ftol']is None and kw['xtol']is None and kw['gtol']==1e-5 and kw['max_nfev']==2500
        assert kw['tr_options']=={'regularize':True,'atol':1e-6,'btol':1e-6,'conlim':1e8,'maxiter':200}
        r=fun(x);J=kw['jac'](x);assert J.shape[1]==len(x)
        return SimpleNamespace(x=x,success=True,status=1,message='fakegtol',nfev=1,njev=1,cost=.5*(r@r),optimality=0.)
    out=m.fit(g,p,channel=channel,solver=fake)
    assert len(calls)==1 and out['status']=='fit_failed'and out['original_gradient_inf']>1e-5
    assert module.RECIPE==original and out['nfev']==1 and out['recipe']['ftol']is None and 'maxiter'not in out['recipe']
    with pytest.raises(ValueError):module.predict(out,g)


@pytest.mark.parametrize('channel,fixture',[('rush',rush_groups),('target',target_groups)])
@pytest.mark.parametrize('mode',['timeout','cap','nonfinite'])
def test_failures_preserved_without_retry(channel,fixture,mode):
    module=m.rush if channel=='rush'else m.target;g=fixture();p=module.fit_preprocessing(g,list(g[0]['cells'][0]['features']));calls=[]
    def fake(fun,x,**kw):
        calls.append(1);r=fun(x)
        if mode=='timeout':raise TimeoutError('cap300')
        return SimpleNamespace(x=x if mode=='cap'else x*np.nan,success=False,status=0,message='maxnfev',nfev=2500,njev=1,cost=.5*(r@r),optimality=1.)
    out=m.fit(g,p,channel=channel,solver=fake)
    assert calls==[1]and out['status']=='fit_failed'and np.isfinite(out['parameters']).all()
    with pytest.raises(ValueError):module.predict(out,g)


@pytest.mark.parametrize('channel,fixture',[('rush',rush_groups),('target',target_groups)])
def test_later_bad_labels_preflight_before_solver(channel,fixture):
    module=m.rush if channel=='rush'else m.target;g=fixture();p=module.fit_preprocessing(g,list(g[0]['cells'][0]['features']));g[-1]['cells'][0]['label']=None;calls=[]
    with pytest.raises((ValueError,TypeError)):m.fit(g,p,channel=channel,solver=lambda *a,**k:calls.append(1))
    assert calls==[]


@pytest.mark.parametrize('channel,fixture',[('rush',rush_groups),('target',target_groups)])
def test_true_native_gradient_acceptance_and_finite_accounting(channel,fixture):
    module=m.rush if channel=='rush'else m.target;g=fixture()
    for group in g:
        for cell in group['cells']:cell['label']=0
        for k in list(group):
            if k.endswith('budget_label'):group[k]=0
    p=module.fit_preprocessing(g,list(g[0]['cells'][0]['features']))
    def fake(fun,x,**kw):
        theta=np.zeros_like(x);theta[-1]=-100.;r=fun(theta)
        return SimpleNamespace(x=theta,success=True,status=1,message='gtol',nfev=2,njev=2,cost=.5*(r@r),optimality=0.)
    out=m.fit(g,p,channel=channel,solver=fake)
    assert out['status']=='completed'and out['original_gradient_inf']<=1e-5
    for row in module.predict(out,g):
        assert min(row['cell_means'])>=0 and np.isfinite(row['cell_means']).all()
