import pytest
from backend.app.product_services.lineup_ablation_research import CONTRACT,SALARY,STACKING,active_indices,predict
from backend.app.product_services.lineup_top_decile_research import CORE_FEATURES,RICH_FEATURES


def test_ablation_removes_whole_declared_groups_retains_football_projections():
    names=CORE_FEATURES+RICH_FEATURES
    removed=[names[i]for i in active_indices(names,'remove_both')]
    assert not(set(removed)&(SALARY|STACKING))
    assert {'mean_sum','marginal_p90_spread_sum','min_skill_workload','total_line_mean'}<=set(removed)
    assert active_indices(names,'original')==list(range(len(names)))
    with pytest.raises(ValueError,match='contract'):active_indices(names,'handpicked')


def test_portable_retrained_model_uses_active_columns_not_zeroed_old_coefficients():
    names=CORE_FEATURES;indices=active_indices(names,'remove_salary');active=[names[i]for i in indices]
    artifact={'contract_id':CONTRACT,'base_features':names,'treatment':'remove_salary','features':active,'mean':[0]*len(active),'scale':[1]*len(active),'coefficients':[0]*len(active),'intercept':0}
    full=[1]*len(names);first=predict(artifact,full)
    for name in SALARY:full[names.index(name)]=10**9
    assert first==predict(artifact,full)==.5
    artifact['features'][0]='actual_score'
    with pytest.raises(ValueError,match='identity'):predict(artifact,full)
