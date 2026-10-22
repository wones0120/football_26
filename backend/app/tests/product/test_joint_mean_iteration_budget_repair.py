from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from backend.app.product_services import joint_mean_iteration_budget_repair as repair
from backend.app.tests.product.test_joint_rush_conditional_means import groups as rush_groups
from backend.app.tests.product.test_joint_target_pass_conditional_means import groups as target_groups


@pytest.mark.parametrize('channel,fixture',[('rush',rush_groups),('target',target_groups)])
def test_only_iteration_budget_changes_and_fresh_initial_objective(channel,fixture):
    module=repair.rush if channel=='rush'else repair.target
    original=deepcopy(module.RECIPE);groups=fixture();cols=list(groups[0]['cells'][0]['features']);prep=module.fit_preprocessing(groups,cols);calls=[]
    data=module.transform_groups([groups[0]],prep)
    expected=repair.rush.initial_parameters(data['X'].shape[1],original)
    def fake(fun,x,**kwargs):
        calls.append(kwargs);assert np.array_equal(x,expected)
        loss,gradient=fun(x);reference=module.objective(x,data,prep)
        assert loss==reference[0]and np.array_equal(gradient,reference[1])
        return SimpleNamespace(success=False,x=x,fun=loss,nit=2500,message='iterationlimit')
    out=repair.fit(groups,prep,channel=channel,optimizer=fake)
    assert len(calls)==1 and calls[0]['options']=={'maxiter':2500,'ftol':original['ftol'],'gtol':original['gtol']}
    assert calls[0]['method']==original['optimizer']and calls[0]['jac']is True
    assert out['status']=='fit_failed'and out['recipe']['maxiter']==2500 and out['objective_recipe']==original
    assert module.RECIPE==original and out['fresh_original_seed_start']and out['retries']==0
    assert {k:v for k,v in out['recipe'].items()if k not in('maxiter','version')}=={k:v for k,v in original.items()if k not in('maxiter','version')}
    with pytest.raises(ValueError):module.predict(out,groups)


@pytest.mark.parametrize('channel,fixture',[('rush',rush_groups),('target',target_groups)])
def test_preflight_and_failure_preserve_without_retry(channel,fixture):
    module=repair.rush if channel=='rush'else repair.target;g=fixture();prep=module.fit_preprocessing(g,list(g[0]['cells'][0]['features']));calls=[]
    def fake(fun,x,**kwargs):
        calls.append(1);fun(x);raise TimeoutError('cap')
    out=repair.fit(g,prep,channel=channel,optimizer=fake)
    assert calls==[1]and out['status']=='fit_failed'and np.isfinite(out['parameters']).all()
    assert out['error_type']=='TimeoutError'
    g[-1]['cells'][0]['label']=None;calls.clear()
    with pytest.raises((ValueError,TypeError)):repair.fit(g,prep,channel=channel,optimizer=fake)
    assert calls==[]
