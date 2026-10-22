"""Exploratory support counts must never become a continuation rule."""
from copy import deepcopy
import pytest
from research.game_progression_pilot_20261020.continuation_followup.support import diagnose,joint_key
from backend.app.tests.product.test_event_boundary_progression import fixture

def source(game='2023_01_A_B',wait=5,kind='RIGHT_CENSORED'):
    c,_=fixture(wait=wait,kind=kind)
    c.update(cycle_id=game+':1',context_key=[game,'A'])
    c['start'].update(half=1,remaining=5,score_sign=0)
    return c

@pytest.mark.parametrize('deadline',[0,5,-1,None,float('nan'),float('inf'),True])
def test_only_strictly_longer_valid_generated_horizons_are_audited(deadline):
    with pytest.raises(ValueError):diagnose(source(),[],deadline)

def test_joint_observations_preserve_unknown_mass_and_exclude_source_game():
    c=source();same=source(wait=90,kind='EXACT_NEXT_ACTION')
    known=source('2023_02_A_C',wait=20,kind='EXACT_NEXT_ACTION');known['start']['remaining']=100
    unknown=deepcopy(known);unknown['context_key'][0]='2023_03_A_D';unknown['state_certified']=False
    censored=source('2023_04_A_E',wait=10);censored['start']['remaining']=100
    rows=[same,known,unknown,censored];before=deepcopy((c,rows))
    result=diagnose(c,rows,80)
    counts=result['source_start_covers_generated_horizon']['counts']
    assert counts['all_observations']==3 and counts['unknown_source']==1
    assert counts['exact_wait_beyond_censor']==2 and counts['unknown_source_exact_beyond_censor']==1
    assert counts.get('exact_wait_at_least_deadline',0)==0 and counts['RIGHT_CENSORED']==1
    assert result['source_start_covers_generated_horizon']['distinct_games_beyond_censor']==2
    assert not result['continuation_supported']and(c,rows)==before

def test_half_score_and_horizon_are_nested_observation_counts():
    c=source();rows=[]
    for index in range(4):
        other=source(f'2023_0{index+2}_A_C',wait=10,kind='EXACT_NEXT_ACTION');other['start']['remaining']=100
        rows.append(other)
    rows[0]['start']['half']=2;rows[1]['start']['score_sign']=1;rows[2]['start']['remaining']=70
    out=diagnose(c,rows,80)
    assert out['same_joint_marks_other_games']['counts']['all_observations']==4
    assert out['same_half_score_sign']['counts']['all_observations']==2
    assert out['source_start_covers_generated_horizon']['counts']['all_observations']==1
    assert out['crosses_120_second_stratum']is False
    assert diagnose(c,rows,121)['crosses_120_second_stratum']is True

def test_joint_mark_key_keeps_action_policy_production_and_unknowns_distinct():
    c=source();raw=dict(play_type_nfl='RUSH',rush_attempt=1,qb_kneel=0)
    assert joint_key(c,raw)!=joint_key(c,dict(raw,qb_kneel=1))
    other=deepcopy(c);other['production'][0]['rushing_yards']=None
    assert joint_key(c,raw)!=joint_key(other,raw)
    other=deepcopy(c);other['production'][0]['rushing_yards']=6
    assert joint_key(c,raw)!=joint_key(other,raw)
    # Source side labels alone cannot change an otherwise identical joint mark.
    other=deepcopy(c);other['source_side']=1;other['production'].reverse()
    other['score_delta'].reverse();other['points_by_type'].reverse()
    assert joint_key(c,raw)==joint_key(other,raw)

def test_invalid_waits_are_counted_without_tail_support():
    c=source();other=source('2023_02_A_C',wait=None,kind='EXACT_NEXT_ACTION');other['start']['remaining']=100
    out=diagnose(c,[other],80)['same_joint_marks_other_games']['counts']
    assert out['all_observations']==out['invalid_wait']==1 and not out.get('exact_wait_beyond_censor')
