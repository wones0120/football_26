"""Demonstrated source bugs; no simulation, source read or fitted model."""
from copy import deepcopy
import pytest
from backend.app.tests.product.test_game_state_reconstruction import row,build
from backend.app.product_services.game_state_reconstruction import (
    _event,state_before,event_count_label_proof,_touchdown_drive_terminal,
    reconstruct_game_transitions,build_original_drive_blocks)
from backend.app.tests.product.test_game_state_reconstruction import LINEAGE

SIDES=['NYJ','BUF']

def passing(**changes):
    return row(play_type='pass',play_type_nfl='PASS',pass_attempt=1,rush_attempt=0,
               qb_dropback=1,passer_player_id='00-0030002',complete_pass=0,incomplete_pass=1,**changes)

def event(raw,proof=None):return _event(raw,state_before(raw,SIDES),SIDES,charting_proof=proof)

def proof(raw):
    return dict(game_id=raw['game_id'],play_id='10',unique_native_key=True,raw_is_throw_away='true',raw_is_drop='false',source_sha256='a'*64,snapshot_id='immutable-ftn-snapshot')

def test_native_spike_without_provider_dropback_is_official_attempt_not_exposure_rewrite():
    raw=passing();raw.update(qb_spike=1,qb_dropback=0)
    before=deepcopy(raw);e=event(raw)
    assert e['choice']=='spike' and e['official_counts']==dict(pass_attempts=1,rush_attempts=0,targets=0)
    assert e['production_by_side'][1]['passing_yards']==e['production_by_side'][1]['receiving_yards']==0
    assert raw==before and raw['qb_dropback']==0

@pytest.mark.parametrize('change',[dict(sack=1),dict(qb_scramble=1),dict(qb_kneel=1),dict(complete_pass=1),dict(receiver_player_id='00-0030003'),dict(touchdown=1),dict(passing_yards=3),dict(no_play=1)])
def test_spike_contradiction_never_becomes_known_positive_attempt(change):
    raw=passing();raw.update(qb_spike=1,qb_dropback=0,**change);e=event(raw)
    assert e['official_counts']['pass_attempts']in(None,0)

def test_upheld_count_finality_is_separate_from_state_transition():
    raw=passing(receiver_player_id='00-0030003',replay_or_challenge=1,replay_or_challenge_result='upheld')
    e=event(raw);p=event_count_label_proof(raw,state_before(raw,SIDES),e)
    assert p['production_by_side'][1]['official_pass_attempts']==1
    assert 'replay_or_challenge_not_independently_resolved'not in e['barriers']
    for result in ('reversed','',None,'UPHELD'):
        raw['replay_or_challenge_result']=result;e=event(raw)
        assert event_count_label_proof(raw,state_before(raw,SIDES),e)['production_by_side'][1]['official_pass_attempts']is None

def test_throwaway_requires_exact_scoped_source_proof_and_preserves_raw():
    raw=passing();before=deepcopy(raw)
    assert event(raw)['official_counts']['targets']is None
    p=proof(raw);e=event(raw,p)
    assert e['official_counts']['targets']==0 and raw==before
    reconstructed=reconstruct_game_transitions([raw],source_lineage=LINEAGE,charting_by_key={(raw['game_id'],'10'):p})
    assert reconstructed['games'][0]['rows'][0]['event']['official_counts']['targets']==0

@pytest.mark.parametrize('change',[dict(receiver_player_id='00-0030003'),dict(complete_pass=1),dict(interception=1),dict(pass_touchdown=1),dict(receiving_yards=2),dict(play_deleted=1),dict(season_type='POST')])
def test_throwaway_cannot_override_source_contradiction(change):
    raw=passing();p=proof(raw);raw.update(change);e=event(raw,p)
    assert e['official_counts']['targets']!=0

@pytest.mark.parametrize('change',[dict(play_id='20'),dict(unique_native_key=False),dict(raw_is_throw_away='false'),dict(raw_is_drop='true'),dict(source_sha256='bad')])
def test_throwaway_missing_or_ambiguous_proof_is_not_zero(change):
    raw=passing();p=proof(raw);p.update(change)
    assert event(raw,p)['official_counts']['targets']is None

