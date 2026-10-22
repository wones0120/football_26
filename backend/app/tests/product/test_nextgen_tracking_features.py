from copy import deepcopy
import pytest
from backend.app.product_services.nextgen_source_components import normalize_nextgen_rows
from backend.app.product_services.nextgen_tracking_features import build_nextgen_features,require_feature_use
NOW='2026-10-20T03:00:00Z'
def block(kind='passing',**kw):
 r=dict(season=2025,week=3,season_type='REG',player_gsis_id='00-0031234',team_abbr='BUF',player_position='QB',attempts=20,completion_percentage_above_expectation=-4,rush_attempts=10,rush_yards_over_expected=-12,avg_time_to_throw=2.5);r.update(kw)
 b=normalize_nextgen_rows([r],stat_type=kind,cutoff=NOW)
 b['source']=dict(snapshot_id='source',content_sha256='a'*64,captured_at=NOW,observed_at=NOW)
 return b
def build(b=None):return build_nextgen_features(b or {'passing':block()},before_period=202606,actual_derived_at=NOW)
def test_vendor_CPOE_and_RYOE_signed_value_units_exposures():
 r=build({'passing':block(),'rushing':block('rushing')})['rows']
 assert r[0]['metrics']['G04-M02']['value']==-4 and r[0]['metrics']['G04-M02']['unit']=='percentage_points'
 assert r[1]['metrics']['G07-M10']['value']==-12 and r[1]['metrics']['G07-M10']['known_exposure']==10
 assert r[0]['supplemental']['avg_time_to_throw']['catalog_id'] is None
def test_season_summaries_POST_current_excluded_not_past_features():
 for kw,reason in [({'week':0},'season_aggregate'),({'season_type':'POST'},'POST'),({'season':2026,'week':6},'current_or_future_period')]:
  r=build({'passing':block(**kw)});assert not r['rows'] and r['excluded'][reason]==1
def test_missing_or_zero_exposure_does_not_verify_reported_difference():
 for v in (None,0):
  x=build({'passing':block(attempts=v)})['rows'][0]['metrics']['G04-M02']
  assert x['value'] is None and x['reported_value']==-4 and x['known_exposure']==v
def test_identity_unknown_never_name_role_or_team_denominator_inferred():
 x=build()['rows'][0];assert x['player_master_id'] is None and x['identity_status']=='native_unresolved_or_ambiguous'
 assert 'game_id' not in x and 'team_attempts' not in x
def test_source_future_wrong_version_and_duplicates_reject():
 b=block();b['source']['captured_at']='2026-10-21T00:00:00Z'
 with pytest.raises(ValueError,match='unavailable'):build({'passing':b})
 b=block();b['rows']*=2
 with pytest.raises(ValueError,match='Duplicate'):build({'passing':b})
 b=block();b['version']='other'
 with pytest.raises(ValueError,match='version'):build({'passing':b})
def test_recapture_stable_content_change_invalidates_and_serving_rejected():
 b=block();first=build({'passing':b});b['source']['snapshot_id']='recapture';b['source']['captured_at']='2026-10-20T02:59:00Z'
 assert build({'passing':b})['semantic_sha256']==first['semantic_sha256']
 b['rows'][0]['values']['completion_percentage_above_expectation']=-3
 assert build({'passing':b})['semantic_sha256']!=first['semantic_sha256']
 assert require_feature_use(first,purpose='offline_descriptive') is first
 with pytest.raises(ValueError,match='cannot'):require_feature_use(first,purpose='current_forecast')

def test_QB_catalog_measure_requires_source_native_QB_position():
 x=build({'passing':block(player_position=None)})['rows'][0]['metrics']['G04-M02']
 assert x['value'] is None and x['reported_value']==-4
