from copy import deepcopy

import pytest

from backend.app.product_services.count_scenario_response import count_world
from backend.app.product_services.count_component_response import component_response
from backend.app.tests.product.test_count_component_response import fixture, IDS, NOW


def test_common_world_uses_single_signed_component_ancestry_not_total_fp_elasticity():
    weekly,reference,bases=fixture();current=deepcopy(reference)
    current['reference_count_forecast']=reference
    current['component_response']=component_response(weekly,reference,current,bases,before_period=202604,cutoff=NOW)
    current['sha256']='SYNTHETIC-parent'
    world=dict(scenario_id='SYNTHETIC-lower-pass',assumptions=[dict(kind='passing_volume',team='BUF',factor=.5,elasticity=.7)])
    result=count_world(current,world,bases,cutoff=NOW)
    by_id={p['player_master_id']:p for p in result['response']['players']}
    # QB non-TD reference2.4; rushing .2 unchanged, passing2.2 halves.
    assert by_id[IDS[0]]['conditional_mean']==pytest.approx(8.9)
    assert by_id[IDS[2]]['conditional_mean']==pytest.approx(7.)
    assert result['changes'][0]['legacy_elasticity_consumption']=='not_consumed'
    world['assumptions'][0]['elasticity']=.1
    second=count_world(current,world,bases,cutoff=NOW)
    assert second['response']['players']==result['response']['players']


def test_counts_are_full_source_and_no_eligibility_preferences_enter_world():
    weekly,reference,bases=fixture();current=deepcopy(reference)
    current['reference_count_forecast']=reference
    current['component_response']=component_response(weekly,reference,current,bases,before_period=202604,cutoff=NOW)
    current['sha256']='SYNTHETIC-parent'
    scenario=dict(scenario_id='SYNTHETIC-concentration',assumptions=[dict(kind='target_concentration',team='BUF',player_master_ids=[IDS[2]],share_delta=.1,elasticity=.7)])
    result=count_world(current,scenario,bases,cutoff=NOW)
    assert len(result['response']['players'])==3
    assert result['response']['new_shared_budgets']['BUF']['reconciliation']['receiving_yards']['allocated']<=80
    assert current['players'][2]['counts']['targets']==5


def test_active_player_transfer_cannot_give_work_to_factually_inactive_recipient():
    weekly,reference,bases=fixture();current=deepcopy(reference)
    current['reference_count_forecast']=reference
    current['component_response']=component_response(weekly,reference,current,bases,before_period=202604,cutoff=NOW)
    current['sha256']='SYNTHETIC-parent'
    current['players'][2]['world_activity']=False
    current['players'][2]['counts']['targets']=0
    world=dict(scenario_id='SYNTHETIC-invalid-recipient',assumptions=[dict(kind='workload_transfer',team='BUF',workload='targets',
        from_player_master_id=IDS[1],to_player_master_id=IDS[2],fraction=.2,elasticity=.7)])
    with pytest.raises(ValueError,match='factually inactive'):count_world(current,world,bases,cutoff=NOW)
