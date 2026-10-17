import numpy as np
import pandas as pd
import pytest

from backend.app.product_services.dedicated_dst_model import (
    FEATURES, build_features, checked_outcomes, choose_on_prior_weeks, learner,
)
from backend.app.product_services.dst_training_labels import SCORING_CONTRACT


def event(week, points=0):
    return dict(contract_id=SCORING_CONTRACT, coverage='complete_final_event_scoring',
                game_id=f'2025_{week:02d}_ARI_BUF', team='ARI', opponent='BUF', player_master_id='canonical-ari',
                dk_points=points, components=dict(sacks=0, interceptions=0, fumble_recoveries=0, points_allowed=20))


def source(events):
    return checked_outcomes(events, [dict(primary_team='ARI',player_master_id='canonical-ari')])


def target(week=3):
    return pd.DataFrame([dict(position='DST',season=2025,week=week,team='ARI',opponent='BUF',
                              player_master_id='canonical-ari',game_id=f'2025_{week:02d}_ARI_BUF',salary=2500)])


def test_strict_prior_weeks_verified_zero_and_unknown_history():
    outcomes=source([event(1,0),event(2,10),event(3,50),event(4,100)])
    features=build_features(target(),outcomes)
    assert features.dst_points_last3.iloc[0]==5
    assert features.dst_history_count.iloc[0]==2
    assert features.dst_home_from_game.iloc[0]==0
    assert features.opponent_conceded_last3.iloc[0]==5
    beginning=build_features(target(1),outcomes)
    assert beginning.dst_history_count.iloc[0]==0
    assert np.isnan(beginning.dst_points_last3.iloc[0])
    assert np.isnan(beginning.game_total_line.iloc[0])
    # Future and current-week truth cannot leak into past features.
    changed=outcomes.copy();changed.loc[changed.week>=3,'points']=-999
    pd.testing.assert_frame_equal(features,build_features(target(),changed))


@pytest.mark.parametrize('change',[dict(coverage='incomplete'),dict(contract_id='old'),
    dict(player_master_id='wrong'),dict(dk_points=None),dict(dk_points=float('nan'))])
def test_unverified_unknown_or_missing_scores_rejected(change):
    with pytest.raises(ValueError):
        source([dict(event(1),**change)])


def test_duplicate_scores_and_target_identity_rejected():
    with pytest.raises(ValueError,match='Duplicate'):
        source([event(1),event(1)])
    rows=source([event(1)])
    wrong=target();wrong['player_master_id']='wrong'
    with pytest.raises(ValueError,match='canonical'):
        build_features(wrong,rows)
    wrong=target();wrong['game_id']='2025_03_ARI_NE'
    with pytest.raises(ValueError,match='identity'):
        build_features(wrong,rows)
    wrong=target();wrong['position']='QB'
    with pytest.raises(ValueError,match='offensive'):
        build_features(wrong,rows)


def test_frozen_candidates_and_train_only_imputation():
    rows=pd.DataFrame(np.ones((10,len(FEATURES))),columns=FEATURES)
    rows.loc[0,'salary']=np.nan
    model=learner('ridge');model.fit(rows,np.arange(10))
    before=model.named_steps['missing'].statistics_.copy()
    model.predict(rows*100000)
    np.testing.assert_array_equal(before,model.named_steps['missing'].statistics_)
    assert model.named_steps['model'].alpha==100
    tree=learner('regularized_tree').named_steps['model']
    assert tree.max_depth==2 and tree.min_samples_leaf==30 and tree.l2_regularization==10
    assert not any('qb' in f.lower() for f in FEATURES)


def test_inner_selection_uses_prior_training_weeks_only():
    frame=pd.DataFrame(dict(season=[2025]*8,week=list(range(1,9)),label=[0.]*8))
    features=pd.DataFrame(np.ones((8,len(FEATURES))),columns=FEATURES)
    _,audit=choose_on_prior_weeks(frame,features,'label')
    assert audit['selected']=='median'
    assert all(r['train_last_week']<r['validation_first_week'] for r in audit['scores'])
    assert all(r['train_n']==5 and r['validation_n']==3 for r in audit['scores'])
