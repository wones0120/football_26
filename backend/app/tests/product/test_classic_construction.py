from collections import Counter
from dataclasses import replace, asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.product_routes import router
from backend.app.product_dependencies import get_optimizer_service
from backend.app.product_services.classic_construction import classify_roster, construction_summary
from backend.app.product_services.classic_construction_review import review_constructions
from backend.app.product_services.classic_strategy_contract import build_strategy_contract, execute_strategy_contract, portfolio_audit
from backend.app.product_services.gpp_optimizer import _build_lineup, build_large_gpp_config, analyze_slate
from backend.app.tests.product.test_classic_strategy_contract import pool, options
from backend.app.tests.product.overlap_ui_fixture import fixture_app
from scripts.analyze_classic_historical_study import classify


def saved(single_te=False, **changes):
    opts = options(enforce_single_te=single_te, max_from_team=3, max_from_game=5,
        max_lineups_per_primary_game=3, max_lineup_overlap=5, **changes)
    return build_strategy_contract(players=pool(), pipeline_options=opts,
        requested=opts, metadata={'projection_run_id': 'synthetic-only'})


def test_te_toggle_removes_only_one_constraint_and_keeps_identical_scoring():
    players = pool(); config = build_large_gpp_config(analyze_slate(players), ownership_available=False,
        max_from_team=3, max_from_game=5)
    models = []
    for value in (True, False):
        _build_lineup(players, config, {p.player_id: 1 for p in players}, [{0, 3, 7}],
            enforce_single_te=value, avoid_dst_opponents=True,
            maximum_player_groups=[({players[1].player_id}, 0)], model_capture=models.append)
    a, b = [m.toDict() for m in models]
    assert a['objective'] == b['objective']
    constraints = lambda m: Counter(json.dumps({k: v for k, v in c.items() if k != 'name'}, sort_keys=True) for c in m['constraints'])
    assert sum((constraints(a) - constraints(b)).values()) == 1
    assert not constraints(b) - constraints(a)


@pytest.mark.parametrize('flex', ['RB', 'WR', 'TE'])
def test_natural_flex_reachable_and_single_te_explicitly_excludes_only_te(flex):
    players=pool(); config=build_large_gpp_config(analyze_slate(players),ownership_available=False,max_from_team=3,max_from_game=5)
    def solve(single):
        return _build_lineup(players,config,None,[],enforce_single_te=single,construction={'flex':flex})
    ids=solve(False); assert ids is not None
    row=classify_roster([players[i] for i in ids]); assert row['flex_position']==flex and row['status']=='available'
    assert len({players[i].player_id for i in ids})==9
    assert sum(players[i].salary for i in ids)<=50000
    assert row['max_team_all']<=3 and row['qb_game_all_players']<=5
    assert (solve(True) is None) == (flex=='TE')


def test_missing_catchers_cannot_bypass_minimum():
    players=[p for p in pool() if not (p.team=='AAA' and p.position in {'WR','TE'})]
    config=build_large_gpp_config(analyze_slate(players),ownership_available=False)
    assert _build_lineup(players,config,None,[],required_player_ids={'AAA-QB-0'}) is None


def test_taxonomy_matches_immutable_research_rosters_and_dst_semantics():
    root=Path(__file__).resolve().parents[4]
    tested=0
    for path in sorted((root/'artifacts/classic_historical_study/contests').glob('*.json')):
        for winner in json.loads(path.read_text()).get('winners',[]):
            players=[{**p,'player_id':p['id']} for p in winner['players']]
            actual=classify_roster(players); expected=classify(winner['players'],{},set())
            assert actual['status']=='available'
            for key in ('flex_position','qb_team_offense_including_qb','qb_pass_catchers','qb_same_team_rb',
                'bring_backs','qb_game_all_players','secondary_opposing_game_count','true_unrelated_oneoffs','max_team_all','max_team_offense'):
                assert actual[key]==expected[key], (path,key)
            tested+=1
    assert tested>=15


def test_invalid_or_missing_context_is_unavailable():
    ps=[asdict(p) for p in pool()[:9]]
    assert classify_roster(ps)['status']=='unavailable'
    assert construction_summary([ps])['distributions']['flex_position']=={}
    assert review_constructions(None,[])['status']=='unavailable'


