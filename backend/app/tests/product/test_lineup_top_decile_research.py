from copy import deepcopy
import pytest
from backend.app.product_services.lineup_top_decile_research import top_decile_boundary,canonical_roster,lineup_features,CORE_FEATURES


def players():
    return [dict(player_id=str(i),role='CPT'if i==0 else'FLEX',position=['QB','WR','RB','TE','K','DST'][i],team='A'if i<3 else'B',game_id='G',mean=10.,p90=20.,salary=15000. if i==0 else 5000.)for i in range(6)]


def test_top10_is_within_field_and_includes_ties():
    boundary=top_decile_boundary([100,90,90,80,70,60,50,40,30,20,10])
    assert boundary['field_size']==11 and boundary['nominal_boundary_rank']==2 and boundary['positives']==3
    assert top_decile_boundary([1,0])['positives']==1


def test_canonical_roster_dedup_respects_captain():
    ps=players();assert canonical_roster(ps,'showdown')==canonical_roster(ps[::-1],'showdown')
    other=deepcopy(ps);other[0]['role']='FLEX';other[1]['role']='CPT'
    assert canonical_roster(ps,'showdown')!=canonical_roster(other,'showdown')
    other[1]['player_id']=other[0]['player_id']
    with pytest.raises(ValueError):canonical_roster(other,'showdown')


def test_features_have_no_postgame_inputs_and_captain_only_multiplies_points_once():
    ps=players();values=lineup_features(ps,'showdown');assert len(values)==len(CORE_FEATURES)
    assert dict(zip(CORE_FEATURES,values))['mean_sum']==65
    for p in ps:p.update(actual_points=999,actual_ownership=100,rank=1)
    assert lineup_features(ps,'showdown')==values
    ps[0]['mean']=None
    with pytest.raises(ValueError,match='no imputed'):lineup_features(ps,'showdown')


def test_optional_workload_is_unknown_not_zero_and_not_a_calibrated_target_forecast():
    ps=players()
    with pytest.raises(ValueError,match='recorded pregame workload'):lineup_features(ps,'showdown',rich=True)


def test_export_float_noise_does_not_split_official_cent_score_ties():
    boundary=top_decile_boundary([100.000001,99.999999]+[90]*8)
    assert boundary["positives"]==2 and boundary["points_cutoff"]==100


def test_portable_predictor_uses_frozen_standardizer_and_rejects_wrong_units():
    from backend.app.product_services.lineup_top_decile_research import predict_artifact,CONTRACT
    n=len(CORE_FEATURES)
    model=dict(contract_id=CONTRACT,features=CORE_FEATURES,mean=[0]*n,scale=[1]*n,coefficients=[0]*n,intercept=0)
    assert predict_artifact(model,[0]*n)==.5
    model['features']=['actual_points']
    with pytest.raises(ValueError,match='feature contract'):predict_artifact(model,[1])
