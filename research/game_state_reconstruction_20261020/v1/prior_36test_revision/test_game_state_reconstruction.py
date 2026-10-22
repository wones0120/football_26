from copy import deepcopy
import pytest
from backend.app.product_services.game_state_reconstruction import reconstruct_game_transitions, state_before, PROJECTION_FIELDS, build_original_drive_blocks

LINEAGE = dict(all_source_rows_retained=True, sha256='a'*64, captured_at='2026-10-20T00:00:00Z', actual_read_at='2026-10-21T00:00:00Z')


def row(**changes):
    raw = dict(game_id='2023_01_BUF_NYJ', play_id=10, season=2023, week=1, season_type='REG',
               home_team='NYJ', away_team='BUF', posteam='BUF', defteam='NYJ', order_sequence=1,
               drive=1, fixed_drive=8, qtr=1, game_half='Half1', quarter_seconds_remaining=900,
               half_seconds_remaining=1800, game_seconds_remaining=3600, down=1, ydstogo=10,
               yardline_100=75, posteam_score=0, defteam_score=0, posteam_score_post=0,
               defteam_score_post=0, play_type='run', play_type_nfl='RUSH', rush_attempt=1,
               pass_attempt=0, sack=0, qb_dropback=0, qb_scramble=0, qb_spike=0, qb_kneel=0,
               two_point_attempt=0, play_deleted=0, replay_or_challenge=0, rusher_player_id='00-0030001',
               yards_gained=-2, rushing_yards=-2, lateral_rush=0, lateral_reception=0,
               lateral_return=0, lateral_recovery=0, penalty=0, touchdown=0, safety=0, field_goal_attempt=0,
               extra_point_attempt=0, defensive_two_point_conv=0,
               defensive_extra_point_conv=0)
    raw.update(changes)
    return raw


def build(*rows):
    return reconstruct_game_transitions(rows, source_lineage=LINEAGE)


def test_native_order_not_numeric_play_id_and_original_drive_separate():
    result=build(row(play_id=90,order_sequence=2,quarter_seconds_remaining=890,half_seconds_remaining=1790,game_seconds_remaining=3590),row())
    steps=result['games'][0]['rows']
    assert [s['play_id'] for s in steps]==['10','90']
    assert steps[0]['original_drive']==1 and steps[0]['fixed_drive']==8
    assert steps[0]['elapsed_to_next']==10
    assert steps[0]['source_ordinal']==1
    assert steps[0]['event']['source_signed_yards']['rushing_yards']==-2


@pytest.mark.parametrize('field,value',[('order_sequence',None),('play_id',10),('order_sequence',1)])
def test_missing_or_duplicate_order_or_key_never_certifies_next(field,value):
    other=row(play_id=20,order_sequence=2)
    other[field]=value
    result=build(row(),other)
    assert not result['games'][0]['native_order_verified']
    assert all(s['next_observed_state'] is None for s in result['games'][0]['rows'])


def test_every_row_retained_including_quarantine_and_no_play():
    result=build(row(),row(play_id=20,order_sequence=2,play_type='no_play',penalty=1),row(game_id='bad'))
    assert result['input_rows']==3
    assert len(result['games'][0]['rows'])==2 and len(result['quarantine'])==1
    assert result['games'][0]['rows'][1]['event']['official_counts']==dict(pass_attempts=0,rush_attempts=0,targets=0)


def test_possession_orientation_maps_points_to_defense_not_initial_offense():
    result=build(row(posteam_score_post=0,defteam_score_post=6,return_touchdown=1,td_team='NYJ'))
    assert result['games'][0]['rows'][0]['event']['score_delta']==[6,0]


def test_missing_scores_not_filled_from_final_or_total_scores():
    state=state_before(row(posteam_score=None,total_home_score=30,home_score=30),['NYJ','BUF'])
    assert state['scores']==[0,None]
    assert 'unknown_preplay_scores' in state['problems']