def td_try_steps():
    common=dict(drive_play_id_started=10,drive_play_id_ended=20,drive_end_transition='TOUCHDOWN')
    td=passing(receiver_player_id='00-0030003');td.update(complete_pass=1,incomplete_pass=0,passing_yards=10,receiving_yards=10,touchdown=1,pass_touchdown=1,td_team='BUF',posteam_score_post=6,**common)
    xp=row(play_id=20,order_sequence=2,play_type='extra_point',play_type_nfl='XP_KICK',rush_attempt=0,extra_point_attempt=1,extra_point_result='good',posteam_score=6,posteam_score_post=7,half_seconds_remaining=1795,game_seconds_remaining=3595,quarter_seconds_remaining=895,**common)
    kick=row(play_id=30,order_sequence=3,drive=2,play_type='kickoff',play_type_nfl='KICK_OFF',rush_attempt=0,kickoff_attempt=1,yardline_100=35,posteam_score=7,posteam_score_post=7,half_seconds_remaining=1795,game_seconds_remaining=3595,quarter_seconds_remaining=895)
    return build(td,xp,kick)['games'][0]['rows'][:2]

def test_td_before_try_proves_terminal_without_losing_or_doubling_points():
    steps=td_try_steps();before=deepcopy(steps)
    assert _touchdown_drive_terminal(steps)
    assert sum(sum(s['event']['typed_points'])for s in steps)==7 and steps==before

@pytest.mark.parametrize('problem',['multipleTD','wrongside','extraoffense','replay','unknownpoints','unknownendpoint'])
def test_td_try_suffix_must_be_exact_and_coherent(problem):
    steps=td_try_steps();last=steps[-1]
    if problem=='multipleTD':last['raw']['touchdown']=1
    if problem=='wrongside':last['state_before']['possession_side']=0
    if problem=='extraoffense':last['event']['physical_offensive_snap']=True
    if problem=='replay':last['raw']['replay_or_challenge']=1
    if problem=='unknownpoints':last['event']['typed_points']=None
    if problem=='unknownendpoint':last['transition_endpoint']=None;last['next_observed_state']=None
    assert not _touchdown_drive_terminal(steps)

def single_fumble_rows(lost=False):
    f=row(fumble=1,fumble_lost=int(lost),fumbled_1_team='BUF',fumbled_1_player_id='00-0030001',
        fumble_recovery_1_team='NYJ'if lost else'BUF',fumble_recovery_1_player_id='00-0030002'if lost else'00-0030001',
        fumbled_2_team=None,fumbled_2_player_id=None,fumble_recovery_2_team=None,fumble_recovery_2_player_id=None)
    nxt=row(play_id=20,order_sequence=2,half_seconds_remaining=1760,quarter_seconds_remaining=860,game_seconds_remaining=3560,
        posteam='NYJ'if lost else'BUF',defteam='BUF'if lost else'NYJ',down=1 if lost else 2,ydstogo=10 if lost else 12,yardline_100=27 if lost else 77)
    return f,nxt

@pytest.mark.parametrize('lost',[False,True])
def test_single_primary_fumble_recovery_uses_native_ids_and_observed_successor(lost):
    rows=single_fumble_rows(lost);before=deepcopy(rows);step=build(*rows)['games'][0]['rows'][0]
    assert step['state_transition_certified'] and step['transition_elapsed_seconds']==40
    p=step['source_transition_proofs'][0]
    assert p['lost']==lost and p['successor_play_id']=='20'
    assert p['recovery_side']==step['transition_endpoint']['possession_side']
    assert 'unproven_full_fumble_possession_chain'in step['event']['barriers']
    assert 'unproven_full_fumble_possession_chain'not in step['transition_barriers']
    assert step['event']['production_by_side'][1]['official_carries']==1
    assert rows==before

@pytest.mark.parametrize('change',[
    {'fumble_recovery_1_team':None},{'fumble_recovery_1_player_id':None},
    {'fumble_recovery_1_player_id':'display name'},
    {'fumbled_1_team':'NYJ'},{'fumbled_1_player_id':'00-0030003'},{'fumble_lost':1},{'fumble_lost':None},
    {'fumbled_2_team':'BUF'},{'fumble_recovery_2_player_id':'00-0030003'},
    {'lateral_recovery':1},{'lateral_rush':None},{'penalty':1},{'replay_or_challenge':1},
    {'replay_or_challenge':1,'replay_or_challenge_result':'reversed'},
    {'play_deleted':1},{'interception':1},{'touchdown':1},
])
def test_fumble_proof_never_fills_missing_or_ambiguous_chain(change):
    f,nxt=single_fumble_rows();f.update(change);step=build(f,nxt)['games'][0]['rows'][0]
    assert not step['state_transition_certified'] and not step['source_transition_proofs']

