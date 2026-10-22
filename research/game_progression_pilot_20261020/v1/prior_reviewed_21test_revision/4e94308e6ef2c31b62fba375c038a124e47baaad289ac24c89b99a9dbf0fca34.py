from copy import deepcopy
import pytest
from backend.app.product_services.game_progression_runtime import STATS,DK_FIELDS,decode_block,rollout,source_bound_dk_replay,mechanics_smoke
from backend.app.product_services.game_progression_policy import compile_policy


def ctx():return dict(game_id='2023_04_A_B',team='A',season=2023,own_pass_share=.6,opponent_pass_share=.6)
def state():return dict(field100=75,phase='KICKOFF',half=1,half_seconds=1800,possession_side=0,scores=[0,0])
def step(elapsed=1800):
    stats=[dict.fromkeys(STATS,0)for _ in range(2)];stats[0].update(official_pass_attempts=1,official_targets=1,physical_plays=1,passing_yards=10,receiving_yards=10,possessions=1)
    return dict(row_id=1,elapsed_seconds=elapsed,score_delta=[0,0],team_stats=stats,points_by_type=[{},{}])
def block():return dict(block_id='b',source_season=2023,context_key=['2023_04_A_B','A'],certified=True,start_possession_side=0,start=dict(field100=75,phase='KICKOFF',half=1,half_seconds=1800,score_sign=0),duration_seconds=1800,steps=[step()],terminal=dict(possession_side=None,field100=None,phase='halftime'),boundary_prefixes=[])


def test_complete_regulation_replays_common_uniforms_and_preserves_team_credits():
    p=compile_policy([block()],[ctx()]);openings=[dict(opening_id='o',source_season=2023,certified=True,first_half=dict(possession_side=0,field100=75,phase='KICKOFF'),second_half=dict(possession_side=1,field100=75,phase='KICKOFF'))]
    before=deepcopy((p,openings));a=rollout(p,openings,[ctx(),ctx()],[.1]*5,arm='contextual');b=rollout(p,openings,[ctx(),ctx()],[.1]*5,arm='control')
    assert a['status']==b['status']=='COMPLETE_REGULATION'and a['state']['half_seconds']==0
    assert a['team_stats']==b['team_stats']and a['team_stats'][0]['official_targets']==a['team_stats'][1]['official_targets']==1
    assert a['player_forecasts']=='UNKNOWN_UNASSIGNED'and(p,openings)==before


def test_score_orientation_and_single_physical_passing_td():
    b=block();s=step();s['team_stats'][0].update(passing_TD=1,receiving_TD=1);s['points_by_type'][0]={'pass_td':1};s['score_delta']=[6,0];b['steps']=[s]
    generated=dict(state(),possession_side=1,scores=[3,7]);r=decode_block(b,generated)
    assert r['state']['scores']==[3,13]and r['team_stats'][1]['passing_TD']==r['team_stats'][1]['receiving_TD']==1
    b['steps'][0]['points_by_type'][0]={'pass_td':2}
    with pytest.raises(ValueError):decode_block(b,generated)


def test_defensive_return_score_is_not_offensive_score():
    b=block();b['steps'][0]['score_delta']=[0,6];b['steps'][0]['points_by_type'][1]={'return_td':1}
    r=decode_block(b,state());assert r['state']['scores']==[0,6]
    assert r['team_stats'][0]['passing_TD']==0


def test_boundary_requires_exact_certified_prefix_no_future_points():
    b=block();boundary=step(1800);boundary.update(row_id=2,team_stats=[dict.fromkeys(STATS,0)for _ in range(2)])
    b['duration_seconds']=2000;b['steps']=[step(1700),boundary,step(2000)]
    assert decode_block(b,state())['status']=='UNKNOWN_HALF_BOUNDARY_PREFIX'
    b['boundary_prefixes']=[dict(elapsed_seconds=1800,steps_count=2,certified=True,half_end=True,terminal_phase='halftime')]
    r=decode_block(b,state());assert r['source_rows']==2 and r['prefix_used']and r['team_stats'][0]['official_pass_attempts']==1
    b['boundary_prefixes'][0]['steps_count']=1
    with pytest.raises(ValueError):decode_block(b,state())
    b['boundary_prefixes'][0]['steps_count']=2
    b['boundary_prefixes'][0]['elapsed_seconds']=1799
    assert decode_block(b,state())['status']=='UNKNOWN_HALF_BOUNDARY_PREFIX'


