from copy import deepcopy
from datetime import datetime, timezone

from backend.app.product_services.workload_evidence import build_workload_evidence, select_measurement
from backend.app.product_services.scenario_allocation import measurement
from backend.app.product_services.analyst_scenarios import _measurement
from backend.app.product_services.optimizer_effectiveness import saved_workload_evidence, candidate_snapshot


def row(**extra):
    return dict(player_id='p',position='RB',carries_mean_3=10.76,projected_carries=10.76,
        pregame_base_carries_mean_3=17,carry_share_mean_3=.56,pregame_base_carry_share_mean_3=.88,
        carries_mean_3_available=True,carry_share_mean_3_available=True,
        workload_feature_cutoff_at='2026-10-09T12:00:00Z',**extra)


def test_original_measurement_and_allocated_proxy_are_separate_without_mutation():
    r=row();before=deepcopy(r);p=build_workload_evidence(r,cutoff='2026-10-10T12:00:00Z')
    assert r==before
    assert p['historical']['carries_mean_3']['value']==17
    assert p['historical']['carry_share_mean_3']['value']==.88
    assert p['derived_proxies']['allocated_carries']['value']==10.76
    assert p['derived_proxies']['projected_carries']['evidence_kind']=='allocated_proxy'
    value,basis=measurement(dict(workload_evidence=p),'carries')
    assert value==17 and 'observed_history:pregame_base_carries_mean_3' in basis
    assert _measurement(dict(workload_evidence=p),'carries',datetime(2026,10,10,12,tzinfo=timezone.utc))==(value,basis)


def test_missing_original_never_uses_allocated_zero_as_observed_history():
    r=row();r.update(pregame_base_carries_mean_3=None,carries_mean_3=0,projected_carries=0)
    p=build_workload_evidence(r)
    assert p['historical']['carries_mean_3']['value'] is None
    assert p['historical']['carries_mean_3']['status']=='original_history_unavailable'
    assert measurement(dict(workload_evidence=p),'carries')[0]==0
    assert 'allocated_proxy' in measurement(dict(workload_evidence=p),'carries')[1]
    assert select_measurement(dict(workload_evidence=p),'carries',allow_proxy=False)==(None,'unavailable')
    r['pregame_base_carries_mean_3']=0
    p=build_workload_evidence(r)
    assert p['historical']['carries_mean_3']['status']=='observed'
    assert 'observed_history' in measurement(dict(workload_evidence=p),'carries')[1]
    r['carries_mean_3_available']=False
    assert build_workload_evidence(r)['historical']['carries_mean_3']['value'] is None


def test_explicit_producer_input_precedes_history_only_with_original_attribution():
    r=row(pregame_expected_carries=20,workload_feature_evidence={
        'pregame_context_source':'official_context','pregame_context_observed_at':'2026-10-09T11:00:00Z'})
    p=build_workload_evidence(r,cutoff='2026-10-10T12:00:00Z')
    v,b=measurement(dict(workload_evidence=p),'carries')
    assert v==20 and 'explicit_pregame_input' in b
    r['workload_feature_evidence']['pregame_context_source']=None
    assert measurement(dict(workload_evidence=build_workload_evidence(r)),'carries')[0]==17
    r['workload_feature_evidence']['pregame_context_source']='official_context'
    r['workload_feature_evidence']['pregame_context_observed_at']='unverified clock'
    assert measurement(dict(workload_evidence=build_workload_evidence(r)),'carries')[0]==17
    r['workload_feature_evidence']['pregame_context_observed_at']='2026-10-11T11:00:00Z'
    p=build_workload_evidence(r,cutoff='2026-10-10T12:00:00Z')
    assert measurement(dict(workload_evidence=p),'carries')[0]==17


def test_projection_time_producer_value_and_clock_stay_together_after_refresh():
    r=row(pregame_expected_carries=25,pregame_context_source='availability_refresh',
        pregame_context_observed_at='2026-10-10T11:00:00Z',workload_feature_evidence={
            'pregame_expected_carries':18,'pregame_context_source':'original_producer',
            'pregame_context_observed_at':'2026-10-09T11:00:00Z'})
    p=build_workload_evidence(r,cutoff='2026-10-10T12:00:00Z')
    item=p['explicit_pregame']['pregame_expected_carries']
    assert item['value']==18 and item['producer_source']=='original_producer'
    assert item['producer_observed_at']=='2026-10-09T11:00:00Z'
    assert measurement(dict(workload_evidence=p),'carries')[0]==18