@pytest.mark.parametrize('changes,reason',[
    ({'play_deleted':1},'deleted_source_row'),
    ({'replay_or_challenge':1},'replay_or_challenge_not_independently_resolved'),
    ({'qb_scramble':1,'rush_attempt':0},'unknown_physical_or_call_shape'),
    ({'pass_attempt':1,'rush_attempt':1},'unknown_physical_or_call_shape'),
    ({'lateral_rush':1},'lateral_credit_chain_unproven'),
])
def test_explicit_ambiguity_barriers(changes,reason):
    assert reason in build(row(**changes))['games'][0]['rows'][0]['barriers']


def test_allzero_native_physical_class_unknown_not_zero():
    step=build(row(rush_attempt=0))['games'][0]['rows'][0]
    assert step['event']['official_counts']['rush_attempts'] is None


def test_sack_once_no_pass_attempt():
    step=build(row(play_type='pass',play_type_nfl='SACK',rush_attempt=0,pass_attempt=1,sack=1,qb_dropback=1))['games'][0]['rows'][0]
    assert step['event']['choice']=='pass'
    assert step['event']['official_counts']==dict(pass_attempts=0,rush_attempts=0,targets=0)


def test_scramble_is_one_carry_and_pass_call():
    step=build(row(qb_scramble=1,qb_dropback=1))['games'][0]['rows'][0]
    assert step['event']['choice']=='pass'
    assert step['event']['official_counts']==dict(pass_attempts=0,rush_attempts=1,targets=0)


def test_missing_receiver_is_unknown_target_not_throwaway_zero():
    step=build(row(play_type='pass',play_type_nfl='PASS',pass_attempt=1,rush_attempt=0,qb_dropback=1))['games'][0]['rows'][0]
    assert step['event']['official_counts']['targets'] is None
    assert 'unknown_target_recipient_census' in step['barriers']


@pytest.mark.parametrize('changes',[
    dict(qtr=3,game_half='Half2',half_seconds_remaining=1800,quarter_seconds_remaining=900,game_seconds_remaining=1800),
    dict(qtr=5,game_half='Overtime',half_seconds_remaining=600,quarter_seconds_remaining=600,game_seconds_remaining=600),
])
def test_halftime_and_ot_never_transferred_as_regular_elapsed(changes):
    result=build(row(),row(play_id=20,order_sequence=2,**changes))
    assert 'half_or_regulation_boundary' in result['games'][0]['rows'][0]['barriers']
    assert result['games'][0]['rows'][0]['elapsed_to_next'] is None


def test_reversed_clock_never_clipped():
    result=build(row(quarter_seconds_remaining=890,half_seconds_remaining=1790,game_seconds_remaining=3590),row(play_id=20,order_sequence=2))
    assert 'reversed_or_corrected_clock' in result['games'][0]['rows'][0]['barriers']
    assert result['games'][0]['rows'][0]['elapsed_to_next'] is None


def test_next_state_is_immediate_admin_not_later_physical():
    result=build(row(),row(play_id=20,order_sequence=2,play_type='time_out',play_type_nfl='TIMEOUT',rush_attempt=0),row(play_id=30,order_sequence=3))
    assert result['games'][0]['rows'][0]['next_play_id']=='20'
    assert result['games'][0]['rows'][0]['next_observed_state']['phase']=='control'


def test_score_disagreement_is_barrier():
    result=build(row(posteam_score_post=6),row(play_id=20,order_sequence=2))
    assert 'reported_post_vs_next_pre_score_disagreement' in result['games'][0]['rows'][0]['barriers']


def test_clock_lineage_and_caps():
    with pytest.raises(ValueError,match='clocks'):
        reconstruct_game_transitions([],source_lineage={**LINEAGE,'actual_read_at':'2026-01-01T00:00:00Z'})
    with pytest.raises(ValueError,match='cap'):
        reconstruct_game_transitions([row()],source_lineage=LINEAGE,max_rows=0)


