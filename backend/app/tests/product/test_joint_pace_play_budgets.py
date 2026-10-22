from copy import deepcopy
import pytest
from backend.app.product_services.joint_pace_play_budgets import build_joint_pace_play_budgets,PACE_VERSION,PAIR_VERSION

TEAMS=('BUF','MIA','NE','NYJ','SF','SEA','LAR','ARI')


def inputs():
    schedule=[];pace=[];pairs=[]
    for week in range(1,6):
        matches=list(zip(TEAMS[:4],TEAMS[4:]))if week<4 else[('BUF','MIA'),('NE','LAR'),('ARI','NYJ'),('SF','SEA')]
        for i,(home,away)in enumerate(matches):
            gid=f'2026_{week:02d}_{away}_{home}';schedule.append(dict(game_id=gid,season=2026,week=week,game_type='REG',home_team=home,away_team=away))
            for team in(home,away):
                seconds=5 if team in TEAMS[:4]else 30
                pace.append(dict(game_id=gid,team=team,metrics={'G01-M04':dict(eligible_events=10,known_outcome_events=10,unknown_outcome_events=0,unknown_eligibility_events=0,observed_outcome_sum=seconds*10,value=seconds,native_order_verified=True)}))
            values=([40,60],[50,70],[60,70],[80,100])[i];values=[x+(week-4)*2 for x in values]
            pairs.append(dict(game_id=gid,season=2026,week=week,home_team=home,away_team=away,values=values+[None,None]))
    p=dict(version=PACE_VERSION,before_period=202606,semantic_sha256='pace',pregame_serving_eligible=False,game_rows=pace)
    q=dict(version=PAIR_VERSION,before_period=202606,semantic_sha256='pair',pregame_serving_eligible=False,game_rows=pairs)
    return p,q,schedule


def test_both_axes_exact_four_cells_and_joint_budget_response():
    r=build_joint_pace_play_budgets(*inputs());v=r['home_away_pooled_observed_profile']
    assert len(r['game_rows'])==20 and len(r['evaluation_game_ids'])==8
    for h in('fast','slow'):
        for a in('fast','slow'):assert v['cells'][h][a]['exact_full_cell']['games']==2
    assert v['both_axes_difference_of_differences']['joint_total_mean']==30
    assert v['cells']['fast']['fast']['exact_full_cell']['population_covariance']==1
    assert v['cells']['fast']['fast']['exact_full_cell']['joint_total_mean']==102


def test_early_reference_labels_absent_even_if_later_reference_outcomes_change():
    p,q,s=inputs()
    for row in p['game_rows']:
        if row['game_id'].startswith('2026_03'):row['metrics']['G01-M04'].update(observed_outcome_sum=990,value=99)
    r=build_joint_pace_play_budgets(p,q,s)
    for row in r['game_rows']:
        if row['week']<4:
            assert row['home_prior_group']is None and row['away_prior_group']is None
            assert not any(v['reference_ready']for v in row['pace_contexts'].values())


def test_strict_prior_does_not_consume_evaluated_current_or_later_pace():
    p,q,s=inputs();before=build_joint_pace_play_budgets(p,q,s)
    for row in p['game_rows']:
        if row['game_id'].startswith('2026_05'):row['metrics']['G01-M04'].update(observed_outcome_sum=990,value=99)
    after=build_joint_pace_play_budgets(p,q,s)
    assert before['game_rows']==after['game_rows']
    for row in after['game_rows']:
        assert all(v['max_contributing_period']is None or v['max_contributing_period']<202600+row['week']for v in row['pace_contexts'].values())


def test_pooled_seconds_exposures_not_mean_of_game_means():
    p,q,s=inputs();m=p['game_rows'][0]['metrics']['G01-M04'];m.update(known_outcome_events=20,eligible_events=20,observed_outcome_sum=200,value=10)
    r=build_joint_pace_play_budgets(p,q,s);v=r['reference_team_pace']['BUF']
    assert v['exact_seconds_per_interval']==300/40


def test_missing_prior_scheduled_game_not_skipped_and_masks_compatible_full_cells():
    p,q,s=inputs();p['game_rows']=[r for r in p['game_rows']if not(r['team']=='BUF'and r['game_id'].startswith('2026_04'))]
    r=build_joint_pace_play_budgets(p,q,s);g=next(x for x in r['game_rows']if x['week']==5 and x['home_team']=='BUF')
    assert g['home_prior_group']is None
    assert g['pace_contexts']['BUF']['unknown_game_ids']==['2026_04_MIA_BUF']
    c=r['home_away_pooled_observed_profile']['cells']['fast']['fast']
    assert c['known_complete_sample']['joint_total_mean']==100
    assert c['exact_full_cell']['joint_total_mean']is None
    assert r['home_away_pooled_observed_profile']['cells']['fast']['slow']['exact_full_cell']['joint_total_mean']==122


