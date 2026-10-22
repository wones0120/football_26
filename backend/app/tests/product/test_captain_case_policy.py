from copy import deepcopy
import numpy as np
import pytest

from backend.app.product_services.captain_case_policy import preference,assessment,metrics
from backend.app.product_services.captain_case_variation import allocate,allocation_plan,profiles,allocate_passers,UNKNOWN


def test_preference_uses_post_condition_counts_without_changing_model_truth():
    policy=preference(dict(scenario_role_preference=dict(enabled=True,rb_min_opportunities=6,receiver_min_targets=3)))
    rb=dict(player_master_id='rb',position='RB',canonical_role='expected_backup',counts=dict(rush_attempts=4.,targets=.5),conditional_on='current normal role')
    original=deepcopy(rb)
    result=assessment(rb,policy)
    assert result['excluded'] and result['value']==4.5 and result['category']=='user_preference'
    assert rb==original
    assert not assessment({**rb,'world_activity':False},policy)['excluded']  # Factual nonparticipation is not a user exclusion.
    receiver=dict(player_master_id='wr',position='WR',canonical_role='expected_backup',counts=dict(rush_attempts=0.,targets=2.3))
    assert assessment(receiver,policy)['excluded']
    # A donor's injury alone must never fabricate recipient work or bypass a rule.
    receiver['teammate_injury']=dict(status='OUT')
    assert assessment(receiver,policy)['excluded']
    # The upstream sourced/conditioned forecast changes first, not the preference.
    expanded={**receiver,'counts':dict(rush_attempts=0.,targets=4.2),'conditional_on':'source-supported updated role, upstream forecast'}
    assert not assessment(expanded,policy)['excluded']
    assert receiver['counts']['targets']==2.3
    assert not assessment(rb,preference({}))['excluded']
    assert not assessment({**rb,'canonical_role':'expected_starter'},policy)['excluded']
    with pytest.raises(ValueError):preference(dict(scenario_role_preference=dict(enabled=True,rb_min_opportunities=float('nan'))))


def test_profile_balanced_counts_do_not_add_an_unsupported_opportunity_tail():
    # A conditional mean of four targets must not become nine from a second,
    # uncalibrated event draw. Joint profiles, not an arbitrary player cap,
    # provide workload variation.
    base={'backup':2.,'receiver':16.};factors={'backup':2.}
    for seed in range(20):
        counts=allocate(24,base,6.,factors,np.random.default_rng(seed))
        assert counts=={'backup':4,'receiver':14,UNKNOWN:6}
    assert base=={'backup':2.,'receiver':16.} and factors=={'backup':2.}
    # A sourced expanded role can legitimately exceed nine; no position ceiling.
    expanded=allocate(24,base,6.,{'backup':10.},np.random.default_rng(1))
    assert expanded['backup']==10 and sum(expanded.values())==24
    zero=allocate(10,{'backup':.2,'receiver':7.8},2.,{'backup':0},np.random.default_rng(1))
    assert zero['backup']==0 and zero[UNKNOWN]==2
    fractional=allocate(10,{'backup':.2,'receiver':7.8},2.,{},np.random.default_rng(1))
    assert fractional['backup']==0  # No automatic one-target floor.


def test_balanced_profile_rounding_conserves_unknowns_and_fractional_budget():
    import math
    for total in range(0,60):
        base={'a':1.4,'b':2.2,'c':7.3};factors={'a':0.,'b':1.7,'c':.8}
        plan=allocation_plan(total,base,4.1,factors)
        counts=allocate(total,base,4.1,factors,None)
        assert sum(counts.values())==total and counts[UNKNOWN]==plan['unknown_count']
        assert counts['a']==0
        for pid,expected in plan['conditional_expected'].items():
            assert math.floor(expected)<=counts[pid]<=math.ceil(expected)
        assert not plan['additional_count_noise']
    assert allocate(10,{'a':2.},8.,{'a':0.},None)=={'a':0,UNKNOWN:10}
    assert allocate(10,{},0.,{},None)=={UNKNOWN:10}
    for bad in [float('nan'),-1.,float('inf')]:
        with pytest.raises(ValueError):allocate(10,{'a':2.},8.,{'a':bad},None)


