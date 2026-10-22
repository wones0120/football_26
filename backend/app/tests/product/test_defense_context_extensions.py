from copy import deepcopy
import pytest

from backend.app.product_services.opportunity_events import build_event_evidence
from backend.app.product_services.defense_context_extensions import build_defense_context_extensions
from backend.app.tests.product.test_defense_context_evidence import play,CUTOFF,SOURCE,IDS

NATIVE='00-0000001';CANONICAL='00000000-0000-0000-0000-000000000001'


def build(rows,proofs=(),ids=None,source=None):
    receipt=dict(event_evidence=build_event_evidence(rows,canonical_ids=ids or IDS,source_receipt=source or SOURCE,cutoff=CUTOFF))
    return build_defense_context_extensions(receipt,before_period=202606,cutoff=CUTOFF,position_evidence=proofs)


def metric(result,key):return result['team_windows'][0]['metrics'][key]


def rush(number=1,**changes):
    return play(number,**(dict(play_type='run',pass_attempt=0,rush_attempt=1,qb_dropback=0,qb_kneel=0,qb_scramble=0,
        rusher_player_id=NATIVE,ydstogo=2,first_down_rush=0,rush_touchdown=0,fixed_drive=1)|changes))


def proof(**changes):
    return dict(dict(game_id='2026_01_BUF_MIA',team='BUF',source_player_id=NATIVE,position='QB',player_master_id=CANONICAL,
        source_id='native-position-source',available_at='2026-10-19T19:00:00Z'),**changes)


def test_provider_cpoe_known_samples_and_yac_completion_denominator_not_incompletion_zero():
    result=build([play(1,cpoe=15,complete_pass=1,yards_after_catch=8),play(2,cpoe=-25,complete_pass=0,yards_after_catch=99),
        play(3,cpoe=None,complete_pass=1,yards_after_catch=None),play(4,qb_spike=1,cpoe=99,complete_pass=0)])
    cpoe=metric(result,'G14-M06');yac=metric(result,'G14-M08')
    assert cpoe['eligible_events']==3 and cpoe['known_outcome_events']==2
    assert cpoe['observed_known_mean']==-5 and cpoe['unknown_outcome_events']==1
    assert yac['eligible_events']==2 and yac['observed_known_mean']==8 and yac['unknown_outcome_events']==1
    assert result['definitions']['G14-M06']['unit']=='provider_percentage_points'


def test_redzone_entered_drive_can_throw_td_after_backing_out_long_never_entered_drive_excluded():
    result=build([play(1,fixed_drive=1,yardline_100=15,pass_touchdown=0),play(2,fixed_drive=1,yardline_100=25,pass_touchdown=1),
        play(3,fixed_drive=2,yardline_100=35,pass_touchdown=1),rush(4,fixed_drive=3,yardline_100=5,rush_touchdown=1)])
    value=metric(result,'G14-M10')
    assert value['eligible_events']==2 and value['known_outcome_events']==2
    assert value['observed_outcome_sum']==1 and value['observed_known_mean']==0.5
    assert result['game_rows'][0]['drive_quality']['observed_redzone_drive_ids']==['1','3']


def test_redzone_missing_drive_unknown_entry_flag_and_duplicate_td_are_not_zero_or_double_td():
    result=build([play(1,fixed_drive=None,yardline_100=10,pass_touchdown=1),
        play(2,fixed_drive=1,yardline_100=None,pass_touchdown=0),
        play(3,fixed_drive=2,yardline_100=10,pass_touchdown=None),
        play(4,fixed_drive=3,yardline_100=10,pass_touchdown=1),play(5,fixed_drive=3,yardline_100=5,pass_touchdown=1)])
    value=metric(result,'G14-M10');quality=result['game_rows'][0]['drive_quality']
    assert value['eligible_events']==2 and value['unknown_outcome_events']==2
    assert value['unknown_eligibility_events']==1
    assert value['observed_known_mean'] is None
    assert quality['redzone_events_missing_drive_id']==1 and quality['conflicting_td_drive_ids']==['3']


