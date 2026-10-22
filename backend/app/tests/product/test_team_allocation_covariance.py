from copy import deepcopy
import pytest
from backend.app.tests.product.test_opportunity_events import play,build,CUTOFF
from backend.app.product_services.player_opportunity_components import build_player_opportunity_components
from backend.app.product_services.team_allocation_covariance import build_team_allocation_covariance,RESIDUAL


def source():
    rows=[]
    for week in (7,8):
        for i in range(4):
            rows.append(play(i+1,game_id=f'2025_{week:02}_SF_WAS',week=week,posteam='SF',receiver_player_id='w' if (i<3 if week==7 else i<1) else 'r'))
        for i,actor in enumerate(('q','r')):
            rows.append(play(10+i,game_id=f'2025_{week:02}_SF_WAS',week=week,posteam='SF',play_type='run',pass_attempt=0,rush_attempt=1,rusher_player_id=actor))
    s=build_player_opportunity_components({'event_evidence':build(rows)},before_period=202509,cutoff=CUTOFF)
    s.update(pregame_serving_eligible=False,evidence_use='postlock_descriptive_not_pregame_or_serving');return s


def run(s=None,**kw):return build_team_allocation_covariance(s or source(),before_period=202509,**kw)


def test_native_target_competition_covariance_conserved_with_residual_coordinate():
    m=run()['team_windows'][0]['metrics']['X02-M09']
    assert [r['key'] for r in m['coordinates']]==['native:r','native:w',RESIDUAL]
    assert m['covariance'][0][0]==pytest.approx(.125)
    assert m['covariance'][0][1]==pytest.approx(-.125)
    assert all(sum(row)==pytest.approx(0) for row in m['covariance'])
    assert m['covariance'][-1]==[0,0,0]
    assert run()['forecast'] is None


def test_rush_universe_includes_QB_and_unknown_canonical_native_mass():
    s=source()
    for r in s['actor_game_rows']:
        if r['source_player_id']=='q':r['player_master_id']=None
    m=run(s)['team_windows'][0]['metrics']['X02-M10']
    q=next(r for r in m['coordinates'] if r['source_player_id']=='q')
    assert q['player_master_id'] is None and m['covariance'] is not None
    assert all(sum(log['known_native_counts'].values())==2 for log in m['logs'])


def test_unknown_physical_eligibility_masks_full_covariance_not_zero_fill():
    s=source();b=s['team_denominators'][0]['official'];b['unknown_eligibility_events']['targets']=1;b['counts']['targets']=None
    m=run(s)['team_windows'][0]['metrics']['X02-M09']
    assert m['covariance'] is None and m['known_complete_allocation_logs']==1
    assert m['known_complete_sample_covariance'] is None


def test_unattributed_mass_cannot_be_assigned_independent_residual_to_certify_known_actors():
    s=source();s['actor_game_rows']=[r for r in s['actor_game_rows'] if not(r['game_id'].split('_')[1]=='07' and r['source_player_id']=='w')]
    m=run(s)['team_windows'][0]['metrics']['X02-M09']
    assert m['covariance'] is None and m['logs'][0]['known_residual_lower_bound']==3
    assert not m['logs'][0]['allocation_vector_exact']


def test_same_source_absent_channel_actor_is_zero_in_complete_vector_not_DNP():
    s=source();r=next(r for r in s['actor_game_rows'] if r['game_id'].split('_')[1]=='07' and r['source_player_id']=='r')
    # Move the one target to w while keeping official team totals; r has measured rushing but no target on this log.
    other=next(r for r in s['actor_game_rows'] if r['game_id'].split('_')[1]=='07' and r['source_player_id']=='w')
    for m,n in ((r['metrics']['targets'],0),(other['metrics']['targets'],4)):
        m.update(observed_outcome_sum=n,known_outcome_events=n,eligible_events=n)
    m=run(s)['team_windows'][0]['metrics']['X02-M09']
    assert m['covariance'] is not None and 'native:r' not in m['logs'][0]['known_native_counts']


def test_single_observed_log_has_no_covariance_and_no_season_transport():
    x=run(last_n=1);m=x['team_windows'][0]['metrics']['X02-M09']
    assert m['observed_team_logs']==1 and m['covariance'] is None
    with pytest.raises(ValueError):run(last_n=0)


def test_order_and_recapture_metadata_stable():
    s=source();sha=run(s)['semantic_sha256'];s['actor_game_rows'].reverse();s['team_denominators'].reverse();s['provenance']['recaptured_at']='later'
    assert run(s)['semantic_sha256']==sha


def test_covariance_contract_never_current_predictive_or_optimizer_consumption():
    from backend.app.product_services.team_allocation_covariance import require_feature_use
    x=run();assert require_feature_use(x,purpose='offline_descriptive') is x
    for purpose in ('model','forecast','optimizer','scenario'):
        with pytest.raises(ValueError):require_feature_use(x,purpose=purpose)
