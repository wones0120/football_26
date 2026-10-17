import json
from copy import deepcopy
from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from backend.app.product_services.analyst_intents import scope_packet, validate_intents, validate_scoped_packet
from backend.app.product_services.analyst_packets import packet_digest,validate
from backend.app.product_services.analyst_preparation import prepare_handoff,bind_handoff,handoff_for_intent
from backend.app.product_services.analyst_scenarios import run_merged
from backend.app.product_services.optimizer import OptimizerService
from backend.app.product_schemas import OptimizerRunRequest
from scripts.run_merged_analyst_fixture import scenario_fixture

NOW=datetime(2099,9,1,12,tzinfo=timezone.utc)

def intent_fixture():
    p,s=scenario_fixture('SHOWDOWN')
    p,s=json.loads(json.dumps([p,s]).replace('\"AAA\"','\"DEN\"').replace('\"BBB\"','\"SEA\"'))
    for g in p['games']:g.update(season=2099,week=1)
    first,second=p['scenario_assumptions']['scenarios']
    second['explicit_user_what_if']=True
    for a in first['assumptions']:a['factor']=1
    item=dict(assessment='Sourced primary assessment with upside',supporting_evidence=['Synthetic source context'],counterevidence=['Synthetic contrary case'],unknowns=['Uncalibrated likelihood'],source_ids=['synthetic'])
    p['optimization_intents']=dict(contract_id='analyst_optimization_intents_v1',
        EXPECTED_GAME={**item,'scenario_ids':[first['scenario_id']]},
        CONTRARIAN={**item,'assessment':'Explicit alternate passing story','scenario_ids':[second['scenario_id']],
            'story_requirements':dict(script='passing_breakout',team=p['games'][0]['teams'][0],require_qb=True,minimum_receivers=2)})
    return p,s

def test_intent_scoping_is_immutable_and_expected_cannot_use_explicit_what_if():
    p,_=intent_fixture();before=deepcopy(p)
    expected=scope_packet(p,'EXPECTED_GAME');contrarian=scope_packet(p,'CONTRARIAN')
    assert p==before
    assert not any(s.get('explicit_user_what_if') for s in expected['scenario_assumptions']['scenarios'])
    assert set(expected['intent_scope']['scenario_ids']).isdisjoint(contrarian['intent_scope']['scenario_ids'])
    assert expected['intent_scope']['authoring_packet_sha256']==packet_digest(p)
    validate_scoped_packet(expected,'EXPECTED_GAME')
    with pytest.raises(ValueError,match='requested optimization intent'):validate_scoped_packet(contrarian,'EXPECTED_GAME')
    p['optimization_intents']['EXPECTED_GAME']['scenario_ids']=p['optimization_intents']['CONTRARIAN']['scenario_ids']
    assert any('what-if' in error for error in validate_intents(p))
    assert validate(p)

def test_automatic_prepare_freezes_distinct_intent_receipts_and_rejects_cross_binding(tmp_path):
    p,s=intent_fixture();key=packet_digest(p)
    req=SimpleNamespace(analyst_mode='AUTO',analyst_strategy='MERGED_SCENARIOS',contest_format='showdown',season=2099,week=1,slate='TEST')
    result=dict(source_manifest={'games':p['games']},source_sha256='same-source',projection_run_id='same-projection')
    receipts={intent:prepare_handoff(request=req,result=result,rows=s['players'],checked_at=NOW.isoformat(),packets={key:p},directory=tmp_path,optimization_intent=intent) for intent in ('EXPECTED_GAME','CONTRARIAN')}
    assert all(r['checked_packet_sha256'] for r in receipts.values())
    assert receipts['EXPECTED_GAME']['checked_packet_sha256']!=receipts['CONTRARIAN']['checked_packet_sha256']
    assert receipts['EXPECTED_GAME']['compatibility_sha256']!=receipts['CONTRARIAN']['compatibility_sha256']
    payload=dict(season=2099,week=1,slate='TEST',contest_format='showdown',objective='gpp',params={'analyst_optimization_intent':'EXPECTED_GAME'})
    result={'analyst_handoff':{'checked_packet_sha256':'mixed-parent'},'analyst_intent_handoffs':receipts}
    assert handoff_for_intent(result,'EXPECTED_GAME')==receipts['EXPECTED_GAME']
    assert handoff_for_intent(result,'CONTRARIAN')==receipts['CONTRARIAN']
    assert handoff_for_intent(result,'MIXED')['checked_packet_sha256']=='mixed-parent'
    bind_handoff(payload,result)
    assert payload['params']['analyst_intent_scenario_ids']==receipts['EXPECTED_GAME']['scenario_ids']
    assert payload['params']['analyst_handoff_applied']['optimization_intent']=='EXPECTED_GAME'
    payload['params']['analyst_optimization_intent']='CONTRARIAN'
    with pytest.raises(ValueError,match='differs from prepared'):bind_handoff(payload,{'analyst_intent_handoffs':receipts})
    with pytest.raises(ValueError,match='Prepare Slate again'):bind_handoff(payload,{'analyst_handoff':receipts['EXPECTED_GAME']})