def test_shortyard_conversion_includes_qb_scramble_td_and_unknown_subset_exclusion():
    result=build([rush(1,qb_scramble=1,first_down_rush=None,rush_touchdown=1),rush(2,ydstogo=1,first_down_rush=0,rush_touchdown=0),
        rush(3,ydstogo=1,first_down_rush=None,rush_touchdown=0),play(4,play_type=None,ydstogo=3),play(5,play_type=None,ydstogo=1)])
    value=metric(result,'G15-M08')
    assert value['eligible_events']==3 and value['known_outcome_events']==2
    assert value['observed_known_mean']==0.5 and value['unknown_outcome_events']==1
    assert value['unknown_eligibility_events']==1


def test_qb_full_rush_proof_and_narrower_scramble_only_without_proof():
    rows=[rush(1,yards_gained=7,qb_scramble=1,rush_touchdown=1),rush(2,yards_gained=3,qb_scramble=0)]
    absent=build(rows,ids={NATIVE:CANONICAL})
    assert metric(absent,'G15-M10')['observed_known_mean'] is None
    assert metric(absent,'G15-M10')['unknown_eligibility_events']==2
    assert metric(absent,'scramble_net_yards_support')['observed_outcome_sum']==7
    known=build(rows,[proof()],ids={NATIVE:CANONICAL})
    assert metric(known,'G15-M10')['observed_outcome_sum']==10
    assert metric(known,'G15-M10')['eligible_events']==2
    assert metric(known,'qb_rush_td_support')['observed_outcome_sum']==1
    assert known['identity_review_requests']==[]


def test_native_position_identity_scope_contradictions_and_future_clocks_reject():
    for changed in (dict(player_master_id='00000000-0000-0000-0000-000000000099'),dict(team='GB'),dict(available_at='2026-10-20T01:00:00Z'),dict(game_id='2026_06_BUF_MIA')):
        with pytest.raises(ValueError):build([rush()],[proof(**changed)],ids={NATIVE:CANONICAL})
    with pytest.raises(ValueError,match='Contradictory'):
        build([rush()],[proof(),proof(position='RB')],ids={NATIVE:CANONICAL})
    unresolved=build([rush()],[proof(player_master_id=None)])
    assert unresolved['identity_review_requests'][0]['source_player_id']==NATIVE
    assert metric(unresolved,'G15-M10')['eligible_events']==1


def test_nonqb_proof_excludes_even_when_rush_eligibility_unknown():
    result=build([play(play_type=None,rusher_player_id=NATIVE)],[proof(position='RB')],ids={NATIVE:CANONICAL})
    assert metric(result,'G15-M10')['unknown_eligibility_events']==0
    assert metric(result,'G15-M10')['eligible_events']==0


def test_recapture_event_order_and_position_receipt_clock_stable_actual_cpoe_change_invalidates():
    rows=[rush(1),play(2,cpoe=10,complete_pass=1,yards_after_catch=4)]
    first=build(rows,[proof()],ids={NATIVE:CANONICAL})
    later=build(list(reversed(rows)),[proof(source_id='recaptured',available_at='2026-10-19T19:30:00Z')],ids={NATIVE:CANONICAL})
    assert first['semantic_measurements_sha256']==later['semantic_measurements_sha256']
    rows[1]['cpoe']=11
    assert first['semantic_measurements_sha256']!=build(rows,[proof()],ids={NATIVE:CANONICAL})['semantic_measurements_sha256']


def test_partial_redzone_drive_zero_flags_remains_unknown_but_terminal_rush_td_proves_zero():
    result=build([play(1,fixed_drive=1,yardline_100=15,pass_touchdown=0),
        play(2,fixed_drive=1,yardline_100=10,pass_touchdown=0),
        rush(3,fixed_drive=2,yardline_100=5,rush_touchdown=1)])
    value=metric(result,'G14-M10')
    assert value['eligible_events']==2 and value['known_outcome_events']==1
    assert value['unknown_outcome_events']==1 and value['observed_outcome_sum']==0
    outcomes=result['game_rows'][0]['drive_quality']['drive_outcomes']
    assert outcomes[0]['completion_basis']=='unknown_no_terminal_evidence'
    assert outcomes[0]['outcome_known'] is False
    assert outcomes[1]['completion_basis']=='observed_rushing_touchdown'
    assert outcomes[1]['terminal_play_ids']==[3]


