from copy import deepcopy
from itertools import combinations
from unittest.mock import patch
import numpy as np
import pytest
from backend.app.product_services import captain_scenario_research as research


def fixture():
    positions=['QB','RB','WR','WR','TE']*2
    players=[dict(id=f'p{i:02}',name=f'Player {i}',team='HOME' if i<5 else 'AWAY',position=pos,salary=4000,captain_salary=6000,projected_mean=float(20-i),projected_p90=float(35-i),high_rushing=pos=='QB') for i,pos in enumerate(positions)]
    game=dict(game='target',cutoff='2026-10-12T12:00:00+00:00',kickoff='2026-10-13T00:00:00+00:00',home='HOME',implied_scores=[27,24],players=players,rules=dict(leader_ids=['p01','p06'],qb_correlations=True),pricing='native')
    keys=research.role_keys(players,'HOME')
    blocks=[dict(game=f'history{i}',available_at='2026-10-01T00:00:00+00:00',kickoff='2026-09-30T00:00:00+00:00',score_errors=[i*4-10,10-i*4],role_errors={key:float((i+index)%5-2) for index,key in enumerate(keys.values())}) for i in range(8)]
    return game,blocks


def test_scenario_boundaries_and_complete_partition():
    scores=np.array([[24,24],[20,20],[31,17],[17,31],[20,6],[6,20],[30,17]])
    assert research.classify(scores).tolist()==[0,1,2,3,4,5,1]


def test_shortlist_includes_qbs_and_canonical_ties():
    game,_=fixture();players=game['players']
    players[5]['projected_p90']=players[0]['projected_p90']
    assert research.shortlist(players)[:2]==['p00','p05']
    players[0]['captain_excluded']=True
    assert 'p00' not in research.shortlist(players)


def test_seed_replay_joint_blocks_and_cutoff_rejection():
    game,blocks=fixture()
    a,labels,audit=research.simulate(game,blocks,draws=100,seed=7)
    b,labels2,audit2=research.simulate(game,blocks,draws=100,seed=7)
    assert np.array_equal(a,b) and np.array_equal(labels,labels2)
    assert audit['draws_sha256']==audit2['draws_sha256']
    # Each outcome row must be one complete historical residual vector.
    expected=[np.array([p['projected_mean']+block['role_errors'][research.role_keys(game['players'],game['home'])[p['id']]] for p in game['players']]) for block in blocks]
    assert all(any(np.array_equal(row,v) for v in expected) for row in a)
    blocks[0]['available_at']=game['cutoff']
    with pytest.raises(ValueError,match='unavailable'):research.simulate(game,blocks,draws=100,seed=7)


def test_solver_matches_brute_force_and_constraints():
    game,_=fixture();ps=game['players'];scores=np.arange(10,dtype=float);capt='p00'
    result=research.solve(ps,capt,scores,game['rules'])
    legal=[ix for ix in combinations(range(10),6) if research.legal([ps[i] for i in ix],capt,game['rules']) and 0 in ix]
    assert scores[result['indices']].sum()==max(scores[list(ix)].sum() for ix in legal)
    expensive=deepcopy(ps[:6])
    for p in expensive:p['salary']=8000;p['captain_salary']=12000
    assert not research.legal(expensive,capt,{})
    assert not research.legal(ps[:6],capt,{'leader_ids':['absent']})


def test_weighted_rates_equal_unconditional_rate_and_empty_scenarios():
    values=np.array([10.,20.,30.]);labels=np.array([0,0,1]);threshold=np.array([15.,15.,15.])
    m=research.metrics(values,labels,threshold)
    assert m['high_finish_rate']==pytest.approx(2/3)
    assert m['weighted_high_finish_rate']==pytest.approx(2/3)
    assert m['scenarios'][2]['high_finish_rate'] is None


def test_evaluation_outcomes_and_actuals_cannot_change_selection():
    game,blocks=fixture();game['actuals']={'p00':{'points':99999}}
    original=research.simulate
    r1=research.research_game(game,blocks,draws=100,seed=7,reference_limit=25)
    def altered(*args,**kwargs):
        out,labels,audit=original(*args,**kwargs)
        if kwargs['seed']==9:out=out[:,::-1]*20
        return out,labels,audit
    game['actuals']={}
    with patch.object(research,'simulate',side_effect=altered):
        r2=research.research_game(game,blocks,draws=100,seed=7,reference_limit=25)
    for arm in ('baseline','simulation_baseline','selected'):
        assert r1[arm]['captain_id']==r2[arm]['captain_id']
        assert r1[arm]['indices']==r2[arm]['indices']
    assert r1['selected']['evaluation']['mean']!=r2['selected']['evaluation']['mean']


def test_timezone_equivalent_cutoff_is_rejected():
    game,blocks=fixture()
    blocks[0]['available_at']='2026-10-12T08:00:00-04:00'
    with pytest.raises(ValueError,match='unavailable'):
        research.simulate(game,blocks,draws=100,seed=7)


def test_negative_fantasy_scores_are_retained():
    game,blocks=fixture()
    for b in blocks:
        b['role_errors']={key:-100. for key in b['role_errors']}
    values,_,audit=research.simulate(game,blocks,draws=100,seed=7)
    assert (values<0).all()
    assert audit['negative_fantasy_outcomes_retained']==values.size