def test_missing_response_never_zero_and_same_complete_sample_for_all_axes():
    p,q,s=inputs();next(r for r in q['game_rows']if r['game_id']=='2026_04_MIA_BUF')['values'][0]=None
    c=build_joint_pace_play_budgets(p,q,s)['home_away_pooled_observed_profile']['cells']['fast']['fast']
    assert c['exact_full_cell']['home_mean']is None and c['exact_full_cell']['away_mean']is None
    assert c['known_complete_sample']['home_mean']==42 and c['known_complete_sample']['away_mean']==62
    assert c['known_complete_sample']['population_covariance']is None


def test_middle_pace_is_excluded_not_donated_to_fast_or_slow():
    p,q,s=inputs()
    for row in p['game_rows']:
        if row['team']=='BUF':row['metrics']['G01-M04'].update(observed_outcome_sum=150,value=15)
    r=build_joint_pace_play_budgets(p,q,s);logs=[v for v in r['game_rows']if v['week']>=4 and v['home_team']=='BUF']
    assert all(v['home_prior_group']=='middle'for v in logs)
    for h in('fast','slow'):
        for a in('fast','slow'):assert not set(v['game_id']for v in logs)&set(r['home_away_pooled_observed_profile']['cells'][h][a]['known_member_game_ids'])


def test_no_swapped_duplicate_native_games_or_orientation():
    p,q,s=inputs();q['game_rows'].append(deepcopy(q['game_rows'][0]))
    with pytest.raises(ValueError,match='Unique physical'):build_joint_pace_play_budgets(p,q,s)
    p,q,s=inputs();q['game_rows'][0]['home_team']='MIA'
    with pytest.raises(ValueError,match='orientation'):build_joint_pace_play_budgets(p,q,s)


def test_zero_variance_and_covariance_baseline_same_sample():
    p,q,s=inputs()
    for row in q['game_rows']:row['values'][:2]=[0,0]
    r=build_joint_pace_play_budgets(p,q,s);c=r['home_away_pooled_observed_profile']['cells']['fast']['fast']['exact_full_cell']
    assert c['joint_total_mean']==0 and c['population_covariance']==0
    assert c['paired_cross_moment']-c['independence_marginal_product']==0


@pytest.mark.parametrize('fault',['bool','negative','fraction','nonfinite'])
def test_invalid_physical_measurements_rejected(fault):
    p,q,s=inputs();q['game_rows'][0]['values'][0]={'bool':True,'negative':-1,'fraction':1.2,'nonfinite':float('nan')}[fault]
    with pytest.raises(ValueError):build_joint_pace_play_budgets(p,q,s)


def test_pace_unknown_partition_and_order_never_certified():
    p,q,s=inputs();p['game_rows'][0]['metrics']['G01-M04']['native_order_verified']=False
    assert build_joint_pace_play_budgets(p,q,s)['reference_team_pace']['BUF']['exact_seconds_per_interval']is None
    p,q,s=inputs();p['game_rows'][0]['metrics']['G01-M04']['unknown_outcome_events']=1
    with pytest.raises(ValueError,match='partition'):build_joint_pace_play_budgets(p,q,s)


def test_changed_scope_recipe_or_duplicate_schedule_rejected():
    p,q,s=inputs();q['before_period']=202605
    with pytest.raises(ValueError):build_joint_pace_play_budgets(p,q,s)
    p,q,s=inputs();s.append(deepcopy(s[0]))
    with pytest.raises(ValueError,match='Unique native'):build_joint_pace_play_budgets(p,q,s)
    with pytest.raises(ValueError,match='Predeclared'):build_joint_pace_play_budgets(*inputs(),last_n=3)


def test_conditional_comparators_materially_hold_each_opposing_axis_fixed():
    r=build_joint_pace_play_budgets(*inputs())['home_away_pooled_observed_profile']
    c=r['fast_minus_slow_by_fixed_opposing_axis']
    assert c['home']['fast']['joint_total_mean']==-30
    assert c['home']['slow']['joint_total_mean']==-60
    assert c['away']['fast']['joint_total_mean']==-20
    assert c['away']['slow']['joint_total_mean']==-50
