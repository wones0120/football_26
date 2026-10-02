from types import SimpleNamespace
from unittest.mock import patch
import pytest
from backend.app.product_services import classic_small_field as service
from backend.app.product_services.classic_portfolio_policy import build_contract,validate_portfolio
from backend.app.product_services.classic_prospective import resolve_risk_policy
from backend.app.product_services.gpp_optimizer import build_large_gpp_config,SlateAnalysis
from backend.app.tests.product.test_classic_small_field import _player


def row(qb,team,opp,score):
    return dict(player_ids=[qb]+[qb+str(i) for i in range(8)],objective_score=score,
                qb={'player_id':qb,'team':team,'opponent':opp},stack={'type':'QB+1'},
                roster=[{'player_id':qb,'position':'QB'}]+[{'player_id':qb+str(i),'position':'WR'} for i in range(8)])


def test_primary_game_cap_counts_both_qb_directions_but_not_oneoffs():
    rows=[row('a','A','B',10),row('b','B','A',9),row('c','C','D',8)]
    assert service._select_global(rows,2,1,set(),{},{},canonical_game_cap=1)==[0,2]
    c=build_contract(requested={'canonical_game_cap':1,'skill_max_appearances':1},count=2,max_exposure=1,maximums={},minimums={},locked=set(),controls=None,minimum_qbs=1,minimum_stacks=1,tradeoffs=None)
    assert validate_portfolio([rows[0],rows[2]],c)['status']=='verified'
    assert 'canonical_game_cap' in validate_portfolio(rows[:2],c)['violations']
    rows[2]['player_ids'][1]=rows[0]['player_ids'][1]
    rows[2]['roster'][1]=rows[0]['roster'][1]
    assert 'skill_max_appearances' in validate_portfolio([rows[0],rows[2]],c)['violations']


@pytest.mark.parametrize('count,expected_qb,expected_skill',[(1,1,1),(5,.6,.8)])
def test_automatic_multi_entry_caps_do_not_zero_one_entry(count,expected_qb,expected_skill):
    players=[_player(str(i),'AAA','BBB',pos,4000,10,20) for i,pos in enumerate(['QB','RB','RB','WR','WR','WR','TE','WR','DST'])]
    controls={'policy':resolve_risk_policy(None),'classifications':{p.player_id:{'bucket':'normal'} for p in players},'candidate_caps':{},'core_classes':{p.player_id:'regular' for p in players}}
    config=build_large_gpp_config(SlateAnalysis(game_count=1,chalk_concentration=0,feature_games=[]),ownership_available=False)
    class Reached(Exception):pass
    def select(*args,**kw):
        assert args[4].get('0',1)==expected_qb
        assert args[4].get('1',1)==expected_skill
        raise Reached
    with patch.object(service,'_admit_candidate_caps',side_effect=lambda c,l,*a:(c,l,{})),patch.object(service,'_select_global',side_effect=select):
        with pytest.raises(Reached):service.analyze_small_field(SimpleNamespace(lineups=[players]*count,config=config),pool_rows=[{'player_id':p.player_id,'gpp_player':p} for p in players],count=count,max_exposure=1,ownership_available=False,production_controls=controls,requested_candidate_count=count)


@pytest.mark.parametrize('key',['canonical_game_cap','skill_max_appearances'])
@pytest.mark.parametrize('value',[0,6,True,1.5])
def test_invalid_preferences_rejected_before_discovery(key,value):
    with pytest.raises(ValueError,match=key):
        service.analyze_small_field(None,pool_rows=[],count=5,max_exposure=1,ownership_available=False,portfolio_constraints={key:value})
