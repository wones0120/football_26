from copy import deepcopy
from datetime import datetime, timezone

import pytest

from backend.app.product_services.gpp_historical_audit import (
    evaluate_run, field_outcome, freeze_choice, summarize,
)


def fixture():
    clock = datetime(2026, 10, 3, tzinfo=timezone.utc)
    run = dict(optimizer_run_id='run', projection_run_id='projection', season=2026, week=4,
               slate_id='SUNDAY_MAIN', contest_format='classic', strategy='classic_large_gpp_v1',
               optimizer_created_at=clock, updated_at=clock, data_cutoff_at=clock,
               constraint_config_json={})
    positions = ['QB','RB','RB','WR','WR','WR','TE','RB','DST']
    lineups = [[dict(player_id=f'p{j}-{i}',dk_player_id=f'{j}{i}',position=pos,roster_position=pos,
                     salary=5000,projection=10+j,p90=20,game_id='A@B 10/04/2026 01:00PM ET')
                for i,pos in enumerate(positions)] for j in range(2)]
    observations = [dict(player_id=p['player_id'],actual_points=5,resolution_status='resolved')
                    for roster in lineups for p in roster]
    return run,lineups,observations


def test_freezes_choice_before_actuals_without_hindsight_reselection():
    run,lineups,observations = fixture()
    choice = freeze_choice(run,lineups)
    assert choice['recommended']['lineup_number'] == 2
    observations = observations[:9]  # The chosen lineup is unscoreable, first lineup is scoreable.
    before = deepcopy((run,lineups,choice))
    result = evaluate_run(run,lineups,choice,observations,[],{}, {})
    assert result['selected_actual_points'] is None
    assert result['first_returned_actual_points'] == 45
    assert result['selected']['lineup_number'] == 2
    assert result['returned_coverage']['scoreable'] == 1
    assert (run,lineups,choice) == before


@pytest.mark.parametrize('clock', ['optimizer_created_at','updated_at','data_cutoff_at'])
def test_late_clock_is_excluded(clock):
    run,lineups,obs = fixture()
    run[clock] = datetime(2026,10,5,tzinfo=timezone.utc)
    assert evaluate_run(run,lineups,freeze_choice(run,lineups),obs,[],{}, {})['eligibility'] == 'excluded'


def test_missing_game_clock_excludes_even_with_other_valid_games():
    run,lineups,obs = fixture()
    lineups[0][0]['game_id'] = ''
    result = evaluate_run(run,lineups,freeze_choice(run,lineups),obs,[],{}, {})
    assert 'incomplete_saved_kickoff_evidence' in result['excluded_reasons']


def test_conflicting_canonical_actuals_are_missing():
    run,lineups,obs = fixture()
    obs.append(dict(obs[-1],actual_points=6))
    result = evaluate_run(run,lineups,freeze_choice(run,lineups),obs,[],{}, {})
    assert result['selected_actual_points'] is None
    assert result['missing_actual_player_ids'] == ['p1-8']


def field():
    return (dict(contest_id='contest',contest_type='gpp',field_size=4,entry_fee=5,prize_pool=30),
            [dict(entry_points=100,entries=1),dict(entry_points=80,entries=2),dict(entry_points=50,entries=1)],
            [dict(min_rank=1,max_rank=1,payout=20),dict(min_rank=2,max_rank=2,payout=10)])


def test_tie_crossing_paid_cutoff_is_uncertain():
    result = field_outcome(80,*field())
    assert result['rank_bounds'] == [2,4]
    assert result['paid_finish'] is None
    assert result['net_return_bounds'] == [-5,5]
    assert field_outcome(110,*field())['paid_finish'] is True
    assert field_outcome(20,*field())['paid_finish'] is False


