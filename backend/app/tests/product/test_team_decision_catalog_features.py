from copy import deepcopy
import pytest
from backend.app.product_services.team_decision_catalog_features import build_team_decision_catalog,SUBSETS

def metric(n=3,d=5,missing=0,uncertain=0):return dict(observed_outcome_sum=n,eligible_events=d,known_outcome_events=d-missing,unknown_outcome_events=missing,unknown_eligibility_events=uncertain)
def game(week=1,**changes):
 g=dict(team='LA',game_id=f'2026_{week:02d}_LA_SF',season=2026,week=week,metrics={m:metric() for m in SUBSETS});g.update(changes);return g
def context(rows=None):return dict(version='environment_context_evidence_v1',before_period=202607,forecast=None,game_rows=rows or [game()],semantic_measurements_sha256='frozen-source-semantic')
def build(rows=None,**kwargs):return build_team_decision_catalog(context(rows),before_period=202607,**kwargs)
def test_declared_decision_definition_all_nine_ids_and_native_team_alias():
 r=build();assert r['game_rows'][0]['team']=='LAR' and set(r['game_rows'][0]['metrics'])==set(SUBSETS)
 assert r['game_rows'][0]['metrics']['G02-M01']['value']==.6
 assert 'scramble is dropback once' in r['definition'] and 'G02-M03' not in r['game_rows'][0]['metrics']
def test_window_pools_counts_not_unweighted_game_rates():
 x=game();y=game(2);y['metrics']={m:metric(1,1) for m in SUBSETS}
 r=build([x,y]);assert r['team_windows'][0]['metrics']['G02-M01']['value']==4/6
@pytest.mark.parametrize('field',['unknown_eligibility_events','unknown_outcome_events'])
def test_unknown_masks_exact_rate_without_zero_imputation(field):
 x=game();x['metrics']['G02-M07'][field]=1
 if field=='unknown_outcome_events':x['metrics']['G02-M07']['known_outcome_events']-=1
 m=build([x])['game_rows'][0]['metrics']['G02-M07'];assert m['value'] is None and m['known_sample_fraction']>0
def test_zero_exposure_is_undefined():
 x=game();x['metrics']['G02-M08']=metric(0,0);assert build([x])['game_rows'][0]['metrics']['G02-M08']['value'] is None
@pytest.mark.parametrize('kwargs',[dict(week=7,game_id='2026_07_LA_SF'),dict(team='GB'),dict(game_id='2025_01_LA_SF')])
def test_future_or_conflicting_native_scope_rejected(kwargs):
 with pytest.raises(ValueError):build([game(**kwargs)])
def test_duplicate_rejected_and_order_invariant():
 with pytest.raises(ValueError,match='Duplicate'):build([game(),game()])
 assert build([game(2),game()])['semantic_sha256']==build([game(),game(2)])['semantic_sha256']
def test_subset_unknowns_retained_and_invalid_outcome_rejected():
 x=game();x['metrics']['G02-M02']=metric(6,5)
 with pytest.raises(ValueError,match='contradiction'):build([x])
 x=game();x['metrics']['G02-M02']=metric(3,6)
 with pytest.raises(ValueError,match='Subset'):build([x])
def test_last_observed_same_season_no_missing_game_zero():
 x=game();y=game(5);r=build([x,y],last_n=1);assert r['team_windows'][0]['observed_game_ids']==['2026_05_LA_SF']
 assert r['pregame_serving_eligible'] is False and r['forecast'] is None


def test_native_empty_known_sample_null_sum_is_not_unknown_outcome_zero():
 x=game();x['metrics']['G02-M08']=metric(0,0);x['metrics']['G02-M08']['observed_outcome_sum']=None
 m=build([x])['game_rows'][0]['metrics']['G02-M08'];assert m['value'] is None and m['known_sample_fraction'] is None and m['known_sample_sum_basis']=='empty_known_sample'
 x['metrics']['G02-M08']=metric(0,2,missing=2);x['metrics']['G02-M08']['observed_outcome_sum']=None
 m=build([x])['game_rows'][0]['metrics']['G02-M08'];assert m['value'] is None and m['unknown_outcome_events']==2
