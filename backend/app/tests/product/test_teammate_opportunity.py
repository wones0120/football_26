from copy import deepcopy
import pulp,pytest
from backend.app.tests.product.test_analyst_discovery import investigated_fixture
from backend.app.product_services.scenario_allocation import AllocationControls,build_ideas
from backend.app.product_services.teammate_opportunity import TeammateControls,scan_pairs,paired_world,investigate


def pair_fixture():
    p,s,_,_=investigated_fixture();p.pop('discovery')
    for r in s['players']:
        if r['position']=='RB':
            r['canonical_role']='expected_starter' if int(r['player_id'][-3:],16)%8==2 else 'expected_backup';r['role_source']='fixture_canonical_depth';r['projected_carries']=10 if r['canonical_role']=='expected_starter' else 5;r['projected_targets']=2
    ideas,_=build_ideas(p,s['players'],AllocationControls());return p,s,ideas


def test_all_game_scan_retains_salary_status_and_role_rejections():
    p,s,ideas=pair_fixture();source=deepcopy(s['players'])
    # Make a canonical backup cheaper and explicitly Q excluded; do not infer a vacancy.
    primary=next(r for r in source if r['position']=='RB' and r['canonical_role']=='expected_starter');backup=next(r for r in source if r['position']=='RB' and r['player_team']==primary['player_team'] and r['player_id']!=primary['player_id']);backup['salary']=primary['salary']-1000;backup['availability_status']='Q'
    games,pairs,_=scan_pairs(p,source,[r for r in s['players'] if r['player_id']!=backup['player_id']],ideas,{'exclude_questionable':True},TeammateControls())
    assert len(games)==len(p['games'])
    assert any(x['backup_id']==backup['player_id'] and 'not an absence fact' in x['reason'] for x in pairs)


def test_share_conservation_and_expected_vs_conditional_are_distinct_without_base_mutation():
    p,s,ideas=pair_fixture();before=deepcopy(s['players']);idea=next(i for i in ideas if i['script']=='run_control');members=[r for r in s['players'] if r['player_team']==idea['team'] and r['position']=='RB'];pair=dict(team=idea['team'],channel='carries',backup_id=members[1]['player_id'],pair_id='test')
    world=paired_world(idea,pair,s['players'],p,AllocationControls(),TeammateControls())
    budget=world['paired_opportunity_budget'];assert budget['sum_before']==pytest.approx(budget['sum_after'])==1
    assert budget['conditional_shares'][pair['backup_id']]>budget['base_shares'][pair['backup_id']]
    assert s['players']==before
    members[1]['projected_carries']=None
    with pytest.raises(ValueError,match='budget unavailable'):paired_world(idea,pair,s['players'],p,AllocationControls(),TeammateControls())


def test_bounded_same_branch_pair_is_legal_and_reports_whole_roster_cost():
    p,s,ideas=pair_fixture();idea=next(i for i in ideas if i['script']=='run_control' and i['team']!='AAA');backs=[r for r in s['players'] if r['player_team']==idea['team'] and r['position']=='RB'];backs[0].update(canonical_role='expected_starter',salary=6500);backs[1].update(canonical_role='expected_backup',salary=4500)
    variables,model=pulp.LpProblem.fromDict(deepcopy(s['model']));lookup={r['player_id']:r for r in s['players']}
    model+=pulp.lpSum(float(lookup[ref['player_master_id']]['salary'])*variables[n] for n,ref in s['variable_players'].items())<=50000;s['model']=model.toDict()
    report=investigate(s,p,s['players'],s['players'],ideas,{'analyst_teammate_point_checks':{backs[1]['player_id']:[10,15]}},AllocationControls())
    assert report['solver_calls']<=6 and report['automatic_portfolio_promotion'] is False and report['baseline_mutation'] is False
    pair=next(x for x in report['pairs'] if x['primary_id']==backs[0]['player_id'] and x['backup_id']==backs[1]['player_id'])
    assert pair['status']=='paired_evaluated'
    for b in pair['branches'].values():assert len(b['roster'])==9 and b['salary']<=50000 and b['required_player_id'] in {r['player_master_id'] for r in b['roster']} and b['omitted_player_id'] not in {r['player_master_id'] for r in b['roster']}
    assert len(pair['conditional_point_checks'])==2 and 'not expected' in pair['conditional_point_checks'][0]['classification']
    assert 'conditional_score_delta' in pair and 'salary_saved_reinvested' in pair and 'secondary_points_break_even' in pair
    # A lock on the primary remains binding and makes the alternative infeasible.
    variables,model=pulp.LpProblem.fromDict(deepcopy(s['model']));n=next(n for n,r in s['variable_players'].items() if r['player_master_id']==backs[0]['player_id']);model+=variables[n]==1;s['model']=model.toDict()
    locked=investigate(s,p,s['players'],s['players'],ideas,{},AllocationControls());pair=next(x for x in locked['pairs'] if x['primary_id']==backs[0]['player_id'] and x['backup_id']==backs[1]['player_id']);assert pair['status']=='infeasible'


