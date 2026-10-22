from copy import deepcopy
import pytest
from backend.app.product_services.offensive_redzone_stalls import build_offensive_redzone_stalls
from backend.app.tests.product.test_redzone_drive_catalog import source

def build(s=None):return build_offensive_redzone_stalls(s or source(),before_period=202606)

def test_native_offense_not_defense_and_nonTD_terminal_fraction():
    r=build();g=r['game_rows'][0];m=g['metrics']['G23-M06']
    assert g['team']=='WAS' and g['opponent']=='SF' and m['value']==.5
    assert m['known_stall_drives']==1 and m['known_touchdown_drives']==1
    assert r['pregame_serving_eligible'] is False and r['forecast'] is None

def test_rushing_and_passingTD_each_success_once_no_shared_scoring_doublevote():
    s=source();s['game_rows'][0]['drive_quality']['drive_outcomes'][1]['completion_basis']='observed_rushing_touchdown'
    m=build(s)['game_rows'][0]['metrics']['G23-M06']
    assert m['value']==0 and m['known_touchdown_drives']==2 and m['observed_entered_drives']==2

def test_unknown_terminal_not_failure_or_zeroTD():
    s=source();g=s['game_rows'][0];g['metrics']['G14-M10'].update(known_outcome_events=1,unknown_outcome_events=1,observed_known_mean=1.,all_eligible_mean=None)
    g['drive_quality']['drive_outcomes'][1].update(outcome_known=False,completion_basis='unknown_no_terminal_evidence',terminal_play_ids=[])
    m=build(s)['game_rows'][0]['metrics']['G23-M06']
    assert m['value'] is None and m['known_terminal_sample_fraction']==0 and m['unknown_terminal_outcomes']==1

def test_missing_drive_and_uncertain_entry_mask_exact():
    s=source();s['game_rows'][0]['drive_quality']['redzone_events_missing_drive_id']=1
    assert build(s)['game_rows'][0]['metrics']['G23-M06']['value'] is None
    s=source();s['game_rows'][0]['metrics']['G14-M10'].update(unknown_eligibility_events=1,all_eligible_mean=None)
    assert build(s)['game_rows'][0]['metrics']['G23-M06']['value'] is None

def test_no_observed_entries_ratio_undefined_not_clean_game():
    s=source();g=s['game_rows'][0];g['metrics']['G14-M10'].update(eligible_events=0,known_outcome_events=0,observed_outcome_sum=None,observed_known_mean=None,all_eligible_mean=None)
    g['drive_quality'].update(observed_redzone_drive_ids=[],drive_outcomes=[])
    m=build(s)['game_rows'][0]['metrics']['G23-M06'];assert m['value'] is None and m['known_stall_drives']==0

def test_pooled_window_and_provider_row_order_invariant():
    s=source();g=deepcopy(s['game_rows'][0]);g['game_id']='2026_02_WAS_SF';g['drive_quality']['drive_outcomes'][1]['completion_basis']='observed_rushing_touchdown';s['game_rows'].append(g)
    a=build(s);assert a['team_windows'][0]['metrics']['G23-M06']['value']==.25
    s['game_rows'].reverse();assert build(s)['semantic_sha256']==a['semantic_sha256']

@pytest.mark.parametrize('change',['future','old_chronology','unsupported_terminal','before_entry'])
def test_scope_and_terminal_proof_rejection(change):
    s=source()
    if change=='future':s['game_rows'][0]['game_id']='2026_06_WAS_SF'
    elif change=='old_chronology':s['version']='defense_context_extensions_v1'
    elif change=='unsupported_terminal':s['game_rows'][0]['drive_quality']['drive_outcomes'][1]['completion_basis']='end_of_log'
    else:s['game_rows'][0]['drive_quality']['drive_outcomes'][0]['terminal_native_orders'][0]['order']=0
    with pytest.raises(ValueError):build(s)
