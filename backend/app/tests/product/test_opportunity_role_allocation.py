from copy import deepcopy

import pytest

from backend.app.product_services.opportunity_role_allocation import allocate_factual_vacancies
from backend.app.product_services.count_component_response import component_response
from backend.app.tests.product.test_count_component_response import fixture, IDS, NOW


def inputs():
    history,reference,bases=fixture()
    proof=dict(player_id=IDS[1],team='BUF',source_ids=['official'],source_uri='https://example.test/official',
        observed_at='2026-09-24T10:00:00Z',received_at='2026-09-24T11:00:00Z',fact_type='game_status',designation='OUT',season=2026,week=4)
    facts=[dict(player_master_id=IDS[1],team='BUF',designation='OUT',evidence=proof)]
    reference['players'][2]['current_role_evidence']={**proof,'player_id':IDS[2],'role':'rotational'}
    assumption=dict(donor_player_master_id=IDS[1],recipient_player_master_id=IDS[2],channel='targets',fraction=.5,
        assumption_id='SYNTHETIC-half-vacancy',rationale='Conditional supported recipient, not expected allocation')
    return history,reference,bases,facts,assumption


def test_factual_out_zeroes_world_production_preserves_reference_and_partial_residual():
    history,reference,bases,facts,assumption=inputs()
    result=allocate_factual_vacancies(reference,unavailable=facts,allocations=[assumption],cutoff=NOW)
    assert reference['players'][1]['counts']['targets']==3
    assert result['players'][1]['counts']==dict(pass_attempts=0.,rush_attempts=0.,targets=0.)
    assert result['players'][1]['hypothetical_active_role_reference_counts']['targets']==3
    assert result['players'][2]['counts']['targets']==6.5
    assert result['teams']['BUF']['reconciliation']['targets']['unallocated']==1.5
    response=component_response(history,reference,result,bases,before_period=202604,cutoff=NOW)
    assert response['players'][1]['conditional_mean']==0
    assert response['players'][1]['base_fp']==6
    assert response['players'][2]['delta_points']>0
    assert response['players'][2]['world_activity'] is None


@pytest.mark.parametrize('kind',['Q','user','future','wrong_identity','cross_team','overallocate','unsupported_role','wrong_status','wrong_period'])
def test_invalid_or_preference_vacancy_and_unsupported_recipient_rejected(kind):
    _,reference,_,facts,assumption=inputs()
    if kind=='wrong_status':facts[0]['evidence']['designation']='Q'
    if kind=='wrong_period':facts[0]['evidence']['week']=3
    if kind=='Q':facts[0]['designation']='Q'
    if kind=='user':facts[0]['evidence']['fact_type']='user_exclusion'
    if kind=='future':facts[0]['evidence']['observed_at']='2026-09-26T00:00:00Z'
    if kind=='wrong_identity':facts[0]['evidence']['player_id']=IDS[0]
    if kind=='cross_team':reference['players'][2]['team']='MIA'
    if kind=='overallocate':assumption['fraction']=1.1
    if kind=='unsupported_role':reference['players'][2]['current_role_evidence']['role']='practice_squad'
    with pytest.raises(ValueError):allocate_factual_vacancies(reference,unavailable=facts,allocations=[assumption],cutoff=NOW)


def test_unknown_reference_is_not_zero_or_donated_and_unknown_recipient_does_not_expand():
    _,reference,_,facts,assumption=inputs()
    reference['players'][1]['counts']['targets']=None
    result=allocate_factual_vacancies(reference,unavailable=facts,allocations=[assumption],cutoff=NOW)
    assert result['players'][2]['counts']['targets']==5
    assert result['availability_conditions']['conditional_allocations'][0]['transferred'] is None
    reference['players'][1]['counts']['targets']=3
    reference['players'][2]['counts']['targets']=None
    result=allocate_factual_vacancies(reference,unavailable=facts,allocations=[assumption],cutoff=NOW)
    assert result['players'][2]['counts']['targets'] is None
    assert result['teams']['BUF']['reconciliation']['targets']['unallocated']==8


