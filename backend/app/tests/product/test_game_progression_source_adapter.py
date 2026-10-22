from copy import deepcopy
import pytest
from backend.app.product_services.game_progression_runtime import STATS,decode_block
from backend.app.product_services.game_progression_source_adapter import prior_contexts,adapt_library


def fixture():
    s=dict(possession_side=0,yardline100=75,phase='scrimmage',half=1,half_seconds_remaining=1800,scores=[0,0]);end=dict(s,possession_side=None,yardline100=None,phase='halftime',half_seconds_remaining=0)
    stats=[dict.fromkeys(STATS,0)for _ in range(2)];stats[0].update(official_pass_attempts=1,official_targets=1,physical_plays=1,passing_yards=10,receiving_yards=10,passing_TD=1,receiving_TD=1,possessions=1)
    row=dict(play_id='1',cumulative_elapsed_endpoint=1800,event=dict(production_by_side=stats,score_delta=[6,0],points_by_type=[{'pass_touchdown':6},{}]))
    block=dict(game_id='2023_04_A_B',block_ordinal=1,start_state=s,physical_start_support={k:s[k]for k in('possession_side','yardline100','phase','half')},source_sides=['A','B'],certified=True,elapsed_seconds=1800,terminal_state=end,steps=[row],certified_prefixes=[dict(through_play_id='1',elapsed_seconds=1800,terminal_state=end)],barriers=[])
    source=dict(version='original_drive_trajectory_blocks_v1',blocks=[block]);ctx=[dict(game_id=block['game_id'],team='A',season=2023,own_pass_share=.5,opponent_pass_share=None)]
    opening=[dict(game_id=block['game_id'],source_season=2023,source_half=h,certified=True,start_state=s)for h in(1,2)]
    return source,opening,ctx


def test_lossless_units_source_orientation_and_boundary_mapping():
    source,opening,ctx=fixture();before=deepcopy(source);v=adapt_library(source,opening,ctx);b=v['blocks'][0]
    assert b['steps'][0]['points_by_type']==[{'pass_td':1},{}]and b['boundary_prefixes'][0]['steps_count']==1
    state=dict(possession_side=1,field100=75,phase='scrimmage',half=1,half_seconds=1800,scores=[0,0])
    out=decode_block(b,state);assert out['state']['scores']==[0,6]and source==before


def test_unknown_production_retained_not_zero_filled():
    source,opening,ctx=fixture();source['blocks'][0]['steps'][0]['event']['production_by_side'][0]['passing_yards']=None
    v=adapt_library(source,opening,ctx);assert not v['blocks'][0]['certified']and v['blocks'][0]['steps'][0]['team_stats'][0]['passing_yards']is None
    assert len(v['blocks'])==1


def test_unscoped_source_and_quarantine_mass_explicit():
    source,opening,ctx=fixture();b=source['blocks'][0];b['start_state']['possession_side']=None;b['physical_start_support']['possession_side']=None
    q=[dict(source_ordinal=1,threat='GLOBAL_POSSIBLE_REG'),dict(source_ordinal=2,threat='EXPLICIT_OUT_OF_SCOPE')]
    v=adapt_library(source,opening,ctx,train_quarantine_rows=q)
    assert not v['blocks']and len(v['unscopable_threats'])==2 and len(v['normalization_coverage'])==1


def test_prior_share_uses_only_exact_prior_windows():
    r=dict(game_id='2023_04_A_B',team='A',period=202304,windows={a:dict(game_ids=['g1','g2','g3'],periods=[202301,202302,202303])for a in('own','opponent')},features={f'weekly3_{a}_{ch}_mean':v for a in('own','opponent')for ch,v in [('pass_attempts',20),('rush_attempts',10)]})
    assert prior_contexts([r])[0]['own_pass_share']==2/3
    r['windows']['own']['game_ids']=[];assert prior_contexts([r])[0]['own_pass_share']is None
    r['windows']['opponent']['periods'][-1]=202304
    with pytest.raises(ValueError):prior_contexts([r])