@pytest.mark.parametrize('fault',['gap','overlap','unknown','total','incomplete','null_score','missing_tiers'])
def test_bad_field_evidence_never_fabricates_returns(fault):
    c,h,t = field()
    if fault == 'gap': t[1]['min_rank'] = t[1]['max_rank'] = 3
    if fault == 'overlap': t[1]['min_rank'] = 1
    if fault == 'unknown': c['contest_type'] = 'unknown'
    if fault == 'total': c['prize_pool'] = 31
    if fault == 'incomplete': c['field_size'] = 5
    if fault == 'null_score': h[0]['entry_points'] = None
    if fault == 'missing_tiers': t=[]
    result = field_outcome(110,c,h,t)
    assert result['paid_finish'] is None
    assert result['net_return_bounds'] is None


def test_hash_mismatch_pool_not_used_and_related_runs_are_one_slate_block():
    run,lineups,obs = fixture()
    pool = [dict(players=lineups[0])]
    run['constraint_config_json'] = dict(strategy_runtime=dict(
        classic_small_field=dict(all_candidates=pool), candidate_pool_manifest=dict(sha256='wrong')))
    result = evaluate_run(run,lineups,freeze_choice(run,lineups),obs,[],{}, {})
    assert result['pool_evidence']['reason'] == 'candidate_pool_hash_mismatch'
    assert result['search_pool_coverage']['count'] == 0
    summary = summarize([result,dict(result,run_id='other')],[])
    assert len(summary['slate_blocks']) == 1
    assert summary['slate_blocks'][0]['runs'] == 2
    assert summary['promotion_eligible'] is False


def test_pending_slate_is_excluded_from_historical_evaluation():
    run,lineups,_ = fixture()
    result = evaluate_run(run,lineups,freeze_choice(run,lineups),[],[],{}, {})
    assert 'historical_results_not_imported' in result['excluded_reasons']


def test_postgame_contaminated_returned_roster_is_excluded():
    run,lineups,obs = fixture()
    lineups[0][0]['actual_points'] = 99
    result = evaluate_run(run,lineups,freeze_choice(run,lineups),obs,[],{}, {})
    assert 'postgame_data_in_saved_returned_candidate' in result['excluded_reasons']


def test_exported_paid_places_work_without_fabricating_payouts():
    c,h,_ = field()
    c.update(places_paid=2,paid_places_source='draftkings_entry_history')
    r=field_outcome(110,c,h,[])
    assert r['paid_finish'] is True and r['paid_cutoff_points']==80
    assert r['net_return_bounds'] is None
    assert field_outcome(80,c,h,[])['paid_finish'] is None
    assert field_outcome(10,c,h,[])['paid_finish'] is False
    c['contest_type']='cash'
    assert field_outcome(110,c,h,[])['paid_finish'] is None


def test_single_entry_tournament_names_preserve_cash_precedence():
    from backend.app.product_services.contest_evidence import classify_contest_type
    assert classify_contest_type('NFL $20K Pylon [Single Entry]')['contest_type']=='gpp'
    assert classify_contest_type('NFL $15K Daily Dollar [Single Entry]')['contest_type']=='gpp'
    assert classify_contest_type('NFL Double Up Pylon [Single Entry]')['contest_type']=='cash'


@pytest.mark.parametrize('stage',['final_selection_miss','candidate_shortlisting_miss','generation_miss','no_observed_paid_candidate_incomplete_pool'])
def test_stage_diagnosis_does_not_call_missing_pool_a_generation_failure(stage):
    run,lineups,obs=fixture()
    c,h,_=field();c.update(places_paid=2,paid_places_source='draftkings_entry_history')
    pool=[]
    if stage=='final_selection_miss':
        for o in obs[:9]: o['actual_points']=20
    elif stage=='candidate_shortlisting_miss':
        hidden=[dict(p,player_id='hidden-'+p['player_id']) for p in lineups[0]]
        pool=[dict(players=hidden)]
        obs += [dict(player_id=p['player_id'],actual_points=20,resolution_status='resolved') for p in hidden]
    elif stage=='generation_miss':
        pool=[dict(players=lineups[0]),dict(players=lineups[1])]
    run['constraint_config_json']={'strategy_runtime':{'classic_small_field':{'all_candidates':pool}}}
    result=evaluate_run(run,lineups,freeze_choice(run,lineups),obs,[c],{'contest':h},{})
    assert result['stage_diagnostics'][0]['diagnosis']==stage