@pytest.mark.parametrize('intent',['EXPECTED_GAME','CONTRARIAN'])
def test_generation_uses_only_intent_worlds_and_keeps_requested_exposure(intent):
    p,s=intent_fixture();scoped=scope_packet(p,intent);pool=pd.DataFrame(s['players'])
    with patch('backend.app.product_services.analyst_scenarios.datetime') as clock:
        clock.now.return_value=NOW
        lineups,r=run_merged(OptimizerService.__new__(OptimizerService),pool,
            params=dict(analyst_optimization_intent=intent,analyst_intent_scenario_ids=scoped['intent_scope']['scenario_ids'],analyst_candidates_per_thesis=1,max_exposure=1,captain_max_exposure=.25),
            packet=scoped,fmt='SHOWDOWN',season=2099,week=1,slate='TEST',requested=4,
            solve_kwargs=dict(contest_type='captain',score_col='p90',stack_params={'enabled':False},include_control_comparison=False))
    assert len(lineups)==4
    assert {s['scenario_id'] for s in r['scenario_definitions']}==set(scoped['intent_scope']['scenario_ids'])
    assert r['optimization_intent']['intent']==intent
    assert r['selection']['constraints_relaxed'] is False
    assert len({next(p['player_id'] for p in l if p['roster_position']=='CPT') for l in lineups})==4
    assert all(l[0]['analyst_optimization_intent']==intent and l[0]['analyst_intent_story_compliance'] for l in lineups)
    if intent=='CONTRARIAN':
        team=scoped['intent_scope']['story_requirements']['team']
        assert all(sum(p['position'] in ['WR','TE'] and p['player_team']==team for p in l)>=2 for l in lineups)

@pytest.mark.parametrize('extra',[{'analyst_optimization_intent':'OTHER'}, {'analyst_optimization_intent':'EXPECTED_GAME','analyst_handoff_mode':'BASELINE'}, {'analyst_optimization_intent':'CONTRARIAN','analyst_strategy':'CONSTRUCTION'}])
def test_api_rejects_unknown_or_unscoped_intent(extra):
    with pytest.raises(ValueError):OptimizerRunRequest(season=2099,week=1,slate='TEST',strategy='showdown_gpp_portfolio_v3',contest_format='showdown',objective='gpp',params={'prepared_input_job_id':'prepared',**extra})


def test_expected_game_can_explicitly_compare_original_construction_on_same_checked_evidence(tmp_path):
    p,s=intent_fixture();key=packet_digest(p)
    req=SimpleNamespace(analyst_mode='AUTO',analyst_strategy='MERGED_SCENARIOS',contest_format='showdown',season=2099,week=1,slate='TEST')
    receipt=prepare_handoff(request=req,result=dict(source_manifest={'games':p['games']},source_sha256='same',projection_run_id='projection'),rows=s['players'],checked_at=NOW.isoformat(),packets={key:p},directory=tmp_path,optimization_intent='EXPECTED_GAME')
    request=OptimizerRunRequest(season=2099,week=1,slate='TEST',strategy='showdown_gpp_portfolio_v3',contest_format='showdown',objective='gpp',params={'prepared_input_job_id':'prepared','analyst_optimization_intent':'EXPECTED_GAME','analyst_strategy':'CONSTRUCTION','captain_positions':['WR','RB'],'captain_position_exception_ids':['named-qb'],'questionable_eligible_player_ids':['named-wr']})
    payload=request.model_dump();bind_handoff(payload,{'analyst_intent_handoffs':{'EXPECTED_GAME':receipt}})
    assert payload['params']['analyst_strategy']=='CONSTRUCTION'
    assert payload['params']['analyst_handoff_applied']['checked_packet_sha256']==receipt['checked_packet_sha256']
    assert payload['params']['captain_position_exception_ids']==['named-qb']