@pytest.mark.parametrize('change',[
    {'posteam':'NYJ','defteam':'BUF'},{'posteam_score':3},{'yardline_100':None},
    {'down':None},{'order_sequence':1},{'half_seconds_remaining':1801},
])
def test_recovery_cannot_override_unqualified_or_conflicting_successor(change):
    f,nxt=single_fumble_rows();nxt.update(change);step=build(f,nxt)['games'][0]['rows'][0]
    assert not step['state_transition_certified'] and not step['source_transition_proofs']

def test_missing_second_fumble_census_column_is_not_an_empty_slot():
    f,nxt=single_fumble_rows();del f['fumbled_2_team'];step=build(f,nxt)['games'][0]['rows'][0]
    assert not step['state_transition_certified']

def accepted_try_penalty_rows():
    attempt=row(play_type='no_play',play_type_nfl='PENALTY',rush_attempt=0,pass_attempt=1,
        two_point_attempt=1,two_point_conv_result='success',posteam_score=6,posteam_score_post=8,
        penalty=1,penalty_type='Unnecessary Roughness',penalty_yards=15,
        desc='TWO-POINT CONVERSION ATTEMPT. ATTEMPT SUCCEEDS. Penalty enforced between downs.')
    kickoff=row(play_id=20,order_sequence=2,play_type='kickoff',play_type_nfl='KICK_OFF',rush_attempt=0,
        kickoff_attempt=1,posteam='NYJ',defteam='BUF',posteam_score=0,posteam_score_post=0,
        defteam_score=8,defteam_score_post=8,yardline_100=20)
    return attempt,kickoff

def test_accepted_try_between_down_penalty_is_not_annulled_by_coarse_play_type():
    rows=accepted_try_penalty_rows();before=deepcopy(rows);step=build(*rows)['games'][0]['rows'][0]
    assert step['state_transition_certified'] and step['state_before']['phase']=='try'
    assert step['source_transition_proofs'][0]['points']==2
    assert step['event']['score_delta']==[0,2] and step['event']['official_counts']==dict(pass_attempts=0,rush_attempts=0,targets=0)
    assert 'no_play_scoring_conflict'in step['event']['barriers'] and rows==before

@pytest.mark.parametrize('change',[
    {'no_play':1},{'no_play':None},{'desc':'Penalty offsetting - No Play.'},
    {'two_point_conv_result':'failure'},{'replay_or_challenge':1,'replay_or_challenge_result':'reversed'},
    {'penalty_type':None},{'penalty':None},{'defensive_two_point_conv':1},{'posteam_score_post':6},
])
def test_try_penalty_proof_does_not_override_cancellation_or_scoring_conflict(change):
    attempt,kickoff=accepted_try_penalty_rows();attempt.update(change);step=build(attempt,kickoff)['games'][0]['rows'][0]
    assert not step['state_transition_certified'] and not step['source_transition_proofs']

@pytest.mark.parametrize('change',[{'defteam_score':6},{'kickoff_attempt':0},{'play_type_nfl':'PENALTY'},{'play_deleted':1},{'kickoff_attempt':0,'play_type':'run','play_type_nfl':'RUSH'},
    {'posteam':'BUF','defteam':'NYJ','posteam_score':8,'posteam_score_post':8,'defteam_score':0,'defteam_score_post':0}])
def test_accepted_try_requires_source_receiving_side_kickoff_and_matching_score(change):
    attempt,kickoff=accepted_try_penalty_rows();kickoff.update(change);step=build(attempt,kickoff)['games'][0]['rows'][0]
    assert not step['state_transition_certified'] and not step['source_transition_proofs']

@pytest.mark.parametrize('channel',['rush','pass','sack'])
def test_teammate_recovery_proves_state_without_inventing_team_yards(channel):
    f,nxt=single_fumble_rows();f['fumble_recovery_1_player_id']='00-0030002'
    fields=['rushing_yards']
    if channel in ('pass','sack'):
        f.update(play_type='pass',play_type_nfl='SACK'if channel=='sack'else'PASS',pass_attempt=1,rush_attempt=0,qb_dropback=1,
            sack=int(channel=='sack'),complete_pass=int(channel=='pass'),passer_player_id='00-0030001',
            receiver_player_id='00-0030001'if channel=='pass'else None,rusher_player_id=None,rushing_yards=None,
            passing_yards=10 if channel=='pass'else None,receiving_yards=10 if channel=='pass'else None)
        fields=['passing_yards','receiving_yards']if channel=='pass'else[]
    before=deepcopy((f,nxt));step=build(f,nxt)['games'][0]['rows'][0]
    assert step['state_transition_certified']and step['transition_endpoint']['possession_side']==1
    assert step['source_transition_proofs'][0]['unproven_production_channels']==fields
    for field in fields:
        assert step['event']['production_by_side'][1][field]is None
        assert step['event']['reported_production_by_side'][1][field]is not None
        assert step['channel_credit_masks'][1][field]is False
    assert (f,nxt)==before

