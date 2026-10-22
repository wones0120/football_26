from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from backend.app.product_services import joint_group_budget_allocation as m


def groups(channel):
    out=[]
    for year,week,value in[(2023,4,1.),(2023,5,3.),(2024,4,10.),(2025,4,20.)]:
        context={k:value*(j+1)/38 for j,k in enumerate(m.TEAM_ADDED)}
        cells=[dict(kind='candidate',source_player_id='a',player_master_id='A',label=1,features={**context,'is_rest':0.,'prior_count':1.}),dict(kind='outside_rest'if channel=='rush'else'outside_target_rest',source_player_id=None,player_master_id=None,label=2,features={**context,'is_rest':1.,'prior_count':1.})]
        extra=deepcopy(cells[0]);extra.update(source_player_id='z',player_master_id='Z',label=0);cells.insert(1,extra)
        g=dict(game_id=f'{year}_{week:02}_A_B',team='B',period=year*100+week,cells=cells)
        if channel=='rush':g['budget_label']=3
        else:
            cells.append(dict(kind='source_pass_minus_target_remainder',label=2,features={**context,'is_rest':2.,'prior_count':1.}));g.update(target_budget_label=3,pass_budget_label=5)
        out.append(g)
    return out


def prepared(channel):
    g=groups(channel);module=m._module(channel);p=module.fit_preprocessing(g,list(g[0]['cells'][0]['features']));gp=m.fit_group_preprocessing(g);d=m.transform_groups(g,p,gp,channel=channel)
    return g,p,gp,d


@pytest.mark.parametrize('channel',['rush','target'])
def test_residual_gradient_jvp_adjoint_and_budget_score_separation(channel):
    g,p,gp,d=prepared(channel);theta,means=m.initial_parameters(d,channel=channel);rng=np.random.default_rng(17)
    for t in(theta,theta+rng.normal(0,.02,len(theta))):
        F,grad=m.objective(t,d,p,channel=channel);r,J=m.residual_system(t,d,p,channel=channel)
        assert F==pytest.approx(.5*(r@r),abs=1e-12)
        assert J.rmatvec(r)==pytest.approx(grad,abs=1e-12)
        q=rng.normal(size=len(t));q/=np.linalg.norm(q);u=rng.normal(size=len(r))
        assert J.matvec(q)@u==pytest.approx(q@J.rmatvec(u),abs=1e-12)
        fd=(m.residual_system(t+1e-5*q,d,p,channel=channel)[0]-m.residual_system(t-1e-5*q,d,p,channel=channel)[0])/2e-5
        assert J.matvec(q)==pytest.approx(fd,abs=1e-8)
        assert J.matvec(q[:,None]).shape==(len(r),1)
        # Budget-only residual weights MUST have exactly zero score derivatives.
        for head in range(1 if channel=='rush' else 2):
            v=np.zeros(len(r));lo=len(d['labels'])+head*len(d['budgets']);v[lo:lo+len(d['budgets'])]=1.
            s=d['X'].shape[1]*8+16
            assert np.array_equal(J.rmatvec(v)[:s],np.zeros(s))
        for j in(0,d['X'].shape[1]*8,d['X'].shape[1]*8+8,len(t)-1):
            delta=np.zeros(len(t));delta[j]=1e-5
            finite=(m.objective(t+delta,d,p,channel=channel)[0]-m.objective(t-delta,d,p,channel=channel)[0])/2e-5
            assert grad[j]==pytest.approx(finite,abs=1e-8)


@pytest.mark.parametrize('channel',['rush','target'])
def test_budget_arity_permutation_and_score_invariance(channel):
    g,p,gp,d=prepared(channel);theta,_=m.initial_parameters(d,channel=channel);first=m.forward(theta,d,channel=channel)
    altered=deepcopy(g)
    for row in altered:
        c=deepcopy(row['cells'][0]);c.update(source_player_id='b',player_master_id='B',label=0);row['cells'].insert(1,c)
        for cell in row['cells']:cell['features']['prior_count']=2.
    second=m.forward(theta,m.transform_groups(altered,p,gp,channel=channel),channel=channel)
    assert np.array_equal(first['heads'],second['heads'])
    perturbed=theta.copy();perturbed[:d['X'].shape[1]*8+16]+=.5
    third=m.forward(perturbed,d,channel=channel)
    assert np.array_equal(first['heads'],third['heads'])
    for i,(lo,hi)in enumerate(zip(d['offsets'][:-1],d['offsets'][1:])):
        assert first['mu'][lo:hi].min()>0
        if channel=='rush':assert first['mu'][lo:hi].sum()==pytest.approx(first['heads'][i,0])
        else:
            assert first['mu'][lo:hi-1].sum()==pytest.approx(first['heads'][i,0])
            assert first['mu'][hi-1]==first['heads'][i,1]
    # Reorder allocation cells, retaining the explicit target D cell last.
    permuted=deepcopy(g)
    for row in permuted:
        if channel=='rush':row['cells'].reverse()
        else:row['cells'][:-2]=row['cells'][:-2][::-1]
    dd=m.transform_groups(permuted,p,gp,channel=channel);fourth=m.forward(theta,dd,channel=channel)
    for i,(lo,hi)in enumerate(zip(d['offsets'][:-1],d['offsets'][1:])):
        if channel=='rush':assert fourth['mu'][lo:hi]==pytest.approx(first['mu'][lo:hi][::-1])
        else:assert fourth['mu'][lo:hi-2]==pytest.approx(first['mu'][lo:hi-2][::-1])
        if channel=='target':assert fourth['mu'][hi-2:hi]==pytest.approx(first['mu'][hi-2:hi])