def test_actual_pure_source_builder_to_decoder_preserves_signed_credit():
    # Shared fixture, not a saved/raw source read or empirical pilot.
    from backend.app.tests.product.test_game_state_reconstruction import row,build
    from backend.app.product_services.game_state_reconstruction import build_original_drive_blocks
    common=dict(drive_play_id_started=10,drive_play_id_ended=20,drive_end_transition='END_HALF',qtr=2,game_half='Half1')
    first=row(quarter_seconds_remaining=10,half_seconds_remaining=10,game_seconds_remaining=1810,**common)
    end=row(play_id=20,order_sequence=2,play_type='quarter_end',play_type_nfl='END_QUARTER',rush_attempt=0,quarter_seconds_remaining=0,half_seconds_remaining=0,game_seconds_remaining=1800,yardline_100=None,**common)
    after=row(play_id=30,order_sequence=3,drive=2,qtr=3,game_half='Half2',quarter_seconds_remaining=900,half_seconds_remaining=1800,game_seconds_remaining=1800)
    source=build_original_drive_blocks(build(first,end,after));ctx=[dict(game_id=first['game_id'],team='BUF',season=2023,own_pass_share=None,opponent_pass_share=None)]
    v=adapt_library(source,[],ctx);b=v['blocks'][0]
    assert b['certified'],b['source_barriers']
    result=decode_block(b,dict(possession_side=0,field100=75,phase='scrimmage',half=1,half_seconds=10,scores=[0,0]))
    assert result['status']=='DECODED'and result['team_stats'][0]['rushing_yards']==-2 and result['team_stats'][0]['possessions']==1


def test_marker_exclusion_requires_explicit_source_proof_and_keeps_ledger():
    source,opening,ctx=fixture();proof=dict.fromkeys(('certified','zero_official_counts','zero_physical_plays','zero_event_points','zero_event_seconds','raw_state_not_filled','deterministic_admin_marker_exclusion'),True);proof.update(kind='GAME_START',corroborating_kickoff_play_id='10')
    marker=dict(game_id='2023_04_A_B',play_id='0',source_ordinal=0,source_order=0,proof=proof);source['deterministic_admin_markers']=[marker]
    v=adapt_library(source,opening,ctx);assert v['deterministic_exclusion_ledger']==[marker]and len(v['blocks'])==1
    marker['proof']['zero_event_seconds']=False
    with pytest.raises(ValueError):adapt_library(source,opening,ctx)


def test_timeout_runoff_requires_and_preserves_retained_source_bridge():
    source,opening,ctx=fixture();proof=dict.fromkeys(('certified','zero_official_counts','zero_physical_plays','zero_event_points','raw_state_not_filled','deterministic_admin_marker_exclusion','elapsed_transfer_certified'),True)
    proof.update(kind='TIMEOUT',phase='control',zero_event_seconds=False,observed_runoff_seconds=20)
    source['deterministic_admin_markers']=[dict(game_id='2023_04_A_B',play_id='2',proof=proof)]
    with pytest.raises(ValueError):adapt_library(source,opening,ctx)
    row=source['blocks'][0]['steps'][0];row['deterministic_clock_bridge']=dict(marker_play_ids=['2'],observed_runoff_preserved=True,zero_football_events=True,elapsed_seconds=1800,source_clock_endpoints=[1800,20,0])
    row['certified_endpoint']=source['blocks'][0]['terminal_state']
    adapted=adapt_library(source,opening,ctx);b=adapted['blocks'][0]
    assert b['duration_seconds']==b['steps'][0]['elapsed_seconds']==1800
    assert b['steps'][0]['source_clock_bridge']==row['deterministic_clock_bridge']
    assert b['steps'][0]['source_transition_endpoint']['phase']=='halftime'
    assert decode_block(b,dict(possession_side=0,field100=75,phase='scrimmage',half=1,half_seconds=1800,scores=[0,0]))['state']['half_seconds']==0
    proof['elapsed_transfer_certified']=False
    with pytest.raises(ValueError):adapt_library(source,opening,ctx)


def test_state_only_and_unknown_channel_are_not_full_joint_forecast():
    source,opening,ctx=fixture();raw=source['blocks'][0];raw['certified']=False;raw['state_transition_certified']=True
    raw['steps'][0]['event']['production_by_side'][0]['receiving_yards']=None
    b=adapt_library(source,opening,ctx)['blocks'][0]
    assert b['source_state_transition_certified']is True and not b['certified']
    assert b['steps'][0]['team_stats'][0]['receiving_yards']is None


def test_phase_specific_kickoff_coordinate_kept_not_scrimmage_geometry():
    source,opening,ctx=fixture();raw=source['blocks'][0]
    raw['start_state'].update(phase='kickoff',yardline100=35,coordinate_system='SOURCE_KICKOFF_FIELD100_PHASE_SPECIFIC')
    raw['physical_start_support'].update(phase='kickoff',yardline100=35,coordinate_system='SOURCE_KICKOFF_FIELD100_PHASE_SPECIFIC')
    v=adapt_library(source,opening,ctx)
    assert v['blocks'][0]['start']['field100']==35 and v['blocks'][0]['start']['coordinate_system']=='SOURCE_KICKOFF_FIELD100_PHASE_SPECIFIC'
    assert v['openings'][0]['first_half']['coordinate_system']=='SOURCE_KICKOFF_FIELD100_PHASE_SPECIFIC'