def test_newest_unscoped_native_out_retains_matching_scoped_official_vacancy_proof():
    from backend.app.product_services.opportunity_role_allocation import unavailable_from_canonical_rows
    _,_,_,facts,_=inputs()
    original=facts[0]['evidence']
    official={**original,'kind':'game_status','status':'OUT','report_phase':'final','scope_verified':True}
    native={**official,'season':None,'week':None,'source_uri':'native://salary','source_ids':['new-native']}
    row=dict(player_id=IDS[1],team='BUF',designation_resolution=dict(contract='factual_game_designation_v1',
        status='resolved',effective_designation='OUT',chosen_fact=native,source_facts=[native,official]))
    found,unknown=unavailable_from_canonical_rows([row],before_period=202604,cutoff=NOW)
    assert len(found)==1 and unknown==[]
    assert found[0]['evidence']['source_ids']==['official']
    assert found[0]['chosen_eligibility_fact']['source_ids']==['new-native']
    row['designation_resolution']['source_facts']=[native]
    found,unknown=unavailable_from_canonical_rows([row],before_period=202604,cutoff=NOW)
    assert not found and len(unknown)==1


def test_component_dependency_through_allocator_is_stable_on_equivalent_recapture():
    history,reference,bases,facts,assumption=inputs()
    first=allocate_factual_vacancies(reference,unavailable=facts,allocations=[assumption],cutoff=NOW)
    response=component_response(history,reference,first,bases,before_period=202604,cutoff=NOW)
    facts[0]['evidence'].update(source_ids=['new-recapture'],observed_at='2026-09-24T12:00:00Z',received_at='2026-09-24T13:00:00Z')
    second=allocate_factual_vacancies(reference,unavailable=facts,allocations=[assumption],cutoff=NOW)
    changed=component_response(history,reference,second,bases,before_period=202604,cutoff=NOW)
    assert response['semantic_sha256']==changed['semantic_sha256']
    assert response['new_count_sha256']!=changed['new_count_sha256']
    assumption['fraction']=.25
    third=allocate_factual_vacancies(reference,unavailable=facts,allocations=[assumption],cutoff=NOW)
    revised=component_response(history,reference,third,bases,before_period=202604,cutoff=NOW)
    assert revised['semantic_sha256']!=response['semantic_sha256']


def test_resolved_native_ir_and_scoped_official_out_keep_distinct_compatible_proofs():
    from backend.app.product_services.opportunity_role_allocation import unavailable_from_canonical_rows
    _,_,_,facts,_=inputs();original=facts[0]['evidence']
    official={**original,'kind':'game_status','status':'OUT','report_phase':'final','scope_verified':True}
    native={**official,'status':'IR','season':None,'week':None,'source_uri':'native://salary','source_ids':['current-native-IR']}
    row=dict(player_id=IDS[1],team='BUF',designation_resolution=dict(contract='factual_game_designation_v1',
        status='resolved',effective_designation='IR',chosen_fact=native,source_facts=[native,official]))
    found,unknown=unavailable_from_canonical_rows([row],before_period=202604,cutoff=NOW)
    assert len(found)==1 and not unknown
    assert found[0]['designation']=='OUT' and found[0]['evidence']['status']=='OUT'
    assert found[0]['effective_designation_at_cutoff']=='IR'
    assert found[0]['chosen_eligibility_fact']['status']=='IR'
    row['designation_resolution']['source_facts']=[native,{**official,'status':'QUESTIONABLE'}]
    assert unavailable_from_canonical_rows([row],before_period=202604,cutoff=NOW)[0]==[]


def test_practice_recipient_cannot_receive_another_players_injury_vacancy():
    _,reference,_,facts,assumption=inputs()
    practice=deepcopy(facts[0]);practice.update(player_master_id=IDS[2],designation='DEV')
    practice['evidence'].update(player_id=IDS[2],designation='DEV',fact_type='roster_status',decision_period=202604,
        scope_basis='validated_current_canonical_roster_participation_prohibition')
    with pytest.raises(ValueError,match='Invalid conditional vacancy'):
        allocate_factual_vacancies(reference,unavailable=[*facts,practice],allocations=[assumption],cutoff=NOW)
