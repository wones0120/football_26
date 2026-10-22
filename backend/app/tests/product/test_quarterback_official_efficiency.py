import pytest
from backend.app.tests.product.test_weekly_effectiveness_catalog_features import row,build
from backend.app.product_services.quarterback_official_efficiency import build_quarterback_official_efficiency

def test_official_signed_QB_ratio_and_original_sources_retained():
 s=build();r=build_quarterback_official_efficiency(s,before_period=202607)
 assert r['rows'][0]['metrics']['G05-M05']['value']==-2/3 and r['rows'][0]['source_ref']==s['rows'][0]['source_ref']
 assert 'kneel-downs and scrambles' in r['definition'] and r['pregame_serving_eligible'] is False

def test_nonQB_not_inferred_from_positive_passing_or_rushing():
 x=row(position='RB');x['raw_row_json']['position']='RB'
 assert build_quarterback_official_efficiency(build([x]),before_period=202607)['rows']==[]

def test_zero_and_unknown_not_zero_efficiency():
 for value in (0,None):
  x=row();x['raw_row_json']['carries']=value
  r=build_quarterback_official_efficiency(build([x]),before_period=202607)
  assert r['rows'][0]['metrics']['G05-M05']['value'] is None

def test_scope_and_current_use_mismatch_rejected():
 s=build();s['pregame_serving_eligible']=True
 with pytest.raises(ValueError):build_quarterback_official_efficiency(s,before_period=202607)
 s=build();s['rows'][0]['week']=7;s['rows'][0]['season']=2026
 with pytest.raises(ValueError):build_quarterback_official_efficiency(s,before_period=202607)

def test_forged_official_ratio_rejected():
 s=build();s['rows'][0]['metrics']['G07-M01']['value']=9
 with pytest.raises(ValueError,match='differs'):build_quarterback_official_efficiency(s,before_period=202607)
