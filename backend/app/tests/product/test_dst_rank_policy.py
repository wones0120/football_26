import numpy as np
import pandas as pd
import pytest

from backend.app.product_services.dst_rank_policy import rank_metrics, combine_predictions, fit_policies


def test_flat_forecasts_have_no_ordering_and_tie_aware_top_five():
    actual=np.array([0,1,2,3,10,20,30.])
    score=rank_metrics(actual,np.full(7,5.))
    assert score['pairwise_accuracy']==.5 and score['spearman']==0
    assert score['top5_actual']==pytest.approx(actual.mean())
    shuffled=np.array([6,0,4,2,1,5,3])
    assert rank_metrics(actual[shuffled],np.full(7,5.))==score


def test_partial_boundary_tie_fractional_inclusion_is_order_invariant():
    actual=np.array([20.,10.,2.,4.,6.,8.]);prediction=np.array([10.,9.,5.,5.,5.,1.])
    score=rank_metrics(actual,prediction,top_k=3)
    assert score['top5_actual']==pytest.approx((20+10+(2+4+6)/3)/3)
    order=np.arange(6)[::-1]
    assert rank_metrics(actual[order],prediction[order],top_k=3)==score


def test_rank_scores_use_only_distinct_actual_pairs_and_do_not_reward_variance():
    actual=np.array([1.,1.,3.])
    assert rank_metrics(actual,actual)['pairwise_pairs']==2
    assert rank_metrics(actual,actual)['pairwise_accuracy']==1
    assert rank_metrics(actual,-actual)['pairwise_accuracy']==0
    assert rank_metrics(actual,-actual)['prediction_std']>0
    with pytest.raises(ValueError):rank_metrics([1,np.nan],[1,2])


def test_ensemble_uses_fixed_weights():
    result=combine_predictions(5.,np.array([1.,9.]),np.array([3.,7.]))
    np.testing.assert_array_equal(result['ensemble'],[3.5,6.5])
    np.testing.assert_array_equal(result['median'],[5.,5.])


def test_temporal_policy_keeps_median_and_training_prefix_separate():
    frame=pd.DataFrame([dict(season=2025,week=week,x=float(index),label=5.) for week in range(1,9) for index in range(10)])
    fitted=fit_policies(frame,['x'],target='label')
    assert fitted.mae_choice==fitted.rank_choice=='median'
    assert fitted.audit['fits']==4 and fitted.audit['inner_prefix_last_week']<fitted.audit['inner_first_week']
    assert fitted.audit['inner_n']==30
    np.testing.assert_array_equal(fitted.predict(frame,policy='rank_selector'),np.full(len(frame),5.))
    before=fitted.models['ridge'].named_steps['missing'].statistics_.copy()
    fitted.predict(frame.assign(x=1e9),policy='ensemble')
    np.testing.assert_array_equal(before,fitted.models['ridge'].named_steps['missing'].statistics_)
