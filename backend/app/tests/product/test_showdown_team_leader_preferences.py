import pandas as pd
import pytest
from backend.app.product_services.showdown_team_leader_preferences import leader_preference as actual_leader_preference,validate_leader_preferences
from backend.app.product_services.optimizer import OptimizerService
from backend.app.tests.product.test_showdown_qb_preferences import pool


@pytest.fixture(autouse=True)
def history(monkeypatch):
    evidence={'rows':[dict(player_id=r['player_id'],position=r['position'],ppg=40-i,games_played=3,games=[]) for i,r in enumerate(pool().to_dict('records'))], 'warnings':{}, 'source_sha256':'fixture'}
    monkeypatch.setattr('backend.app.product_services.showdown_team_leader_preferences.load_rankings',lambda *a,**k:evidence)
    return evidence


def leader_preference(players,params):
    return actual_leader_preference(players,params,season=2026,week=4)


def test_leaders_use_season_averages_ties_and_home_evidence_without_mutation(history):
    players=pool();players['game_id']='SEA@SF 10/11/2026 08:20PM ET'
    original=players.copy(deep=True)
    either=leader_preference(players,{'require_team_leader':True})
    assert set(either['required_player_ids'])=={'p2','p3'} and not either['home_only']
    assert either['through_week']==3 and either['scope']=='captain_or_flex'
    home=leader_preference(players,{'require_team_leader':True,'require_home_team_leader':True})
    assert home['required_player_ids']==['p3'] and home['home_team']=='SF'
    players.loc[players.player_id=='p5','projection']=1000
    assert leader_preference(players,{'require_team_leader':True,'require_home_team_leader':True})['required_player_ids']==['p3']
    next(r for r in history['rows'] if r['player_id']=='p5')['ppg']=37
    assert set(leader_preference(players,{'require_team_leader':True,'require_home_team_leader':True})['required_player_ids'])=={'p3','p5'}
    players.loc[players.player_id=='p5','projection']=original.loc[5,'projection']
    pd.testing.assert_frame_equal(players,original)


def test_missing_history_never_replaced_by_projections(history):
    history['rows']=[r for r in history['rows'] if r['player_id'] not in {'p3','p5','p7','p9'}]
    with pytest.raises(ValueError,match='both teams'):
        leader_preference(pool(),{'require_team_leader':True})


def test_kicker_can_be_leader(history):
    next(r for r in history['rows'] if r['player_id']=='p6')['ppg']=100
    assert 'p6' in leader_preference(pool(),{'require_team_leader':True})['required_player_ids']


@pytest.mark.parametrize('params,showdown', [({'require_team_leader':'yes'},True),({'require_home_team_leader':True},True),({'require_team_leader':True},False)])
def test_invalid_preferences_fail(params,showdown):
    with pytest.raises(ValueError):validate_leader_preferences(params,showdown=showdown)


def test_home_evidence_required_and_default_off():
    assert not leader_preference(pool(),{})['enabled']
    with pytest.raises(ValueError,match='home-team evidence'):
        leader_preference(pool(),{'require_team_leader':True,'require_home_team_leader':True})


@pytest.mark.parametrize('slot',['CPT','FLEX'])
def test_solver_and_validator_require_leader_in_either_slot(slot):
    players=pool();optimizer=OptimizerService.__new__(OptimizerService)
    # Low-scoring required player tests actual hard enforcement, not lucky selection.
    players.loc[players.player_id=='p4',['projection','p90']]=0
    kwargs={'locked_captain_player_id':'p4'} if slot=='CPT' else {'flex_only_player_ids':{'p4'}}
    rows=optimizer._solve_lineup(players,contest_type='captain',stack_params={'required_team_leader_ids':['p4']},include_control_comparison=False,**kwargs)
    assert rows and any(p['player_id']=='p4' and p['roster_position']==slot for p in rows)
    assert optimizer._validate_showdown_lineups([rows],requested_lineups=1,max_exposure=1,required_team_leader_ids={'p4'})[0]
    valid,reason=optimizer._validate_showdown_lineups([rows],requested_lineups=1,max_exposure=1,required_team_leader_ids={'missing'})
    assert not valid and 'team leader' in reason


def test_solver_cannot_fall_back_when_leader_missing():
    assert OptimizerService.__new__(OptimizerService)._solve_lineup(pool(),contest_type='captain',stack_params={'required_team_leader_ids':['missing']},include_control_comparison=False) is None


@pytest.mark.parametrize('strategy,objective',[('showdown_cash_baseline_v1','cash'),('showdown_gpp_portfolio_v3','gpp')])
def test_run_enforces_home_leader_and_blocks_excluded_leader(monkeypatch,strategy,objective):
    from backend.app.tests.product.test_showdown_qb_preferences import service
    monkeypatch.setattr('backend.app.product_services.showdown_data_readiness.is_live_slate',lambda *a,**k:False)
    optimizer=service();optimizer._load_player_pool.return_value['game_id']='SEA@SF 10/11/2026 08:20PM ET'
    params={'num_lineups':1,'require_team_leader':True,'require_home_team_leader':True}
    job=optimizer.run_job(season=2026,week=4,slate='THURSDAY_NIGHT',contest_format='showdown',objective=objective,strategy=strategy,params=params.copy())
    assert job.status=='completed',job.message
    assert any(p['player_id']=='p3' for p in job.results[0])
    assert job.params['strategy_runtime']['team_leader_preference']['required_player_ids']==['p3']
    with pytest.raises(ValueError,match='Required season-average team leader is unavailable'):
        optimizer.run_job(season=2026,week=4,slate='THURSDAY_NIGHT',contest_format='showdown',objective=objective,strategy=strategy,params={**params,'exclude_player_ids':['p3']})


def test_incomplete_history_names_the_actual_showdown_control(monkeypatch):
    def missing(*args,**kwargs):
        raise ValueError('Season-average rank limits need complete stats and snap coverage for Week 5')
    monkeypatch.setattr('backend.app.product_services.showdown_team_leader_preferences.load_rankings',missing)
    with pytest.raises(ValueError,match='turn off Require at least one season-average non-QB team leader'):
        leader_preference(pool(),{'require_team_leader':True})
