from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from backend.app.product_services.dst_feature_pipeline import DstFeatureContext, repair_dst_frame, prepare_candidate_frames
from backend.app.product_services.canonical_projection_inputs import load_dst_candidate_inputs
from backend.app.services.lineup_learning import LineupLearningService
from backend.app.tests.product.test_dedicated_dst_model import event, source, target


def context():
    events=[event(1,0),event(2,10),dict(event(3,50),game_id='2025_03_BUF_ARI')]
    return DstFeatureContext(source(events),'checked-events','checked-identities','retrospective')


def test_matrix_real_home_and_history_feed_identical_train_and_predict_fields():
    row=target();row['game_id']=None;row['is_home']=0;row['player_games_history']=0;row['dk_points']=0.
    ctx=context()
    generated,audit=repair_dst_frame(row,ctx,matrix_generation=True)
    assert generated.game_id.iloc[0]=='2025_03_BUF_ARI'
    assert generated.is_home.iloc[0]==1
    assert generated.player_games_history.iloc[0]==2
    assert generated.player_roll3_mean.iloc[0]==5
    assert generated.dk_points.iloc[0]==50
    train,prediction,metadata=prepare_candidate_frames(generated,generated,ctx)
    pd.testing.assert_frame_equal(train,prediction)
    assert metadata['training']['policy']==metadata['prediction']['policy']
    assert not audit['live_enabled']


def test_future_labels_missing_and_real_zero_retained_without_leakage():
    row=target(1);row['game_id']='2025_01_ARI_BUF';row['dk_points']=99.
    generated,_=repair_dst_frame(row,context(),matrix_generation=True)
    assert generated.dk_points.iloc[0]==0
    assert np.isnan(generated.player_roll3_mean.iloc[0])
    future=target(4);future['dk_points']=0.
    generated,_=repair_dst_frame(future,context(),matrix_generation=True)
    assert np.isnan(generated.dk_points.iloc[0])
    changed=context();changed.outcomes.loc[changed.outcomes.week>=3,'points']=-99
    before,_=repair_dst_frame(target(3).assign(game_id=None),context())
    after,_=repair_dst_frame(target(3).assign(game_id=None),changed)
    pd.testing.assert_frame_equal(before,after)


def test_offense_cells_unchanged_and_candidate_loader_is_explicit():
    dst=target().assign(game_id=None,is_home=0,player_games_history=0)
    offense=dst.copy();offense['position']='QB';offense['player_master_id']='offense';offense['is_home']=1
    frame=pd.concat([dst,offense],ignore_index=True)
    repaired,_=repair_dst_frame(frame,context())
    pd.testing.assert_frame_equal(frame.loc[[1]],repaired.loc[[1],frame.columns],check_dtype=False)
    with patch('backend.app.product_services.canonical_projection_inputs.load_inputs',return_value=(frame,frame,{'legacy':True})) as normal, patch('backend.app.product_services.dst_training_labels.select_corrected_dst_labels',return_value=(frame,{'verified':True})) as labels:
        train,pred,metadata=load_dst_candidate_inputs(None,dst_candidate_context=context(),dst_label_dataset={'verified':True},season=2025,week=3)
    assert normal.call_count==1 and metadata['legacy'] and not metadata['live_enabled']
    assert labels.call_count==1 and metadata['dst_candidate_labels']['verified']
    assert train.loc[0,'is_home']==pred.loc[0,'is_home']==1


def test_generation_opt_in_cannot_persist_and_actual_service_returns_repaired_rows():
    session=MagicMock();service=LineupLearningService(session)
    with pytest.raises(ValueError,match='persist=False'):
        service.rebuild_player_game_feature_matrix(source_system='draftkings',season_start=2025,season_end=2025,dst_candidate_context=context())
    session.execute.assert_not_called()
    player=SimpleNamespace(position='DST',team='ARI',uid='ARI',player_master_id='canonical-ari',
        source_player_key='native-dst',name='Cardinals',opponent='BUF',salary=2500,actual_points=0,
        game_total_line=45.,team_spread_line=0.,team_implied_total=22.5,opponent_implied_total=22.5)
    service._projection_feature_cache={('draftkings',2025,3,'MAIN'):{'placeholder':{}}}
    session.execute.return_value.scalars.return_value.all.return_value=[]
    with patch.object(service,'_fetch_available_slate_slices',return_value=[(2025,3,'MAIN')]), patch.object(service,'_compute_player_projection_lookup',return_value=({},{})), patch.object(service,'_fetch_slate_player_pool',return_value=[player]):
        result=service.rebuild_player_game_feature_matrix(source_system='draftkings',season_start=2025,season_end=2025,dst_candidate_context=context(),persist=False)
    assert result['slates_failed']==0 and result['rows_written']==0 and not result['live_enabled']
    row=result['candidate_rows'][0]
    assert row['is_home']==1 and row['player_roll3_mean']==5 and row['dk_points']==50
    session.commit.assert_not_called();session.bulk_insert_mappings.assert_not_called()
    assert all(str(call.args[0]).lstrip().startswith('SELECT') for call in session.execute.call_args_list)


def test_artifact_predictor_receives_repaired_home_history_and_cannot_score_training():
    from backend.app.product_services.dst_feature_pipeline import score_dst_candidate_bundle
    train=target(2).assign(label_dk_total_points=10.)
    model=MagicMock();model.predict.return_value=np.array([7.])
    columns=['is_home','player_roll3_mean','player_games_history']
    bundle=dict(training=train,context=context(),models={'repaired_dedicated':model},metadata={'dedicated_columns':columns})
    prediction,audit=score_dst_candidate_bundle(bundle,target().assign(game_id=None))
    inputs=model.predict.call_args.args[0]
    assert inputs.iloc[0].tolist()==[1.,5.,2.]
    assert prediction['mean'].tolist()==[7.] and not audit['persisted']
    with pytest.raises(ValueError,match='overlap'):
        score_dst_candidate_bundle(bundle,train)
