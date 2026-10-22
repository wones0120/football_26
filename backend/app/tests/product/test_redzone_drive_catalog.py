from copy import deepcopy
import pytest
from backend.app.product_services.redzone_drive_catalog import build_redzone_drive_catalog
from backend.app.product_services.defense_context_extensions import DEFINITIONS

def source():return dict(version='native_order_redzone_drives_v1',chronology_basis='native_order_sequence',before_period=202606,evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,definitions=deepcopy(DEFINITIONS),semantic_measurements_sha256='entered-drives',provenance={},game_rows=[dict(game_id='2026_01_WAS_SF',defense_team='SF',offense_team='WAS',metrics={'G14-M10':dict(eligible_events=2,known_outcome_events=2,unknown_outcome_events=0,unknown_eligibility_events=0,observed_outcome_sum=1.,observed_known_mean=.5,all_eligible_mean=.5)},drive_quality=dict(observed_redzone_drive_ids=['1','2'],uncertain_redzone_drive_ids=[],conflicting_td_drive_ids=[],redzone_events_missing_drive_id=0,drive_outcomes=[dict(drive_id='1',outcome_known=True,native_order_verified=True,first_entry_order=1,terminal_native_orders=[dict(play_id=2,order=2)],completion_basis='observed_passing_touchdown',terminal_play_ids=[2]),dict(drive_id='2',outcome_known=True,native_order_verified=True,first_entry_order=3,terminal_native_orders=[dict(play_id=4,order=4)],completion_basis='provider_punt_terminal',terminal_play_ids=[4])]))])
def build(s=None):return build_redzone_drive_catalog(s or source(),before_period=202606)
def test_exact_entered_drive_conversion_and_terminal_proof():
 r=build()['game_rows'][0];assert r['metrics']['G14-M10']['value']==.5 and r['drive_quality']['drive_outcomes'][1]['completion_basis']=='provider_punt_terminal'
def test_partial_drive_not_noTD_zero():
 s=source();m=s['game_rows'][0]['metrics']['G14-M10'];m.update(known_outcome_events=1,unknown_outcome_events=1,observed_known_mean=1.,all_eligible_mean=None)
 o=s['game_rows'][0]['drive_quality']['drive_outcomes'][1];o.update(outcome_known=False,completion_basis='unknown_no_terminal_evidence',terminal_play_ids=[])
 m=build(s)['game_rows'][0]['metrics']['G14-M10'];assert m['value'] is None and m['known_sample_fraction_or_mean']==1.
def test_missing_native_drive_masks_exact_not_assigned_zero_trips():
 s=source();s['game_rows'][0]['drive_quality']['redzone_events_missing_drive_id']=1
 assert build(s)['game_rows'][0]['metrics']['G14-M10']['value'] is None
@pytest.mark.parametrize('kind',['duplicate','unsupported_terminal','numerator','future'])
def test_native_terminal_and_scope_contradictions_rejected(kind):
 s=source();g=s['game_rows'][0]
 if kind=='duplicate':g['drive_quality']['observed_redzone_drive_ids']=['1','1']
 elif kind=='unsupported_terminal':g['drive_quality']['drive_outcomes'][1]['completion_basis']='end_of_source'
 elif kind=='numerator':g['metrics']['G14-M10']['observed_outcome_sum']=2
 else:g['game_id']='2026_06_WAS_SF'
 with pytest.raises(ValueError):build(s)
def test_current_serving_marker_rejected():
 s=source();s['pregame_serving_eligible']=True
 with pytest.raises(ValueError):build(s)


def test_legacy_play_id_chronology_cannot_close_catalog():
 s=source();s['version']='defense_context_extensions_v1'
 with pytest.raises(ValueError,match='source'):build(s)
 s=source();s['game_rows'][0]['drive_quality']['drive_outcomes'][0]['native_order_verified']=False
 with pytest.raises(ValueError,match='chronology'):build(s)


def test_known_terminal_before_native_entry_rejected_even_with_true_marker():
 s=source();s['game_rows'][0]['drive_quality']['drive_outcomes'][0]['terminal_native_orders'][0]['order']=0
 with pytest.raises(ValueError,match='chronology'):build(s)