def test_aborted_single_recovery_keeps_rush_credit_unknown_and_chain_explicit():
    f,nxt=single_fumble_rows();f.update(aborted_play=1,lateral_recovery=1)
    step=build(f,nxt)['games'][0]['rows'][0]
    assert step['state_transition_certified']and step['event']['production_by_side'][1]['rushing_yards']is None
    assert step['event']['production_by_side'][1]['official_carries']==1
    assert {p['discharges']for p in step['source_transition_proofs']}=={'unproven_full_fumble_possession_chain','lateral_credit_chain_unproven'}
    f['lateral_rusher_player_id']='00-0030002';step=build(f,nxt)['games'][0]['rows'][0]
    assert not step['state_transition_certified']

def test_recovery_yard_unknown_survives_blocks_and_cycle_compilation():
    from backend.app.product_services.event_boundary_progression import compile_cycles
    f,nxt=single_fumble_rows();f.update(aborted_play=1,lateral_recovery=1)
    for raw in (f,nxt):raw['game_id']='2023_01_NYJ_BUF'
    reconstruction=build(f,nxt)
    contexts=[dict(game_id=f['game_id'],season=2023,team=team,own_pass_share=0.5,opponent_pass_share=0.5)for team in SIDES]
    cycle=compile_cycles(reconstruction,build_original_drive_blocks(reconstruction),contexts)['cycles'][0]
    assert cycle['state_certified']and cycle['production'][1]['official_carries']==1
    assert cycle['production'][1]['rushing_yards']is None

@pytest.mark.parametrize('lost',[False,True])
def test_punt_muff_native_recovery_changes_possession_without_offensive_opportunities(lost):
    f,nxt=single_fumble_rows();f.update(play_type='punt',play_type_nfl='PUNT',punt_attempt=1,rush_attempt=0,rusher_player_id=None,rushing_yards=None,
        fumbled_1_team='NYJ',fumbled_1_player_id='00-0030003',punt_returner_player_id='00-0030003',
        fumble_recovery_1_team='BUF'if lost else'NYJ',fumble_recovery_1_player_id='00-0030001'if lost else'00-0030003',fumble_lost=int(lost))
    nxt.update(posteam='BUF'if lost else'NYJ',defteam='NYJ'if lost else'BUF')
    step=build(f,nxt)['games'][0]['rows'][0]
    assert step['state_transition_certified']
    assert step['event']['official_counts']==dict(pass_attempts=0,rush_attempts=0,targets=0)
    assert step['event']['physical_offensive_snap']is False

@pytest.mark.parametrize('kind',['pass','run','punt'])
def test_special_formation_with_unspecified_provider_class_preserves_official_flags(kind):
    raw=row(play_type=kind,play_type_nfl='UNSPECIFIED',down=4,desc='(Punt formation) native action',rushing_yards=2)
    if kind=='pass':raw.update(pass_attempt=1,rush_attempt=0,qb_dropback=1,passer_player_id='00-0030002',receiver_player_id='00-0030003',complete_pass=1,passing_yards=2,receiving_yards=2,rushing_yards=None)
    if kind=='punt':raw.update(desc='(Field Goal formation) native punt',rush_attempt=0,rushing_yards=None,punt_attempt=1,punter_player_id='00-0030002')
    before=deepcopy(raw);e=event(raw)
    assert e['native_action_class_proof']['original_native_class']=='UNSPECIFIED'
    assert e['physical_offensive_snap']is (kind!='punt')
    assert e['official_counts']['pass_attempts']==int(kind=='pass')and e['official_counts']['rush_attempts']==int(kind=='run')
    assert event_count_label_proof(raw,state_before(raw,SIDES),e)['production_by_side'][1]['physical_plays']==int(kind!='punt')
    assert raw==before

@pytest.mark.parametrize('change',[{'desc':'ordinary play'},{'down':3},{'punt_attempt':1},{'play_deleted':1},{'penalty':1},
    {'rush_attempt':None},{'pass_attempt':1},{'rusher_player_id':None},{'replay_or_challenge':1,'replay_or_challenge_result':'reversed'}])
def test_special_formation_does_not_override_missing_or_conflicting_evidence(change):
    raw=row(play_type='run',play_type_nfl='UNSPECIFIED',down=4,desc='(Punt formation) native rush');raw.update(change)
    assert event(raw)['native_action_class_proof']is None
