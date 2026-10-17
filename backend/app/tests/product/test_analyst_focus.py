from copy import deepcopy
from datetime import datetime,timezone
from unittest.mock import patch
import pandas as pd
import pytest
from backend.app.product_services.analyst_focus import prepare_focus,focused_world,audit_story,validate_contrarian,scan_contrarian
from backend.app.product_services.analyst_scenarios import run_merged,build_scenarios
from backend.app.product_services.optimizer import OptimizerService
from scripts.run_merged_analyst_fixture import scenario_fixture
from backend.app.tests.product.test_analyst_discovery import investigated_fixture
NOW=datetime(2099,9,1,12,tzinfo=timezone.utc)


def test_focus_scope_and_watchlist_do_not_authorize_generic_fallback():
    p,_=scenario_fixture('CLASSIC');sid=p['scenario_assumptions']['scenarios'][0]['scenario_id']
    with pytest.raises(ValueError,match='single game'):prepare_focus(p,{'analyst_scenario_focus_mode':'SELECTED_ONLY','analyst_scenario_focus_ids':[sid]},'CLASSIC')
    with pytest.raises(ValueError,match='existing canonical'):prepare_focus(p,{'analyst_scenario_focus_mode':'SELECTED_ONLY','analyst_scenario_focus_ids':['missing']},'CLASSIC')
    p,s= scenario_fixture('SHOWDOWN');sid=p['scenario_assumptions']['scenarios'][0]['scenario_id'];p['contrarian_analysis']={'contract_id':'contrarian_analysis_v1','findings':[{'scenario_id':sid,'status':'watchlist'}]}
    with pytest.raises(ValueError,match='Watchlist'):prepare_focus(p,{'analyst_scenario_focus_mode':'SELECTED_ONLY','analyst_scenario_focus_ids':[sid]},'SHOWDOWN')


def test_showdown_selected_story_conserves_budget_requires_relevant_captain_and_replays():
    p,s=scenario_fixture('SHOWDOWN');before=deepcopy(s);sid=p['scenario_assumptions']['scenarios'][0]['scenario_id'];params={'analyst_scenario_focus_mode':'SELECTED_ONLY','analyst_scenario_focus_ids':[sid],'max_exposure':1,'analyst_candidates_per_thesis':4}
    focused,report=prepare_focus(p,params,'SHOWDOWN');sc=build_scenarios(focused,s['players'],fmt='SHOWDOWN',decision_at=NOW.isoformat())[0];world=focused_world(sc,s['players'],focused);budget=world['opportunity_budget'];assert budget['baseline_total']==budget['conditional_total']==100 and budget['conditional_targets']+budget['conditional_carries']==pytest.approx(100)
    kwargs=dict(contest_type='captain',score_col='p90',stack_params={'enabled':False},locked_player_ids=set(),include_control_comparison=False)
    with patch('backend.app.product_services.analyst_scenarios.datetime') as clock:
        clock.now.return_value=NOW
        lineups,result=run_merged(OptimizerService.__new__(OptimizerService),pd.DataFrame(s['players']),params=params,packet=p,fmt='SHOWDOWN',season=2099,week=1,slate='SYNTHETIC_SHOWDOWN',requested=2,solve_kwargs=kwargs)
    assert len(lineups)==2 and result['focus']['selected_scenario_ids']==[sid] and result['packet_sha256']==__import__('backend.app.product_services.analyst_packets',fromlist=['packet_digest']).packet_digest(p)
    requirement=report['requirements'][0]
    for c in result['candidates']:
        if c['scores']:assert c['scenario_ids']==[sid] and audit_story(c['roster'],s['players'],requirement)
    assert s==before and result['quality_screen']=='none'


def test_classic_selected_only_never_generates_derived_unselected_opposite_branch():
    from backend.app.product_services.scenario_allocation import generate_allocated
    p,s,_,_=investigated_fixture();p.pop('discovery');sid=p['scenario_assumptions']['scenarios'][0]['scenario_id'];params={'analyst_scenario_focus_mode':'SELECTED_ONLY','analyst_scenario_focus_ids':[sid],'max_exposure':1}
    p,focus=prepare_focus(p,params,'CLASSIC');selected,worlds,selection,plan=generate_allocated(s,p,s['players'],params,2)
    assert selected
    allowed={(f['team'],f['script']) for f in focus['requirements']}
    assert all((i['team'],i['script']) in allowed for i in plan['ideas'])
    assert all(c['construction_audit']['passed'] for c in selected)
    assert not any(i['idea_id']==c['allocated_idea_id'] for i in plan['rejected_ideas'] for c in selected)


def test_contrarian_screen_covers_all_games_and_does_not_claim_unknown_ownership():
    p,s=scenario_fixture('CLASSIC');report=scan_contrarian(p,s['players'],fmt='CLASSIC',decision_at=NOW.isoformat())
    assert len(report['scanned_games'])==len(p['games']) and report['automatic_projection_mutation'] is False
    assert all(c['status']=='watchlist_research_required' and 'not asserted' in c['ownership_status'] for c in report['candidates'])


def test_explicit_user_what_if_stays_inactive_in_mixed_default():
    p,_=scenario_fixture('SHOWDOWN');sid=p['scenario_assumptions']['scenarios'][0]['scenario_id'];p['contrarian_analysis']={'contract_id':'contrarian_analysis_v1','findings':[{'scenario_id':sid,'status':'user_what_if'}]};original=deepcopy(p)
    normal,report=prepare_focus(p,{},'SHOWDOWN')
    assert sid not in {s['scenario_id'] for s in normal['scenario_assumptions']['scenarios']} and report['inactive_explicit_user_what_if_ids']==[sid] and p==original


def test_focused_user_what_if_captain_expansion_keeps_parent_lineage_and_story():
    from backend.app.tests.product.test_captain_analyst import captain_fixture
    from backend.app.product_services.analyst_packets import validate
    p,s=captain_fixture();sid=p['scenario_assumptions']['scenarios'][0]['scenario_id'];a=next(a for a in p['scenario_assumptions']['scenarios'][0]['assumptions'] if a['kind']=='passing_volume' and a['factor']>1)
    p['contrarian_analysis']={'contract_id':'contrarian_analysis_v1','findings':[dict(scenario_id=sid,game_id=a['game_id'],team=a['team'],script='passing',status='user_what_if',team_points_target=40,opportunity_shift=.18,source_ids=['synthetic'],as_of=NOW.isoformat(),mechanism='Explicit synthetic score-target what-if',conditions=['Successful drives'],counterevidence=['Unproven efficiency'],unknowns=['Likelihood'])]}
    assert not validate(p)
    kwargs=dict(contest_type='captain',score_col='p90',stack_params={'enabled':False},locked_player_ids=set(),include_control_comparison=False)
    params={'analyst_scenario_focus_mode':'SELECTED_ONLY','analyst_scenario_focus_ids':[sid],'max_exposure':1,'analyst_candidates_per_thesis':2}
    with patch('backend.app.product_services.analyst_scenarios.datetime') as clock:
        clock.now.return_value=NOW
        lineups,result=run_merged(OptimizerService.__new__(OptimizerService),pd.DataFrame(s['players']),params=params,packet=p,fmt='SHOWDOWN',season=2099,week=1,slate='SYNTHETIC_SHOWDOWN',requested=2,solve_kwargs=kwargs)
    assert len(lineups)==2 and all(l[0]['analyst_focus_story_compliance'] for l in lineups)
    assert all(sc['focus_requirement']['finding']['team_points_target']==40 for sc in result['scenario_definitions'])