def test_saved_choice_requires_identical_completed_source_packet_and_projection():
    from types import SimpleNamespace
    from backend.app.product_services.teammate_opportunity import validate_choice,digest
    from backend.app.product_services.analyst_packets import packet_digest
    p,s,_=pair_fixture();params={'analyst_teammate_choice':{'source_optimizer_run_id':'source','pair_id':'pair','branch':'cheaper'}}
    job=SimpleNamespace(status='completed',projection_run_id='projection',params={'strategy_runtime':{'football_analyst':{'packet_sha256':packet_digest(p),'teammate_opportunity':{'source_rows_sha256':digest(s['players']),'pairs':[{'pair_id':'pair','status':'paired_evaluated','branches':{'cheaper':{'solver_status':'Optimal'}}}]}}}})
    service=SimpleNamespace(get_job=lambda _:job)
    validate_choice(service,params,p,s['players'],'projection')
    with pytest.raises(ValueError,match='matching projection'):validate_choice(service,params,p,s['players'],'other')
    changed=deepcopy(s['players']);changed[0]['salary']+=100
    with pytest.raises(ValueError,match='snapshot mismatch'):validate_choice(service,params,p,changed,'projection')
    job.status='failed'
    with pytest.raises(ValueError,match='completed matching'):validate_choice(service,params,p,s['players'],'projection')


def test_explicit_choice_keeps_hard_portfolio_revalidation_and_no_quality_veto(monkeypatch):
    from backend.app.product_services.teammate_opportunity import apply_choice
    from backend.app.product_services import analyst_challenger
    p,s,ideas=pair_fixture();rows=s['players'];before=deepcopy(rows)
    selected=[{'roster':[{'player_master_id':r['player_id'],'role':'SELECTED'} for r in rows[:9]],'allocated_idea_id':'reserved','discovery_finding_ids':['finding']}]
    world={'scenario_id':'conditional','means':{r['player_id']:1 for r in rows},'p90':{r['player_id']:2 for r in rows},'opportunity_budget':{}}
    pair={'pair_id':'pair','status':'paired_evaluated','idea_id':'idea','score_improves':False,'conditional_world':world,'branches':{'cheaper':{'roster':[{'player_master_id':r['player_id']} for r in rows[-9:]]}}}
    params={'analyst_teammate_choice':{'source_optimizer_run_id':'source','pair_id':'pair','branch':'cheaper'},'player_locks':['locked'],'max_exposure':.5}
    calls=[]
    def reject(portfolio,received_rows,received_params,n,controls,reservations):
        calls.append((received_params,reservations));return False
    monkeypatch.setattr(analyst_challenger,'feasible_portfolio',reject)
    monkeypatch.setattr(analyst_challenger,'metric',lambda *_:0)
    with pytest.raises(ValueError,match='no relaxation'):apply_choice(selected,[],{'pairs':[pair]},rows,params,AllocationControls(),{'reserved_idea_ids':['reserved']})
    assert calls[0]==(params,['reserved']) and rows==before
    monkeypatch.setattr(analyst_challenger,'feasible_portfolio',lambda *_:True)
    report={'pairs':[pair]};out,worlds=apply_choice(selected,[],report,rows,params,AllocationControls(),{'reserved_idea_ids':['reserved']})
    assert len(out)==1 and out[0]['teammate_pair_id']=='pair' and report['applied_choice']['negative_conditional_cost_accepted_by_explicit_choice'] is True
    assert report['applied_choice']['constraints_relaxed'] is False and rows==before
    assert report['mode']=='APPLIED_CONDITIONAL_ALTERNATIVE' and 'replaced one allocation slot' in report['portfolio_effect']