def test_inputs_immutable_and_schema_covers_corrections():
    raw=row();before=deepcopy(raw);build(raw)
    assert raw==before
    assert {'play_deleted','replay_or_challenge','penalty','order_sequence','drive','fixed_drive'}<=set(PROJECTION_FIELDS)


def drive_rows():
    common=dict(drive_play_id_started=10,drive_play_id_ended=20,drive_end_transition='PUNT')
    return [row(**common),row(play_id=20,order_sequence=2,play_type='punt',play_type_nfl='PUNT',
        rush_attempt=0,punt_attempt=1,punt_blocked=0,quarter_seconds_remaining=890,
        half_seconds_remaining=1790,game_seconds_remaining=3590,**common),
        row(play_id=30,order_sequence=3,drive=2,posteam='NYJ',defteam='BUF',
            quarter_seconds_remaining=880,half_seconds_remaining=1780,game_seconds_remaining=3580)]


def test_certified_drive_uses_actual_contiguous_rows_and_next_field():
    blocks=build_original_drive_blocks(build(*drive_rows()))
    b=blocks['blocks'][0]
    assert b['certified'],b['barriers']
    assert b['elapsed_seconds']==20
    assert b['points_by_side']==[0,0]
    assert b['team_official_counts'][1]['rush_attempts']==1
    assert b['terminal_state']['possession_side']==0
    assert b['terminal_state']['yardline100']==75  # Not 100 minus gained yards.
    assert [p['elapsed_seconds'] for p in b['certified_prefixes']]==[10,20]
    assert blocks['coverage']['uncertified_groups']==1


def test_missing_original_start_and_noncontiguous_id_do_not_certify():
    rows=drive_rows();rows[0].pop('drive_play_id_started')
    blocks=build_original_drive_blocks(build(*rows))
    assert not blocks['blocks'][0]['certified']
    rows=drive_rows()+[row(play_id=40,order_sequence=4,drive=1)]
    blocks=build_original_drive_blocks(build(*rows))
    assert 'missing_or_noncontiguous_original_drive' in blocks['blocks'][0]['barriers']


def test_unknown_row_breaks_prefix_cannot_resume_later():
    rows=drive_rows();rows[0]['receiver_player_id']=None
    rows[0].update(play_type='pass',play_type_nfl='PASS',pass_attempt=1,rush_attempt=0,qb_dropback=1)
    b=build_original_drive_blocks(build(*rows))['blocks'][0]
    assert not b['certified'] and not b['certified_prefixes']


def test_zero_offensive_special_group_stays_in_mass():
    rows=drive_rows()[1:]
    rows[0].update(drive_play_id_started=20)
    b=build_original_drive_blocks(build(*rows))['blocks'][0]
    assert b['source_row_count']==1 and b['physical_offensive_snap_count']==0
    assert b['certified']


def test_terminal_metadata_without_typed_event_not_certified():
    rows=drive_rows();rows[1]['punt_attempt']=0
    b=build_original_drive_blocks(build(*rows))['blocks'][0]
    assert not b['certified']
    assert 'terminal_metadata_without_event_proof' in b['barriers']


def test_return_td_try_safety_points_native_side_typed():
    r=row(touchdown=1,return_touchdown=1,td_team='NYJ',defteam_score_post=6)
    e=build(r)['games'][0]['rows'][0]['event']
    assert e['typed_points']==e['score_delta']==[6,0]
    r=row(safety=1,defteam_score_post=2)
    assert build(r)['games'][0]['rows'][0]['event']['typed_points']==[2,0]
    r=row(play_type='extra_point',play_type_nfl='XP_KICK',rush_attempt=0,
          extra_point_attempt=1,extra_point_result='good',posteam_score_post=1)
    assert build(r)['games'][0]['rows'][0]['event']['typed_points']==[0,1]


