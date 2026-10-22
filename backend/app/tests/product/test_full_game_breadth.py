from copy import deepcopy
import pytest
from backend.app.product_services.full_game_breadth import strict_dk,role_universe,map_game,generate,legacy_select
from backend.app.product_services.scenario_breadth import generate_pool,signature
from backend.app.product_services.scenario_allocation import plan_slots,AllocationControls
from backend.app.tests.product.test_scenario_breadth import prepared


def stat(**values):
    names='passing_yards passing_tds passing_interceptions rushing_yards rushing_tds receptions receiving_yards receiving_tds passing_2pt_conversions rushing_2pt_conversions receiving_2pt_conversions special_teams_tds fumble_recovery_tds rushing_fumbles_lost receiving_fumbles_lost sack_fumbles_lost attempts completions targets carries'.split()
    return {**dict.fromkeys(names,0),**values}


def test_scoring_retains_negative_and_separate_bonuses_and_rejects_unknown():
    assert strict_dk(stat(passing_interceptions=3,sack_fumbles_lost=1))==-4
    assert strict_dk(stat(rushing_fumbles_lost=1,receiving_fumbles_lost=1))==-2
    assert strict_dk(stat(passing_yards=300,rushing_yards=100,receiving_yards=100))==41
    assert strict_dk(stat(passing_tds=2,receiving_tds=1,receiving_2pt_conversions=1,special_teams_tds=1))==22
    with pytest.raises(ValueError,match='Unknown'):strict_dk({**stat(), 'receiving_fumbles_lost':None})


def evidence(targets=0,carries=0):
    return {'historical':{k+'_mean_3':{'value':v,'status':'available'} for k,v in [('targets',targets),('carries',carries)]}}


def test_preference_exclusion_keeps_opportunity_and_backup_production_residual():
    full=[]
    for t in ['A','B']:
        full.extend([dict(player_id=t+'QB',position='QB',team=t,expected_depth_role='expected_starter',workload_evidence=evidence(carries=2)),
          dict(player_id=t+'D',position='DST',team=t),
          dict(player_id=t+'1',position='WR',team=t,included=False,user_preference_exclusions=['preference'],workload_evidence=evidence(targets=10)),
          dict(player_id=t+'2',position='WR',team=t,workload_evidence=evidence(targets=5))])
    eligible=[dict(r,player_master_id=r['player_id']) for r in full if r.get('included') is not False]
    universe,audit=role_universe(full,eligible)
    players=[dict(source_player_id='q',position='QB',prior={'attempts':30,'targets':0,'carries':2},stats=stat(passing_yards=100,completions=3),zero_basis=None),
      dict(source_player_id='backup',position='QB',prior={'attempts':1,'targets':0,'carries':0},stats=stat(passing_yards=20,completions=1),zero_basis=None),
      dict(source_player_id='w1',position='WR',prior={'attempts':0,'targets':10,'carries':0},stats=stat(receiving_yards=100,receptions=3,targets=4,special_teams_tds=1),zero_basis=None),
      dict(source_player_id='w2',position='WR',prior={'attempts':0,'targets':5,'carries':0},stats=stat(receiving_yards=20,receptions=1,targets=1),zero_basis=None)]
    template={'sides':[dict(team=t,players=deepcopy(players),dst=8,budget={}) for t in ['X','Y']]}
    points,ledger=map_game(template,'A','B',universe)
    assert points['A1']==16 and points['A2']==3 and points['AQB']==4
    assert any(a['position']=='RETURN_SPECIALIST' and a['residual'] and a['dk_points']==6 for a in ledger[0]['actors'])
    assert any(a['source_player_id']=='backup' and a['residual'] for a in ledger[0]['actors'])
    template['sides'][0]['players'][2]['stats']['receiving_yards']+=1
    with pytest.raises(ValueError,match='accounting'):map_game(template,'A','B',universe)
    with pytest.raises(ValueError,match='unknown opportunity'):role_universe(full,[*eligible,dict(player_master_id='unknown')])