@pytest.mark.parametrize('single', [True,False])
def test_review_shared_solver_components_replacement_and_parity(single):
    c=saved(single); run=execute_strategy_contract(c)
    assert run.status=='completed'
    replay=execute_strategy_contract(json.loads(json.dumps(c)))
    assert [[p.player_id for p in r] for r in run.lineups]==[[p.player_id for p in r] for r in replay.lineups]
    ids=[[p.player_id for p in r] for r in run.lineups]
    before=json.dumps(c,sort_keys=True)
    report=review_constructions(c,ids)
    assert before==json.dumps(c,sort_keys=True)
    assert report['implementation_matches_saved']
    assert report['active_constraints']['max_exposure']==.8
    assert report['active_constraints']['max_lineup_overlap']==5
    assert report['active_constraints']['max_lineups_per_primary_game']==3
    by_family={r['family']:r for r in report['comparisons']}
    te=by_family['TE FLEX / two TEs']['individual']
    assert te['status']==('excluded_by_user_preference' if single else 'feasible')
    assert by_family['RB FLEX / three RBs']['individual']['status']=='feasible'
    assert by_family['QB with same-team RB without WR/TE']['individual']['status']=='excluded_by_strategy_eligibility'
    for row in report['comparisons']:
        for mode in ('individual','replacement'):
            r=row[mode]
            if r['status']=='feasible':
                assert r['component_sum_matches_solver']
                assert r['construction']['max_team_all']<=3
                assert r['construction']['qb_game_all_players']<=5
                if mode=='replacement': assert r['portfolio_validation']['status']=='verified'
    assert all(by_family[name]['individual']['status']=='feasible' for name in (
        'Exactly one WR/TE with QB','Exactly two WR/TE with QB','No offensive bring-back',
        'Exactly one offensive bring-back','Exactly two offensive bring-backs','Opposing RB bring-back',
        'QB with same-team RB and WR/TE','True unrelated one-off','Secondary opposing mini-stack'))
    audit=portfolio_audit(c,run.lineups)
    assert audit['validation']['status']=='verified'
    assert next(r for r in audit['settings'] if r['key']=='enforce_single_te')['effective']==single
    assert c['effective']['resolved_config']['objective_weights']=={'projection':.35,'ceiling':.48,'leverage':0.,'correlation':.17}


def test_template_minima_and_not_searched_are_explicit():
    c=saved();run=execute_strategy_contract(c);ids=[[p.player_id for p in r] for r in run.lineups]
    report=review_constructions(c,ids,entry=3)
    row=next(r for r in report['comparisons'] if r['family']=='Exactly one WR/TE with QB')
    assert row['individual']['status']=='excluded_by_generation_template'
    report=review_constructions(c,ids[:1])
    row=next(r for r in report['comparisons'] if r['family']=='RB FLEX / three RBs')
    assert row['replacement']['status']=='not_searched'
    summary=construction_summary([[asdict(p) for p in r] for r in run.lineups],c)
    assert 'no broad candidate universe' in summary['coverage']
    assert 'top 10%' in summary['research_scope'] and 'minimums' in summary['definitions']


def test_actual_ui_request_api_service_persistence_and_get_never_solves():
    client=TestClient(fixture_app())
    for single in (True,False):
        response=client.post('/fixture/submit',json={'season':2000,'week':1,'slate':'SUNDAY_MAIN',
            'strategy':'classic_large_gpp_v1','contest_format':'classic','objective':'gpp',
            'optimizer_run_id':f'synthetic-te-{single}', 'params':{'num_lineups':5,'max_exposure':.8,
                'enforce_single_te':single,'max_players_per_team':3,'max_players_per_game':5,
                'max_lineup_overlap':5,'max_lineups_per_primary_game':3}})
        assert response.status_code==200,response.text
        data=response.json();report=data['report'];c=report['effective_strategy_contract']
        assert data['saved_options']['enforce_single_te']==report['enforce_single_te']==single
        assert c['requested']['enforce_single_te']==single
        assert c['effective']['pipeline_options']['enforce_single_te']==single
        assert report['construction_summary']['selected_count']==5
        with patch('backend.app.product_services.classic_construction_review._build_lineup',side_effect=AssertionError('GET must not solve')):
            assert client.get('/api/optimizer/results/'+report['job_id']).status_code==200
        assert client.post('/api/optimizer/results/'+report['job_id']+'/construction-review').json()['status']=='completed'


def test_minimum_two_template_can_select_three_pass_catchers():
    players=pool()
    config=build_large_gpp_config(analyze_slate(players),ownership_available=False,max_from_team=4)
    rules=replace(config.stack_rules,min_pass_catchers=2)
    ids=_build_lineup(players,config,None,[],stack_rules=rules,
        required_player_ids={'AAA-QB-0','AAA-WR-0','AAA-WR-1','AAA-TE-0'})
    actual=classify_roster([players[i] for i in ids])
    assert actual['qb_pass_catchers']==3
    assert actual['max_team_all']==4


def test_review_retains_explicit_risk_and_player_caps():
    c=saved(False,elevated_player_ids=['AAA-QB-0','AAA-TE-0'],
        elevated_player_max_exposure=.4,max_elevated_players_per_lineup=1,
        maximum_exposure_by_player={'BBB-RB-0':0},minimum_exposure_by_player={'CCC-TE-0':1})
    run=execute_strategy_contract(c)
    assert run.status=='completed'
    report=review_constructions(c,[[p.player_id for p in row] for row in run.lineups])
    for row in report['comparisons']:
        for kind in ('individual','replacement'):
            r=row[kind]
            if r['status']=='feasible':
                assert 'BBB-RB-0' not in r['player_ids']
                assert 'CCC-TE-0' in r['player_ids']
                assert len(set(r['player_ids']) & {'AAA-QB-0','AAA-TE-0'})<=1
                assert r['selection_treatment'] in {'matches_reviewed_saved_entry','matches_another_saved_entry','feasible_but_not_selected_in_saved_portfolio'}
                assert set(r['deltas_vs_saved_entry'])=={'mean','p90','objective_score'}