def test_joint_role_profiles_distinguish_observed_zero_from_missing_and_require_current_qb():
    history=[];games=[]
    for week,(completions,yards) in enumerate([(15,140),(21,240),(25,330)],1):
        period=202600+week
        games.append(dict(team='A',period=period,pass_attempts=30.,rush_attempts=20.,completions=completions,passing_yards=yards,source_ids=[week]))
        history.append(dict(team='A',period=period,player_master_id='qb',source_player_id='q',source_id=week,pass_attempts=30.,rush_attempts=2.,targets=0.))
        history.append(dict(team='A',period=period,player_master_id='backup',source_player_id='b',source_id=week+10,pass_attempts=0.,rush_attempts=0. if week==1 else 5.,targets=0. if week==1 else 1.))
        if week>1:history.append(dict(team='A',period=period,player_master_id='receiver',source_player_id='r',source_id=week+20,pass_attempts=0.,rush_attempts=0.,targets=4.))
    members={'qb':dict(canonical_role='expected_starter',counts=dict(pass_attempts=27.,rush_attempts=2.,targets=None)),
        'backup':dict(canonical_role='expected_backup',counts=dict(pass_attempts=None,rush_attempts=4.,targets=.5)),
        'receiver':dict(canonical_role='expected_backup',counts=dict(pass_attempts=None,rush_attempts=0.,targets=3.))}
    result=profiles(history,games,team='A',starter_id='qb',members=members,before_period=202604)
    low=result['profiles'][-1]
    assert low['period']==202601 and low['multipliers']['backup']['rush_attempts']==0 and low['multipliers']['backup']['targets']==0
    assert low['multipliers']['receiver']['targets']==1. and any(x['player_master_id']=='receiver' for x in low['unknowns'])
    assert min(p['completion_factor'] for p in result['profiles'])<1<max(p['completion_factor'] for p in result['profiles'])
    with pytest.raises(ValueError,match='current-starter'):profiles(history,games,team='A',starter_id='other',members=members,before_period=202604)


def test_coverage_prefers_more_complete_roster_success_cases_over_a_protected_floor():
    worlds=[dict(world_id=str(i),player_scores={'base':55.,'volatile':v,'safe':40.}) for i,v in enumerate((100.,100.,0.))]
    optimum={'0':155.,'1':155.,'2':95.}
    base=[dict(player_master_id='base',role='FLEX')]
    upside=metrics(base+[dict(player_master_id='volatile',role='FLEX')],worlds,optimum,.9)
    stable=metrics(base+[dict(player_master_id='safe',role='FLEX')],worlds,optimum,.9)
    assert upside['competitive_cases']==2 and stable['competitive_cases']==1
    assert upside['worst_capture_ratio']<stable['worst_capture_ratio']
    assert upside['selection_value']>stable['selection_value']


def test_passer_allocation_uses_observed_shares_and_retains_relief_trick_and_unlinked_work():
    profile=dict(starter_id='qb',observed_team_attempts=30.,passers=[
        dict(player_master_id='qb',source_player_id='native-qb',source_id=1,attempts=27.),
        dict(player_master_id='relief',source_player_id='native-relief',source_id=2,attempts=2.),
        dict(player_master_id='wr',source_player_id='native-wr',source_id=3,attempts=1.)])
    original=deepcopy(profile)
    result,audit=allocate_passers(30,profile,{'qb','wr'})
    assert result=={'qb':27,'wr':1,UNKNOWN:2} and profile==original
    assert sum(r['case_attempts'] for r in audit)==30
    assert next(r for r in audit if r['player_master_id']=='relief')['recipient']==UNKNOWN
    # A user/salary exclusion cannot turn the relief/trick-play shares into QB work.
    excluded,_=allocate_passers(30,profile,{'qb'})
    assert excluded=={'qb':27,UNKNOWN:3}
    unlinked=deepcopy(profile);unlinked['passers'][1]['player_master_id']=None
    assert allocate_passers(30,unlinked,{'qb','wr'})[0]==result
    full=dict(starter_id='qb',observed_team_attempts=30.,passers=[profile['passers'][0]|{'attempts':30.}])
    assert allocate_passers(39,full,{'qb'})[0]=={'qb':39,UNKNOWN:0}
    for n in range(45):assert sum(allocate_passers(n,profile,{'qb','wr'})[0].values())==n
    with pytest.raises(ValueError,match='sourced passer'):
        allocate_passers(30,profile|{'observed_team_attempts':31.},{'qb'})
