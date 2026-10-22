import pytest
from backend.app.product_services.role_transport_support import historical_vector,current_vectors,role_distance


def test_prior_share_normalization_and_unknown_current_never_filled():
    side={'prior_team_volume':{'targets':40,'carries':20},'players':[{'source_player_id':'te','position':'TE','prior':{'targets':10,'carries':0}}]}
    vector=historical_vector(side)
    assert vector[3]==.25 and vector[4]==0 and len(vector)==9
    assert role_distance(vector,vector,[1]*9)==0
    with pytest.raises(ValueError,match='denominator'):
        current_vectors([{'team':'A'}],{})
    with pytest.raises(ValueError,match='feature contract'):
        role_distance([1],[1,2],[1])
