from copy import deepcopy
from datetime import UTC,datetime,timedelta

import pytest

from backend.app.product_services.showdown_player_context import compose_player_contexts,assess_availability,attach_context_fields
from backend.app.product_services.factual_designation import DRESSING_REPORT,FINAL_REPORT
from backend.app.product_services.opportunity_role_allocation import unavailable_from_canonical_rows,allocate_factual_vacancies
from backend.app.tests.product.test_count_component_response import fixture,IDS

NOW=datetime(2026,10,19,21,tzinfo=UTC);PID=IDS[1]
SALARY=dict(player_id=PID,player_master_id=PID,player_name='SYNTHETIC reserve RB',team='BUF',position='RB',season=2026,week=6,kickoff_at='2026-10-20T00:15:00Z')


def fact(kind,status,minutes,**kwargs):
    at=(NOW-timedelta(minutes=minutes)).isoformat()
    return dict(player_id=PID,team='BUF',position='RB',kind=kind,status=status,source='SYNTHETIC-'+kind,
        source_ids=[kind+status],source_uri='https://www.nfl.com/injuries/league/2026/reg6',
        observed_at=at,received_at=at,**kwargs)


def context(extra=(),roster='RES',roster_minutes=120):
    facts=[fact('game_status','OUT',180,report_contract=FINAL_REPORT,report_phase='final',scope_verified=True,
        season=2026,week=6,kickoff_at='2026-10-20T00:15:00Z',published_at='2026-10-17T17:00:00Z'),fact('game_status','IR',60),fact('game_status','QUESTIONABLE',10),fact('roster_status',roster,roster_minutes),*extra]
    return compose_player_contexts([SALARY],facts,cutoff=NOW,max_age_hours=24)[0]


def test_fresh_reserve_proof_binds_unavailability_without_erasing_game_q_conflict():
    row=context();e=row['evidence_json']
    assert e['designation_resolution']['status']=='conflict'
    assert e['designation_resolution']['conflicts'][0]['status']=='QUESTIONABLE'
    assert e['availability_state']=='UNAVAILABLE'
    assert e['binding_roster_unavailability']['status']=='RES'
    assert 'game_designation_conflict_retained_under_roster_unavailability' in e['canonical_context_reason_codes']
    assert assess_availability({**e,'position':'RB'},cutoff=NOW,evaluated_at=NOW,max_age_hours=24)==('UNAVAILABLE',[])
    from pandas import DataFrame
    attached=attach_context_fields(DataFrame([dict(player_id=PID,position='RB')]),[row]).iloc[0].to_dict()
    attached.update(team='BUF')
    assert attached['binding_roster_unavailability']['status']=='RES'
    unavailable,unknown=unavailable_from_canonical_rows([attached],before_period=202606,cutoff=NOW)
    assert len(unavailable)==1 and not unknown
    assert unavailable[0]['evidence']['kind']=='roster_status'
    assert unavailable[0]['retained_designation_conflicts'][0]['status']=='QUESTIONABLE'
    _,reference,_=fixture();reference['before_period']=202606
    value=allocate_factual_vacancies(reference,unavailable=unavailable,cutoff=NOW)
    assert value['players'][1]['world_activity'] is False
    assert value['players'][1]['counts']==dict(pass_attempts=0.,rush_attempts=0.,targets=0.)


@pytest.mark.parametrize('case',['ACT','stale','roster_conflict'])
def test_active_stale_or_conflicting_roster_cannot_hide_game_conflict(case):
    row=context(roster='ACT') if case=='ACT' else context(roster_minutes=30*60) if case=='stale' else context(extra=[fact('roster_status','ACT',120)])
    e=row['evidence_json']
    assert e['availability_state']=='UNKNOWN'
    assert e['binding_roster_unavailability'] is None
    assert assess_availability({**e,'position':'RB'},cutoff=NOW,evaluated_at=NOW,max_age_hours=24)[0]=='UNKNOWN'


def test_later_valid_official_game_active_overrides_reserve_prohibition():
    dressing=fact('game_status','ACTIVE',1,game_active=True,report_contract=DRESSING_REPORT,scope_verified=True,
        season=2026,week=6,kickoff_at='2026-10-20T00:15:00Z')
    row=context(extra=[dressing]);e=row['evidence_json']
    assert e['binding_roster_unavailability'] is None
    assert e['availability_state']=='AVAILABLE'
    assert e['designation_resolution']['status']=='resolved'


def test_bound_roster_capture_wrappers_do_not_change_authored_research_semantics():
    from backend.app.product_services.analyst_research_requests import _canonical_context_facts
    evidence=context()['evidence_json'];first=_canonical_context_facts(evidence)
    evidence['binding_roster_unavailability'].update(source_ids=['recaptured-roster'],observed_at=NOW.isoformat(),received_at=NOW.isoformat())
    assert _canonical_context_facts(evidence)==first
    evidence['binding_roster_unavailability']['status']='ACT'
    assert _canonical_context_facts(evidence)!=first


def test_practice_squad_prohibition_is_not_replacement_vacancy_or_invented_normal_work():
    row=context(roster='DEV');e=row['evidence_json']
    assert e['availability_state']=='UNAVAILABLE'
    source={**e,'player_id':PID,'team':'BUF','position':'RB'}
    facts,unknown=unavailable_from_canonical_rows([source],before_period=202606,cutoff=NOW)
    assert facts[0]['designation']=='DEV' and not unknown
    _,reference,_=fixture();reference['before_period']=202606
    value=allocate_factual_vacancies(reference,unavailable=facts,cutoff=NOW)
    assert value['players'][1]['world_activity'] is False
    assert value['players'][1]['replacement_vacancy_eligible'] is False
    assert value['availability_conditions']['hypothetical_active_role_vacancies']=={}
