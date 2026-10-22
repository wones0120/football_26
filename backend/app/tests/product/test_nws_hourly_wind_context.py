from copy import deepcopy
import pytest
from backend.app.tests.product.test_nws_hourly_precipitation_context import fixture,run
from backend.app.product_services.nws_hourly_wind_context import parse_native_wind,build_nws_hourly_wind

def parent():
 args=fixture();args[0]['properties']['periods'][0]['windSpeed']='10 mph';return run(args)

def test_exact_source_speed_product_not_observed_height_or_averaging_claim():
 x=build_nws_hourly_wind(parent());assert x['wind']['native_scalar']==10 and x['wind']['scalar_meters_per_second']==pytest.approx(4.4704)
 assert x['averaging_duration']is None and x['forecast_height_meters']is None and x['forecast_interval_is_wind_averaging_duration']is False
 assert x['gust_field_present']is False and x['gust_value_not_substituted']is True
 assert x['model_consumed']is False and x['pregame_serving_eligible']is False

@pytest.mark.parametrize('value',['5 to 10 mph','5 to 5 mph'])
def test_textual_ranges_keep_bounds_without_midpoint_even_equal(value):
 x=parse_native_wind(value);assert x['native_lower']==5 and x['native_upper']in(5,10)
 assert x['native_scalar']is None and x['scalar_meters_per_second']is None and x['native_is_range']is True

@pytest.mark.parametrize('value',[None,10,True,'10','-2 mph','nan mph','10 to 5 mph','10 km','10 mph gusting 20 mph',dict(unitCode='wmoUnit:percent',value=10),dict(unitCode='wmoUnit:mi_h-1',value=None),dict(unitCode='wmoUnit:mi_h-1',value=True),dict(unitCode='wmoUnit:mi_h-1',value=float('inf')),dict(unitCode='wmoUnit:mi_h-1',value=10**1000)])
def test_invalid_missing_or_wrong_unit_wind_never_zero_or_gust_substitution(value):
 x=parse_native_wind(value);assert x['native_scalar']is None and x['unknown_reasons']

@pytest.mark.parametrize('unit,value,expected',[('wmoUnit:mi_h-1',10,4.4704),('wmoUnit:km_h-1',36,10),('wmoUnit:m_s-1',10,10),('wmoUnit:kn',10,1852/360)])
def test_explicit_quantitative_units(unit,value,expected):
 x=parse_native_wind(dict(unitCode=unit,value=value));assert x['native_unit']==unit and x['native_scalar']==value and x['scalar_meters_per_second']==pytest.approx(expected)

def test_known_zero_is_valid_and_missing_speed_not_filled_from_gust():
 assert parse_native_wind('0 mph')['native_scalar']==0
 p=parent();del p['native_period']['windSpeed'];p['native_period']['windGust']='20 mph';x=build_nws_hourly_wind(p)
 assert x['wind']['native_scalar']is None and x['gust_field_present']is True

@pytest.mark.parametrize('reason',['original_source_capture_or_game_chronology_unknown','unknown_or_stale_hourly_forecast_publication','native_venue_not_proven_inside_source_grid_polygon','missing_or_ambiguous_kickoff_interval','unlocated_or_invalid_forecast_interval'])
def test_bound_parent_weather_binding_failures_mask_speed(reason):
 p=parent();p['unknown_reasons']=[reason];x=build_nws_hourly_wind(p)
 assert x['wind']['native_scalar']is None and x['wind']['raw_native_wind']=='10 mph'

def test_missing_precip_probability_does_not_erase_independent_wind_field():
 p=parent();p['unknown_reasons']=['missing_or_invalid_explicit_percent_probability'];p['probability_percent']=None;p['probability_fraction']=None
 assert build_nws_hourly_wind(p)['wind']['native_scalar']==10

@pytest.mark.parametrize('change',[None,'bytes','semantic','producer','future'])
def test_managed_parent_reader_authentication(tmp_path,monkeypatch,change):
 import json,hashlib
 from pathlib import Path
 from backend.app.product_services import nws_hourly_precipitation_context
 from backend.app.product_services.nws_hourly_wind_context import load_reviewed_nws_hourly_parent
 monkeypatch.chdir(tmp_path);x=parent();x['provenance']=dict(producer_code_sha256=hashlib.sha256(Path(nws_hourly_precipitation_context.__file__).read_bytes()).hexdigest(),actual_publication_at='2026-10-20T14:00:00Z')
 if change=='semantic':x['native_period']['windSpeed']='20 mph'
 if change=='producer':x['provenance']['producer_code_sha256']='b'*64
 if change=='future':x['provenance']['actual_publication_at']='2026-10-21T00:00:00Z'
 b=json.dumps(x).encode();sha=hashlib.sha256(b).hexdigest();p=Path('artifacts/nws_hourly_precipitation_context')/(sha+'.json');p.parent.mkdir(parents=True);p.write_bytes(b);ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(b))
 if change=='bytes':p.write_bytes(b+b' ')
 if change:
  with pytest.raises(ValueError):load_reviewed_nws_hourly_parent(ref,cutoff='2026-10-20T15:00:00Z')
 else:assert load_reviewed_nws_hourly_parent(ref,cutoff='2026-10-20T15:00:00Z')['semantic_sha256']==x['semantic_sha256']