def test_td_not_duplicated_as_passing_plus_receiving_points():
    r=row(touchdown=1,pass_touchdown=1,td_team='BUF',posteam_score_post=6)
    assert build(r)['games'][0]['rows'][0]['event']['typed_points']==[0,6]


def test_source_scoring_correction_and_missing_side_stay_barriers():
    r=row(touchdown=1,td_team=None,posteam_score_post=6)
    assert 'unknown_touchdown_scoring_side' in build(r)['games'][0]['rows'][0]['barriers']
    r=row(posteam_score=7,posteam_score_post=6)
    assert 'unknown_or_corrected_score_delta' in build(r)['games'][0]['rows'][0]['barriers']


def test_certified_half_end_is_own_zero_clock_boundary_not_next_half_field():
    common=dict(drive_play_id_started=10,drive_play_id_ended=20,drive_end_transition='END_HALF',qtr=2,game_half='Half1')
    first=row(quarter_seconds_remaining=10,half_seconds_remaining=10,game_seconds_remaining=1810,**common)
    end=row(play_id=20,order_sequence=2,play_type='quarter_end',play_type_nfl='END_QUARTER',
            rush_attempt=0,quarter_seconds_remaining=0,half_seconds_remaining=0,game_seconds_remaining=1800,
            yardline_100=None,**common)
    after=row(play_id=30,order_sequence=3,drive=2,qtr=3,game_half='Half2',
              quarter_seconds_remaining=900,half_seconds_remaining=1800,game_seconds_remaining=1800)
    b=build_original_drive_blocks(build(first,end,after))['blocks'][0]
    assert b['certified'],b['barriers']
    assert b['elapsed_seconds']==10
    assert b['terminal_state']['phase']=='halftime'
    assert b['terminal_state']['yardline100'] is None
    assert b['certified_prefixes'][-1]['elapsed_seconds']==10


def test_clock_zero_alone_cannot_certify_half_end():
    rows=drive_rows();rows[1].update(drive_end_transition='END_HALF',qtr=2,quarter_seconds_remaining=0,
        half_seconds_remaining=0,game_seconds_remaining=1800,game_half='Half1')
    rows[0]['drive_end_transition']='END_HALF'
    b=build_original_drive_blocks(build(*rows))['blocks'][0]
    assert not b['certified']
    assert 'terminal_metadata_without_event_proof' in b['barriers']


def test_opening_requires_native_beginning_not_first_observed_offensive_los():
    from backend.app.product_services.game_state_reconstruction import opening_state_evidence
    o=opening_state_evidence(build(row()))
    assert not o[0]['certified']
    assert 'first_action_not_proven_kickoff' in o[0]['barriers']
    kickoff=row(play_id=20,order_sequence=2,play_type='kickoff',play_type_nfl='KICK_OFF',rush_attempt=0,kickoff_attempt=1)
    assert not opening_state_evidence(build(kickoff))[0]['certified']
    start=row(play_type=None,play_type_nfl='GAME_START',rush_attempt=0)
    assert opening_state_evidence(build(start,kickoff))[0]['certified']


def test_explicit_no_play_precedes_allzero_contradiction_but_cannot_score():
    step=build(row(no_play=1,rush_attempt=0))['games'][0]['rows'][0]
    assert step['event']['official_counts']['rush_attempts']==0
    step=build(row(no_play=1,touchdown=1,td_team='BUF',posteam_score_post=6))['games'][0]['rows'][0]
    assert 'no_play_scoring_conflict' in step['barriers']


def test_penalty_unknown_not_normal_play_and_stats_side_signed():
    step=build(row(penalty=None))['games'][0]['rows'][0]
    assert 'unknown_penalty_status' in step['barriers']
    assert step['event']['team_stats_by_side'][1]['net_offensive_yards']==-2
    r=row(safety=1,defteam_score_post=2)
    e=build(r)['games'][0]['rows'][0]['event']
    assert e['points_by_type']==[{'safety':2},{}]
