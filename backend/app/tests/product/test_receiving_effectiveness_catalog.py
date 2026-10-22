from copy import deepcopy
import pytest
from backend.app.product_services.receiving_effectiveness_catalog import build_receiving_effectiveness_catalog,DEFINITIONS
P='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
def source():
 metrics={mid:dict(observed_outcome_sum=1.,eligible_events=2,known_outcome_events=2,unknown_outcome_events=0,unknown_eligibility_events=0,exact_within_log_mean=.5,known_attributed_sample_mean=.5) for mid in DEFINITIONS}
 return dict(version='player_effectiveness_components_v1',before_period=202607,evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,definitions={k:dict(variant=v[0],unit=v[1]) for k,v in DEFINITIONS.items()},actor_game_rows=[dict(game_id='2026_01_WAS_SF',team='WAS',source_player_id='00-0031234',player_master_id=P,metrics=metrics,unknown_native_attribution_exposures={'receiver':0},inherited_team_unknown_eligibility={'targets':0})],team_denominators=[dict(team='WAS',full_team_targets=20)],unattributed_events=[],identity_review_requests=[],semantic_measurements_sha256='measured-source',provenance={'source':{'snapshot_id':'original'}})
def build(s=None):return build_receiving_effectiveness_catalog(s or source(),before_period=202607)
def test_four_exact_measured_denominators_and_full_team_preserved():
 r=build();assert set(r['actor_game_rows'][0]['metrics'])==set(DEFINITIONS) and r['team_denominators'][0]['full_team_targets']==20
 assert all(m['value']==.5 for m in r['actor_game_rows'][0]['metrics'].values())
@pytest.mark.parametrize('field',['unknown_native_attribution_exposures','inherited_team_unknown_eligibility'])
def test_identity_or_eligibility_uncertainty_masks_exact_and_keeps_sample(field):
 s=source();s['actor_game_rows'][0][field]['receiver' if field.startswith('unknown') else 'targets']=1
 for m in s['actor_game_rows'][0]['metrics'].values():m['exact_within_log_mean']=None
 r=build(s);assert all(m['value'] is None and m['known_attributed_sample_mean']==.5 for m in r['actor_game_rows'][0]['metrics'].values())
def test_inconsistent_exactness_rejected_not_silently_trusted():
 s=source();s['actor_game_rows'][0]['unknown_native_attribution_exposures']['receiver']=1
 with pytest.raises(ValueError,match='exactness'):build(s)
def test_signed_source_epa_and_yac_not_clipped():
 s=source()
 for mid in ('G09-M06','G09-M08'):s['actor_game_rows'][0]['metrics'][mid].update(observed_outcome_sum=-2.,exact_within_log_mean=-1.)
 assert build(s)['actor_game_rows'][0]['metrics']['G09-M08']['value']==-1
@pytest.mark.parametrize('change',[dict(game_id='2026_07_WAS_SF'),dict(team='GB'),dict(player_master_id='invalid')])
def test_scope_or_identity_conflicts_rejected(change):
 s=source();s['actor_game_rows'][0].update(change)
 with pytest.raises(ValueError):build(s)
def test_zero_denominator_never_zero_rate():
 s=source()
 for m in s['actor_game_rows'][0]['metrics'].values():m.update(eligible_events=0,known_outcome_events=0,observed_outcome_sum=None,exact_within_log_mean=None)
 assert all(m['value'] is None for m in build(s)['actor_game_rows'][0]['metrics'].values())
def test_definition_or_current_serving_markers_rejected():
 s=source();s['pregame_serving_eligible']=True
 with pytest.raises(ValueError):build(s)
 s=source();s['definitions']['G09-M06']['variant']='route_proxy'
 with pytest.raises(ValueError,match='definition'):build(s)
