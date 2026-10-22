import importlib.util
from pathlib import Path
import pytest
s=importlib.util.spec_from_file_location('proof',Path(__file__).with_name('proof.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def p(**changes):return dict(dict(observed_source_offense_rows=80,known_physical_snaps=60,unknown_possible_physical=0,unknown_units=0,all_physical_units_known=True,native_on_field_union={'on'}),**changes)
def rush(**changes):return dict(dict(source_offense_rows=80,unknown_official_rush_membership=0,unknown_rusher_events=0,lateral_or_unknown_lateral_events=0,known_official_carries=1,actors={'runner':dict(official_carries=1)}),**changes)
def target(**changes):return dict(dict(counts={'rec':1},unknown_all=False,unknown_native={'rec'},events=40,observed_game=True),**changes)
@pytest.mark.parametrize('channel',['pass_attempts','rush_attempts','targets'])
def test_off_field_every_source_play_known_zero_all_roles(channel):assert m.proof_zero('missing',channel,p())['zero']
@pytest.mark.parametrize('channel',['pass_attempts','rush_attempts','targets'])
def test_unknown_possible_play_masks_every_zero(channel):assert not m.proof_zero('missing',channel,p(unknown_possible_physical=1),rush(),target())['zero']
def test_onfield_not_no_passing_eligibility():assert not m.proof_zero('on','pass_attempts',p())['zero']
def test_rush_credit_census_can_prove_onfield_zero():assert m.proof_zero('on','rush_attempts',p(),rush())['zero']
@pytest.mark.parametrize('field',['unknown_official_rush_membership','unknown_rusher_events','lateral_or_unknown_lateral_events'])
def test_unknown_rush_membership_credit_masks(field):assert not m.proof_zero('on','rush_attempts',p(),rush(**{field:1}))['zero']
def test_positive_rush_not_relabelled_zero():assert not m.proof_zero('runner','rush_attempts',p(native_on_field_union={'runner'}),rush())['zero']
def test_target_unknown_recipient_offfield_specific_actor_only():
 assert m.proof_zero('on','targets',p(),target=target())['zero']
 assert not m.proof_zero('rec','targets',p(native_on_field_union={'rec'}),target=target())['zero']
def test_attribution_conflict_unknown_other_candidates_masks():assert not m.proof_zero('on','targets',p(),target=target(unknown_all=True))['zero']
def test_missing_game_not_zero():assert not m.proof_zero('on','targets',p(),target=target(observed_game=False))['zero']
def test_unknown_unit_prevents_offfield_shortcut_but_not_independent_rush_census():
 q=p(all_physical_units_known=False,unknown_units=1)
 assert not m.proof_zero('missing','pass_attempts',q)['zero']
 assert m.proof_zero('missing','rush_attempts',q,rush())['zero']


def test_positive_credit_overrides_offfield_shortcut():
 assert not m.proof_zero('runner','rush_attempts',p(),rush())['zero']
 assert not m.proof_zero('rec','targets',p(),target=target())['zero']

def test_same_key_credited_actor_outside_eleven_invalidates_offfield_proof():
 ids=[str(i)for i in range(11)];block=dict(unit_registry={'u':dict(native_participant_roles=[[n,'WR']for n in ids])},event_basis=[dict(game_id='g',play_id='1',team='BUF',unit_id='u',physical_membership=True)]);q={('g','BUF'):p(cross_credit_conflicts=[])}
 r=dict(game_id='g',play_id='1',eligible=True,native_rusher_valid=True,native_rusher='other',offense='BUF')
 m.corroborate_native_credits(q,block,[r],[])
 assert not q['g','BUF']['all_physical_units_known']and q['g','BUF']['cross_credit_conflicts']
 assert not m.proof_zero('missing','pass_attempts',q['g','BUF'])['zero']


def credit_fixture(eligible=True,unit='u',has_event=True,lateral=None):
 ids=['inside']+[str(i)for i in range(10)];block=dict(unit_registry={'u':dict(native_participant_roles=[[n,'WR']for n in ids])},event_basis=[dict(game_id='g',play_id='1',team='BUF',unit_id=unit,physical_membership=True)]if has_event else[])
 q={('g','BUF'):p(cross_credit_conflicts=[])}
 r=dict(game_id='g',play_id='1',eligible=eligible,native_rusher_valid=True,native_rusher='inside',offense='BUF',reported_lateral_rusher=lateral)
 return q,block,r

@pytest.mark.parametrize('eligible',[True,None])
def test_initial_and_lateral_possible_credits_contradict_eleven(eligible):
 q,b,r=credit_fixture(eligible=eligible,lateral='00-0000001')
 m.corroborate_native_credits(q,b,[r],[])
 assert not q['g','BUF']['all_physical_units_known']
 q,b,r=credit_fixture(eligible=eligible);r['native_rusher']='outside'
 m.corroborate_native_credits(q,b,[r],[])
 assert not q['g','BUF']['all_physical_units_known']

@pytest.mark.parametrize('missing',['event','unit'])
def test_unavailable_same_key_unit_corroboration_blocks_shortcut(missing):
 q,b,r=credit_fixture(has_event=missing!='event',unit=None if missing=='unit'else'u')
 m.corroborate_native_credits(q,b,[r],[])
 assert not q['g','BUF']['all_physical_units_known']
 assert 'missing_matching' in q['g','BUF']['cross_credit_conflicts'][0]['reasons'][0]

def test_known_false_credit_exclusion_does_not_invalidate_unit():
 q,b,r=credit_fixture(eligible=False,lateral='00-0000001');m.corroborate_native_credits(q,b,[r],[])
 assert q['g','BUF']['all_physical_units_known']

def test_weekly_native_count_contradiction_never_repaired():
 candidate=dict(source_player_id='missing',target_source_id='row',counts=dict(pass_attempts=0,rush_attempts=1,targets=0))
 result=m.credit_compatibility('rush_attempts',[candidate],2,rush())
 assert result['status']=='CONTRADICTED'and result['conflicts'][0]['weekly_source_count']==1
 assert candidate['counts']['rush_attempts']==1

def test_unknown_target_remainder_not_independent_census():
 candidate=dict(source_player_id='rec',target_source_id='row',counts=dict(pass_attempts=0,rush_attempts=0,targets=1))
 result=m.credit_compatibility('targets',[candidate],1,target=target())
 assert result['budget_compatible']and result['unknown_recipient_or_eligibility_membership_retained']
 assert result['independent_NFL_census']=='UNKNOWN'


def test_outside_rest_credit_lowerbound_contradiction_is_not_donated():
 candidate=dict(source_player_id='on',target_source_id='row',counts=dict(pass_attempts=0,rush_attempts=0,targets=0))
 result=m.credit_compatibility('targets',[candidate],1,target=target(),outside_rest=0)
 assert result['status']=='CONTRADICTED'
 assert result['conflicts'][0]['scope']=='OUTSIDE_CANDIDATE_REST'