def test_group_preprocessing_once_per_group_and_no_label_leakage():
    g,p,gp,d=prepared('rush');expected=np.mean([1/38,3/38]);assert gp['centers'][0]==pytest.approx(expected)
    changed=deepcopy(g)
    for _ in range(10):changed[0]['cells'].append(deepcopy(changed[0]['cells'][0]))
    changed[0]['budget_label']=999 # Not used by group preprocessing.
    changed[2]['cells'][0]['label']=None
    assert m.fit_group_preprocessing(changed)==gp
    changed=deepcopy(g);changed[0]['cells'][1]['features'][m.TEAM_ADDED[0]]=55.
    with pytest.raises(ValueError):m.raw_group_inputs(changed)


@pytest.mark.parametrize('channel',['rush','target'])
def test_native_false_success_failure_and_no_global_mutation(channel):
    g,p,gp,d=prepared(channel);original=deepcopy(m.SOLVER_OPTIONS);calls=[]
    def fake(fun,x,**kw):
        calls.append(1);assert kw['gtol']==1e-5 and kw['max_nfev']==2500 and kw['ftol']is None and kw['xtol']is None
        r=fun(x);kw['jac'](x)
        return SimpleNamespace(x=x,success=True,status=1,message='fake',cost=.5*(r@r),optimality=0.,nfev=1,njev=1)
    out=m.fit(g,p,gp,channel=channel,solver=fake)
    assert out['status']=='fit_failed'and out['original_gradient_inf']>1e-5 and calls==[1]and m.SOLVER_OPTIONS==original
    with pytest.raises(ValueError):m.predict(out,g)


@pytest.mark.parametrize('channel',['rush','target'])
def test_timeout_nonfinite_preflight_preserved(channel):
    g,p,gp,d=prepared(channel);calls=[]
    def timeout(fun,x,**kw):calls.append(1);fun(x);raise TimeoutError('300s')
    out=m.fit(g,p,gp,channel=channel,solver=timeout)
    assert out['status']=='fit_failed'and out['error_type']=='TimeoutError'and np.isfinite(out['parameters']).all()and calls==[1]
    g[-1]['cells'][0]['label']=None;calls.clear()
    with pytest.raises((ValueError,TypeError)):m.fit(g,p,gp,channel=channel,solver=timeout)
    assert calls==[]


@pytest.mark.parametrize('channel',['rush','target'])
def test_zero_train_budget_floor_is_init_only_and_real_gradient_acceptance(channel):
    g=groups(channel)
    for row in g:
        for c in row['cells']:c['label']=0
        for k in list(row):
            if k.endswith('budget_label'):row[k]=0
    module=m._module(channel);p=module.fit_preprocessing(g,list(g[0]['cells'][0]['features']));gp=m.fit_group_preprocessing(g);d=m.transform_groups(g,p,gp,channel=channel)
    theta,means=m.initial_parameters(d,channel=channel)
    assert np.array_equal(means,np.zeros_like(means))
    assert np.isfinite(theta).all()
    k=1 if channel=='rush'else 2;theta[-k:]=-100.
    assert m.forward(theta,d,channel=channel)['heads'].max()<m.INIT_ZERO_MEAN_FLOOR
    def fake(fun,x,**kw):
        t=np.zeros_like(x);t[-k:]=-100.;r=fun(t)
        return SimpleNamespace(x=t,success=True,status=1,message='gtol',cost=.5*(r@r),optimality=0.,nfev=2,njev=2)
    out=m.fit(g,p,gp,channel=channel,solver=fake)
    assert out['status']=='completed'and out['original_gradient_inf']<=1e-5
    assert all(min(row['cell_means'])>=0 for row in m.predict(out,g))