def test_joint_state_generation_uses_frozen_legal_model_no_stack_injection():
    snapshot,rows,ideas,worlds=prepared();before=deepcopy(snapshot)
    states=[{'state_id':'low_pace','points':{r['player_id']:float(i%9) for i,r in enumerate(rows)}}]
    candidates,audit=generate(snapshot,states,{})
    assert len(candidates)==1 and len(candidates[0]['roster'])==9
    assert snapshot==before and audit['attempts'][0]['solver_status']=='Optimal'
    assert candidates[0]['conditional_state_score']==sum(states[0]['points'][p['player_master_id']] for p in candidates[0]['roster'])
    empty,audit=generate(snapshot,states,{'maximum_exposure_by_player':dict.fromkeys([r['player_id'] for r in rows],0)})
    assert empty==[] and audit['attempts'][0]['solver_status']=='Infeasible'


def test_bounded_generation_uses_one_thread_and_abstains_on_unproven_incumbent(monkeypatch):
    import pulp
    snapshot, rows, _, _ = prepared()
    states = [{'state_id':'bounded', 'points':{r['player_id']:1.0 for r in rows}}]
    def unproven(model, solver):
        assert solver.timeLimit == 2 and solver.threads == 1
        model.status = pulp.LpStatusOptimal
        model.sol_status = pulp.LpSolutionIntegerFeasible
    monkeypatch.setattr(pulp.LpProblem, 'solve', unproven)
    candidates, audit = generate(snapshot, states, {}, research_solver_seconds=2)
    assert not candidates and audit['attempts'][0]['solver_status'] == 'unproven_abstained'
    with pytest.raises(ValueError, match='budget'):
        generate(snapshot, states * 39, {}, research_solver_seconds=2)


def test_legacy_adapter_uses_construction_not_origin_and_underfills_honestly():
    snapshot,rows,ideas,worlds=prepared();plan=plan_slots(ideas,3,AllocationControls())
    pool,_=generate_pool(snapshot,rows,ideas,worlds,{},3)
    for c in pool:c['allocated_idea_id']='new_generator_label'
    selected,audit=legacy_select(pool,worlds,rows,{'max_lineup_overlap':5},3,plan)
    assert len(selected)==3 and not audit['constraints_relaxed'] and len({signature(c) for c in selected})==3
    empty,audit=legacy_select(pool,worlds,rows,{'maximum_exposure_by_player':dict.fromkeys([r['player_id'] for r in rows],0)},3,plan)
    assert empty==[] and audit['solver_status']=='underfilled'


def test_state_plan_is_seeded_symmetric_and_never_uses_target_outcomes():
    from backend.app.product_services.full_game_breadth import build_states
    full=[]
    for t in ['A','B']:
        full += [dict(player_id=t+'Q',position='QB',team=t,expected_depth_role='expected_starter',workload_evidence=evidence(carries=2)),dict(player_id=t+'D',position='DST',team=t)]
    eligible=[dict(r,player_master_id=r['player_id'],game_id='target',game_total_line=44,team_spread_line=-3 if r['team']=='A' else 3) for r in full]
    games=[]
    for i in range(20):
        sides=[]
        for t in ['X','Y']:
            p=dict(source_player_id=t,position='QB',prior={'attempts':30,'targets':0,'carries':2},stats=stat(carries=2,rushing_yards=i),zero_basis=None)
            sides.append(dict(team=t,players=[p],qb_prior_carries=2,dst=4,budget={'plays':50+i,'drives':10,'points':i+7,'targets':0,'carries':2}))
        games.append(dict(game_id=str(i),sides=sides,total_line=40+i/2,home_margin_line=3))
    library=dict(games=games,target_schedule=[dict(game_id='target',home_team='A',away_team='B',home_score=999)])
    a,audit=build_states(library,full,eligible);b,_=build_states(library,full,eligible)
    assert a==b and len(a)==11
    assert {s['state_id'] for s in a} >= {'favored_stalled:target','low_pace:target','productive_both:target'}
    assert all(s['points']['AD']==4 for s in a)
    assert audit['contexts']['target']['home_margin_line']==3
    assert all('999' not in str(s) for s in a)
