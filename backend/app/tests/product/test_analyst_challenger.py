from copy import deepcopy
import pulp
from backend.app.tests.product.test_analyst_discovery import investigated_fixture
from backend.app.product_services.scenario_allocation import AllocationControls,build_ideas,generate_allocated
from backend.app.product_services.analyst_challenger import ChallengerControls,vulnerabilities,hunt,canonical_roster,feasible_portfolio


def dependent_fixture():
    packet,snapshot,_,_=investigated_fixture();packet.pop('discovery')
    for r in snapshot['players']:r['predicted_p10']=r['projection']*.1
    ideas,_=build_ideas(packet,snapshot['players'],AllocationControls());idea=next(i for i in ideas if i['script']=='run_control');pid=idea['eligible_receiver_ids'][0]
    locked=deepcopy(snapshot);variables,model=pulp.LpProblem.fromDict(locked['model']);var=next(n for n,r in locked['variable_players'].items() if r['player_master_id']==pid);model+=variables[var]==1;locked['model']=model.toDict()
    candidates,worlds,_,plan=generate_allocated(locked,packet,snapshot['players'],{},5)
    assert len(candidates)==5 and all(pid in {p['player_master_id'] for p in c['roster']} for c in candidates)
    return packet,snapshot,ideas,candidates,worlds,pid


def test_heavy_core_and_expensive_rb_dependence_are_identified_and_captain_dedup_is_role_aware():
    rows=[dict(player_id=str(i),position='RB',player_team='A',salary=7000,projection=20,name=str(i)) for i in range(4)]
    candidates=[dict(roster=[dict(player_master_id='0',role='SELECTED'),dict(player_master_id='1',role='SELECTED'),dict(player_master_id=str(2+i%2),role='SELECTED')]) for i in range(5)]
    v,a=vulnerabilities(candidates,rows,ChallengerControls());assert v[0]['appearances']==5 and a['expensive_rb_groups']
    a=dict(roster=[dict(player_master_id='a',role='CPT'),dict(player_master_id='b',role='FLEX')]);b=dict(roster=[dict(player_master_id='a',role='FLEX'),dict(player_master_id='b',role='CPT')]);assert canonical_roster(a)!=canonical_roster(b)


def test_credible_counter_search_is_bounded_legal_and_improves_real_condition_coverage():
    p,s,ideas,candidates,worlds,pid=dependent_fixture();params={'analyst_challenger_controls':{'max_solver_calls':1,'minimum_coverage_gain':0}}
    selected,expanded,report=hunt(s,p,s['players'],candidates,ideas,worlds,params,5,AllocationControls(),{'reserved_idea_ids':[]})
    assert report['solver_calls']<=1 and report['accepted_candidate_count']==1
    admitted=next(a for a in report['attempts'] if a['status']=='admitted');assert admitted['classification']=='generation_gap' and admitted['relative_coverage_gain']>0
    novel=next(c for c in report['candidate_pool'] if c.get('challenger_vulnerability_id'));assert pid not in {p['player_master_id'] for p in novel['roster']} and novel['construction_audit']['passed']
    assert len(novel['roster'])==9 and feasible_portfolio(selected,s['players'],params,5,AllocationControls(),[])
    assert report['quality_screen']=='none' and report['constraints_relaxed'] is False
    assert len(expanded)>len(worlds)
    # An already-generated unselected counter roster closes a selection gap with no solve.
    reused,_,again=hunt(s,p,s['players'],candidates,ideas,worlds,params,5,AllocationControls(),{'reserved_idea_ids':[]},candidate_pool=report['candidate_pool'])
    assert any(a['classification']=='selection_gap' and a['status']=='existing_candidate_supported' for a in again['attempts'])
    assert again['accepted_candidate_count']==0


def test_locks_unsupported_and_infeasible_scenarios_remain_explicit_without_relaxation():
    p,s,ideas,candidates,worlds,pid=dependent_fixture()
    _,_,locked=hunt(s,p,s['players'],candidates,ideas,worlds,{'locked_player_ids':[pid]},5,AllocationControls(),{'reserved_idea_ids':[]})
    assert any(a['classification']=='unavoidable_locked_dependence' for a in locked['attempts'])
    selected,_,unsupported=hunt(s,p,s['players'],candidates,[],worlds,{},5,AllocationControls(),{'reserved_idea_ids':[]});assert selected and unsupported['solver_calls']==0
    variables,model=pulp.LpProblem.fromDict(deepcopy(s['model']));model+=variables[next(iter(variables))]<=-1;s['model']=model.toDict()
    _,_,bad=hunt(s,p,s['players'],candidates,ideas,worlds,{},5,AllocationControls(),{'reserved_idea_ids':[]});assert any(a.get('solver_status')=='Infeasible' for a in bad['attempts'])
    assert bad['constraints_relaxed'] is False
