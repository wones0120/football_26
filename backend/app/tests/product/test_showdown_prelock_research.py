from copy import deepcopy
import json

import pandas as pd
import pulp
import pytest

from backend.app.product_services.classic_prospective import digest_payload
from backend.app.product_services.optimizer import OptimizerService
from backend.app.product_services.rule_library import resolve_strategy_profile
from backend.app.product_services.showdown_single_entry import select_single_entry_lineups, DEFAULT_WEIGHTS
from scripts.finalize_showdown_prelock_shadow import mask_diagnostic_ownership, read_frozen
from scripts.research_showdown_prelock import (
    capture_model, render_solution, signature, thesis, validate_lineup, joint_portfolio,
)


def pool():
    rows = []
    for team in ('PIT','CLE'):
        for index,position in enumerate(('QB','WR','WR','RB','TE','K','DST')):
            rows.append({'player_id':f'{team}-{index}','name':f'{team}-{index}',
                'player_team':team,'opponent_team':'CLE' if team=='PIT' else 'PIT',
                'position':position,'salary':4500+100*index,'projection':14-index,
                'p90':25-index,'optimizer_context_ceiling_score':25.1-index,
                'optimizer_context_adjustment':.1,'captain_objective_multiplier':1.05,
                'showdown_qb_eligible':True,'pregame_availability_probability':1.,
                'game_total_line':38.5,'team_implied_total':20.5 if team=='PIT' else 18.,
                'team_spread_line':-2.5 if team=='PIT' else 2.5})
    return pd.DataFrame(rows)


def solved():
    frame = pool()
    profile = resolve_strategy_profile(contest_format='showdown',objective='gpp')
    stack = {'hard_qb_correlations':True,'require_starting_qb':True,'saturate_correlations':True,
             'opportunity_gate':True,'use_role_ownership':False,'ownership_weight':.08}
    kwargs = {'contest_type':'captain','score_col':'optimizer_context_ceiling_score',
              'stack_params':stack,'rule_profile':profile,'include_control_comparison':False}
    service = OptimizerService.__new__(OptimizerService)
    model = capture_model(service,frame,kwargs)
    assert model.solve(pulp.PULP_CBC_CMD(msg=False)) == pulp.LpStatusOptimal
    return frame,profile,stack,kwargs,service,model


def test_captured_model_and_render_match_production_objective_and_roster():
    frame,profile,stack,kwargs,service,model = solved()
    rendered = render_solution(frame,model,model.objective,stack,profile)
    original = service._solve_lineup(frame,**kwargs)
    assert signature(rendered) == signature(original)
    assert rendered[0]['solver_objective_value'] == pytest.approx(original[0]['solver_objective_value'])
    for field in ('salary','projection','p90'):
        assert sum(row[field] for row in rendered) == pytest.approx(sum(row[field] for row in original))


@pytest.mark.parametrize('failure', ['duplicate','slots','salary','out','one_team'])
def test_legality_validation_rejects_material_failures(failure):
    frame,profile,stack,kwargs,service,model = solved()
    lineup = render_solution(frame,model,model.objective,stack,profile)
    if failure=='duplicate':lineup[1]['player_id']=lineup[0]['player_id']
    elif failure=='slots':lineup[1]['roster_position']='CPT'
    elif failure=='salary':lineup[0]['salary']=50001
    elif failure=='out':lineup[0]['pregame_availability_probability']=0
    elif failure=='one_team':
        for row in lineup:row['player_team']='PIT'
    with pytest.raises(ValueError):validate_lineup(lineup)


def test_diagnostic_ownership_is_uniformly_unavailable_without_weight_changes():
    frame,profile,stack,kwargs,service,model = solved()
    original = render_solution(frame,model,model.objective,stack,profile)
    for row in original:
        row['ownership']=25.
        row['captain_ownership']=15.
        row['flex_ownership']=25.
    original[1]['ownership']=None
    masked = mask_diagnostic_ownership(deepcopy(original))
    _,report = select_single_entry_lineups([masked],num_contests=1)
    assert report['objective_weights']==DEFAULT_WEIGHTS
    assert report['all_candidates'][0]['objective_contributions']['chalk_penalty']==0
    assert all(row['ownership'] is None for row in masked)
    assert original[0]['ownership']==25.
    assert masked[0]['diagnostic_ownership']==25.


def test_different_captains_in_balanced_same_core_do_not_create_new_theses():
    rows = [{'player_id':str(i),'player_team':'PIT' if i<3 else 'CLE',
             'position':('QB','WR','WR','QB','WR','WR')[i],
             'roster_position':'CPT' if i==1 else 'FLEX'} for i in range(6)]
    other = deepcopy(rows)
    other[1]['roster_position']='FLEX'
    other[4]['roster_position']='CPT'
    assert thesis(rows)==thesis(other)=='balanced competitive'


def test_joint_portfolio_uses_different_cores_and_captains(monkeypatch):
    monkeypatch.setattr('scripts.research_showdown_prelock.make_cbc_solver',
                        lambda backend:pulp.PULP_CBC_CMD(msg=False))
    records = [{'captain_id':str(i),'single_entry_score':1-i*.001,'research_thesis':str(i)} for i in range(4)]
    cores = ['abcdef','abcdef','abcghi','abjklm']
    lineups = [[{'player_id':pid} for pid in core] for core in cores]
    chosen = joint_portfolio(records,lineups,3,different_captains=True,different_theses=True,max_shared=4)
    assert chosen==[0,2,3]


def test_frozen_hash_failure_is_closed(tmp_path):
    payload = {'player_pool':[{'player_id':'canonical','projection':10}]}
    path = tmp_path/'freeze.json'
    path.write_text(json.dumps({'payload':payload,'sha256':digest_payload(payload)}))
    assert read_frozen(path)['payload']==payload
    payload['player_pool'][0]['projection']=11
    path.write_text(json.dumps({'payload':payload,'sha256':digest_payload({'old':True})}))
    with pytest.raises(ValueError,match='Hash mismatch'):read_frozen(path)