def test_full_block_cannot_hide_elapsed_gap_after_last_source_row():
    b=block();b['steps'][0]['elapsed_seconds']=1700
    with pytest.raises(ValueError):decode_block(b,state())


def test_credit_unknown_and_opportunity_doublecount_fail():
    for key,value in[('official_targets',2),('passing_yards',None),('receiving_yards',11),('physical_plays',2)]:
        b=block();b['steps'][0]['team_stats'][0][key]=value
        with pytest.raises(ValueError):decode_block(b,state())


def test_unsupported_opening_uniform_and_event_limits_visible():
    p=compile_policy([block()],[ctx()]);o=[dict(opening_id='o',source_season=2023,certified=True,first_half=dict(possession_side=0,field100=75,phase='KICKOFF'),second_half=dict(possession_side=1,field100=75,phase='KICKOFF'))]
    assert rollout(p,[],[ctx(),ctx()],[.1],arm='control')['status']=='UNSUPPORTED_TRAJECTORY'
    assert rollout(p,o,[ctx(),ctx()],[.1],arm='control')['status']=='INCOMPLETE_UNIFORM_STREAM'
    assert rollout(p,o,[ctx(),ctx()],[.1]*5,arm='control',max_events=1)['status']=='INCOMPLETE_EVENT_CAP'


def test_signed_source_scoring_is_not_future_player_forecast():
    r=source_bound_dk_replay(dict(dict.fromkeys(DK_FIELDS,0),fumbles_lost=1),full_individual_credits_known=True)
    assert r['points']==-1 and not r['future_player_forecast']
    assert source_bound_dk_replay({},full_individual_credits_known=False)['points']is None


def test_smoke_fixed_common_streams_and_cap_never_quality_acceptance():
    p=compile_policy([block()],[ctx()]);game=dict(game_id='2026_01_A_B',context_by_side=[ctx(),ctx()])
    out=mechanics_smoke(p,[],[game],clock=lambda:0.)
    assert len(out['paths'])==64 and out['status_counts']=={'UNSUPPORTED_TRAJECTORY':64}
    assert out['paths'][0]['uniform_stream_sha256']==out['paths'][1]['uniform_stream_sha256']
    assert not out['forecast_quality_assessed']and not out['tail_calibration_assessed']
    ticks=iter([0.,121.,122.]);out=mechanics_smoke(p,[],[game],clock=lambda:next(ticks))
    assert out['status']=='INCOMPLETE_TIME_CAP'and out['status_counts']=={'NOT_RUN_TIME_CAP':64}


def test_uncertified_opening_mass_masks_successful_path_law():
    p=compile_policy([block()],[ctx()]);o=dict(opening_id='a',source_season=2023,certified=True,first_half=dict(possession_side=0,field100=75,phase='KICKOFF'),second_half=dict(possession_side=1,field100=75,phase='KICKOFF'))
    out=rollout(p,[o,dict(o,opening_id='b',certified=False)],[ctx(),ctx()],[.1]*5,arm='control')
    assert out['status']=='COMPLETE_REGULATION'and not out['full_law_known']


@pytest.mark.parametrize('phase',['try','kickoff','control'])
def test_zero_clock_does_not_omit_pending_untimed_phase(phase):
    b=block();b['terminal']['phase']=phase
    assert decode_block(b,state())['status']=='UNKNOWN_PENDING_UNTIMED_OR_BOUNDARY_PHASE'


def test_early_source_half_end_is_unknown_not_clamped_or_exception():
    b=block();b['duration_seconds']=100;b['steps'][0]['elapsed_seconds']=100
    assert decode_block(b,state())['status']=='UNKNOWN_SOURCE_BOUNDARY_ALIGNMENT'


def test_td_and_yardage_need_compatible_opportunity_and_scoring_type():
    for label,value in[('passing_TD',2),('rushing_TD',1),('rushing_yards',3)]:
        b=block();b['steps'][0]['team_stats'][0][label]=value
        with pytest.raises(ValueError):decode_block(b,state())
    b=block();b['steps'][0]['points_by_type']=[{'field_goal':1},{'return_td':1}];b['steps'][0]['score_delta']=[3,6]
    with pytest.raises(ValueError):decode_block(b,state())