def test_legacy_saved_packets_are_read_as_written_not_backfilled_or_relabelled():
    packet=dict(contract_id='workload_evidence_v1',player_id='p',historical={
        'carries_mean_3':dict(status='observed',available=True,value=10.76)},derived_proxies={},explicit_pregame={})
    config={'strategy_runtime':{'player_pool':{'rows':[dict(player_id='p',workload_evidence=packet)]}}}
    before=deepcopy(config)
    assert measurement(dict(workload_evidence=packet),'carries')==(10.76,'historical.carries_mean_3')
    assert saved_workload_evidence(config)['p']==packet
    assert candidate_snapshot(config,'classic')['workload_evidence']['contract_id']=='workload_evidence_v1'
    assert config==before


def test_exclusion_does_not_change_measurement_or_remove_model_actor():
    a=row();b={**a,'included':False,'user_preference_exclusions':['user_exclusion']}
    assert build_workload_evidence(a)==build_workload_evidence(b)
    future=build_workload_evidence(row(workload_feature_evidence={'targets_mean_3':3}),cutoff='2026-10-08T12:00:00Z')
    assert measurement(dict(workload_evidence=future),'carries')==(None,'unavailable')


def test_proxy_sensitivity_never_certifies_v2_observed_role():
    from backend.app.product_services.scenario_allocation import role_measurement
    r=row();r.pop('pregame_base_carries_mean_3')
    p={'workload_evidence':build_workload_evidence(r)}
    assert measurement(p,'carries')[0]==10.76
    assert role_measurement(p,'carries')==(None,'unavailable')
    p['workload_evidence']['historical']['carries_mean_3'].update(
        status='observed',available=True,value=17,source_field='carries_mean_3')
    assert role_measurement(p,'carries')==(None,'unavailable')


def test_v2_unknown_role_cannot_enter_plan_through_legacy_proxy_fallback():
    from scripts.run_merged_analyst_fixture import scenario_fixture
    from backend.app.product_services.scenario_allocation import build_ideas, AllocationControls
    packet, snapshot = scenario_fixture('CLASSIC')
    scenario = deepcopy(packet['scenario_assumptions']['scenarios'][0])
    scenario['assumptions'] = scenario['assumptions'][:2]
    packet['scenario_assumptions']['scenarios'] = [scenario]
    for player in packet['players']:
        player['workload_evidence'] = build_workload_evidence(dict(
            player_id=player['player_master_id'], position=player['position'],
            projected_targets=8, projected_carries=20))
    controls = AllocationControls(minimum_credibility=.1)
    original = deepcopy(packet)
    ideas, rejected = build_ideas(packet, snapshot['players'], controls)
    assert not ideas and rejected
    assert all('cannot certify construction role' in item['rejection_reason'] for item in rejected)
    assert packet == original
    # Same missing role/proxy source under archived semantics remains readable
    # and follows its original proxy-backed role behavior.
    for player in packet['players']:
        player['workload_evidence']['contract_id'] = 'workload_evidence_v1'
    legacy, _ = build_ideas(packet, snapshot['players'], controls)
    assert legacy and all(item['score_components']['proxy_only'] is False for item in legacy)


def test_packet_validation_accepts_both_versions_and_rejects_false_v2_history():
    from scripts.run_merged_analyst_fixture import scenario_fixture
    from backend.app.product_services.analyst_packets import validate
    packet,_=scenario_fixture('CLASSIC')
    assert not validate(packet)
    p=packet['players'][0]
    r=row();r.update(player_id=p['player_master_id'],position=p['position'])
    p['workload_evidence']=build_workload_evidence(r)
    assert not validate(packet)
    p['workload_evidence']['historical']['carries_mean_3']['source_field']='carries_mean_3'
    assert 'observed workload source is not original history' in validate(packet)