def test_explicit_single_te_review_override_uses_same_pinned_frame_without_mutation():
    c=saved(True);run=execute_strategy_contract(c)
    ids=[[p.player_id for p in row] for row in run.lineups]
    before=json.dumps(c,sort_keys=True)
    review=review_constructions(c,ids,enforce_single_te=False)
    assert json.dumps(c,sort_keys=True)==before
    assert review['pinned_contract_sha256']==c['sha256']
    assert review['saved_enforce_single_te'] is True and review['review_enforce_single_te'] is False
    assert set(review['changed_settings'])=={'enforce_single_te'}
    for key,value in c['effective']['pipeline_options'].items():
        if key!='enforce_single_te': assert review['active_constraints'][key]==value
    te=next(r for r in review['comparisons'] if r['family']=='TE FLEX / two TEs')
    assert te['individual']['status']=='feasible'
    assert te['individual']['construction']['composition']['TE']==2
    assert te['individual']['component_sum_matches_solver']


def test_turning_single_te_on_cannot_certify_retained_double_te_entries():
    c=saved(False)
    players=pool()
    config=build_large_gpp_config(analyze_slate(players),ownership_available=False,max_from_team=3,max_from_game=5)
    roster=_build_lineup(players,config,None,[],construction={'flex':'TE'})
    ids=[players[i].player_id for i in roster]
    # Underfilled immutable fixture: the retained TE roster is itself enough to
    # prove the reviewed single-TE preference cannot hold for a full replacement.
    report=review_constructions(c,[ids,ids],entry=1,enforce_single_te=True)
    row=next(r for r in report['comparisons'] if r['family']=='RB FLEX / three RBs')
    assert row['individual']['status']=='feasible'
    assert row['replacement']['status']=='infeasible'
    assert row['replacement']['solver']['binding_exclusion']=='enforce_single_te_in_retained_entry'


def test_invalid_saved_positional_composition_does_not_search():
    c=saved()
    ids=[p.player_id for p in pool() if p.position=='RB'][:9]
    with patch('backend.app.product_services.classic_construction_review._build_lineup',side_effect=AssertionError('No search')):
        result=review_constructions(c,[ids])
    assert result['status']=='unavailable'
    assert 'invalid positional' in result['reason']


@pytest.mark.parametrize('kind,status,code', [
    ('missing_job', 404, 'saved_run_not_found'),
    ('missing_contract', 422, 'frozen_inputs_missing'),
    ('missing_frame', 422, 'frozen_inputs_missing'),
    ('missing_portfolio', 422, 'frozen_inputs_missing'),
    ('wrong_strategy', 422, 'incompatible_contract'),
    ('checksum', 422, 'incompatible_contract'),
    ('entry_zero', 422, 'invalid_entry'),
    ('entry_outside', 422, 'invalid_entry'),
    ('calculation', 500, 'calculation_failure'),
])
def test_review_route_reports_actionable_failure_without_search_or_writes(kind, status, code):
    c = saved()
    job = SimpleNamespace(strategy='classic_large_gpp_v1', status='completed',
        params={'effective_strategy_contract': c}, results=[[{'player_id': 'saved-player'}]])
    if kind == 'missing_contract': job.params = {}
    if kind == 'missing_frame': del c['effective']['players']
    if kind == 'missing_portfolio': job.results = []
    if kind == 'wrong_strategy': job.strategy = 'different'
    if kind == 'checksum': c['sha256'] = 'invalid'
    entry = 0 if kind == 'entry_zero' else 2 if kind == 'entry_outside' else 1
    before = json.dumps(job.__dict__, sort_keys=True)
    app = FastAPI(); app.include_router(router)
    lookups = []
    def get_job(job_id):
        lookups.append(job_id)
        if kind == 'calculation': raise RuntimeError('private exception must not be exposed')
        return None if kind == 'missing_job' else job
    app.dependency_overrides[get_optimizer_service] = lambda: SimpleNamespace(get_job=get_job)
    with patch('backend.app.product_services.classic_construction_review._build_lineup', side_effect=AssertionError('No solve')):
        response = TestClient(app).post(f'/api/optimizer/results/saved-job/construction-review?entry={entry}&enforce_single_te=false', json={})
    assert response.status_code == status, response.text
    detail = response.json()['detail']
    assert detail['code'] == code
    assert detail['job_id'] == 'saved-job' and detail['entry'] == entry
    assert response.headers['X-Construction-Review-Request-ID'] == detail['request_id']
    assert 'private exception' not in response.text
    assert lookups == ['saved-job']
    assert json.dumps(job.__dict__, sort_keys=True) == before
