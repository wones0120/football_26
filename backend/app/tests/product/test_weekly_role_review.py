from copy import deepcopy
import pytest

from backend.app.product_services.weekly_role_review import CONTRACT, fumble_counts, validate_weekly_review, scan_weekly_review, discovery_findings
from scripts.build_analyst_shadow_fixtures import fixture


def weekly_fixture():
    packet,snapshot=fixture('CLASSIC')
    for g in packet['games']:g.update(season=2099,week=2)
    pid=packet['players'][1]['player_master_id']
    o=dict(observation_id='prior:rb',player_master_id=pid,source_native_player_id='SYNTHETIC:'+pid,source_native_row_id='raw:1',source_id='synthetic',
        previous_game_id='SYNTH_PRIOR',season=2099,week=1,team='AAA',available_at='2099-09-01T10:00:00Z',completion_status='verified_complete',
        stats=dict(fumbles_total=2,fumbles_lost_total=1,carries=25),events=[dict(event_id='native:fum',kind='ball_security',player_master_id=pid,identity_evidence='native_id',sequence=10,source_id='synthetic',summary='SYNTHETIC fumble'),dict(event_id='native:return',kind='post_event_usage',player_master_id=pid,identity_evidence='native_id',sequence=20,source_id='synthetic',summary='SYNTHETIC returned')])
    f=dict(finding_id='rb_role',player_master_id=pid,game_id='SYNTH_A_B',formats=['CLASSIC'],observation_ids=['prior:rb'],status='watchlist',forecast_basis='coach_conditional',
        what_happened='Two fumbles, one lost',actual_reaction='SYNTHETIC returned; conditional warning',alternative_interpretations=['Ordinary role','Discipline if issue persists'],contrary_evidence=['Returned'],role_mechanism='Possible future carry redistribution',conditions=['Observed role decision'],model_accounting=dict(status='partial',delta_fields=['post_event_reaction']),next_checks=['Current practice/role'],roster_implication='Compare ordinary and reduced role only if measured',as_of=packet['decision_at'],expires_at=packet['games'][0]['kickoff_at'],
        factual_premises=[],branches=[dict(branch_id='continuity',conditions=['Ordinary role'],role_implication='No numerical change'),dict(branch_id='discipline',conditions=['Actual restriction'],role_implication='Investigate share donor/recipient')])
    packet['weekly_role_review']=dict(contract_id=CONTRACT,observations=[o],findings=[f])
    return packet,snapshot,o,f


def test_fumbles_distinct_from_lost_and_unknown_not_zero():
    assert fumble_counts(dict(fumbles_total=2,fumbles_lost_total=1))==dict(fumbles=2.,fumbles_lost=1.)
    assert fumble_counts({})==dict(fumbles=None,fumbles_lost=None)
    with pytest.raises(ValueError):fumble_counts(dict(fumbles_total=1,fumbles_lost_total=2))


def test_deterministic_all_game_scan_and_no_motivation_penalty():
    packet,snapshot,o,f=weekly_fixture();before=deepcopy(packet)
    report=scan_weekly_review(packet,snapshot['players'],fmt='CLASSIC')
    assert len(report['games'])==3 and report['candidates'][0]['signals'][0]['fumbles_lost']==1
    assert report['candidates'][0]['action_status']=='watchlist_no_numerical_adjustment'
    assert scan_weekly_review(packet,snapshot['players'],fmt='CLASSIC')==report and packet==before
    assert discovery_findings(packet)==[]
    f['motivation_bonus']=3
    assert any('unsupported causal' in e for e in validate_weekly_review(packet))


def test_canonical_sequence_clock_and_unverified_role_gates():
    packet,snapshot,o,f=weekly_fixture();assert validate_weekly_review(packet)==[]
    o['events'][1]['sequence']=1
    assert any('sequence' in e for e in validate_weekly_review(packet))
    o['events'][1]['sequence']=20;o['events'][0]['identity_evidence']='display_name'
    assert any('raw name' in e for e in validate_weekly_review(packet))
    o['available_at']='2100-01-01T12:00:00Z'
    assert any('future observation' in e for e in validate_weekly_review(packet))
    f['status']='supported_model_delta';f['discovery_action']=dict(idea_id='run',required_player_ids=[f['player_master_id']])
    assert any('distinct measured' in e for e in validate_weekly_review(packet))


def test_sourced_measured_delta_uses_existing_bounded_discovery():
    from backend.app.product_services.analyst_discovery import prepare_actions
    packet,snapshot,o,f=weekly_fixture()
    packet['sources'][0]['fact_assertions']={'role':'SYNTHETIC measured role changed'}
    packet['sources'][0]['completed_game_ids']=['SYNTH_PRIOR']
    o['completion_evidence_source_id']='synthetic'
    f.update(status='supported_model_delta',forecast_basis='measured_role',factual_premises=[dict(source_id='synthetic',fact_key='role',text='SYNTHETIC measured role changed')],discovery_action=dict(idea_id='run',required_player_ids=[f['player_master_id']]))
    assert validate_weekly_review(packet)==[]
    findings=discovery_findings(packet);assert len(findings)==1
    ideas=[dict(idea_id='run',team='AAA')]
    report=prepare_actions(packet,snapshot['players'],ideas,5,{})
    assert report['reserved_idea_ids']==['run'] and ideas[0]['discovery_required_player_ids']==[f['player_master_id']]
    assert len(report['findings'])==1
    f['model_accounting']['status']='already_accounted'
    assert any('distinct measured' in e for e in validate_weekly_review(packet))


def test_missing_weekly_packet_is_explicit_for_showdown():
    packet,snapshot=fixture('SHOWDOWN')
    report=scan_weekly_review(packet,snapshot['players'],fmt='SHOWDOWN')
    assert len(report['games'])==1 and report['games'][0]['missing_player_ids']
    assert report['automatic_bonus'] is False and report['candidates']==[]


def test_later_research_cannot_backfill_an_earlier_frozen_decision():
    packet,snapshot,_,_=weekly_fixture()
    with pytest.raises(ValueError,match='earlier decision'):
        scan_weekly_review(packet,snapshot['players'],fmt='CLASSIC',decision_at='2099-08-31T10:00:00Z')
