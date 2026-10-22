from copy import deepcopy
import pytest
from backend.app.product_services.defensive_catalog_features import build_defensive_catalog,DEFINITIONS,BASE_IDS,EXT_IDS

def pair():
 def src(version,ids):
  return dict(version=version,before_period=202606,definitions={k:deepcopy(DEFINITIONS[k]) for k in ids},game_rows=[dict(game_id='2026_01_WAS_SF',defense_team='SF',offense_team='WAS',metrics={k:dict(eligible_events=2,known_outcome_events=2,unknown_outcome_events=0,unknown_eligibility_events=0,observed_outcome_sum=1.,observed_known_mean=.5,all_eligible_mean=.5) for k in ids})],provenance=dict(source=dict(snapshot_id='native-source',content_sha256='sourcehash'),event_receipt_sha256='same-event'),semantic_measurements_sha256=version)
 return src('defense_context_evidence_v1',BASE_IDS),src('defense_context_extensions_v1',EXT_IDS)
def build(a=None,b=None):
 x,y=pair();return build_defensive_catalog(a or x,b or y,before_period=202606,yac_lateral_evidence=[dict(game_id='2026_01_WAS_SF',defense_team='SF',eligible_completed_passes=(b or y)['game_rows'][0]['metrics']['G14-M08']['eligible_events'] if (b or y)['game_rows'] else 0,proven_no_lateral=(b or y)['game_rows'][0]['metrics']['G14-M08']['eligible_events'] if (b or y)['game_rows'] else 0,known_lateral=0,unknown_lateral=0)])
def test_all_nine_precise_definitions_and_source_scope():
 r=build();assert set(r['game_rows'][0]['metrics'])==set(DEFINITIONS) and len(r['team_windows'])==1
 assert r['pregame_serving_eligible'] is False and r['forecast'] is None
@pytest.mark.parametrize('which',[0,1])
def test_native_defense_scope_mismatch_rejected(which):
 s=list(pair());s[which]['game_rows'][0]['defense_team']='GB'
 with pytest.raises(ValueError):build(*s)
def test_missing_component_game_not_zero():
 a,b=pair();b['game_rows']=[]
 with pytest.raises(ValueError,match='coverage'):build(a,b)
def test_unknown_denominators_mask_exact_keep_known_mean():
 a,b=pair();m=a['game_rows'][0]['metrics']['G15-M01'];m.update(unknown_eligibility_events=1,all_eligible_mean=None)
 r=build(a,b)['game_rows'][0]['metrics']['G15-M01'];assert r['value'] is None and r['known_sample_fraction_or_mean']==.5
def test_zero_exposure_undefined_not_zero_rate():
 a,b=pair();m=b['game_rows'][0]['metrics']['G14-M08'];m.update(eligible_events=0,known_outcome_events=0,observed_outcome_sum=None,observed_known_mean=None,all_eligible_mean=None)
 assert build(a,b)['game_rows'][0]['metrics']['G14-M08']['value'] is None
def test_signed_epa_and_cpoe_not_clipped():
 a,b=pair()
 for m in (a['game_rows'][0]['metrics']['G15-M02'],b['game_rows'][0]['metrics']['G14-M06']):m.update(observed_outcome_sum=-2.,observed_known_mean=-1.,all_eligible_mean=-1.)
 assert build(a,b)['game_rows'][0]['metrics']['G15-M02']['value']==-1
@pytest.mark.parametrize('kind',['future','source','definition','binary'])
def test_contract_contradictions_rejected(kind):
 a,b=pair()
 if kind=='future':a['game_rows'][0]['game_id']='2026_06_WAS_SF'
 elif kind=='source':b['provenance']['source']['snapshot_id']='different'
 elif kind=='definition':b['definitions']['G14-M06']['variant']='fake'
 else:a['game_rows'][0]['metrics']['G15-M01']['observed_outcome_sum']=3
 with pytest.raises(ValueError):build(a,b)
def test_window_pools_exposure_not_means():
 a,b=pair()
 for src in (a,b):
  r=deepcopy(src['game_rows'][0]);r['game_id']='2026_02_WAS_SF'
  for m in r['metrics'].values():m.update(eligible_events=1,known_outcome_events=1,observed_outcome_sum=1.,observed_known_mean=1.,all_eligible_mean=1.)
  src['game_rows'].append(r)
 assert build(a,b)['team_windows'][0]['metrics']['G15-M01']['value']==2/3


def test_catalog_total_distinct_from_rate_and_unknown_mask():
 a,b=pair();r=build(a,b)['game_rows'][0]['metrics']
 for mid in ('G14-M08','G15-M02'):assert r[mid]['catalog_value']==r[mid]['exact_within_log_total']==1 and r[mid]['rate_value']==.5
 for src,mid in ((a,'G15-M02'),(b,'G14-M08')):src['game_rows'][0]['metrics'][mid].update(unknown_eligibility_events=1,all_eligible_mean=None)
 r=build(a,b)['game_rows'][0]['metrics'];assert all(r[mid]['exact_within_log_total'] is None for mid in ('G14-M08','G15-M02'))

def test_empty_official_sample_total_zero_rate_undefined():
 a,b=pair()
 for src,mid in ((a,'G15-M02'),(b,'G14-M08')):src['game_rows'][0]['metrics'][mid].update(eligible_events=0,known_outcome_events=0,observed_outcome_sum=None,observed_known_mean=None,all_eligible_mean=None)
 r=build(a,b)['game_rows'][0]['metrics'];assert all(r[mid]['exact_within_log_total']==0 and r[mid]['rate_value'] is None for mid in ('G14-M08','G15-M02'))


def test_lateral_unknown_or_positive_masks_defense_total_but_preserves_initial_catcher():
 for field in ('known_lateral','unknown_lateral'):
  a,b=pair();p=dict(game_id='2026_01_WAS_SF',defense_team='SF',eligible_completed_passes=2,proven_no_lateral=1,known_lateral=0,unknown_lateral=0);p[field]=1
  m=build_defensive_catalog(a,b,before_period=202606,yac_lateral_evidence=[p])['game_rows'][0]['metrics']['G14-M08']
  assert m['catalog_value'] is None and m['initial_catcher_yac_sum']==1 and m['initial_catcher_yac_per_completion']==.5

def test_raw_native_lateral_proof_absent_flag_never_false():
 from backend.app.product_services.defensive_catalog_features import measure_yac_lateral_coverage
 raw=dict(season_type='REG',season=2026,week=1,game_id='2026_01_WAS_SF',defteam='SF',play_id=1,pass_attempt=1,complete_pass=1,qb_spike=0,two_point_attempt=0,play_type='pass')
 p=measure_yac_lateral_coverage([raw,dict(raw,play_id=2,lateral_reception=0),dict(raw,play_id=3,lateral_reception=1,lateral_receiving_yards=80)],before_period=202606)[0]
 assert p['proven_no_lateral']==p['known_lateral']==p['unknown_lateral']==1
 with pytest.raises(ValueError,match='Duplicate'):measure_yac_lateral_coverage([raw,dict(raw,play_id=1.0)],before_period=202606)