def test_conflicting_rush_and_pass_td_same_drive_is_unknown():
    result=build([play(1,fixed_drive=1,yardline_100=15,pass_touchdown=1),
        rush(2,fixed_drive=1,yardline_100=5,rush_touchdown=1)])
    assert metric(result,'G14-M10')['unknown_outcome_events']==1
    assert result['game_rows'][0]['drive_quality']['drive_outcomes'][0]['completion_basis']=='conflicting_touchdown_evidence'


@pytest.mark.parametrize('value',[-100.01,100.01])
def test_cpoe_outside_physical_range_rejected_without_clipping(value):
    with pytest.raises(ValueError,match='CPOE outside physical'):
        build([play(1,cpoe=value)])


def test_cpoe_physical_boundaries_retained():
    result=build([play(1,cpoe=-100),play(2,cpoe=100)])
    assert metric(result,'G14-M06')['known_outcome_events']==2
    assert metric(result,'G14-M06')['observed_known_mean']==0


@pytest.mark.parametrize('changes,basis',[
    (dict(play_type='field_goal',field_goal_attempt=1,field_goal_result='made',fixed_drive_result='Field goal',drive_end_transition='FIELD_GOAL'),'provider_field_goal_terminal'),
    (dict(play_type='field_goal',field_goal_attempt=1,field_goal_result='missed',fixed_drive_result='Missed field goal',drive_end_transition='MISSED_FG'),'provider_missed_field_goal_terminal'),
    (dict(play_type='punt',punt_attempt=1,punt_blocked=0,fixed_drive_result='Punt',drive_end_transition='PUNT'),'provider_punt_terminal'),
    (dict(interception=1,fixed_drive_result='Turnover',drive_end_transition='INTERCEPTION'),'provider_interception_terminal'),
    (dict(fumble_lost=1,fixed_drive_result='Turnover',drive_end_transition='FUMBLE'),'provider_fumble_lost_terminal'),
    (dict(fourth_down_failed=1,fixed_drive_result='Turnover on downs',drive_end_transition='DOWNS'),'provider_turnover_on_downs_terminal'),
])
def test_source_corroborated_non_td_terminal_proves_redzone_zero(changes,basis):
    result=build([play(1,fixed_drive=1,pass_touchdown=0),play(2,fixed_drive=1,pass_touchdown=0,**changes)])
    assert metric(result,'G14-M10')['known_outcome_events']==1
    assert metric(result,'G14-M10')['observed_outcome_sum']==0
    assert result['game_rows'][0]['drive_quality']['drive_outcomes'][0]['completion_basis']==basis


@pytest.mark.parametrize('changes',[
    dict(play_type='punt',punt_attempt=1,punt_blocked=1,fixed_drive_result='Punt',drive_end_transition='PUNT'),
    dict(play_type='punt',punt_attempt=1,punt_blocked=0,fixed_drive_result='Punt'),
    dict(interception=0,fixed_drive_result='Turnover',drive_end_transition='INTERCEPTION'),
    dict(interception=1,fixed_drive_result='Turnover',drive_end_transition='INTERCEPTION',no_play=1),
    dict(interception=1,fixed_drive_result='Turnover',drive_end_transition='INTERCEPTION',two_point_attempt=1),
])
def test_attempt_or_uncorroborated_or_excluded_terminal_is_not_proven_zero(changes):
    result=build([play(1,fixed_drive=1,pass_touchdown=0),play(2,fixed_drive=1,pass_touchdown=0,**changes)])
    assert metric(result,'G14-M10')['known_outcome_events']==0
    assert metric(result,'G14-M10')['unknown_outcome_events']==1
