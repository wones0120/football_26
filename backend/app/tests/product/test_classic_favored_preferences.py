import pytest
from backend.app.product_services.classic_favored_preferences import favored_positions, is_favored
from backend.app.product_schemas import OptimizerRunRequest
from backend.app.product_services.optimizer import OptimizerService
from backend.app.tests.product.test_single_lineup import roster

@pytest.mark.parametrize('spread,expected', [(-3,True),(-.5,True),(0,False),(3,False),(None,False),('bad',False),(float('nan'),False),(float('-inf'),False),(False,False)])
def test_conventional_spread_and_unknowns(spread,expected):
    assert is_favored({'team_spread_line':spread}) is expected

@pytest.mark.parametrize('position,index', [('QB',0),('RB',1),('WR',3),('TE',6),('DST',8),('RB',7)])
def test_final_validation_checks_every_selected_position_including_flex(position,index):
    rows=roster()
    for row in rows:row['team_spread_line']=-3
    rows[index]['position']=position
    kwargs=dict(requested_lineups=1,max_exposure=1,enforce_single_te=False,avoid_dst_opponents=False,favored_team_positions={position})
    assert OptimizerService._validate_classic_lineups([rows],**kwargs)[0]
    for bad in [3,0,None]:
        rows[index]['team_spread_line']=bad
        ok,reason=OptimizerService._validate_classic_lineups([rows],**kwargs)
        assert not ok and 'favored-team' in reason
    assert OptimizerService._validate_classic_lineups([rows],**{**kwargs,'favored_team_positions':set()})[0]


def test_controls_default_off_and_validate_api():
    assert favored_positions({})==set()
    assert favored_positions({'force_favored_rb':1,'force_favored_dst':True})=={'RB','DST'}
    for bad in ['true',2,None,[],float('nan')]:
        with pytest.raises(ValueError,match='force_favored_qb'):
            OptimizerRunRequest(season=2026,week=5,slate='SUNDAY_MAIN',strategy='classic_large_gpp_v1',params={'force_favored_qb':bad})
    with pytest.raises(ValueError,match='Classic'):
        OptimizerRunRequest(season=2026,week=5,slate='SUNDAY_NIGHT',strategy='showdown_gpp_portfolio_v3',params={'force_favored_rb':1})
