from copy import deepcopy
import pytest
from research.game_progression_pilot_20261020.clock_stop_amendment.amendment import build_records

def fixture():
    bindings=dict(game_id='2023_06_NO_HOU',native_game_uuid='native-game-uuid',raw_source_sha256='a'*64,
        decoded_sha256='b'*64,base_ledger_sha256='c'*64,base_projection_sha256='d'*64,assessment_sha256='e'*64)
    raw=[dict(playId=10,orderSequence=1,quarter=2,clockTime='02:10'),
        dict(playId=90,orderSequence=2,quarter=2,clockTime='01:58',playType='TIMEOUT',playDeleted=False,playReviewStatus=None,playDescription='Two-Minute Warning'),
        dict(playId=20,orderSequence=3,quarter=2,clockTime='01:58')]
    base=[]
    for ordinal,r in enumerate((raw[0],raw[2])):
        base.append(dict(record_id=f'clock_timeout_action_observation_v1|{bindings["base_projection_sha256"]}|{ordinal}',
            provenance=dict(native_cycle_id=f'{bindings["game_id"]}:{r["playId"]}',projection_sha256=bindings['base_projection_sha256'],source_ordinal_zero_based=ordinal),
            pre_event=dict(clock=dict(status='SOURCE_PRE_EVENT_VALIDATED',quarter=2,quarter_seconds=130 if ordinal==0 else 118)),
            raw_pre_event=dict(order_sequence=r['orderSequence'])))
    case=dict(play_id=90,order_sequence=2,quarter=2,source_clock='01:58',reported_description='Two-Minute Warning',
        status='SOURCE_TYPED_CLOCK_STOP_OBSERVATION',reason='SOURCE_REPORTED_TWO_MINUTE_WARNING',same_quarter_clock_bracket=True,
        preceding_matched_play_id=10,following_matched_play_id=20,timeout_team=None,timeout_budget_debit_proven=False,
        physical_play_end_clock=None,restart_policy=None,generated_state_transition_supported=False)
    return [case],raw,base,bindings

def test_append_observation_binds_actual_base_anchors_without_changing_inputs():
    args=fixture();before=deepcopy(args);out=build_records(*args)
    assert args==before and len(out)==1
    r=out[0]
    assert r['operation']=='APPEND_SOURCE_OBSERVATION'and r['replaces_record_id']is None
    assert r['anchor_links']['preceding']['base_record_id']==args[2][0]['record_id']
    assert r['provenance']['raw_table_ordinal_zero_based']==1
    assert r['observed_clock']['quarter_seconds']==118 and r['observed_clock']['derived_game_seconds']==1918
    assert all(v is None for v in r['unobserved'].values())and r['opportunity_or_scoring_credit']is None
    assert r['continuation_support']=='UNKNOWN'and not r['generated_policy_supported']and not r['activation']
    assert build_records(*args)==out

def test_generic_stop_does_not_gain_a_known_cause_or_team_debit():
    cases,raw,base,bindings=fixture();cases[0].update(reason='UNKNOWN_STOP_CAUSE',reported_description='Timeout at 01:58.')
    raw[1]['playDescription']='Timeout at 01:58.'
    r=build_records(cases,raw,base,bindings)[0]
    assert r['clock_stop']['reason']=='UNKNOWN_STOP_CAUSE'and r['unobserved']['timeout_team']is None
    assert r['unobserved']['timeout_debit']is None

@pytest.mark.parametrize('change',[
    {'playDeleted':True},{'playType':'PASS'},{'clockTime':'2023-10-15T18:21:04Z'},
    {'playReviewStatus':'REVERSED'},{'quarter':3},{'orderSequence':4},
])
def test_conflicting_native_evidence_cannot_be_amended(change):
    cases,raw,base,bindings=fixture();raw[1].update(change)
    with pytest.raises(ValueError):build_records(cases,raw,base,bindings)

@pytest.mark.parametrize('which',['missing_raw','duplicate_raw','duplicate_order','duplicate_base','missing_anchor','wrong_clock','foreign_projection','bad_base_id','base_collision','duplicate_case'])
def test_ambiguous_or_unbound_identity_and_brackets_are_rejected(which):
    cases,raw,base,bindings=fixture()
    if which=='missing_raw':raw.pop(1)
    if which=='duplicate_raw':raw.append(deepcopy(raw[1]))
    if which=='duplicate_order':raw[2]['orderSequence']=2
    if which=='duplicate_base':base.append(deepcopy(base[0]))
    if which=='missing_anchor':base.pop()
    if which=='wrong_clock':base[0]['pre_event']['clock']['quarter_seconds']=129
    if which=='foreign_projection':base[0]['provenance']['projection_sha256']='f'*64
    if which=='bad_base_id':base[0]['record_id']='unbound-id'
    if which=='base_collision':base.append(dict(provenance=dict(native_cycle_id='2023_06_NO_HOU:90')))
    if which=='duplicate_case':cases.append(deepcopy(cases[0]))
    with pytest.raises(ValueError):build_records(cases,raw,base,bindings)

def test_excluded_assessment_markers_are_not_added():
    cases,raw,base,bindings=fixture();cases.append(dict(status='UNQUALIFIED_RAW_ONLY_RECORD',play_id=10))
    assert len(build_records(cases,raw,base,bindings))==1
