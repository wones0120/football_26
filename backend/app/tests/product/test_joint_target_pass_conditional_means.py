from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from backend.app.product_services import joint_target_pass_conditional_means as m


def groups():
    return [dict(game_id=f'{y}_04_A_B',team='B',period=y*100+4,target_budget_label=3,pass_budget_label=5,cells=[
        dict(kind='candidate',source_player_id='native',player_master_id='uuid',label=1,features={'prior':y-2022.,'is_rest':0.,'is_remainder':0.}),
        dict(kind='outside_target_rest',label=2,features={'prior':None,'is_rest':1.,'is_remainder':0.}),
        dict(kind='source_pass_minus_target_remainder',label=2,features={'prior':None,'is_rest':0.,'is_remainder':1.})])for y in(2023,2024,2025)]


def test_joint_gradient_both_budget_identities_and_remainder_distinct():
    g=groups();p=m.fit_preprocessing(g,list(g[0]['cells'][0]['features']));d=m.transform_groups(g,p)
    t=m.core.initial_parameters(d['X'].shape[1]);loss,grad=m.objective(t,d,p)
    for j in range(len(t)):
        a=t.copy();b=t.copy();a[j]+=1e-6;b[j]-=1e-6
        assert grad[j]==pytest.approx((m.objective(a,d,p)[0]-m.objective(b,d,p)[0])/2e-6,abs=1e-7)
    model=dict(status='completed',preprocessing=p,parameters=t.tolist())
    for r in m.predict(model,g):
        assert r['target_mean']==sum(r['cell_means'][:-1])
        assert r['pass_mean']==r['target_mean']+r['cell_means'][-1]
        assert r['known_outside_target_mean']==r['cell_means'][-2]
        assert 0<=r['target_mean']<=r['pass_mean']


def test_train_only_and_unknown_not_zero():
    g=groups();cols=list(g[0]['cells'][0]['features']);p=m.fit_preprocessing(g,cols);changed=deepcopy(g)
    changed[1]['cells'][0]['features']['prior']=999
    assert m.fit_preprocessing(changed,cols)==p
    changed[1]['cells'][0]['label']=None
    with pytest.raises(ValueError):m.transform_groups(changed,p)


@pytest.mark.parametrize('mutate',[lambda g:g[0]['cells'].pop(),lambda g:g[0].update(target_budget_label=6),lambda g:g[0]['cells'][-1].update(kind='outside_target_rest')])
def test_invalid_accounting_or_celltypes_rejected(mutate):
    g=groups();mutate(g)
    with pytest.raises(ValueError):m.fit_preprocessing(g,['prior','is_rest','is_remainder'])


def test_failed_recipe_blocks_without_retry():
    calls=[]
    def fake(fun,t,**kw):calls.append(1);return SimpleNamespace(success=False,x=t,fun=1.,nit=500,message='limit')
    g=groups();p=m.fit_preprocessing(g,['prior','is_rest','is_remainder']);out=m.fit(g,p,optimizer=fake)
    assert out['status']=='fit_failed'and len(calls)==1
    with pytest.raises(ValueError):m.predict(out,g)
