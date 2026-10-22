from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import csv
import io

import pytest
from fastapi import HTTPException

from backend.app.api.product_routes import download_optimizer_lineups
from backend.app.product_services.gpp_recommendation import evaluate_candidates, candidate_id, recommended_lineup


def test_shared_world_export_preserves_order_and_authenticates_selection():
    from backend.app.product_services.shared_world_runtime import recommendation, RECOMMENDATION_POLICY
    from backend.app.product_services.shared_world_selection import POLICY
    candidates=[lineup(0,9,50,True),lineup(20,10,20,True)]
    for index,rs in enumerate(candidates,1):rs[0]['shared_world_selection_rank']=index
    selection=dict(policy_id=POLICY,status='completed',requested=2,selection_steps=[
        dict(anchor_conditional_mean_points=90,maximum_incremental_gain_points=0),
        dict(anchor_conditional_mean_points=80,maximum_incremental_gain_points=20)])
    saved=job(candidates,'showdown');saved.params.update(analyst_selection_policy=POLICY,
        strategy_runtime={'football_analyst':{'shared_world_selection':selection}})
    saved.params['gpp_recommendation']=recommendation(saved.params['gpp_recommendation'],candidates,selection)
    assert saved.params['gpp_recommendation']['policy_id']==RECOMMENDATION_POLICY
    assert recommended_lineup(saved) is candidates[0]
    saved.params['strategy_runtime']['football_analyst']['shared_world_selection']['requested']=3
    with pytest.raises(ValueError,match='receipt differs'):recommended_lineup(saved)


def lineup(offset=0, mean=10, upside=20, showdown=False):
    positions = ['QB', 'RB', 'RB', 'WR', 'WR', 'WR', 'TE', 'RB', 'DST']
    if showdown:
        positions = ['QB', 'WR', 'WR', 'RB', 'TE', 'K']
    return [dict(player_id=f'canonical-{offset+i}', dk_player_id=str(100+offset+i),
        dk_captain_id=str(1000+offset+i), position=pos,
        roster_position=('CPT' if i == 0 else 'FLEX') if showdown else pos,
        salary=5000, projection=mean * (1.5 if showdown and i == 0 else 1),
        p90=upside * (1.5 if showdown and i == 0 else 1), name=f'Player {offset+i}')
        for i,pos in enumerate(positions)]


def evaluate(candidates, format='classic'):
    return evaluate_candidates(candidates, run_id='run', season=2026, week=5, slate='SUNDAY_MAIN',
        contest_format=format, projection_run_id='projection', data_cutoff_at='2026-10-10T12:00:00Z')


def job(candidates, format='classic'):
    return SimpleNamespace(job_id='run', status='completed', objective='gpp', strategy='classic_large_gpp_v1',
        season=2026, week=5, slate='SUNDAY_MAIN', contest_format=format, projection_run_id='projection',
        results=candidates, params={'gpp_recommendation':evaluate(candidates, format)})


def test_compares_all_candidates_projected_points_first_and_preserves_inputs():
    candidates = [lineup(0, 10, 35), lineup(20, 11, 20)]
    before = deepcopy(candidates)
    r = evaluate(candidates)
    assert r['recommended']['lineup_number'] == 2
    assert r['recommended']['projected_points'] == 99
    assert r['candidates'][1]['marginal_upside_sum'] == 315
    assert r['status'] == 'provisional'
    assert r['paid_finish_probability'] is None and r['expected_return'] is None
    assert candidates == before


def test_upside_breaks_equal_mean_then_identity_breaks_ties_independent_of_order():
    a, b = lineup(0, 10, 20), lineup(20, 10, 21)
    assert evaluate([a,b])['recommended']['candidate_id'] == candidate_id(b)
    b = lineup(20, 10, 20)
    assert evaluate([a,b])['recommended']['candidate_id'] == evaluate([b,a])['recommended']['candidate_id']


@pytest.mark.parametrize('invalid', ['nan','missing','salary','identity','slot'])
def test_invalid_candidate_cannot_win_and_abstains_if_none_valid(invalid):
    bad = lineup(0, 100, 200)
    if invalid == 'nan': bad[0]['projection'] = float('nan')
    if invalid == 'missing': del bad[0]['projection']
    if invalid == 'salary': bad[0]['salary'] = 50000
    if invalid == 'identity': bad[0]['player_id'] = bad[1]['player_id']
    if invalid == 'slot': bad[0]['position'] = bad[0]['roster_position'] = 'WR'
    r = evaluate([bad,lineup(20)])
    assert r['recommended']['lineup_number'] == 2
    assert r['exceptions']
    assert evaluate([bad])['recommended'] is None
    assert evaluate([bad])['status'] == 'unavailable'


def test_duplicate_rosters_compared_once_and_availability_not_cleared():
    a = lineup(); a[0]['official_availability_status'] = 'Q'
    r=evaluate([a,deepcopy(a)])
    assert len(r['candidates']) == 1
    assert r['recommended']['availability_exceptions'][0]['designation'] == 'Q'
    assert 'Duplicate' in r['exceptions'][0]['reason']


def test_missing_upside_stays_unavailable_not_zero():
    a=lineup(); del a[0]['p90']
    assert evaluate([a])['recommended']['marginal_upside_sum'] is None


def test_captain_uses_slot_weighted_points_once_and_unconditioned_baseline():
    a=lineup(showdown=True)
    assert evaluate([a],'showdown')['recommended']['projected_points'] == 65
    b=lineup(20, 9, 20, showdown=True)
    for p in b:
        p['baseline_projection']=p['projection']; p['baseline_p90']=p['p90']
        p['projection']=100; p['p90']=200
    assert evaluate([a,b],'showdown')['recommended']['candidate_id'] == candidate_id(a)
    swapped=deepcopy(a);swapped[0]['roster_position']='FLEX';swapped[1]['roster_position']='CPT'
    assert candidate_id(a) != candidate_id(swapped)


def test_recommended_export_has_exactly_one_lineup_and_preserves_all_candidates():
    j=job([lineup(0,10),lineup(20,11)])
    with patch('backend.app.product_services.evaluation_record.record_export') as record:
        response=download_optimizer_lineups('run', service=SimpleNamespace(get_job=lambda _:j, engine=MagicMock()), recommended_only=True)
    assert record.call_args.args[1] == 'run'
    assert record.call_args.args[3] == response.body
    assert record.call_args.args[4] == [j.results[1]]
    rows=list(csv.reader(io.StringIO(response.body.decode())))
    assert len(rows)==2
    assert set(rows[1]) == {p['dk_player_id'] for p in j.results[1]}
    assert len(j.results)==2
    assert 'recommended' in response.headers['content-disposition']


@pytest.mark.parametrize('mutation',['identity','scope','projection','failed','report','index'])
def test_recommendation_export_rejects_stale_or_missing_saved_choice(mutation):
    j=job([lineup()])
    if mutation=='identity': j.results[0][0]['player_id']='different'
    if mutation=='scope': j.slate='SUNDAY_LATE'
    if mutation=='projection': j.projection_run_id='other'
    if mutation=='failed': j.status='failed'
    if mutation=='report': j.params={}
    if mutation=='index': j.params['gpp_recommendation']['recommended']['lineup_number']=2
    with pytest.raises(ValueError): recommended_lineup(j)
    with pytest.raises(HTTPException):
        download_optimizer_lineups('run',service=SimpleNamespace(get_job=lambda _:j),recommended_only=True)