@pytest.mark.parametrize('intent',['EXPECTED_GAME','CONTRARIAN'])
def test_broader_captain_support_search_preserves_story_identity_and_half_cap(intent):
    from collections import Counter
    p,s=intent_fixture();scoped=scope_packet(p,intent);original=deepcopy(s['players'])
    with patch('backend.app.product_services.analyst_scenarios.datetime') as clock:
        clock.now.return_value=NOW
        lineups,r=run_merged(OptimizerService.__new__(OptimizerService),pd.DataFrame(s['players']),
            params=dict(analyst_optimization_intent=intent,analyst_intent_scenario_ids=scoped['intent_scope']['scenario_ids'],
                        analyst_candidates_per_thesis=2,max_exposure=1,captain_max_exposure=.5),
            packet=scoped,fmt='SHOWDOWN',season=2099,week=1,slate='TEST',requested=4,
            solve_kwargs=dict(contest_type='captain',score_col='p90',stack_params={'enabled':False},include_control_comparison=False))
    assert len(lineups)==4 and s['players']==original
    assert max(Counter(next(p['player_id'] for p in lineup if p['roster_position']=='CPT') for lineup in lineups).values())<=2
    search=r['captain_candidate_search']
    assert search['policy_id']=='analyst_eligible_captain_support_v1'
    assert search['budget_exhausted'] is False and search['solves_used']<=search['maximum_solves']
    assert any(c['distinct_supporting_rosters']>=2 for c in search['coverage'])
    signatures={tuple(sorted((p['player_master_id'],p['role']) for p in c['roster'])) for c in r['candidates']}
    assert len(signatures)==len(r['candidates'])>4
    assert all(set(c['scenario_ids'])<=set(scoped['intent_scope']['scenario_ids']) for c in r['candidates'])
    assert r['selection']['constraints_relaxed'] is False
    if intent=='CONTRARIAN':
        by_id={str(row['player_id']):row for row in original};team=scoped['intent_scope']['story_requirements']['team']
        for candidate in r['candidates']:
            players=[by_id[row['player_master_id']] for row in candidate['roster']]
            assert any(row['position']=='QB' and row['player_team']==team for row in players)
            assert sum(row['position'] in ['WR','TE'] and row['player_team']==team for row in players)>=2


def test_classic_scenario_first_retains_authored_intent_report_and_no_opposite_worlds():
    from backend.app.tests.product.test_scenario_allocation import supported_fixture
    p, s = supported_fixture()
    for g in p['games']: g.update(season=2099, week=1)
    first = deepcopy(p['scenario_assumptions']['scenarios'][0]); first['assumptions']=first['assumptions'][:2]
    other = deepcopy(first); other['scenario_id']='other_authored_world'
    p['scenario_assumptions']['scenarios']=[first,other]
    item=dict(assessment='Synthetic primary',supporting_evidence=['Synthetic verified source'],counterevidence=['Other channel'],unknowns=['Future outcome'],source_ids=['synthetic'])
    p['optimization_intents']=dict(contract_id='analyst_optimization_intents_v1',EXPECTED_GAME={**item,'scenario_ids':[first['scenario_id']]},CONTRARIAN={**item,'scenario_ids':[other['scenario_id']]})
    scoped=scope_packet(p,'EXPECTED_GAME')
    with patch('backend.app.product_services.analyst_scenarios.datetime') as clock:
        clock.now.return_value=NOW
        lineups, report=run_merged(OptimizerService.__new__(OptimizerService),pd.DataFrame(s['players']),
            params=dict(analyst_optimization_intent='EXPECTED_GAME',max_exposure=1,analyst_portfolio_mode='SCENARIO_FIRST'),
            packet=scoped,fmt='CLASSIC',season=2099,week=1,slate='TEST',requested=1,
            solve_kwargs=dict(contest_type='classic',score_col='p90',stack_params={'enabled':False},include_control_comparison=False))
    assert len(lineups)==1
    assert report['optimization_intent']['intent']=='EXPECTED_GAME'
    assert report['optimization_intent']['scenario_ids']==[first['scenario_id']]
    assert all(not idea['derived_alternative'] for idea in report['scenario_allocation_plan']['ideas'])
    assert lineups[0][0]['analyst_optimization_intent']=='EXPECTED_GAME'


def test_classic_intent_request_requires_checked_preparation_or_snapshot_receipt():
    params={'analyst_optimization_intent':'EXPECTED_GAME','analyst_handoff_mode':'AUTO','analyst_strategy':'MERGED_SCENARIOS','analyst_packet_sha256':'b'*64}
    with pytest.raises(ValueError,match='automatic checked'):
        OptimizerRunRequest(season=2099,week=1,slate='TEST',strategy='classic_large_gpp_v1',contest_format='classic',objective='gpp',params=params)
    accepted=OptimizerRunRequest(season=2099,week=1,slate='TEST',strategy='classic_large_gpp_v1',contest_format='classic',objective='gpp',params={**params,'analyst_handoff_compatibility_sha256':'a'*64})
    assert accepted.params['analyst_optimization_intent']=='EXPECTED_GAME'
