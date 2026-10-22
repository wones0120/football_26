from copy import deepcopy
import pytest
from backend.app.product_services.captain_scoring_calibration import two_td_probability,td_rows,feature_rows,scores,paired_interval


def test_exact_two_touchdown_concentration_depletes_remaining_opportunities():
    assert two_td_probability({'a':2.,'b':1.},{'a':2,'b':1})==pytest.approx(4/9)
    assert two_td_probability({'a':2.,'b':1.},{'a':2,'b':1},deplete=True)==pytest.approx(1/3)
    assert two_td_probability({'a':1.},{'a':2},deplete=True)==1
    assert two_td_probability({'a':1.,'b':1.},{'a':1,'b':1})==0
    with pytest.raises(ValueError):two_td_probability({'a':1.},{'a':1})
    with pytest.raises(ValueError):two_td_probability({'a':float('nan')},{'a':2})


def test_role_rate_predictions_cannot_consume_current_period_td_labels():
    rows=[]
    for period in [202301,202302,202401]:
        for i in range(2):
            rows.append(dict(period=period,team='CHI',opponent='NE',source_id=len(rows)+1,player_master_id='actor'+str(i),source_player_id=str(i),position='RB',rush_attempts=10.,rushing_tds=1.,targets=0.,receptions=0.,receiving_tds=0.,passing_tds=0.))
    original=deepcopy(rows);first,_=td_rows(rows,before_period=202402)
    changed=deepcopy(rows);changed[-1]['rushing_tds']=0.;changed[-2]['rushing_tds']=2.
    second,_=td_rows(changed,before_period=202402)
    assert len(first)==len(second)==1
    assert first[0]['label']==0 and second[0]['label']==1
    assert first[0]['baseline']==second[0]['baseline'] and first[0]['candidate']==second[0]['candidate']
    assert first[0]['rates_max_period']==202302
    assert rows==original
    with pytest.raises(ValueError,match='Future'):td_rows(rows,before_period=202401)


def feature_fixture():
    games=[];schedules=[];history=[]
    for week in range(1,6):
        games.append(dict(period=202600+week,team='CHI',opponent='NE',fg_att=2.,fg_made=1.,pass_tds=2.,rush_tds=1.,source_ids=[week]))
        schedules.append(dict(game_id=f'2026_{week:02d}_NE_CHI',season=2026,week=week,home_team='CHI',away_team='NE',created_at='2026-01-01T00:00:00Z',raw_nfl_schedule_id=week,raw_row_json=dict(total_line=50.5,spread_line=3.,home_score=999)))
        history.append(dict(source_id=week,period=202600+week,imported_at='2026-10-01T00:00:00Z'))
    market=dict(game_id='2026_05_NE_CHI',market_snapshot_id='q',home_team='CHI',away_team='NE',game_total=50.5,home_spread=-3.,kickoff_at='2026-10-08T20:00:00Z',observed_at='2026-10-08T18:00:00Z',ingested_at='2026-10-08T18:01:00Z')
    return games,schedules,[market],history


def test_market_sign_source_clocks_and_current_outcome_do_not_leak_into_features():
    games,schedules,markets,history=feature_fixture()
    rows,_=feature_rows(games,schedules,markets,history,before_period=202606)
    target=next(a for a in rows if a['period']==202605)
    assert target['features']==[26.75,23.75,2.,1.,3.] and target['original_input_chronology_verified']
    assert target['feature_source_ids']==[1,2,3,4] and 5 not in target['feature_source_ids']
    games[-1]['fg_made']=4.;schedules[-1]['raw_row_json']['home_score']=0
    changed,_=feature_rows(games,schedules,markets,history,before_period=202606)
    assert changed[-1]['features']==target['features'] and changed[-1]['label']==4
    history[3]['imported_at']='2026-10-08T19:30:00Z'
    late,ex=feature_rows(games,schedules,markets,history,before_period=202606)
    assert not any(a['period']==202605 for a in late)
    assert any('unavailable' in a['reason'] for a in ex)
    with pytest.raises(ValueError,match='Future'):feature_rows(games,schedules,markets,history,before_period=202605)


def test_proper_scores_and_game_cluster_intervals():
    good,_,_=scores([0,1],[[.9,.1],[.1,.9]])
    bad,_,_=scores([0,1],[[.1,.9],[.9,.1]])
    assert good['log_loss']<bad['log_loss'] and good['brier']<bad['brier']
    ci=paired_interval([-1.,-1.,-2.,-2.],['game1','game1','game2','game2'])
    assert ci['games']==2 and ci['upper']<0
    with pytest.raises(ValueError):scores([0],[[.2,.2]])
