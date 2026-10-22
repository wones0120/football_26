from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from backend.app.product_services import joint_rush_conditional_means as m


def groups():
    return [dict(game_id=f'{year}_04_A_B', team='B', period=year*100+4,budget_label=3,cells=[
        dict(kind='candidate',source_player_id='native',player_master_id='uuid',label=0,features={'prior':float(year-2022),'missing':None}),
        dict(kind='outside_rest',source_player_id=None,player_master_id=None,label=3,features={'prior':None,'missing':None})]) for year in (2023,2024,2025)]


def test_train_only_frozen_unknown_and_immutability():
    g=groups();p=m.fit_preprocessing(g,['prior','missing']);changed=deepcopy(g)
    changed[1]['cells'][0]['features']={'prior':999.,'missing':5.}
    changed[2]['cells'][0]['label']=2;changed[2]['cells'][1]['label']=1
    assert p==m.fit_preprocessing(changed,['prior','missing'])
    X=m.transform_groups(changed,p)['X']
    assert np.all(X[:,1]==0) and np.all(X[:,3]==1) and g==groups()


def test_gradient_budget_sum_and_permutation():
    g=groups();p=m.fit_preprocessing(g,['prior','missing']);d=m.transform_groups(g,p)
    t=m.initial_parameters(d['X'].shape[1]);loss,grad=m.objective(t,d,p)
    for j in range(len(t)):
        plus=t.copy();minus=t.copy();plus[j]+=1e-6;minus[j]-=1e-6
        assert grad[j]==pytest.approx((m.objective(plus,d,p)[0]-m.objective(minus,d,p)[0])/2e-6,abs=1e-7)
    model=dict(status='completed',parameters=t.tolist(),recipe=m.RECIPE,preprocessing=p)
    a=m.predict(model,g);reverse=deepcopy(g)
    for group in reverse:group['cells'].reverse()
    b=m.predict(model,reverse)
    for x,y in zip(a,b):
        assert min(x['cell_means'])>=0 and x['budget_mean']==sum(x['cell_means'])
        assert x['budget_mean']==pytest.approx(y['budget_mean']) and x['cell_means']==y['cell_means'][::-1]


@pytest.mark.parametrize('bad',[None,-1,float('nan'),1.5])
def test_unknown_invalid_labels_never_zero(bad):
    g=groups();g[0]['cells'][0]['label']=bad
    with pytest.raises((ValueError,TypeError)):m.fit_preprocessing(g,['prior','missing'])


def test_rest_and_budget_required():
    for modify in (lambda g:g[0]['cells'].pop(),lambda g:g[0].update(budget_label=4)):
        g=groups();modify(g)
        with pytest.raises(ValueError):m.fit_preprocessing(g,['prior','missing'])


def test_nonconvergence_preserved_no_retry_inference():
    calls=[]
    def fake(fun,t,**kw):
        calls.append(kw);return SimpleNamespace(success=False,fun=1.,x=t,message='limit',nit=500)
    g=groups();p=m.fit_preprocessing(g,['prior','missing']);model=m.fit(g,p,optimizer=fake)
    assert len(calls)==1 and model['status']=='fit_failed' and model['parameters']
    with pytest.raises(ValueError):m.predict(model,g)


def test_invalid_later_split_preflights_before_fit():
    calls=[];g=groups();p=m.fit_preprocessing(g,['prior','missing']);g[-1]['cells'][0]['label']=None
    with pytest.raises((ValueError,TypeError)):m.fit(g,p,optimizer=lambda *a,**k:calls.append(1))
    assert not calls


def test_objective_exception_preserves_partial_finite_parameters():
    def fake(fun,t,**kw):
        fun(t)
        raise FloatingPointError('forced nonfinite objective')
    g=groups();p=m.fit_preprocessing(g,['prior','missing']);model=m.fit(g,p,optimizer=fake)
    assert model['status']=='fit_failed' and model['error_type']=='FloatingPointError'
    assert np.isfinite(model['parameters']).all()


def test_nonfinite_optimizer_result_serializable_and_blocked():
    def fake(fun,t,**kw):
        return SimpleNamespace(success=True,fun=float('nan'),x=t*np.nan,message='invalid',nit=1)
    import json
    g=groups();p=m.fit_preprocessing(g,['prior','missing']);model=m.fit(g,p,optimizer=fake)
    assert model['status']=='fit_failed'
    json.dumps(model,allow_nan=False)
    with pytest.raises(ValueError):m.predict(model,g)
